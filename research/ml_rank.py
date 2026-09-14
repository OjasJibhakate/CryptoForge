import os
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")
SPLIT = pd.Timestamp("2024-01-01")
RETRAIN_EVERY = 20
EMBARGO = 6
HORIZON = 5
K = 10


def features(close, funding=None):
    ret = close.pct_change()
    f = {}
    for n in [5, 14, 30, 60, 120]:
        f[f"mom_{n}"] = close / close.shift(n) - 1.0
    for n in [14, 30, 60]:
        f[f"vol_{n}"] = ret.rolling(n).std()
    f["vol_ratio"] = f["vol_14"] / (f["vol_60"] + 1e-9)
    for n in [30, 60]:
        hh = close.rolling(n).max()
        ll = close.rolling(n).min()
        f[f"dist_high_{n}"] = (hh - close) / close
        f[f"dist_low_{n}"] = (close - ll) / close
    delta = close.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    f["rsi_14"] = up / (up + dn + 1e-9)
    vol = close.pct_change().rolling(30).std()
    f["rel_mom_30"] = f["mom_30"] - f["mom_30"].mean(axis=1).values[:, None]
    f["rel_mom_14"] = f["mom_14"] - f["mom_14"].mean(axis=1).values[:, None]
    idx_ret = ret.mean(axis=1)
    f["mkt_mom_5"] = pd.DataFrame(np.tile(idx_ret.rolling(5).sum().values[:, None], (1, close.shape[1])),
                                  index=close.index, columns=close.columns)
    if funding is not None:
        f["funding_7"] = funding.rolling(7).mean().reindex_like(close)
    return f


def build_dataset(close, funding=None):
    feats = features(close, funding)
    fwd = close.shift(-HORIZON) / close - 1.0
    fwd = fwd.sub(fwd.mean(axis=1), axis=0)
    frames = []
    for name, df in feats.items():
        s = df.stack()
        s.name = name
        frames.append(s)
    X = pd.concat(frames, axis=1)
    y = fwd.stack().rename("y")
    data = X.join(y, how="inner").replace([np.inf, -np.inf], np.nan).dropna()
    return data


def walk_forward(close, data):
    dates = data.index.get_level_values(0).unique().sort_values()
    preds = pd.Series(index=data.index, dtype=float)
    model = None
    last_train = None
    params = {"objective": "regression", "learning_rate": 0.05, "num_leaves": 31,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 5,
              "min_data_in_leaf": 100, "verbose": -1}
    for d in dates:
        if d < SPLIT:
            continue
        if model is None or (d - last_train).days >= RETRAIN_EVERY:
            train_dates = dates[(dates < d - pd.Timedelta(days=EMBARGO))]
            mask = data.index.get_level_values(0).isin(train_dates)
            Xtr = data.loc[mask].drop(columns="y")
            ytr = data.loc[mask, "y"]
            model = lgb.train(params, lgb.Dataset(Xtr, label=ytr), num_boost_round=200)
            last_train = d
        day = data.loc[data.index.get_level_values(0) == d]
        if day.empty:
            continue
        preds.loc[day.index] = model.predict(day.drop(columns="y"))
    return preds


def preds_to_weights(close, preds):
    p = preds.unstack()
    p = p.reindex(index=close.index, columns=close.columns)
    ranks = p.rank(axis=1, ascending=False)
    n = p.notna().sum(axis=1)
    long = ranks.le(K)
    short = ranks.gt(n - K, axis=0)
    w = long.astype(float) - short.astype(float)
    gross = w.abs().sum(axis=1).replace(0.0, np.nan)
    return w.div(gross, axis=0).fillna(0.0)


def main():
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()
    close = bt.price_panel(uni, "1d", "close")
    keep = close.columns[close.notna().sum() > 250]
    close = close[keep]
    funding = bt.funding_daily_panel(list(keep), close.index)
    print(f"universe {close.shape[1]} assets, {len(close)} days")
    data = build_dataset(close, funding)
    print(f"dataset rows {len(data)}")
    preds = walk_forward(close, data)
    w = preds_to_weights(close, preds)
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=365)
    net = r["net"]
    oos = bt.metrics(net[net.index >= SPLIT], 365)
    scaled = bt.scaled_metrics(net[net.index >= SPLIT], 0.40, 365)
    print(f"\n=== ML RANKER (OOS {SPLIT.date()}+) ===")
    print(f"Sharpe {oos['sharpe']:.2f} | CAGR {oos['cagr']*100:.1f}% | MaxDD {oos['max_dd']*100:.1f}% | "
          f"at40%DD CAGR {scaled['cagr']*100:.1f}% | turnover {r['turnover'].mean():.3f}")


if __name__ == "__main__":
    main()
