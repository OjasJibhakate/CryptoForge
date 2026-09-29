"""Hypothetical replay of missed paper-trading days. Never touches the live ledger.

When the machine is off, the live book simply holds its positions until the next
run: that is what the account really did, and the next live row marks it at real
prices. This tool answers a different question -- what would the frozen rules have
done on the missed days? -- and writes the answer to daily_backfill.csv,
trades_backfill.csv and targets_backfill.csv beside the live files. account.json,
daily.csv, trades.csv and targets.csv are never modified. (Until 2026-09-30 this
tool wrote into the live files, which broke ledger replay; see repair_ledger.py.)

Replay for each missed day mirrors engine.run_once, except fills execute at that
day's just-closed daily close instead of the live tick price:

  * signals from daily closes available at that date (no look-ahead),
  * fills at the last closed daily close,
  * funding from real historical funding payments inside each run window.

Each contiguous gap starts from the live book at the day before it (rebuilt by
paper/ledger.py and checked against the logged cash).

Usage:
    py -m paper.backfill                 # replay gaps up to yesterday (UTC)
    py -m paper.backfill --to 2026-09-20 # replay only up to a given date
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import candidates, ledger, market, risk, store, strategy
from . import config as cfg
from .broker import PaperBroker

FUND_WINDOW_START = pd.Timestamp("2026-08-01")

DAILY_COLS = ["date", "equity", "cash", "gross_notional", "net_notional",
              "n_long", "n_short", "funding_pnl", "fees", "drawdown", "breaker",
              "vol_scale", "gross_scale", "return_pct"]
TRADES_COLS = ["timestamp", "run_date", "symbol", "side", "qty", "price",
               "notional", "fee", "slippage", "reason"]
TARGETS_COLS = ["date", "symbol", "target_weight", "price"]


def utc_today():
    return datetime.now(timezone.utc).date()


def run_ts(d):
    return datetime(d.year, d.month, d.day, 0, 6, tzinfo=timezone.utc)


def read_csv(path, **kw):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path, encoding="utf-8", **kw)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def hypo_files(profile):
    d = cfg.profile_dir(profile)
    return {k: os.path.join(d, f"{k}_backfill.csv") for k in ("daily", "trades", "targets")}


def run_timestamp_from_trades(trades, run_date):
    """Actual engine run time for a date, from fill timestamps (fallback 00:06)."""
    if trades.empty:
        return run_ts(run_date)
    hits = trades[trades["run_date"].astype(str) == run_date.strftime("%Y-%m-%d")]
    if hits.empty:
        return run_ts(run_date)
    ts = pd.to_datetime(hits["timestamp"], errors="coerce").min()
    if pd.isna(ts):
        return run_ts(run_date)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def detect_gaps(profile, to_date):
    """Contiguous runs of dates with no live row and no hypothetical row yet."""
    daily = read_csv(cfg.files(profile)["daily"])
    if daily.empty:
        raise RuntimeError(f"[{profile}] no daily history, nothing to backfill from")
    have = set(pd.to_datetime(daily["date"]).dt.date)
    done = read_csv(hypo_files(profile)["daily"])
    done = set(pd.to_datetime(done["date"]).dt.date) if not done.empty else set()
    gaps, cur = [], []
    d = min(have) + timedelta(days=1)
    while d <= to_date:
        if d not in have and d not in done:
            cur.append(d)
        elif cur:
            gaps.append(cur)
            cur = []
        d += timedelta(days=1)
    if cur:
        gaps.append(cur)
    return gaps


def reconstruct(profile, cutoff):
    """The live book after the last live run on or before `cutoff`."""
    cstr = cutoff.strftime("%Y-%m-%d")
    _, st = ledger.replay(profile, upto=cstr)
    daily = read_csv(cfg.files(profile)["daily"])
    d = daily[daily["date"].astype(str) <= cstr]
    return {"cash": st.get("cash", cfg.INITIAL_CAPITAL), "positions": st.get("positions", {}),
            "avg_entry": st.get("avg_entry", {}), "hwm": st.get("hwm", cfg.INITIAL_CAPITAL),
            "breaker": bool(int(d["breaker"].iloc[-1])) if len(d) else False,
            "logged_cash": float(d["cash"].iloc[-1]) if len(d) else None,
            "last_live": d["date"].astype(str).iloc[-1] if len(d) else None,
            "trades": ledger.load(profile)[1]}


def fetch_klines(symbols):
    data = {}
    for i, s in enumerate(symbols):
        try:
            df = market.daily_klines(s)
        except market.RateLimited:
            raise
        if df is None or df.empty:
            continue
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        data[s] = df.set_index("timestamp").sort_index()
        if (i + 1) % 50 == 0:
            print(f"  klines {i + 1}/{len(symbols)} ...")
    return data


def build_panels(kdata, symbols):
    closes = {s: kdata[s]["close"] for s in symbols if s in kdata and "close" in kdata[s].columns}
    vols = {s: kdata[s]["volume"] for s in symbols if s in kdata and "volume" in kdata[s].columns}
    close = pd.DataFrame(closes).sort_index()
    return close, pd.DataFrame(vols).reindex(close.index)


_funding_cache = {}


def funding_df(symbol):
    if symbol in _funding_cache:
        return _funding_cache[symbol]
    start_ms = int(FUND_WINDOW_START.tz_localize("UTC").timestamp() * 1000)
    df = market.funding_since(symbol, start_ms)
    if df is None or df.empty:
        _funding_cache[symbol] = pd.DataFrame()
        return _funding_cache[symbol]
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    _funding_cache[symbol] = df.set_index("timestamp").sort_index()
    return _funding_cache[symbol]


def funding_accrual(symbols, prev_ts, run_ts_):
    rates = {}
    for s in symbols:
        df = funding_df(s)
        if df.empty:
            continue
        m = (df.index > prev_ts) & (df.index <= run_ts_)
        if m.any():
            rates[s] = float(df.loc[m, "fundingRate"].sum())
    return rates


def funding_signal_panel(symbols, hist_index):
    series = {}
    for s in symbols:
        df = funding_df(s)
        if df.empty:
            continue
        series[s] = df["fundingRate"].resample("1D").sum()
    if not series:
        return pd.DataFrame(index=hist_index)
    return pd.DataFrame(series).reindex(hist_index).fillna(0.0)


def replay_gap(profile, st, gap, close, volume):
    pcfg = candidates.cfg_for(profile)
    broker = PaperBroker(cash=st["cash"], positions=dict(st["positions"]),
                         avg_entry=dict(st["avg_entry"]))
    hwm, breaker = st["hwm"], st["breaker"]
    prev_run = run_timestamp_from_trades(st["trades"], pd.Timestamp(st["last_live"]).date())
    out = {"trades": [], "targets": [], "daily": []}
    for D in gap:
        hist_c = close[close.index < pd.Timestamp(D)]
        hist_v = volume.reindex(hist_c.index)
        if hist_c.empty or len(hist_c) < cfg.MIN_HISTORY_DAYS:
            print(f"[{profile}] {D}: insufficient history, skipping")
            continue
        fund_panel = None
        if pcfg["funding_tilt"] or pcfg["regime"]:
            last = strategy.pit_mask(hist_c, hist_v).iloc[-1]
            fund_panel = funding_signal_panel(list(last[last].index), hist_c.index)
        raw = candidates.compute_targets(hist_c, hist_v, fund_panel, profile)
        if raw.empty:
            print(f"[{profile}] {D}: no targets, skipping")
            continue
        prices = hist_c.iloc[-1].dropna().to_dict()
        run = run_ts(D).replace(tzinfo=None)
        rates = funding_accrual(list(broker.positions().keys()), prev_run.replace(tzinfo=None), run)
        funding_pnl = broker.apply_funding(rates, prices)
        equity = broker.equity(prices)
        hwm = max(hwm, equity)
        risked, rinfo = risk.apply_risk(
            raw, equity, hwm, breaker, strategy.realized_portfolio_vol(hist_c, raw),
            pcfg["dd_breaker_trigger"], current_weights=broker.current_weights(prices),
            vol_target=pcfg.get("vol_target", "default"))
        fills, _ = broker.rebalance(risked, prices, reason="backfill")
        equity_after = broker.equity(prices)
        breaker = bool(rinfo["breached"])
        ds = D.strftime("%Y-%m-%d")
        for fl in fills:
            out["trades"].append({"timestamp": run.strftime("%Y-%m-%d %H:%M:%S"), "run_date": ds,
                                  "symbol": fl["symbol"], "side": fl["side"],
                                  "qty": round(fl["qty"], 8), "price": round(fl["price"], 8),
                                  "notional": round(fl["notional"], 4), "fee": round(fl["fee"], 6),
                                  "slippage": round(fl["slippage"], 6), "reason": "backfill"})
        for sym, w in risked.items():
            out["targets"].append({"date": ds, "symbol": sym, "target_weight": round(float(w), 6),
                                   "price": round(float(prices.get(sym, 0.0)), 8)})
        out["daily"].append({"date": ds, "equity": round(equity_after, 4), "cash": round(broker.cash, 4),
                             "gross_notional": round(broker.gross_notional(prices), 4),
                             "net_notional": round(broker.net_notional(prices), 4),
                             "n_long": sum(1 for q in broker.positions().values() if q > 0),
                             "n_short": sum(1 for q in broker.positions().values() if q < 0),
                             "funding_pnl": round(funding_pnl, 6),
                             "fees": round(sum(f["fee"] + f["slippage"] for f in fills), 6),
                             "drawdown": round(rinfo["drawdown"], 6), "breaker": int(breaker),
                             "vol_scale": round(rinfo["vol_scale"], 4),
                             "gross_scale": round(rinfo["gross_scale"], 4),
                             "return_pct": round(equity_after / cfg.INITIAL_CAPITAL - 1.0, 6)})
        prev_run = run
        print(f"[{profile}] {ds}: {len(fills)} hypothetical fills, funding ${funding_pnl:+.2f} "
              f"-> equity ${equity_after:,.2f}")
    return out


def write_backfill(profile, result):
    hf = hypo_files(profile)
    for key, cols, sort in (("daily", DAILY_COLS, ["date"]), ("trades", TRADES_COLS, ["timestamp"]),
                            ("targets", TARGETS_COLS, ["date", "symbol"])):
        new = pd.DataFrame(result[key], columns=cols)
        if new.empty:
            continue
        old = read_csv(hf[key])
        out = pd.concat([old, new], ignore_index=True) if not old.empty else new
        out.sort_values(sort, kind="stable").to_csv(hf[key], index=False, encoding="utf-8")
    first, last = result["daily"][0]["date"], result["daily"][-1]["date"]
    store.log_event(profile, "BACKFILL", f"hypothetical replay {first}..{last} written to "
                                         f"*_backfill.csv; live ledger untouched")
    print(f"[{profile}] wrote {len(result['daily'])} hypothetical day(s) to {hf['daily']}")


def main():
    ap = argparse.ArgumentParser(description="Hypothetical replay of missed paper-trading days")
    ap.add_argument("--to", default=None, help="replay up to YYYY-MM-DD (default: yesterday UTC)")
    a = ap.parse_args()
    to_date = (datetime.strptime(a.to, "%Y-%m-%d").date() if a.to else utc_today() - timedelta(days=1))

    plans = {}
    for profile in candidates.strategy_profiles():
        if not os.path.exists(cfg.files(profile)["account"]):
            continue
        try:
            gaps = detect_gaps(profile, to_date)
        except RuntimeError as e:
            print(f"[{profile}] {e}; skipping")
            continue
        if not gaps:
            print(f"[{profile}] no gaps through {to_date}")
            continue
        ok_gaps = []
        for gap in gaps:
            st = reconstruct(profile, gap[0] - timedelta(days=1))
            ok = st["logged_cash"] is not None and abs(st["cash"] - st["logged_cash"]) < 1.0
            print(f"[{profile}] gap {gap[0]}..{gap[-1]}: live book at {st['last_live']} rebuilt, cash "
                  f"${st['cash']:,.2f} vs logged ${st['logged_cash'] or float('nan'):,.2f} -> "
                  f"{'OK' if ok else 'MISMATCH, skipping this gap'}")
            if ok:
                ok_gaps.append((gap, st))
        if ok_gaps:
            plans[profile] = ok_gaps
    if not plans:
        print("Nothing to backfill.")
        return

    print("Pulling market data (klines + funding) ...")
    held = {p: set().union(*(set(st["positions"]) for _, st in g)) for p, g in plans.items()}
    universe = {}
    if any(candidates.cfg_for(p).get("universe") != "crypto_only" for p in plans):
        universe["all"] = set(market.candidate_symbols())
    if any(candidates.cfg_for(p).get("universe") == "crypto_only" for p in plans):
        universe["crypto"] = set(candidates.crypto_candidates())
        classes = candidates.contract_classes()
    kdata = fetch_klines(sorted(set().union(*universe.values(), *held.values())))
    for profile, gaps in plans.items():
        if candidates.cfg_for(profile).get("universe") == "crypto_only":
            cols = [s for s in universe["crypto"] | held[profile] if candidates.is_crypto(s, classes)]
        else:
            cols = sorted(universe["all"] | held[profile])
        close, volume = build_panels(kdata, cols)
        for gap, st in gaps:
            result = replay_gap(profile, st, gap, close, volume)
            if result["daily"]:
                write_backfill(profile, result)


if __name__ == "__main__":
    main()
