import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")


def harvest_weights(funding, lookback=3, max_assets=10, min_rate=0.0):
    f = funding.rolling(lookback).mean()
    elig = (f > min_rate) & f.notna()
    if max_assets is not None:
        ranks = f.where(elig).rank(axis=1, ascending=False)
        elig = ranks.le(max_assets)
    w = elig.astype(float)
    gross = w.sum(axis=1).replace(0.0, np.nan)
    w = w.div(gross, axis=0).fillna(0.0)
    return w


def funding_harvest(funding, lookback=3, max_assets=10, min_rate=0.0,
                    fee_bps=5.0, slip_bps=2.0, spread_legs=2):
    w = harvest_weights(funding, lookback, max_assets, min_rate)
    w_held = w.shift(1).fillna(0.0)
    gross_ret = (w_held * funding.reindex_like(w_held).fillna(0.0)).sum(axis=1)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    cost = turnover * spread_legs * (fee_bps + slip_bps) / 1e4
    net = gross_ret - cost
    return net, w


if __name__ == "__main__":
    interval = "1d"
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()[:45]
    close = bt.price_panel(uni, interval, "close")
    keep = close.columns[close.notna().sum() > 250]
    funding = bt.funding_daily_panel(list(keep), close.loc[:, keep].index)
    print(f"funding panel: {funding.shape}, non-zero {int((funding != 0).sum().sum())}")

    ppy = 365
    rows = []
    for lb in [1, 3, 7]:
        for ma in [5, 10, 20]:
            for mr in [-0.001, 0.0, 0.0005]:
                net, w = funding_harvest(funding, lookback=lb, max_assets=ma, min_rate=mr)
                m = bt.metrics(net, ppy)
                sm = bt.scaled_metrics(net, 0.40, ppy)
                rows.append({"lookback": lb, "max_assets": ma, "min_rate": mr,
                             "sharpe": m["sharpe"], "cagr": m["cagr"], "maxdd": m["max_dd"],
                             "at40dd": sm["cagr"], "scale": sm["scale"]})
    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(df.round(3).to_string(index=False))
    df.to_csv(os.path.join(bt.DATA_DIR, "carry_sweep.csv"), index=False)

    best = df.iloc[0]
    net, w = funding_harvest(funding, lookback=int(best["lookback"]),
                             max_assets=int(best["max_assets"]), min_rate=float(best["min_rate"]))
    idx = net.index
    bounds = np.linspace(0, len(idx), 6).astype(int)
    print(f"\nBest carry sub-periods: lb={int(best['lookback'])} ma={int(best['max_assets'])} mr={best['min_rate']}")
    for i in range(5):
        seg = net.iloc[bounds[i]:bounds[i + 1]]
        m = bt.metrics(seg, ppy)
        print(f"  {idx[bounds[i]].date()} -> {idx[bounds[i+1]-1].date()}: "
              f"CAGR {m['cagr']*100:7.2f}%  Sharpe {m['sharpe']:5.2f}  MaxDD {m['max_dd']*100:6.2f}%")
