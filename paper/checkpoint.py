"""Forward-validation checkpoint report. READ-ONLY: never trades, never edits state.

Compares the live/paper run (the clean validation dataset) against the frozen
historical baseline WITHOUT reclassifying anything. Reports the 9 items:

  1. sample size  2. net performance  3. realized costs  4. realized funding
  5. drawdown  6. concentration  7. execution deviations  8. operational failures
  9. comparison with the frozen historical baseline

Usage:
    python -m paper.checkpoint                 # full period to date
    python -m paper.checkpoint --from 2026-09-23   # forward window only

Validation language (fixed):
  Historical backtest = positive historical evidence
  2024+ historical OOS = contaminated
  11-day (pre-freeze) paper = execution evidence only
  Forward period from --from = clean validation dataset
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

from paper import config as cfg

HIST_BASELINE = {
    "baseline": {"sharpe": 1.17, "cagr": 33.9, "dd": -32.9, "turnover": 0.185,
                 "fund_bps": 954, "fee_bps": 472, "win": 47.8, "top5": 45.6},
    "wave3": {"sharpe": 1.56, "cagr": 30.5, "dd": -26.3, "turnover": 0.137,
              "fund_bps": 1345, "fee_bps": 350, "win": 46.9, "top5": 63.0},
}
STRESS_MULT = {"fee": 2.0, "slip": 2.5}  # 10bps fee + 5bps slip vs 5+2 base


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
    print(r.stdout.strip())
    return r.returncode == 0


def summarize(profile, fwd_from):
    f = cfg.files(profile)
    acc = json.load(open(f["account"], encoding="utf-8"))
    daily = read_csv(f["daily"])
    trades = read_csv(f["trades"])
    events = read_csv(f["events"])
    if daily.empty:
        return None
    daily["date"] = pd.to_datetime(daily["date"])
    fwd = daily[daily["date"] >= pd.Timestamp(fwd_from)].copy() if fwd_from else daily.copy()
    if fwd.empty:
        return None

    eq0 = float(daily[daily["date"] < pd.Timestamp(fwd_from)]["equity"].iloc[-1]) \
        if fwd_from and (daily["date"] < pd.Timestamp(fwd_from)).any() \
        else float(acc["initial_capital"])
    eq1 = float(fwd["equity"].iloc[-1])
    rets = fwd["equity"].pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(365)) if len(rets) > 1 and rets.std() > 0 else 0.0
    dd = float((fwd["equity"] / fwd["equity"].cummax() - 1).min())

    for c in ["funding_pnl", "fee_pnl", "slip_pnl", "long_pnl", "short_pnl",
              "spread_pnl", "turnover", "margin_util",
              "top1_share", "top3_share", "top5_share"]:
        if c not in fwd.columns:
            fwd[c] = 0.0
    if "missing_funding" not in fwd.columns:
        fwd["missing_funding"] = ""
    ndays = max((fwd["date"].max() - fwd["date"].min()).days, 1)
    ann = 365.0 / ndays
    fund_bps = float(fwd["funding_pnl"].sum() / eq0 * 1e4 * ann)
    fee_bps = float(fwd["fee_pnl"].sum() / eq0 * 1e4 * ann)
    slip_bps = float(fwd["slip_pnl"].sum() / eq0 * 1e4 * ann)
    s_fee = fee_bps * STRESS_MULT["fee"]
    s_slip = slip_bps * STRESS_MULT["slip"]

    top1 = float(fwd["top1_share"].iloc[-1]) * 100
    top3 = float(fwd["top3_share"].iloc[-1]) * 100
    top5 = float(fwd["top5_share"].iloc[-1]) * 100
    miss = fwd[fwd["missing_funding"].astype(str).str.len() > 0]
    brk = int(fwd["breaker"].sum()) if "breaker" in fwd.columns else 0
    evts = events[pd.to_datetime(events["timestamp"], errors="coerce")
                  >= pd.Timestamp(fwd_from)] if (not events.empty and fwd_from) else events
    fails = evts[~evts["kind"].isin(["BACKFILL", "BACKFILL_ADJUST", "MISSING_FUNDING",
                                     "CIRCUIT_BREAKER"])] if not evts.empty else evts
    dev = ""
    if not fwd.empty and fwd["date"].duplicated().any():
        dev += "duplicate daily rows; "
    gap = fwd["date"].diff().dt.days
    if (gap > 2).any(skipna=True):
        dev += f"date gap {int(gap.max())}d; "
    return dict(profile=profile, n=len(fwd), days=ndays, eq0=eq0, eq1=eq1,
                ret=(eq1 / eq0 - 1) * 100, sharpe=sharpe, dd=dd * 100,
                long=float(fwd["long_pnl"].sum()), short=float(fwd["short_pnl"].sum()),
                spread=float(fwd["spread_pnl"].sum()),
                fund=float(fwd["funding_pnl"].sum()), fee=float(fwd["fee_pnl"].sum()),
                slip=float(fwd["slip_pnl"].sum()),
                fund_bps=fund_bps, fee_bps=fee_bps, slip_bps=slip_bps,
                s_fee=s_fee, s_slip=s_slip,
                turnover=float(fwd["turnover"].mean()),
                margin=float(fwd["margin_util"].iloc[-1]) if "margin_util" in fwd else 0.0,
                top1=top1, top3=top3, top5=top5,
                miss_days=len(miss), breaker_days=brk,
                n_events=len(evts) if evts is not None else 0,
                n_fails=len(fails) if fails is not None else 0,
                dev=dev or "none detected")


def main():
    ap = argparse.ArgumentParser(description="Forward-validation checkpoint (read-only)")
    ap.add_argument("--from", dest="fwd_from", default=None,
                    help="forward window start YYYY-MM-DD (default: whole history)")
    a = ap.parse_args()

    print("=" * 72)
    print("CRYPTOFORGE FORWARD CHECKPOINT — READ ONLY")
    print(f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
          + (f" | forward window from {a.fwd_from}" if a.fwd_from else " | full history"))
    print("Historical backtest = positive historical evidence | "
          "2024+ OOS = contaminated | pre-freeze paper = execution evidence only")
    print("=" * 72)
    print("freeze gate:")
    ok = freeze_ok()
    print()

    for profile in ("baseline", "wave3"):
        s = summarize(profile, a.fwd_from)
        if s is None:
            print(f"--- {profile}: no forward rows ---\n")
            continue
        h = HIST_BASELINE[profile]
        print(f"--- {profile} ({cfg.cfg_for(profile)['label']}) ---")
        print(f"1. sample: {s['n']} daily rows over {s['days']}d")
        print(f"2. net: ${s['eq0']:,.2f} -> ${s['eq1']:,.2f} ({s['ret']:+.2f}%), "
              f"Sharpe {s['sharpe']:.2f}, long ${s['long']:+.2f} / short ${s['short']:+.2f} "
              f"/ spread ${s['spread']:+.2f}")
        print(f"3. costs: fees ${s['fee']:.2f} ({s['fee_bps']:.0f}bps/yr) + slippage "
              f"${s['slip']:.2f} ({s['slip_bps']:.0f}bps/yr); stress 10+5: "
              f"fees {s['s_fee']:.0f} + slip {s['s_slip']:.0f}bps/yr; turnover {s['turnover']:.3f}/day")
        print(f"4. funding: ${s['fund']:+.2f} ({s['fund_bps']:+.0f}bps/yr ann.) — "
              f"{'MATERIAL' if abs(s['fund']) > abs(s['ret']/100*s['eq0'])*0.2 else 'minor'} "
              f"vs net move")
        print(f"5. drawdown: {s['dd']:.2f}% (frozen max {h['dd']:.1f}%); "
              f"breaker active {s['breaker_days']}d; margin util {s['margin']:.2f}x")
        flag = "  <-- FLAG: concentration above historical baseline" \
            if s['top5'] > h['top5'] + 10 else ""
        print(f"6. concentration: top1 {s['top1']:.1f}% / top3 {s['top3']:.1f}% / "
              f"top5 {s['top5']:.1f}% (historical top5 {h['top5']:.1f}%){flag}")
        print(f"7. execution deviations: {s['dev']}missing-funding days {s['miss_days']}")
        print(f"8. operational: {s['n_events']} events, {s['n_fails']} non-routine "
              f"(non breaker/missing/backfill)")
        print(f"9. vs frozen baseline: Sharpe {s['sharpe']:.2f} vs {h['sharpe']:.2f} | "
              f"turnover {s['turnover']:.3f} vs {h['turnover']:.3f} | "
              f"fund {s['fund_bps']:+.0f} vs {h['fund_bps']:+.0f}bps/yr | "
              f"top5 {s['top5']:.1f}% vs {h['top5']:.1f}%")
        print(f"freeze gate at report time: {'OK' if ok else 'DRIFT — INVALID'}")
        print()
    print("Month-end is the first checkpoint, not final proof. "
          "No tuning. No reclassification.")


if __name__ == "__main__":
    main()
