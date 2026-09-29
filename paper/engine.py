import sys
import time
import argparse
import traceback
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import config as cfg
from . import candidates, market, strategy, risk, store
from .broker import PaperBroker


def _utc_now():
    return datetime.now(timezone.utc)


def _run_date():
    return _utc_now().strftime("%Y-%m-%d")


def _ms(dt):
    return int(dt.timestamp() * 1000)


def collect_funding_rates(symbols, since_dt):
    rates = {}
    for s in symbols:
        df = market.funding_since(s, _ms(since_dt))
        if df.empty:
            continue
        rates[s] = float(df["fundingRate"].sum())
        time.sleep(0.02)
    return rates


def _prev_marks(profile, acc):
    """Prices the carried positions were last marked at: account.json's last_marks,
    or (first run after diagnostics v2) the previous run's fill/target prices."""
    if acc.get("last_marks"):
        return acc["last_marks"]
    run_date = acc.get("last_run_date")
    marks = {}
    if not run_date:
        return marks
    f = cfg.files(profile)
    for key, col in (("trades", "run_date"), ("targets", "date")):
        try:
            df = pd.read_csv(f[key], encoding="utf-8")
        except Exception:
            continue
        df = df[df[col] == run_date]
        marks.update(dict(zip(df["symbol"], pd.to_numeric(df["price"], errors="coerce"))))
    return marks


def _exante_beta(close, positions, prices, equity, n=60):
    """Sum over positions of (notional / equity) x 60-day beta to BTC."""
    if equity <= 0 or "BTCUSDT" not in close.columns:
        return float("nan")
    r = close.pct_change().tail(n)
    btc = r["BTCUSDT"]
    total = 0.0
    for s, q in positions.items():
        px = prices.get(s)
        if not px or s not in r.columns:
            continue
        if s == "BTCUSDT":
            b = 1.0
        else:
            pair = pd.concat([r[s], btc], axis=1, keys=["a", "b"]).dropna()
            if len(pair) < 30 or not pair["b"].var():
                continue
            b = pair["a"].cov(pair["b"]) / pair["b"].var()
        total += q * px / equity * b
    return float(total)


