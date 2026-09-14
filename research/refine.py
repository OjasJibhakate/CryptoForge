import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")
SPLIT = pd.Timestamp("2024-01-01")


def load_panel(interval="1d", min_hist=250, max_assets=None):
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()
    if max_assets:
        uni = uni[:max_assets]
    close = bt.price_panel(uni, interval, "close")
    keep = close.columns[close.notna().sum() > min_hist]
    return close[keep]


def xs_weights(close, lookback=30, skip=0, k=5, weight="equal", vol_lookback=30,
               risk_adj=False, long_short=True):
    ret = close.pct_change()
    vol = ret.rolling(vol_lookback).std()
    mom = close.shift(skip) / close.shift(skip + lookback) - 1.0
    score = (mom / vol) if risk_adj else mom
    score = score.replace([np.inf, -np.inf], np.nan)
    ranks = score.rank(axis=1, ascending=False)
    n = score.notna().sum(axis=1)
    kk = np.minimum(k, (n // 2).clip(lower=1))
    long = ranks.le(kk, axis=0)
    if long_short:
        short = ranks.gt(n - kk, axis=0)
    else:
        short = pd.DataFrame(False, index=score.index, columns=score.columns)
    w = long.astype(float) - short.astype(float)
    if weight == "invvol":
        iv = (1.0 / vol).replace([np.inf, -np.inf], np.nan)
        w = w * iv
    gross = w.abs().sum(axis=1).replace(0.0, np.nan)
    return w.div(gross, axis=0).fillna(0.0)


def evaluate(close, w, ppy=365):
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=ppy)
    net = r["net"]
    ins = bt.metrics(net[net.index < SPLIT], ppy)
    oos = bt.metrics(net[net.index >= SPLIT], ppy)
    full = bt.metrics(net, ppy)
    scaled = bt.scaled_metrics(net, 0.40, ppy)
    return {"is_sharpe": ins["sharpe"], "oos_sharpe": oos["sharpe"], "full_sharpe": full["sharpe"],
            "oos_cagr": oos["cagr"] * 100, "full_dd": full["max_dd"] * 100,
            "at40dd_cagr": scaled["cagr"] * 100, "scale": scaled["scale"],
            "turnover": r["turnover"].mean()}


def main():
    close = load_panel("1d", min_hist=250)
    print(f"universe: {close.shape[1]} assets, {len(close)} days "
          f"{close.index.min().date()} -> {close.index.max().date()}")
    rows = []
    for lb in [14, 21, 30, 45, 60, 90]:
        for k in [3, 5, 10, 20]:
            for ra in [False, True]:
                for wmode in ["equal", "invvol"]:
                    w = xs_weights(close, lookback=lb, k=k, weight=wmode, risk_adj=ra)
                    m = evaluate(close, w)
                    m.update({"lookback": lb, "k": k, "risk_adj": ra, "weight": wmode})
                    rows.append(m)
    df = pd.DataFrame(rows)
    cols = ["lookback", "k", "risk_adj", "weight", "is_sharpe", "oos_sharpe",
            "full_sharpe", "oos_cagr", "full_dd", "at40dd_cagr", "scale", "turnover"]
    df = df[cols]
    print("\n=== TOP BY OOS SHARPE (untouched 2024+) ===")
    print(df.sort_values("oos_sharpe", ascending=False).head(15).round(2).to_string(index=False))
    print("\n=== PLATEAU BY LOOKBACK (mean oos_sharpe across k/weight) ===")
    print(df.groupby("lookback")[["is_sharpe", "oos_sharpe", "at40dd_cagr", "turnover"]].mean().round(2).to_string())
    df.to_csv(os.path.join(bt.DATA_DIR, "xs_refine.csv"), index=False)
    return df


if __name__ == "__main__":
    main()
