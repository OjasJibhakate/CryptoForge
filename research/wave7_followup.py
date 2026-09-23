"""Wave7 follow-up: is the CTR stack a new signal or momentum in a costume?
 1. correlation of CTR sleeve returns vs wave3 sleeve returns (IS and OOS)
 2. CTR + wave3 blend: does adding it improve the book?
 3. CTR costs: turnover 0.62 vs momentum 0.27 -- cost tolerance at 10+5 / 20+10
 4. sub-periods of CTR stack
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
K = 10


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    ftilt = sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask)
    ctrend = sum((close - close.rolling(n).mean()) / close.rolling(n).std().replace(0, np.nan)
                 for n in (5, 10, 20, 40, 60)) / 5.0

    w_mom = sz.xs(ftilt, mask, k=K)
    w_ctr = sz.xs(ctrend, mask, k=K)
    r_mom = bt.portfolio_backtest(ret.fillna(0.0), w_mom, funding=fund, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    r_ctr = bt.portfolio_backtest(ret.fillna(0.0), w_ctr, funding=fund, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    a, b = r_mom["net"], r_ctr["net"]
    print("=== 1. CTR vs wave3-momentum sleeve return correlation ===")
    for label, sl in [("IS  (<2024)", a.index < SPLIT), ("OOS (>=2024)", a.index >= SPLIT),
                      ("full", slice(None))]:
        x, y = a[sl], b[sl]
        print(f"  {label:<12} corr {x.corr(y):+.3f}")

    print("\n=== 2. blend: 50/50 of weights ===")
    wb = (w_mom + w_ctr) / 2.0
    r_b = bt.portfolio_backtest(ret.fillna(0.0), wb, funding=fund, leverage_cap=1.0,
                                asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    for nm, net in [("mom sleeve", a), ("CTR sleeve", b), ("50/50 blend", r_b["net"])]:
        m = bt.metrics(net, PPY)
        o = bt.metrics(net[net.index >= SPLIT], PPY)
        sc = bt.scaled_metrics(net, 0.40, PPY)
        print(f"  {nm:<12} full Sh {m['sharpe']:5.2f} CAGR {m['cagr']*100:6.1f}% "
              f"DD {m['max_dd']*100:6.1f}% | OOS {o['sharpe']:5.2f} | at40DD {sc['cagr']*100:5.1f}%")

    print("\n=== 3. cost tolerance (fee+slip bps per side) ===")
    for fee, slip in [(2, 1), (5, 2), (10, 5), (20, 10)]:
        line = f"  {fee}+{slip}:"
        for nm, w in [("mom", w_mom), ("CTR", w_ctr), ("blend", wb)]:
            r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=1.0,
                                      asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=PPY)
            m = bt.metrics(r["net"], PPY)
            line += f"  {nm} Sh {m['sharpe']:.2f}/CAGR {m['cagr']*100:5.1f}%"
        print(line)

    print("\n=== 4. CTR stack sub-periods ===")
    idx = b.index
    bb = np.linspace(0, len(idx), 6).astype(int)
    for j in range(5):
        seg = b.iloc[bb[j]:bb[j + 1]]
        m = bt.metrics(seg, PPY)
        print(f"   {idx[bb[j]].date()} -> {idx[bb[j+1]-1].date()}: Sharpe {m['sharpe']:5.2f}  "
              f"CAGR {m['cagr']*100:7.1f}%  DD {m['max_dd']*100:6.1f}%")


if __name__ == "__main__":
    main()
