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


def wave3_w(close, mask, fund, veto_ma=None, renormalize=True, regime=True, rm=True,
            veto_on_shorts=True):
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    score = sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask)
    w = sz.xs(score, mask, k=K)

    if veto_ma:
        ma = close.rolling(veto_ma).mean()
        above = close > ma
        ok = ((w > 0) & above) | (((w < 0) & ~above) if veto_on_shorts else (w < 0))
        w = w.where(ok, 0.0)
        if renormalize:
            w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)

    if regime:
        btc = close["BTCUSDT"]
        ma200 = btc.rolling(200).mean()
        overlay = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=close.index).where(ma200.notna(), 1.0)
        w = w.mul(overlay, axis=0)

    if rm:
        base = (w.shift(1) * ret.fillna(0.0).reindex_like(w)).sum(axis=1)
        rv = base.rolling(90).std() * np.sqrt(365)
        scale = (0.20 / rv).clip(upper=2.0).shift(1).fillna(1.0)
        w = w.mul(scale, axis=0)
    return w


def evaluate(close, w, fund, label, detail=False):
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    ins = bt.metrics(net[net.index < SPLIT], PPY)
    oos = bt.metrics(net[net.index >= SPLIT], PPY)
    full = bt.metrics(net, PPY)
    sc = bt.scaled_metrics(net, 0.40, PPY)
    print(f"{label:<42} IS {ins['sharpe']:5.2f} | OOS {oos['sharpe']:5.2f} | full {full['sharpe']:5.2f} | "
          f"CAGR {full['cagr']*100:6.1f}% | DD {full['max_dd']*100:7.1f}% | at40DD {sc['cagr']*100:6.1f}% | "
          f"turn {r['turnover'].mean():.2f}")
    return net


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)

    print("=== PER-COIN TREND VETO on top of wave3 ===")
    print("veto = zero out a long whose price is below its own MA, a short whose price is above\n")
    base = evaluate(close, wave3_w(close, mask, fund), fund, "wave3 baseline (current live)")
    for n in [20, 50, 100, 200]:
        evaluate(close, wave3_w(close, mask, fund, veto_ma=n), fund, f"+ veto MA{n} (renormalised)")
    print()
    for n in [20, 50]:
        evaluate(close, wave3_w(close, mask, fund, veto_ma=n, renormalize=False), fund,
                 f"+ veto MA{n} (gross shrinks, no renorm)")
    print()
    evaluate(close, wave3_w(close, mask, fund, veto_ma=50, veto_on_shorts=False), fund,
             "+ veto MA50 LONGS ONLY")

    print("\n=== SUB-PERIODS: baseline vs best veto ===")
    for label, w in [("wave3 baseline", wave3_w(close, mask, fund)),
                     ("wave3 + veto MA50", wave3_w(close, mask, fund, veto_ma=50))]:
        net = bt.portfolio_backtest(close.pct_change().fillna(0.0), w, funding=fund,
                                    leverage_cap=1.0, asset_cap=1.0, fee_bps=5.0,
                                    slip_bps=2.0, ppy=PPY)["net"]
        print(f"\n{label}:")
        idx = net.index
        b = np.linspace(0, len(idx), 6).astype(int)
        for j in range(5):
            seg = net.iloc[b[j]:b[j + 1]]
            m = bt.metrics(seg, PPY)
            print(f"   {idx[b[j]].date()} -> {idx[b[j+1]-1].date()}: Sharpe {m['sharpe']:5.2f}  "
                  f"CAGR {m['cagr']*100:7.1f}%  DD {m['max_dd']*100:6.1f}%")

    print("\n=== COST CHECK ===")
    for label, w in [("baseline", wave3_w(close, mask, fund)),
                     ("veto MA50", wave3_w(close, mask, fund, veto_ma=50))]:
        line = f"  {label:<12}"
        for fee, slip in [(5, 2), (10, 5), (20, 10)]:
            r = bt.portfolio_backtest(close.pct_change().fillna(0.0), w, funding=fund,
                                      leverage_cap=1.0, asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=PPY)
            m = bt.metrics(r["net"], PPY)
            line += f"  {fee}+{slip}: Sh {m['sharpe']:.2f}/CAGR {m['cagr']*100:5.1f}%"
        print(line)


if __name__ == "__main__":
    main()