def run_once(profile, force=False, dry_run=False):
    pcfg = candidates.cfg_for(profile)

    if pcfg.get("kind") == "copy_sim":
        from . import copytrader
        acc = copytrader.simulate()
        if acc is None:
            print(f"[{profile}] no trade log found ({copytrader.TRADE_FILE}); skipping")
            return None
        print(f"[{profile}] replayed {acc['source_trades']} copied trades | "
              f"equity ${acc['cash']:,.2f} ({(acc['cash']/acc['initial_capital']-1)*100:+.2f}%)")
        return acc

    acc = candidates.load_account(profile)
    if acc.get("retired"):
        print(f"[{profile}] retired {acc['retired'].get('date')} ({acc['retired'].get('reason')}); skipping")
        return acc
    today = _run_date()
    if not force and acc.get("last_run_date") == today:
        print(f"[{profile}] skip — already ran for {today}")
        return acc

    print(f"[{profile}] loading market data for {today} ...")
    close, volume = candidates.load_market(profile)
    if close.empty:
        print(f"[{profile}] no market data; aborting")
        return acc
    print(f"[{profile}] market panel: {close.shape[1]} symbols x {len(close)} days")

    funding_panel = None
    if pcfg["funding_tilt"] or pcfg["regime"]:
        mask = strategy.pit_mask(close, volume)
        last = mask.iloc[-1]
        univ = list(last[last].index) if len(last) else []
        print(f"[{profile}] fetching funding signal for {len(univ)} universe symbols ...")
        funding_panel = market.funding_daily_recent(univ, index=close.index)

    raw_targets = candidates.compute_targets(close, volume, funding_panel, profile)
    if raw_targets.empty:
        print(f"[{profile}] no targets produced; aborting")
        return acc

    held = set(acc.get("positions", {}).keys())
    needed = sorted(set(raw_targets.index) | held)
    prices = market.live_prices(needed)
    missing = [s for s in needed if s not in prices]
    if missing:
        print(f"[{profile}] warning: no price for {len(missing)} symbols")

    broker = PaperBroker(cash=acc["cash"], positions=acc.get("positions", {}),
                         avg_entry=acc.get("avg_entry", {}))

    last_run = acc.get("last_run_utc")
    since = (datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
             if last_run else _utc_now() - timedelta(days=1))
    rates = collect_funding_rates(list(broker.positions().keys()), since)
    funding_pnl = broker.apply_funding(rates, prices)
    print(f"[{profile}] funding applied: ${funding_pnl:+.4f}")

    equity = broker.equity(prices)
    hwm = max(acc.get("high_water_mark", equity), equity)
    rvol = strategy.realized_portfolio_vol(close, raw_targets)
    risked, rinfo = risk.apply_risk(raw_targets, equity, hwm, acc.get("breaker_active", False),
                                    rvol, pcfg["dd_breaker_trigger"],
                                    current_weights=broker.current_weights(prices),
                                    vol_target=pcfg.get("vol_target", "default"))
    print(f"[{profile}] equity ${equity:,.2f} | vol {rvol*100:.1f}% (scale {rinfo['vol_scale']:.2f}) | "
          f"dd {rinfo['drawdown']*100:.1f}% | breach {rinfo['breached']} | gross {rinfo['gross_after_risk']:.2f}")

    if dry_run:
        print(f"[{profile}] DRY RUN — {len(risked)} targets:")
        print(risked.sort_values().to_string())
        return acc

    fills, _ = broker.rebalance(risked, prices)
    equity_after = broker.equity(prices)
    fees = sum(f["fee"] + f["slippage"] for f in fills)
    fee_pnl = sum(f["fee"] for f in fills)
    slip_pnl = sum(f["slippage"] for f in fills)
    n_long = sum(1 for q in broker.positions().values() if q > 0)
    n_short = sum(1 for q in broker.positions().values() if q < 0)

    # Diagnostics only: leg P&L from fills, concentration from current notionals.
    # No strategy, sizing, or cost logic is touched by these numbers.
    prev_pos = dict(acc.get("positions", {}))
    prev_avg = dict(acc.get("avg_entry", {}))
    day_pnl = {}
    for s, q0 in prev_pos.items():
        px = prices.get(s)
        avg = prev_avg.get(s)
        if not px or not avg or q0 == 0:
            continue
        day_pnl[s] = q0 * (px - avg)
    long_pnl = sum(v for s, v in day_pnl.items() if prev_pos.get(s, 0) > 0)
    short_pnl = sum(v for s, v in day_pnl.items() if prev_pos.get(s, 0) < 0)
    notionals = {s: abs(q) * prices.get(s, 0.0)
                 for s, q in broker.positions().items() if prices.get(s)}
    tot_notion = sum(notionals.values())
    ranked = sorted(notionals.values(), reverse=True)
    cum = pd.Series(ranked).cumsum() / tot_notion if tot_notion > 0 else pd.Series([0])
    top1 = float(cum.iloc[0]) if len(cum) > 0 else 0.0
    top3 = float(cum.iloc[2]) if len(cum) > 2 else float(cum.iloc[-1]) if len(cum) else 0.0
    top5 = float(cum.iloc[4]) if len(cum) > 4 else float(cum.iloc[-1]) if len(cum) else 0.0
    turnover = sum(abs(f["notional"]) for f in fills) / equity_after if equity_after > 0 else 0.0
    margin_util = broker.gross_notional(prices) / equity_after if equity_after > 0 else 0.0
    missing = sorted(set(broker.positions()) - set(rates)) if rates else sorted(broker.positions())

    # Diagnostics v2 (2026-09-30, additive; legacy columns above are kept as they were).
    # long/short_pnl_day: carried positions marked from the previous run's prices (the
    # legacy long_pnl/short_pnl are unrealized-vs-average-entry totals, not flows).
    # missing_funding_held: positions carried INTO this run with no funding print (the
    # legacy column also lists positions opened this run, which cannot have one).
    marks0 = _prev_marks(profile, acc)
    long_day = short_day = 0.0
    for s, q0 in prev_pos.items():
        px, p0 = prices.get(s), marks0.get(s)
        if not px or not p0 or not np.isfinite(p0) or q0 == 0:
            continue
        if q0 > 0:
            long_day += q0 * (px - p0)
        else:
            short_day += q0 * (px - p0)
    carried_missing = sorted(s for s in prev_pos if prev_pos[s] and s not in rates)
    if carried_missing:
        store.log_event(profile, "MISSING_FUNDING",
                        f"{len(carried_missing)} carried positions had no funding observation "
                        f"this run (treated as 0.0): {','.join(carried_missing[:10])}")
    now = _utc_now()
    hours_since_prev = (now - since).total_seconds() / 3600.0 if last_run else float("nan")
    try:
        classes = candidates.contract_classes()
        tf_gross = sum(v for s, v in notionals.items()
                       if (classes.get(s) or [None])[0] == "TRADIFI_PERPETUAL")
        tradfi_share = tf_gross / tot_notion if tot_notion > 0 else 0.0
    except Exception:
        tradfi_share = float("nan")
    beta_btc = _exante_beta(close, broker.positions(), prices, equity_after)

    acc["cash"] = broker.cash
    acc["positions"] = {k: v for k, v in broker.positions().items() if abs(v) > 0}
    acc["avg_entry"] = {k: v for k, v in broker.avg.items() if abs(broker.positions().get(k, 0.0)) > 0}
    acc["last_marks"] = {k: float(prices[k]) for k in acc["positions"] if prices.get(k)}
    acc["high_water_mark"] = hwm
    acc["breaker_active"] = bool(rinfo["breached"])
    acc["last_run_utc"] = now.strftime("%Y-%m-%d %H:%M:%S")
    acc["last_run_date"] = today
    acc["runs"] = int(acc.get("runs", 0)) + 1

    store.log_trades(profile, fills, today)
    store.log_targets(profile, today, risked, prices)
    store.log_daily(profile, {
        "date": today, "equity": equity_after, "cash": broker.cash,
        "gross_notional": broker.gross_notional(prices),
        "net_notional": broker.net_notional(prices),
        "n_long": n_long, "n_short": n_short,
        "funding_pnl": funding_pnl, "fees": fees,
        "fee_pnl": fee_pnl, "slip_pnl": slip_pnl,
        "long_pnl": long_pnl, "short_pnl": short_pnl,
        "spread_pnl": long_pnl + short_pnl,
        "turnover": turnover, "margin_util": margin_util,
        "top1_share": top1, "top3_share": top3, "top5_share": top5,
        "missing_funding": ",".join(missing[:10]),
        "drawdown": rinfo["drawdown"], "breaker": rinfo["breached"],
        "vol_scale": rinfo["vol_scale"], "gross_scale": rinfo["gross_scale"],
        "return_pct": (equity_after / acc["initial_capital"] - 1.0),
        "long_pnl_day": long_day, "short_pnl_day": short_day,
        "missing_funding_held": ",".join(carried_missing[:10]),
        "run_utc": acc["last_run_utc"], "hours_since_prev": hours_since_prev,
        "tradfi_share": tradfi_share, "beta_btc": beta_btc,
    })
    if rinfo["breached"]:
        store.log_event(profile, "CIRCUIT_BREAKER",
                        f"drawdown {rinfo['drawdown']*100:.1f}% -> gross x{rinfo['gross_scale']}")
    store.save_account(profile, acc)

    print(f"[{profile}] {len(fills)} fills | fees ${fees:.2f} | equity ${equity_after:,.2f} "
          f"({(equity_after/acc['initial_capital']-1)*100:+.2f}%) | long {n_long} short {n_short}")
    return acc


