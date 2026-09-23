"""Leverage/sizing overlay on the wave3 book: which construction turns the
proven edge into the biggest return inside the 40% max-drawdown budget?

Candidates (all carry funding + realistic costs, full 2019-2026 history):
  1. wave3 1x (live book, no extra leverage)
  2. wave3 2x / 3x notional (gross-capped, per-name cap kept)
  3. vol-target overlays 0.45 / 0.60 / 0.80 (scale to realized vol)
  4. risk-managed overlay (RM 0.20 target, cap 2x) -- wave3 live already has this
  5. best of sweep appended? (only if sweep found a consistent winner)

Judged on at-40%-DD CAGR (the budget), OOS Sharpe, and worst sub-period.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
import strategy_zoo as sz
from strategy_zoo2 import load_full

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365


def row(name, net):
    m = bt.metrics(net, PPY)
    o = bt.metrics(net[net.index >= SPLIT], PPY)
    sc = bt.scaled_metrics(net, 0.40, PPY)
    print(f"{name:<44} full Sh {m['sharpe']:5.2f} CAGR {m['cagr']*100:7.1f}% "
          f"DD {m['max_dd']*100:7.1f}% | OOS {o['sharpe']:5.2f} | "
          f"at40DD {sc['cagr']*100:7.1f}% (x{sc['scale']:.2f})")
    return {"name": name, "net": net, "at40dd": sc["cagr"]}


def vol_scale(ret_series, target, lookback=30):
    rv = ret_series.rolling(lookback).std() * np.sqrt(365)
    return (target / rv.replace(0, np.nan)).fillna(1.0)


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change().fillna(0.0)
    vol30 = close.pct_change().rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    ftilt = sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask)
    btc = close["BTCUSDT"]
    ma200 = btc.rolling(200).mean()
    overlay = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=close.index).where(ma200.notna(), 1.0)

    base_w = sz.xs(ftilt, mask).mul(overlay, axis=0)

    def run(w, lev=1.0):
        return bt.portfolio_backtest(ret, w * lev, funding=fund, leverage_cap=lev,
                                     asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)["net"]

    print("=== LEVERAGE / SIZING OVERLAYS ON wave3 BOOK ===\n")
    outs = []
    outs.append(row("1x live book", run(base_w, 1.0)))
    for lev in [1.5, 2.0, 3.0]:
        outs.append(row(f"{lev}x notional", run(base_w, lev)))
    base_net = run(base_w, 1.0)
    for tgt in [0.45, 0.60, 0.80]:
        vs = vol_scale(base_net, tgt).shift(1).fillna(1.0)
        outs.append(row(f"vol-target {tgt:.2f}", run(base_w.mul(vs, axis=0), 2.0)))
    rv90 = base_net.rolling(90).std() * np.sqrt(365)
    rm = (0.20 / rv90).clip(upper=2.0).shift(1).fillna(1.0)
    outs.append(row("RM overlay 0.20/cap2 (live wave3)", run(base_w.mul(rm, axis=0), 2.0)))

    best = max(outs, key=lambda d: d["at40dd"])
    print(f"\nBest inside 40% DD: {best['name']} at {best['at40dd']*100:.1f}% CAGR")
    print("\n--- sub-periods of the best ---")
    idx = best["net"].index
    b = np.linspace(0, len(idx), 6).astype(int)
    for j in range(5):
        seg = best["net"].iloc[b[j]:b[j + 1]]
        m = bt.metrics(seg, PPY)
        print(f"   {idx[b[j]].date()} -> {idx[b[j+1]-1].date()}: Sharpe {m['sharpe']:5.2f}  "
              f"CAGR {m['cagr']*100:7.1f}%  DD {m['max_dd']*100:6.1f}%")
    best["net"].to_csv(os.path.join(bt.DATA_DIR, "crazy_best_net.csv"))


if __name__ == "__main__":
    main()
