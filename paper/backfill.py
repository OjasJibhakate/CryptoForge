"""Backfill missed daily paper-trading days using historical market data.

Fills per-day rows for dates missing from paper/state/<profile>/daily.csv.
Existing rows (live engine runs) are NEVER re-priced: their equity/cash/fills
stay exactly as recorded. Only one field is ever touched on a live row -- the
funding_pnl of the first live run after a gap -- and only to strip out payments
that the backfilled rows already credited (otherwise funding would be counted
twice). The stripped value and the reason are logged as a BACKFILL_ADJUST event.

Replay for each missing day mirrors engine.run_once, except fills execute at
that day's just-closed daily close instead of the live tick price:

  * signals from daily closes available at that date (no look-ahead),
  * fills at the last closed daily close,
  * funding from real historical funding payments inside each run window.

Usage:
    py -m paper.backfill                 # detect gaps vs today (UTC) and replay
    py -m paper.backfill --to 2026-09-20 # replay only up to a given date

Only strategy profiles (baseline, wave3) are replayed. copytrader is a static
log replay and needs no backfill. account.json is never modified except via the
live engine -- after backfill, the book matches the last live run.
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import config as cfg
from . import market, strategy, risk
from .broker import PaperBroker

STRATEGY_PROFILES = ("baseline", "wave3")
FUND_WINDOW_START = pd.Timestamp("2026-08-01")

DAILY_COLS = ["date", "equity", "cash", "gross_notional", "net_notional",
              "n_long", "n_short", "funding_pnl", "fees", "drawdown", "breaker",
              "vol_scale", "gross_scale", "return_pct"]
TRADES_COLS = ["timestamp", "run_date", "symbol", "side", "qty", "price",
               "notional", "fee", "slippage", "reason"]
TARGETS_COLS = ["date", "symbol", "target_weight", "price"]
EVENTS_COLS = ["timestamp", "kind", "message"]


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


def run_timestamp_from_trades(trades, run_date):
    """Actual engine run time for a date, from fill timestamps (fallback 00:06)."""
    if trades.empty:
        return run_ts(run_date)
    hits = trades[trades["run_date"] == run_date.strftime("%Y-%m-%d")]
    if hits.empty:
        return run_ts(run_date)
    ts = pd.to_datetime(hits["timestamp"], errors="coerce").min()
    if pd.isna(ts):
        return run_ts(run_date)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def detect_gap(profile, to_date):
    daily = read_csv(cfg.files(profile)["daily"])
    if daily.empty:
        raise RuntimeError(f"[{profile}] no daily history, nothing to backfill from")
    have = sorted(pd.to_datetime(daily["date"]).dt.date.unique())
    have_set = set(have)
    missing = []
    d = have[0] + timedelta(days=1)
    while d <= to_date:
        if d not in have_set:
            missing.append(d)
        d += timedelta(days=1)
    if not missing:
        return None, None, daily
    return have, missing, daily


def col_sum(df, col):
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def reconstruct(profile, cutoff):
    """Rebuild cash/positions/avg_entry/hwm/breaker from fills+funding through `cutoff`."""
    f = cfg.files(profile)
    cstr = cutoff.strftime("%Y-%m-%d")
    trades = read_csv(f["trades"])
    daily = read_csv(f["daily"])
    fills = trades[trades["run_date"] <= cstr].copy() if not trades.empty else trades
    dhist = daily[pd.to_datetime(daily["date"]).dt.date <= cutoff].copy() if not daily.empty else daily

    cur, avg = {}, {}
    for _, fl in fills.iterrows():
        s = fl["symbol"]
        px = float(fl["price"])
        dq = float(fl["qty"])
        old = cur.get(s, 0.0)
        new = old + dq
        if abs(new) * px < cfg.MIN_ORDER_USD:
            cur[s] = 0.0
            avg[s] = 0.0
        elif old == 0 or (old * new < 0):
            avg[s] = px
        elif abs(new) > abs(old):
            prev = avg.get(s, px)
            avg[s] = (abs(old) * prev + abs(dq) * px) / (abs(old) + abs(dq))
        cur[s] = new
    positions = {k: v for k, v in cur.items() if abs(v) > 0}
    avg_entry = {k: v for k, v in avg.items() if abs(cur.get(k, 0.0)) > 0}

    cash = (cfg.INITIAL_CAPITAL
            - float((pd.to_numeric(fills["qty"], errors="coerce").fillna(0.0)
                     * pd.to_numeric(fills["price"], errors="coerce").fillna(0.0)).sum())
            - col_sum(fills, "fee") - col_sum(fills, "slippage")
            + col_sum(dhist, "funding_pnl"))
    hwm = cfg.INITIAL_CAPITAL
    if not dhist.empty:
        hwm = max(hwm, float(pd.to_numeric(dhist["equity"], errors="coerce").max()))
    breaker = bool(int(dhist.iloc[-1]["breaker"])) if not dhist.empty else False
    logged_cash = (float(pd.to_numeric(
        dhist[dhist["date"] == cstr]["cash"], errors="coerce").iloc[-1])
        if not dhist.empty and (dhist["date"] == cstr).any() else None)
    return {"cash": cash, "positions": positions, "avg_entry": avg_entry,
            "hwm": hwm, "breaker": breaker, "logged_cash": logged_cash,
            "trades": trades}


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


def build_panels(kdata):
    closes = {s: df["close"] for s, df in kdata.items() if "close" in df.columns}
    vols = {s: df["volume"] for s, df in kdata.items() if "volume" in df.columns}
    close = pd.DataFrame(closes).sort_index()
    volume = pd.DataFrame(vols).reindex(close.index)
    return close, volume


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
        try:
            df = funding_df(s)
        except market.RateLimited:
            raise
        if df.empty:
            continue
        m = (df.index > prev_ts) & (df.index <= run_ts_)
        if m.any():
            rates[s] = float(df.loc[m, "fundingRate"].sum())
    return rates


def funding_signal_panel(symbols, hist_index):
    series = {}
    for s in symbols:
        try:
            df = funding_df(s)
        except market.RateLimited:
            raise
        if df.empty:
            continue
        d = df["fundingRate"].resample("1D").sum()
        series[s] = d
    if not series:
        return pd.DataFrame(index=hist_index)
    return pd.DataFrame(series).reindex(hist_index).fillna(0.0)


def replay_profile(profile, st, missing, close, volume):
    pcfg = cfg.cfg_for(profile)
    broker = PaperBroker(cash=st["cash"], positions=dict(st["positions"]),
                         avg_entry=dict(st["avg_entry"]))
    hwm, breaker = st["hwm"], st["breaker"]
    prev_run = run_timestamp_from_trades(st["trades"], missing[0] - timedelta(days=1))

    new_trades, new_targets, new_daily = [], [], []
    for D in missing:
        hist_c = close[close.index < pd.Timestamp(D)]
        hist_v = volume.reindex(hist_c.index)
        if hist_c.empty or len(hist_c) < cfg.MIN_HISTORY_DAYS:
            print(f"[{profile}] {D}: insufficient history, skipping")
            continue
        fund_panel = None
        if pcfg["funding_tilt"] or pcfg["regime"]:
            mask = strategy.pit_mask(hist_c, hist_v)
            last = mask.iloc[-1]
            univ = list(last[last].index)
            fund_panel = funding_signal_panel(univ, hist_c.index)
        raw = strategy.compute_targets(hist_c, hist_v, fund_panel, profile)
        if raw.empty:
            print(f"[{profile}] {D}: no targets, skipping")
            continue
        prices = hist_c.iloc[-1].dropna().to_dict()

        run = run_ts(D).replace(tzinfo=None)
        rates = funding_accrual(list(broker.positions().keys()), prev_run.replace(tzinfo=None), run)
        funding_pnl = broker.apply_funding(rates, prices)

        equity = broker.equity(prices)
        hwm = max(hwm, equity)
        rvol = strategy.realized_portfolio_vol(hist_c, raw)
        risked, rinfo = risk.apply_risk(
            raw, equity, hwm, breaker, rvol, pcfg["dd_breaker_trigger"],
            current_weights=broker.current_weights(prices),
            vol_target=pcfg.get("vol_target", "default"))
        fills, _ = broker.rebalance(risked, prices)
        equity_after = broker.equity(prices)
        fees = sum(fl["fee"] + fl["slippage"] for fl in fills)
        n_long = sum(1 for q in broker.positions().values() if q > 0)
        n_short = sum(1 for q in broker.positions().values() if q < 0)
        breaker = bool(rinfo["breached"])
        ds = D.strftime("%Y-%m-%d")
        for fl in fills:
            new_trades.append({"timestamp": run.strftime("%Y-%m-%d %H:%M:%S"),
                               "run_date": ds, "symbol": fl["symbol"], "side": fl["side"],
                               "qty": round(fl["qty"], 8), "price": round(fl["price"], 8),
                               "notional": round(fl["notional"], 4),
                               "fee": round(fl["fee"], 6), "slippage": round(fl["slippage"], 6),
                               "reason": "backfill"})
        for sym, w in risked.items():
            new_targets.append({"date": ds, "symbol": sym, "target_weight": round(float(w), 6),
                                "price": round(float(prices.get(sym, 0.0)), 8)})
        new_daily.append({"date": ds, "equity": round(equity_after, 4),
                          "cash": round(broker.cash, 4),
                          "gross_notional": round(broker.gross_notional(prices), 4),
                          "net_notional": round(broker.net_notional(prices), 4),
                          "n_long": n_long, "n_short": n_short,
                          "funding_pnl": round(funding_pnl, 6), "fees": round(fees, 6),
                          "drawdown": round(rinfo["drawdown"], 6), "breaker": int(breaker),
                          "vol_scale": round(rinfo["vol_scale"], 4),
                          "gross_scale": round(rinfo["gross_scale"], 4),
                          "return_pct": round(equity_after / cfg.INITIAL_CAPITAL - 1.0, 6)})
        prev_run = run
        print(f"[{profile}] {ds}: {len(fills)} fills, fees ${fees:.2f}, "
              f"funding ${funding_pnl:+.2f} -> equity ${equity_after:,.2f}")
    return {"trades": new_trades, "targets": new_targets, "daily": new_daily}


_close_cache = {}


def close_on(symbol, day):
    if symbol in _close_cache:
        px, upto = _close_cache[symbol]
        if upto >= day:
            return px
    try:
        df = market.daily_klines(symbol)
    except market.RateLimited:
        raise
    if df is None or df.empty:
        return None
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    hit = df[df.index < pd.Timestamp(day) + pd.Timedelta(days=1)]
    if hit.empty:
        return None
    px = float(hit.iloc[-1]["close"])
    _close_cache[symbol] = (px, day)
    return px


def patch_next_live_row(profile, cutoff, missing, cutoff_positions, all_trades):
    """Strip double-counted funding from the first live run after the gap.

    The live engine credited ALL payments since the cutoff run; the backfilled
    rows already credited the payments up to the end of the last missing day.
    Equity/cash/fills of the live row stay untouched; only funding_pnl is
    reduced to the residual window, and the change is logged as an event.
    """
    f = cfg.files(profile)
    next_date = (missing[-1] + timedelta(days=1)).strftime("%Y-%m-%d")
    daily = read_csv(f["daily"])
    hits = daily[daily["date"] == next_date]
    if hits.empty:
        print(f"[{profile}] no live row on {next_date}, nothing to adjust")
        return
    events = read_csv(f["events"])
    tag = f"[backfill] adjusted {next_date}"
    if not events.empty and events["message"].astype(str).str.contains(tag, regex=False).any():
        print(f"[{profile}] {next_date} funding already adjusted, skipping")
        return
    old_val = float(hits.iloc[0]["funding_pnl"])
    gap_end = run_ts(missing[-1]).replace(tzinfo=None)
    next_ts = run_timestamp_from_trades(all_trades, missing[-1] + timedelta(days=1))
    resid_day = (missing[-1] + timedelta(days=1))
    rates = funding_accrual(list(cutoff_positions.keys()), gap_end, next_ts.replace(tzinfo=None))
    new_val = 0.0
    for s, q in cutoff_positions.items():
        if q == 0 or s not in rates:
            continue
        px = close_on(s, resid_day)
        if px is None or px <= 0:
            continue
        new_val += -q * px * rates[s]
    daily.loc[daily["date"] == next_date, "funding_pnl"] = round(new_val, 6)
    daily.to_csv(f["daily"], index=False, encoding="utf-8")
    evt = pd.DataFrame([{"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                         "kind": "BACKFILL_ADJUST",
                         "message": f"{tag}: funding_pnl {old_val:+.4f} -> {new_val:+.4f} "
                                    f"(removed payments already credited to backfilled rows; "
                                    f"equity/cash/fills unchanged)"}])
    events = pd.concat([events, evt], ignore_index=True)
    events.to_csv(f["events"], index=False, encoding="utf-8")
    print(f"[{profile}] {next_date}: funding {old_val:+.4f} -> {new_val:+.4f} "
          f"(equity untouched)")


def write_backfill(profile, result):
    f = cfg.files(profile)
    daily = pd.concat([read_csv(f["daily"]),
                       pd.DataFrame(result["daily"], columns=DAILY_COLS)],
                      ignore_index=True)
    daily["date"] = daily["date"].astype(str)
    daily = daily.sort_values("date", kind="stable").reset_index(drop=True)
    trades = read_csv(f["trades"])
    trades = pd.concat([trades, pd.DataFrame(result["trades"], columns=TRADES_COLS)],
                       ignore_index=True)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], errors="coerce")
    trades = trades.sort_values("timestamp", kind="stable").reset_index(drop=True)
    trades["timestamp"] = trades["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    targets = pd.concat([read_csv(f["targets"]),
                         pd.DataFrame(result["targets"], columns=TARGETS_COLS)],
                        ignore_index=True)
    targets["date"] = targets["date"].astype(str)
    targets = targets.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    events = pd.concat([read_csv(f["events"]),
                        pd.DataFrame([{
                            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                            "kind": "BACKFILL",
                            "message": f"replayed missing days "
                                       f"{result['daily'][0]['date']}..{result['daily'][-1]['date']} "
                                       f"using historical closes; live rows untouched"}])],
                       ignore_index=True)
    daily.to_csv(f["daily"], index=False, encoding="utf-8")
    trades.to_csv(f["trades"], index=False, encoding="utf-8")
    targets.to_csv(f["targets"], index=False, encoding="utf-8")
    events.to_csv(f["events"], index=False, encoding="utf-8")
    print(f"[{profile}] wrote {len(result['daily'])} backfilled day(s)")


def main():
    ap = argparse.ArgumentParser(description="Backfill missed paper-trading days")
    ap.add_argument("--to", default=None, help="replay up to YYYY-MM-DD (default: today UTC)")
    a = ap.parse_args()
    to_date = (datetime.strptime(a.to, "%Y-%m-%d").date() if a.to else utc_today())

    plans, recon = {}, {}
    for profile in STRATEGY_PROFILES:
        have, missing, daily = detect_gap(profile, to_date)
        pre = float(daily["equity"].iloc[-1]) if not daily.empty else 0.0
        if missing is None:
            print(f"[{profile}] no gaps through {to_date}, latest equity ${pre:,.2f}")
            continue
        cutoff = missing[0] - timedelta(days=1)
        print(f"[{profile}] gap: cutoff {cutoff}, missing "
              f"{[d.strftime('%m-%d') for d in missing]}, latest equity ${pre:,.2f}")
        st = reconstruct(profile, cutoff)
        ok = (st["logged_cash"] is None or abs(st["cash"] - st["logged_cash"]) < 5.0)
        print(f"[{profile}] cutoff {cutoff}: reconstructed cash ${st['cash']:,.2f} vs logged "
              f"${st['logged_cash'] if st['logged_cash'] is not None else float('nan'):,.2f} "
              f"-> {'OK' if ok else 'MISMATCH, aborting this profile'}")
        if not ok:
            continue
        plans[profile] = (cutoff, missing, pre)
        recon[profile] = st
    if not plans:
        print("Nothing to backfill.")
        return

    print("Pulling market data (klines + funding) up to today ...")
    symbols = market.candidate_symbols()
    held = set()
    for profile in plans:
        held |= set(recon[profile]["positions"].keys())
    print(f"candidate pool: {len(symbols)} symbols + {len(held)} held")
    kdata = fetch_klines(sorted(set(symbols) | held))
    close, volume = build_panels(kdata)
    print(f"panel: {close.shape[1]} symbols x {len(close)} rows, "
          f"{close.index.min().date()} -> {close.index.max().date()}")

    for s in sorted(held):
        try:
            funding_df(s)
        except market.RateLimited:
            print("RATE LIMITED during funding pre-warm; aborting before any writes.")
            return
    print(f"funding pre-warmed for {len(held)} held symbols")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(cfg.BASE_DIR, f"state_backup_{stamp}")
    for profile in plans:
        dst = os.path.join(backup, profile)
        os.makedirs(dst, exist_ok=True)
        for fn in ("account.json", "daily.csv", "trades.csv", "targets.csv", "events.csv"):
            src = os.path.join(cfg.profile_dir(profile), fn)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst, fn))
    print(f"backed up state to {backup}")

    for profile, (cutoff, missing, pre) in plans.items():
        result = replay_profile(profile, recon[profile], missing, close, volume)
        if result["daily"]:
            write_backfill(profile, result)
        else:
            print(f"[{profile}] nothing replayed, state untouched")
            continue
        patch_next_live_row(profile, cutoff, missing, recon[profile]["positions"],
                            read_csv(cfg.files(profile)["trades"]))


if __name__ == "__main__":
    main()
