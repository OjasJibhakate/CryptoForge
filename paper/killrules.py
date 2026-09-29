"""Pre-registered kill rules (FORWARD_PROTOCOL.md amendment 1, adopted 2026-09-30).

Thresholds come from backtests only (research/c3_backtest.py, realistic execution),
fixed before C3's first run and before C1/C2's first month-end checkpoint.

  K1  risk model falsified: drawdown from the account high-water mark at or beyond
      the backtest's worst drawdown -> KILL.
  K2  performance falsified: at each fixed look (90/180/365/730 forward days),
      z = (live Sharpe - backtest Sharpe) / SE, SE = sqrt((1 + SR_bt^2 / 2) / years).
      z < -2.0 -> KILL. Between looks the latest look's verdict stands.
  W1  carry check (funding-tilted books): funding P&L over the trailing 90 forward
      days <= 0 -> WARN. Funding is most of the backtested return since 2023.

Acting on a KILL:  py -m paper.engine --profile <p> --retire "<rule and date>"
This module never trades.
"""
import math

import numpy as np
import pandas as pd

from . import config as cfg

REFERENCE = {
    "baseline": {"sharpe": 1.14, "max_dd": -0.333, "forward_from": "2026-09-24", "carry": False},
    "wave3": {"sharpe": 1.53, "max_dd": -0.265, "forward_from": "2026-09-24", "carry": True},
    "c3": {"sharpe": 1.62, "max_dd": -0.265, "forward_from": None, "carry": True},
}
LOOKS = (90, 180, 365, 730)
Z_KILL = -2.0
W1_DAYS = 90


def forward_path(profile, daily, acc, fwd_from=None):
    """(eq0, eq0_date, forward rows): eq0 is the last equity before the forward start,
    or initial capital when the account started inside the forward period."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.drop_duplicates("date", keep="last").sort_values("date")
    start = fwd_from or REFERENCE.get(profile, {}).get("forward_from")
    start = pd.Timestamp(start) if start else pd.Timestamp(acc["start_utc"]).normalize()
    before, fwd = d[d["date"] < start], d[d["date"] >= start]
    if len(before):
        return float(before["equity"].iloc[-1]), before["date"].iloc[-1], fwd
    return (float(acc.get("initial_capital", cfg.INITIAL_CAPITAL)),
            pd.Timestamp(acc["start_utc"]).normalize(), fwd)


def live_sharpe(eq0, eq0_date, rows):
    """Annualized Sharpe from run-to-run returns; robust to missed days (annualizes by
    elapsed calendar time, not by row count)."""
    path = np.array([eq0] + rows["equity"].astype(float).tolist())
    r = path[1:] / path[:-1] - 1.0
    years = max((rows["date"].iloc[-1] - eq0_date).days, 1) / 365.0
    if len(r) < 2 or np.std(r, ddof=1) == 0:
        return float("nan"), years
    ann_ret = math.log(path[-1] / path[0]) / years
    ann_vol = np.std(r, ddof=1) * math.sqrt(len(r) / years)
    return float(ann_ret / ann_vol), years


def evaluate(profile, daily, acc):
    """{'status': OK|WARN|KILL|RETIRED|NO DATA, 'lines': [...]}"""
    if acc.get("retired"):
        return {"status": "RETIRED", "lines": [f"retired {acc['retired']}"]}
    ref = REFERENCE.get(profile)
    if ref is None or daily.empty:
        return {"status": "NO DATA", "lines": ["no kill-rule reference or no rows"]}
    eq0, eq0_date, fwd = forward_path(profile, daily, acc)
    if fwd.empty:
        return {"status": "NO DATA", "lines": ["no forward rows yet"]}
    status, lines = "OK", []

    dd = float(fwd["equity"].iloc[-1]) / float(acc.get("high_water_mark", eq0)) - 1.0
    k1 = dd <= ref["max_dd"]
    lines.append(f"K1 drawdown {dd * 100:.1f}% vs backtest worst {ref['max_dd'] * 100:.1f}% -> "
                 f"{'KILL' if k1 else 'ok'}")
    status = "KILL" if k1 else status

    span = (fwd["date"].iloc[-1] - eq0_date).days
    passed = [L for L in LOOKS if span >= L]
    if passed:
        L = passed[-1]
        rows = fwd[fwd["date"] <= eq0_date + pd.Timedelta(days=L)]
        sr, years = live_sharpe(eq0, eq0_date, rows)
        se = math.sqrt((1 + ref["sharpe"] ** 2 / 2) / years)
        z = (sr - ref["sharpe"]) / se
        k2 = z < Z_KILL
        lines.append(f"K2 day-{L} look: live Sharpe {sr:+.2f} vs backtest {ref['sharpe']:.2f} "
                     f"(SE {se:.2f}, z {z:+.2f}, kill below {Z_KILL}) -> {'KILL' if k2 else 'ok'}")
        status = "KILL" if k2 else status
    else:
        nxt = next(L for L in LOOKS if span < L)
        lines.append(f"K2 first look at day {nxt} (day {span} now): "
                     f"{(eq0_date + pd.Timedelta(days=nxt)).date()}")

    if ref["carry"] and span >= W1_DAYS:
        cut = fwd["date"].iloc[-1] - pd.Timedelta(days=W1_DAYS)
        f90 = float(pd.to_numeric(fwd.loc[fwd["date"] > cut, "funding_pnl"], errors="coerce").sum())
        w1 = f90 <= 0
        lines.append(f"W1 funding last {W1_DAYS}d ${f90:+.2f} -> {'WARN' if w1 else 'ok'}")
        if w1 and status == "OK":
            status = "WARN"
    return {"status": status, "lines": lines}
