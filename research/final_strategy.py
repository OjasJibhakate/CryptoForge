import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import strategies as st

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")
SPLIT = pd.Timestamp("2024-01-01")


def load():
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()
    close = bt.price_panel(uni, "1d", "close")
    keep = close.columns[close.notna().sum() > 250]
    return close[keep]


def xs_variant(close, lookback, k=10, risk_adj=True):
    ret = close.pct_change()
    vol = ret.rolling(30).std()
    mom = close / close.shift(lookback) - 1.0
    score = (mom / vol) if risk_adj else mom
    score = score.replace([np.inf, -np.inf], np.nan)
    ranks = score.rank(axis=1, ascending=False)
    n = score.notna().sum(axis=1)
    kk = np.minimum(k, (n // 2).clip(lower=1))
    long = ranks.le(kk, axis=0)
    short = ranks.gt(n - kk, axis=0)
    w = long.astype(float) - short.astype(float)
    gross = w.abs().sum(axis=1).replace(0.0, np.nan)
    return w.div(gross, axis=0).fillna(0.0)


def ensemble(close, lookbacks=(14, 21, 30, 45, 60), k=10):
    ws = [xs_variant(close, lb, k=k, risk_adj=True) for lb in lookbacks]
    return sum(ws) / len(ws)


def run():
    close = load()
    ret = close.pct_change().fillna(0.0)
    ppy = 365

    w = ensemble(close)
    r = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=ppy)
    net = r["net"]

    print(f"universe {close.shape[1]} assets | {close.index.min().date()} -> {close.index.max().date()}")
    ins = bt.metrics(net[net.index < SPLIT], ppy)
    oos = bt.metrics(net[net.index >= SPLIT], ppy)
    full = bt.metrics(net, ppy)
    scaled = bt.scaled_metrics(net, 0.40, ppy)
    print(f"\nENSEMBLE XS MOMENTUM (lb 14-60, k=10, risk-adj, dollar-neutral, daily rebalance)")
    print(f"  IS   Sharpe {ins['sharpe']:.2f}  CAGR {ins['cagr']*100:6.1f}%  MaxDD {ins['max_dd']*100:6.1f}%")
    print(f"  OOS  Sharpe {oos['sharpe']:.2f}  CAGR {oos['cagr']*100:6.1f}%  MaxDD {oos['max_dd']*100:6.1f}%")
    print(f"  FULL Sharpe {full['sharpe']:.2f}  CAGR {full['cagr']*100:6.1f}%  MaxDD {full['max_dd']*100:6.1f}%")
    print(f"  -> to hit 40% DD use {scaled['scale']:.2f}x leverage: CAGR {scaled['cagr']*100:.1f}% "
          f"(DD {scaled['max_dd']*100:.1f}%)")
    print(f"  turnover/day {r['turnover'].mean():.3f}")

    print("\n  SUB-PERIOD ROBUSTNESS:")
    idx = net.index
    bounds = np.linspace(0, len(idx), 6).astype(int)
    for i in range(5):
        seg = net.iloc[bounds[i]:bounds[i + 1]]
        m = bt.metrics(seg, ppy)
        print(f"    {idx[bounds[i]].date()} -> {idx[bounds[i+1]-1].date()}: "
              f"Sharpe {m['sharpe']:5.2f}  CAGR {m['cagr']*100:7.1f}%  MaxDD {m['max_dd']*100:6.1f}%")

    print("\n  COST SENSITIVITY (full period):")
    for fee, slip in [(2, 1), (5, 2), (10, 5), (20, 10)]:
        rr = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=ppy)
        m = bt.metrics(rr["net"], ppy)
        print(f"    fee {fee}+{slip} bps: Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:6.1f}%")

    equity = (1 + net).cumprod()
    out = pd.DataFrame({"equity": equity, "net_ret": net})
    out.to_csv(os.path.join(bt.DATA_DIR, "ensemble_equity.csv"))
    print("\n  equity curve saved -> research/data/ensemble_equity.csv")
    return net, close


if __name__ == "__main__":
    run()
