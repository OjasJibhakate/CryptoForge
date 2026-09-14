import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import config as cfg
from . import market, strategy, risk, store
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


def run_once(profile, force=False, dry_run=False):
    pcfg = cfg.cfg_for(profile)

    if pcfg.get("kind") == "copy_sim":
        from . import copytrader
        acc = copytrader.simulate()
        if acc is None:
            print(f"[{profile}] no trade log found ({copytrader.TRADE_FILE}); skipping")
            return None
        print(f"[{profile}] replayed {acc['source_trades']} copied trades | "
              f"equity ${acc['cash']:,.2f} ({(acc['cash']/acc['initial_capital']-1)*100:+.2f}%)")
        return acc

    acc = store.load_account(profile)
    today = _run_date()
    if not force and acc.get("last_run_date") == today:
        print(f"[{profile}] skip — already ran for {today}")
        return acc

    print(f"[{profile}] loading market data for {today} ...")
    close, volume = market.load_market()
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

    raw_targets = strategy.compute_targets(close, volume, funding_panel, profile)
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
    n_long = sum(1 for q in broker.positions().values() if q > 0)
    n_short = sum(1 for q in broker.positions().values() if q < 0)

    acc["cash"] = broker.cash
    acc["positions"] = {k: v for k, v in broker.positions().items() if abs(v) > 0}
    acc["avg_entry"] = {k: v for k, v in broker.avg.items() if abs(broker.positions().get(k, 0.0)) > 0}
    acc["high_water_mark"] = hwm
    acc["breaker_active"] = bool(rinfo["breached"])
    acc["last_run_utc"] = _utc_now().strftime("%Y-%m-%d %H:%M:%S")
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
        "drawdown": rinfo["drawdown"], "breaker": rinfo["breached"],
        "vol_scale": rinfo["vol_scale"], "gross_scale": rinfo["gross_scale"],
        "return_pct": (equity_after / acc["initial_capital"] - 1.0),
    })
    if rinfo["breached"]:
        store.log_event(profile, "CIRCUIT_BREAKER",
                        f"drawdown {rinfo['drawdown']*100:.1f}% -> gross x{rinfo['gross_scale']}")
    store.save_account(profile, acc)

    print(f"[{profile}] {len(fills)} fills | fees ${fees:.2f} | equity ${equity_after:,.2f} "
          f"({(equity_after/acc['initial_capital']-1)*100:+.2f}%) | long {n_long} short {n_short}")
    return acc


def status(profile):
    acc = store.load_account(profile)
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
    p.add_argument("--profile", choices=cfg.PROFILES, default="baseline")
    p.add_argument("--all", action="store_true", help="run every profile")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()
    profiles = list(cfg.PROFILES) if a.all else [a.profile]
    if a.status:
        for pr in profiles:
            status(pr)
            print("-" * 40)
    elif a.loop:
        loop(profiles[0])
    else:
        for pr in profiles:
            run_once(pr, force=a.force, dry_run=a.dry_run)
