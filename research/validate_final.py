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


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    mom = sz.zs(mom_stack / vol30, mask)
    ftilt = mom - sz.zs(f7, mask)
    btc = close["BTCUSDT"]

    def run(score, overlay, k=10, fee=5.0, slip=2.0):
        w = sz.xs(score, mask, k=k)
        if overlay is not None:
            w = w.mul(overlay, axis=0)
        r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=PPY)
        net = r["net"]
        return net

    def line(label, net):
        m = bt.metrics(net, PPY)
        o = bt.metrics(net[net.index >= SPLIT], PPY)
        i = bt.metrics(net[net.index < SPLIT], PPY)
        sc = bt.scaled_metrics(net, 0.40, PPY)
        print(f"{label:<34} IS {i['sharpe']:5.2f}  OOS {o['sharpe']:5.2f}  full {m['sharpe']:5.2f}  "
              f"CAGR {m['cagr']*100:5.1f}%  DD {m['max_dd']*100:6.1f}%  at40DD {sc['cagr']*100:5.1f}%")

    reg = lambda n, soft: pd.Series(np.where(btc > btc.rolling(n).mean(), 1.0, soft), index=btc.index)

    print("=== MA-LENGTH SENSITIVITY of the regime filter (soft=0.5) ===")
    for n in [50, 100, 150, 200, 250, 300, 365]:
        line(f"ftilt + regime MA{n}", run(ftilt, reg(n, 0.5)))

    print("\n=== SOFT-SCALE SENSITIVITY (MA=200) ===")
    for s in [0.0, 0.25, 0.5, 0.75, 1.0]:
        line(f"ftilt + regime soft={s}", run(ftilt, reg(200, s)))

    print("\n=== k SENSITIVITY (MA=200, soft=0.5) ===")
    for k in [3, 5, 10, 15, 20, 30]:
        line(f"ftilt + regime k={k}", run(ftilt, reg(200, 0.5), k=k))

    print("\n=== COST SENSITIVITY (MA=200, soft=0.5, k=10) ===")
    for fee, slip in [(2, 1), (5, 2), (10, 5), (20, 10), (30, 15)]:
        line(f"cost {fee}+{slip}", run(ftilt, reg(200, 0.5), fee=fee, slip=slip))

    print("\n=== TREND-ENSEMBLE MOMENTUM (more lookbacks) + regime ===")
    for lbs in [(14, 21, 30, 45, 60), (10, 20, 40, 80), (20, 60, 120), (30, 90, 180)]:
        ms = sum(close / close.shift(lb) - 1.0 for lb in lbs) / len(lbs)
        sc = sz.zs(ms / vol30, mask) - sz.zs(f7, mask)
        line(f"ftilt lbs{lbs}", run(sc, reg(200, 0.5)))

    print("\n=== FINAL CANDIDATE sub-periods (ftilt + MA200 soft 0.5, k=10) ===")
    net = run(ftilt, reg(200, 0.5))
    idx = net.index
    b = np.linspace(0, len(idx), 6).astype(int)
    for j in range(5):
        seg = net.iloc[b[j]:b[j + 1]]
        m = bt.metrics(seg, PPY)
        print(f"   {idx[b[j]].date()} -> {idx[b[j+1]-1].date()}: Sharpe {m['sharpe']:5.2f}  "
              f"CAGR {m['cagr']*100:7.1f}%  DD {m['max_dd']*100:6.1f}%")
    m = bt.metrics(net, PPY)
    oos = net[net.index >= SPLIT]
    t = bt.metrics(oos, PPY)["sharpe"] * np.sqrt(len(oos) / PPY)
    print(f"\n   full Sharpe {m['sharpe']:.2f} | CAGR {m['cagr']*100:.1f}% | DD {m['max_dd']*100:.1f}% | "
          f"OOS t = {t:.2f}")
    pd.DataFrame({"net": net, "equity": (1 + net).cumprod()}).to_csv(
        os.path.join(bt.DATA_DIR, "final_candidate_equity.csv"))


if __name__ == "__main__":
    main()