def retire(profile, reason):
    """Kill-rule exit: settle funding, close the book at live prices (fees charged) and
    mark the account retired so scheduled runs skip it. Paper only; one-way by design."""
    if candidates.cfg_for(profile).get("kind") != "strategy":
        print(f"[{profile}] not a strategy profile; nothing to retire")
        return None
    acc = candidates.load_account(profile)
    if acc.get("retired"):
        print(f"[{profile}] already retired: {acc['retired']}")
        return acc
    if not acc.get("last_run_utc"):
        print(f"[{profile}] never ran; nothing to retire")
        return acc
    held = sorted(acc.get("positions", {}))
    prices = market.live_prices(held) if held else {}
    broker = PaperBroker(cash=acc["cash"], positions=acc.get("positions", {}),
                         avg_entry=acc.get("avg_entry", {}))
    since = datetime.strptime(acc["last_run_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    funding_pnl = broker.apply_funding(collect_funding_rates(held, since), prices)
    fills, _ = broker.rebalance(pd.Series(dtype=float), prices, reason="retire")
    equity = broker.equity(prices)
    now = _utc_now()
    today = now.strftime("%Y-%m-%d")
    hwm = max(acc.get("high_water_mark", equity), equity)
    acc["cash"] = broker.cash
    acc["positions"] = {k: v for k, v in broker.positions().items() if abs(v) > 0}
    acc["avg_entry"] = {k: v for k, v in broker.avg.items() if abs(broker.positions().get(k, 0.0)) > 0}
    acc["last_marks"] = {k: float(prices[k]) for k in acc["positions"] if prices.get(k)}
    acc["high_water_mark"] = hwm
    acc["last_run_utc"] = now.strftime("%Y-%m-%d %H:%M:%S")
    acc["last_run_date"] = today
    acc["runs"] = int(acc.get("runs", 0)) + 1
    acc["retired"] = {"date": today, "utc": acc["last_run_utc"], "reason": reason}
    store.log_trades(profile, fills, today)
    store.log_daily(profile, {
        "date": today, "equity": equity, "cash": broker.cash,
        "gross_notional": broker.gross_notional(prices), "net_notional": broker.net_notional(prices),
        "n_long": 0, "n_short": 0, "funding_pnl": funding_pnl,
        "fees": sum(f["fee"] + f["slippage"] for f in fills),
        "fee_pnl": sum(f["fee"] for f in fills), "slip_pnl": sum(f["slippage"] for f in fills),
        "drawdown": equity / hwm - 1.0 if hwm > 0 else 0.0, "breaker": acc.get("breaker_active", False),
        "vol_scale": 0.0, "gross_scale": 0.0, "return_pct": equity / acc["initial_capital"] - 1.0,
        "run_utc": acc["last_run_utc"],
    })
    store.log_event(profile, "RETIRED", f"{reason} | closed {len(fills)} positions, equity ${equity:,.2f}")
    store.save_account(profile, acc)
    print(f"[{profile}] RETIRED ({reason}): {len(fills)} closing fills, equity ${equity:,.2f}")
    return acc


def status(profile):
    acc = candidates.load_account(profile)
    print(f"profile       : {acc.get('profile', profile)}  ({acc.get('label', '')})")
    print(f"strategy      : {acc['strategy']}")
    print(f"started (UTC) : {acc['start_utc']}")
    print(f"runs          : {acc['runs']}")
    print(f"initial       : ${acc['initial_capital']:,.2f}")
    print(f"hwm           : ${acc['high_water_mark']:,.2f}")
    print(f"breaker       : {acc['breaker_active']}")
    print(f"open positions: {len(acc.get('positions', {}))}")
    if acc.get("last_run_utc"):
        print(f"last run      : {acc['last_run_utc']}")


def loop(profile):
    print(f"[{profile}] loop mode — running daily just after 00:05 UTC. Ctrl+C to stop.")
    while True:
        try:
            run_once(profile)
        except Exception as e:
            print(f"[{profile}] run error: {e}")
            store.log_event(profile, "ERROR", str(e))
        target = _utc_now().replace(hour=0, minute=5, second=0, microsecond=0)
        if _utc_now() >= target:
            target += timedelta(days=1)
        time.sleep(max(30.0, (target - _utc_now()).total_seconds()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="CryptoForge paper-trading daily engine")
    p.add_argument("--profile", choices=candidates.ALL_PROFILES, default="baseline")
    p.add_argument("--all", action="store_true", help="run every profile")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--retire", metavar="REASON",
                   help="close --profile's book for good (kill-rule exit, see FORWARD_PROTOCOL.md)")
    a = p.parse_args()
    profiles = list(candidates.ALL_PROFILES) if a.all else [a.profile]
    if a.retire:
        if a.all:
            p.error("--retire takes one --profile, not --all")
        retire(a.profile, a.retire)
    elif a.status:
        for pr in profiles:
            status(pr)
            print("-" * 40)
    elif a.loop:
        loop(profiles[0])
    else:
        # Each profile is isolated: one failing (e.g. C3's exchangeInfo call) must not
        # stop the others. A rate limit stops the batch to avoid hammering the API.
        failed = []
        for pr in profiles:
            try:
                run_once(pr, force=a.force, dry_run=a.dry_run)
            except market.RateLimited as e:
                failed.append(pr)
                print(f"[{pr}] RATE LIMITED: {e}; stopping this batch")
                break
            except Exception as e:
                failed.append(pr)
                traceback.print_exc()
                print(f"[{pr}] RUN FAILED: {type(e).__name__}: {e}")
                try:
                    store.log_event(pr, "ERROR", f"{type(e).__name__}: {e}")
                except Exception:
                    pass
        if failed:
            sys.exit(1)
