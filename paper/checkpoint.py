"""Forward-validation checkpoint report. READ-ONLY: never trades, never edits state.

Compares each live/paper book against its frozen historical baseline WITHOUT
reclassifying anything. Reports the 9 protocol items plus ledger integrity and the
pre-registered kill rules (FORWARD_PROTOCOL.md amendment 1):

  1. sample size  2. net performance  3. realized costs  4. realized funding
  5. drawdown  6. concentration  7. execution deviations  8. operational failures
  9. comparison with the frozen historical baseline

Usage:
    python -m paper.checkpoint                    # each book's own forward window
    python -m paper.checkpoint --from 2026-09-24  # a common window start

Validation language (fixed):
  Historical backtest = positive historical evidence
  2024+ historical OOS = contaminated
  Pre-freeze paper (through 2026-09-23) = execution evidence only
  Forward period (C1/C2 from 2026-09-24, C3 from its first run) = clean validation data
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from paper import candidates, killrules, ledger
from paper import config as cfg

# research/c3_backtest.py, realistic execution (drift-inclusive turnover, live funding
# timing). top5_notional = mean share of gross in the 5 largest positions (same
# definition as the live top5_share column); top5_pnl = share of total P&L from the
# 5 best names (TRADEFORGE_AUDIT.md section 9) -- a different quantity, shown only.
HIST_BASELINE = {
    "baseline": {"sharpe": 1.14, "cagr": 32.9, "dd": -33.3, "turnover": 0.211,
                 "fund_bps": 954, "top5_notional": 26.2, "top5_pnl": 45.6},
    "wave3": {"sharpe": 1.53, "cagr": 29.5, "dd": -26.5, "turnover": 0.153,
              "fund_bps": 1345, "top5_notional": 26.2, "top5_pnl": 63.0},
    "c3": {"sharpe": 1.62, "cagr": 31.8, "dd": -26.5, "turnover": 0.153,
           "fund_bps": 1369, "top5_notional": 26.2, "top5_pnl": None},
}
STRESS_MULT = {"fee": 2.0, "slip": 2.5}  # 10bps fee + 5bps slip vs 5+2 base
ROUTINE_EVENTS = {"BACKFILL", "BACKFILL_ADJUST", "MISSING_FUNDING", "CIRCUIT_BREAKER",
                  "LEDGER_REPAIR"}
MIN_RETURNS_FOR_SHARPE = 30


def read_csv(path):
    if os.path.exists(path) and os.path.getsize(path) > 3:
        try:
            return pd.read_csv(path, encoding="utf-8")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def freeze_ok():
    r = subprocess.run([sys.executable, "paper/freeze_manifest.py", "--check"],
                       capture_output=True, text=True, cwd=os.path.dirname(
                           os.path.dirname(os.path.abspath(__file__))))
    print(r.stdout.rstrip())
    return r.returncode == 0


def _col(df, name, default=np.nan):
    return pd.to_numeric(df[name], errors="coerce") if name in df.columns else pd.Series(default, index=df.index)


def summarize(profile, fwd_from=None):
    f = cfg.files(profile)
    if not os.path.exists(f["account"]):
        return None
    acc = json.load(open(f["account"], encoding="utf-8"))
    daily, events = read_csv(f["daily"]), read_csv(f["events"])
    if daily.empty:
        return None
    eq0, eq0_date, fwd = killrules.forward_path(profile, daily, acc, fwd_from)
    if fwd.empty:
        return None
    start = fwd["date"].min()
    eq1 = float(fwd["equity"].iloc[-1])
    span = max((fwd["date"].max() - eq0_date).days, 1)
    ann = 365.0 / span
    path = pd.Series([eq0] + fwd["equity"].astype(float).tolist())
    dd_window = float((path / path.cummax() - 1).min())
    dd_hwm = eq1 / float(acc.get("high_water_mark", eq0)) - 1.0
    n_ret = len(path) - 1
    sharpe = killrules.live_sharpe(eq0, eq0_date, fwd)[0] if n_ret >= MIN_RETURNS_FOR_SHARPE else None

    rec, _ = ledger.replay(profile)
    rec.index = pd.to_datetime(rec.index)
    w = rec[rec.index >= start]
    # Leg P&L: the engine's per-run long/short_pnl_day (diagnostics v2) is exact even when
    # a date has several runs; dates without it use the ledger replay, which merges a
    # date's runs (exact for the single-run dates logged before v2).
    rows = daily.copy()
    rows["date"] = pd.to_datetime(rows["date"])
    rows = rows[rows["date"] >= start]
    lng = sht = 0.0
    for day, g in rows.groupby("date"):
        if "long_pnl_day" in g.columns and _col(g, "long_pnl_day").notna().all():
            lng += float(_col(g, "long_pnl_day").sum())
            sht += float(_col(g, "short_pnl_day").sum())
        elif day in w.index:
            lng += float(w.loc[day, "long_pnl"])
            sht += float(w.loc[day, "short_pnl"])
    legs = dict(long=lng, short=sht, fund=float(w["funding"].sum()), fee=float(w["fees"].sum()),
                slip=float(w["slippage"].sum()))
    explained = legs["long"] + legs["short"] + legs["fund"] - legs["fee"] - legs["slip"]
    integrity = ledger.verify(profile)
    turnover = float((w["traded"] / w["equity"]).mean()) if len(w) else 0.0

    last = fwd.iloc[-1]
    top = {k: float(_col(fwd, f"{k}_share").iloc[-1]) * 100 for k in ("top1", "top3", "top5")}
    tradfi = float(_col(fwd, "tradfi_share").iloc[-1]) * 100
    beta = float(_col(fwd, "beta_btc").iloc[-1])

    dev = []
    full = daily.copy()
    full["date"] = pd.to_datetime(full["date"])
    fw_full = full[full["date"] >= start]
    if fw_full["date"].duplicated().any():
        dev.append(f"{int(fw_full['date'].duplicated().sum())} duplicate daily rows")
    gaps = fwd["date"].diff().dt.days
    if (gaps > 1).any():
        dev.append(f"missed days: {int((gaps - 1).clip(lower=0).sum())} (longest gap {int(gaps.max())}d)")
    run_ts = pd.to_datetime(fwd["run_utc"], errors="coerce") if "run_utc" in fwd.columns \
        else pd.Series(pd.NaT, index=fwd.index)
    run_ts = run_ts.fillna(pd.Series(rec["run_ts"].reindex(fwd["date"]).values, index=fwd.index))
    prev_ts = rec["run_ts"][rec.index < start]
    seq = pd.concat([prev_ts.tail(1), pd.Series(run_ts.values)], ignore_index=True).dropna()
    hrs = seq.diff().dt.total_seconds().dropna() / 3600.0
    odd = hrs[(hrs < 12) | (hrs > 36)]
    if len(odd):
        dev.append(f"{len(odd)} irregular run intervals ({', '.join(f'{h:.1f}h' for h in odd)})")
    miss_new = fwd["missing_funding_held"].astype(str).replace("nan", "") \
        if "missing_funding_held" in fwd.columns else pd.Series("", index=fwd.index)
    n_v2 = int(_col(fwd, "hours_since_prev").notna().sum()) if "hours_since_prev" in fwd.columns else 0
    miss_days = int((miss_new.str.len() > 0).sum())

    evts = events[pd.to_datetime(events["timestamp"], errors="coerce") >= start] if not events.empty else events
    fails = evts[~evts["kind"].isin(ROUTINE_EVENTS)] if not evts.empty else evts
    return dict(profile=profile, acc=acc, start=start, eq0=eq0, eq0_date=eq0_date, eq1=eq1,
                n=len(fwd), span=span, ret=(eq1 / eq0 - 1) * 100, sharpe=sharpe, n_ret=n_ret,
                legs=legs, explained=explained, actual=eq1 - eq0, integrity=integrity,
                fund_bps=legs["fund"] / eq0 * 1e4 * ann, fee_bps=legs["fee"] / eq0 * 1e4 * ann,
                slip_bps=legs["slip"] / eq0 * 1e4 * ann, turnover=turnover,
                dd_window=dd_window * 100, dd_hwm=dd_hwm * 100,
                breaker_days=int(_col(fwd, "breaker", 0).sum()),
                margin=float(_col(fwd, "margin_util").iloc[-1]), top=top, tradfi=tradfi, beta=beta,
                dev=dev, miss_days=miss_days, n_v2=n_v2, n_events=len(evts), fails=fails,
                kill=killrules.evaluate(profile, daily, acc))


def report(s, h):
    L = s["legs"]
    print(f"--- {s['profile']} ({candidates.cfg_for(s['profile'])['label']}) ---")
    print(f"1. sample: {s['n']} forward rows, {s['span']}d from {s['eq0_date'].date()} close "
          f"(window starts {s['start'].date()})")
    sh = f"{s['sharpe']:+.2f}" if s["sharpe"] is not None else \
        f"n/a ({s['n_ret']} returns < {MIN_RETURNS_FOR_SHARPE})"
    print(f"2. net: ${s['eq0']:,.2f} -> ${s['eq1']:,.2f} ({s['ret']:+.2f}%), Sharpe {sh}")
    print(f"   legs (ledger replay): long ${L['long']:+,.2f} | short ${L['short']:+,.2f} | "
          f"funding ${L['fund']:+,.2f} | fees -${L['fee']:,.2f} | slippage -${L['slip']:,.2f}")
    print(f"   = ${s['explained']:+,.2f} vs actual ${s['actual']:+,.2f} "
          f"({'reconciles' if abs(s['explained'] - s['actual']) < 1.0 else 'DOES NOT RECONCILE'})")
    print(f"3. costs: fees {s['fee_bps']:.0f} + slippage {s['slip_bps']:.0f} bps/yr "
          f"(stress 10+5: {s['fee_bps'] * STRESS_MULT['fee'] + s['slip_bps'] * STRESS_MULT['slip']:.0f}); "
          f"turnover {s['turnover']:.3f}/day vs backtest {h['turnover']:.3f}")
    print(f"4. funding: ${L['fund']:+,.2f} ({s['fund_bps']:+.0f} bps/yr ann.) vs backtest {h['fund_bps']:+.0f}")
    print(f"5. drawdown: window {s['dd_window']:.2f}% | from account high-water mark {s['dd_hwm']:.2f}% "
          f"| backtest worst {h['dd']:.1f}% | breaker {s['breaker_days']}d | margin util {s['margin']:.2f}x")
    flag = "  <-- FLAG: above backtest +10pp" if s["top"]["top5"] > h["top5_notional"] + 10 else ""
    pnl5 = f"; backtest P&L top-5 {h['top5_pnl']:.1f}% is a different measure" if h["top5_pnl"] else ""
    print(f"6. concentration (share of gross): top1 {s['top']['top1']:.1f}% / top3 {s['top']['top3']:.1f}% / "
          f"top5 {s['top']['top5']:.1f}% vs backtest top5 {h['top5_notional']:.1f}%{flag}{pnl5}")
    if np.isfinite(s["tradfi"]):
        tf_flag = "  <-- FLAG: C3 must hold 0%" if s["profile"] == "c3" and s["tradfi"] > 0 else \
            ("  (known deviation: backtest was crypto-only until 2026)" if s["tradfi"] > 0 else "")
        print(f"   TradFi share {s['tradfi']:.1f}%{tf_flag} | ex-ante BTC beta {s['beta']:+.2f} "
              f"(backtest ~0.00)")
    print(f"7. execution deviations: {'; '.join(s['dev']) or 'none'}; carried-position funding gaps "
          f"on {s['miss_days']} of {s['n_v2']} rows logged since diagnostics v2")
    v = s["integrity"]
    print(f"8. operational: {s['n_events']} events, {len(s['fails'])} non-routine"
          + (f" ({', '.join(s['fails']['kind'].astype(str).unique())})" if len(s['fails']) else "")
          + f" | ledger {'reconciles' if v['ok'] else 'DOES NOT RECONCILE'} "
            f"(max equity error ${v['max_err']:.4f}, positions {'match' if v['positions_match'] else 'DIFFER'})")
    sh9 = f"{s['sharpe']:+.2f}" if s["sharpe"] is not None else "n/a"
    print(f"9. vs frozen baseline: Sharpe {sh9} vs {h['sharpe']:.2f} | turnover {s['turnover']:.3f} vs "
          f"{h['turnover']:.3f} | funding {s['fund_bps']:+.0f} vs {h['fund_bps']:+.0f} bps/yr")
    k = s["kill"]
    print(f"KILL RULES: {k['status']}")
    for ln in k["lines"]:
        print(f"   {ln}")


def main():
    ap = argparse.ArgumentParser(description="Forward-validation checkpoint (read-only)")
    ap.add_argument("--from", dest="fwd_from", default=None,
                    help="common window start YYYY-MM-DD (default: each book's forward start)")
    a = ap.parse_args()

    print("=" * 78)
    print("CRYPTOFORGE FORWARD CHECKPOINT — READ ONLY")
    print(f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
          + (f" | window from {a.fwd_from}" if a.fwd_from else " | each book's forward window"))
    print("Historical backtest = positive historical evidence | 2024+ OOS = contaminated | "
          "pre-freeze paper = execution evidence only")
    print("=" * 78)
    print("freeze gate:")
    ok = freeze_ok()
    print()
    for profile in candidates.strategy_profiles():
        s = summarize(profile, a.fwd_from)
        if s is None:
            print(f"--- {profile}: no forward rows ---\n")
            continue
        report(s, HIST_BASELINE[profile])
        print(f"freeze gate at report time: {'OK' if ok else 'DRIFT — INVALID'}")
        print()
    print("A forward window under ~1.5-3 years cannot confirm or reject these edges on returns "
          "(research: live years needed for t=2). Kill rules K1/K2 are the only pre-registered "
          "exits. No tuning. No reclassification.")


if __name__ == "__main__":
    main()
