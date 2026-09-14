import os
import sys
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
from strategy_zoo2 import load_full

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 10
HORIZON = 5
EMBARGO = 6
RETRAIN_EVERY = 20
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class MLP(nn.Module):
    def __init__(self, n_in, h1=96, h2=48):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, h1), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(h1, h2), nn.ReLU(),
            nn.Linear(h2, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def build_features(close, volume, qav, tbqav, fund):
    ret = close.pct_change()
    f = {}
    for n in [3, 5, 14, 30, 60, 120]:
        f[f"mom_{n}"] = close / close.shift(n) - 1.0
    for n in [14, 30]:
        f[f"vol_{n}"] = ret.rolling(n).std()
    f["vol_ratio"] = f["vol_14"] / (f["vol_30"] + 1e-9)
    f["rsi_14"] = ret.clip(lower=0).rolling(14).mean() / (ret.abs().rolling(14).mean() + 1e-9)
    hi, lo = close.rolling(60).max(), close.rolling(60).min()
    f["dist_high"] = (hi - close) / close
    f["dist_low"] = (close - lo) / close
    tbr = (tbqav / qav.replace(0, np.nan)).clip(0.2, 0.8)
    f["tbr_5"] = tbr.rolling(5).mean()
    f["tbr_chg"] = tbr.rolling(3).mean() - tbr.rolling(20).mean()
    f["fund_7"] = fund.rolling(7).mean().reindex_like(close)
    f["fund_chg"] = fund.rolling(3).mean().reindex_like(close) - fund.rolling(20).mean().reindex_like(close)
    idx_ret = ret.mean(axis=1)
    f["mkt_mom_5"] = pd.DataFrame(np.tile(idx_ret.rolling(5).sum().to_numpy()[:, None], (1, close.shape[1])),
                                  index=close.index, columns=close.columns)
    f["mkt_vol_30"] = pd.DataFrame(np.tile(ret.mean(axis=1).rolling(30).std().to_numpy()[:, None], (1, close.shape[1])),
                                   index=close.index, columns=close.columns)
    fwd = close.shift(-HORIZON) / close - 1.0
    fwd = fwd.sub(fwd.mean(axis=1), axis=0)
    return f, fwd


def to_matrix(f, fwd):
    names = list(f.keys())
    stacked = [f[n].stack() for n in names]
    X = pd.concat(stacked, axis=1)
    X.columns = names
    y = fwd.stack().rename("y")
    data = X.join(y, how="inner").replace([np.inf, -np.inf], np.nan).dropna()
    dates = data.index.get_level_values(0)
    return data, names, dates


def main():
    t0 = time.time()
    close, volume, high, low, qav, tbqav, ntr = load_full()
    fund = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    f, fwd = build_features(close, volume, qav, tbqav, fund)
    data, names, dates = to_matrix(f, fwd)
    print(f"device {DEVICE} | torch {torch.__version__} | "
          f"{torch.cuda.get_device_name(0) if DEVICE=='cuda' else 'cpu'}")
    print(f"dataset {data.shape[0]:,} rows x {len(names)} features | build {time.time()-t0:.1f}s")

    Xall = data[names].to_numpy(np.float32)
    yall = data["y"].to_numpy(np.float32)
    uniq = np.array(sorted(set(dates)))
    day_index = pd.Series(np.arange(len(uniq)), index=uniq)
    didx = day_index.loc[dates].to_numpy()

    split_d = day_index.loc[SPLIT]
    preds = np.full(len(data), np.nan, np.float32)
    model = None
    last_train = -10 ** 9
    n_retrain = 0
    tt = time.time()

    for d in range(int(split_d), len(uniq)):
        if d - last_train >= RETRAIN_EVERY:
            train_mask = didx < (d - EMBARGO)
            Xtr = torch.from_numpy(Xall[train_mask]).to(DEVICE)
            ytr = torch.from_numpy(yall[train_mask]).to(DEVICE)
            model = MLP(Xall.shape[1]).to(DEVICE)
            opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
            lossf = nn.MSELoss()
            model.train()
            n = Xtr.shape[0]
            bs = 16384
            for epoch in range(4):
                perm = torch.randperm(n, device=DEVICE)
                for i in range(0, n, bs):
                    b = perm[i:i + bs]
                    opt.zero_grad()
                    out = model(Xtr[b])
                    loss = lossf(out, ytr[b])
                    loss.backward()
                    opt.step()
            model.eval()
            last_train = d
            n_retrain += 1
        cur = didx == d
        if cur.sum() == 0:
            continue
        with torch.no_grad():
            xb = torch.from_numpy(Xall[cur]).to(DEVICE)
            preds[cur] = model(xb).cpu().numpy()

    train_secs = time.time() - tt
    print(f"walk-forward: {n_retrain} retrains in {train_secs:.1f}s "
          f"({train_secs/max(n_retrain,1):.2f}s per retrain)")

    valid = ~np.isnan(preds)
    pred_df = pd.Series(preds[valid], index=pd.MultiIndex.from_arrays(
        [dates[valid], data.index.get_level_values(1)[valid]]))
    scores = pred_df.unstack()
    scores = scores.reindex(index=close.index, columns=close.columns)

    def xs_w(score, k=K):
        s = score.copy()
        ranks = s.rank(axis=1, ascending=False)
        n = s.notna().sum(axis=1)
        kk = np.minimum(k, (n // 2).clip(lower=1))
        long = ranks.le(kk, axis=0).astype(float)
        short = ranks.gt(n - kk, axis=0).astype(float)
        w = long - short
        return w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)

    w = xs_w(scores)
    ret = close.pct_change().fillna(0.0)

    # rank IC: does the model actually rank forward returns?
    fwd5 = close.shift(-HORIZON) / close - 1.0
    ics = []
    for d in scores.index:
        if d not in fwd5.index:
            continue
        a = scores.loc[d]
        b = fwd5.loc[d]
        j = pd.concat([a, b], axis=1).dropna()
        if len(j) > 10:
            ics.append(j.iloc[:, 0].corr(j.iloc[:, 1], method="spearman"))
    ics = pd.Series(ics).dropna()
    print(f"\nrank IC (pred vs realized fwd {HORIZON}d): mean {ics.mean():+.4f}  "
          f"t-stat {ics.mean()/ics.std()*np.sqrt(len(ics)):+.2f}  n={len(ics)}")
    print(f"  IC>0 on {(ics>0).mean()*100:.1f}% of days (50% = no skill)")

    r = bt.portfolio_backtest(ret, w, funding=None, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    o = bt.metrics(net[net.index >= SPLIT], PPY)
    sc = bt.scaled_metrics(net[net.index >= SPLIT], 0.40, PPY)
    print(f"\n=== GPU MLP RANKER (daily rebalance, OOS {SPLIT.date()}+) ===")
    print(f"Sharpe {o['sharpe']:.2f} | CAGR {o['cagr']*100:.1f}% | MaxDD {o['max_dd']*100:.1f}% | turnover {r['turnover'].mean():.3f}")

    # hold HORIZON days (match the label horizon)
    reb = np.zeros(len(close), dtype=bool)
    reb[::HORIZON] = True
    w5 = w.copy()
    w5.loc[~reb, :] = np.nan
    w5 = w5.ffill().fillna(0.0)
    r5 = bt.portfolio_backtest(ret, w5, funding=None, leverage_cap=1.0, asset_cap=1.0,
                               fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    o5 = bt.metrics(r5["net"][r5["net"].index >= SPLIT], PPY)
    print(f"=== same model, holding {HORIZON} days ===")
    print(f"Sharpe {o5['sharpe']:.2f} | CAGR {o5['cagr']*100:.1f}% | MaxDD {o5['max_dd']*100:.1f}% | turnover {r5['turnover'].mean():.3f}")
    print(f"\nreference: plain momentum OOS Sharpe ~1.59; this model on the same window is {'better' if o['sharpe']>1.59 else 'WORSE'}.")


if __name__ == "__main__":
    main()
