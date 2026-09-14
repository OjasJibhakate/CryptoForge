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
from gpu_model import MLP, build_features, to_matrix

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 10
HORIZON = 5
EMBARGO = 6
RETRAIN_EVERY = 40
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def run_width(Xall, yall, didx, widths):
    uniq = np.unique(didx)
    split_d = np.searchsorted(uniq, np.searchsorted(uniq, 0))  # placeholder
    # map SPLIT via date index passed in externally
    return uniq


def evaluate(Xall, yall, didx, n_uniq, split_d, h1, h2):
    preds = np.full(len(yall), np.nan, np.float32)
    model = None
    last = -10 ** 9
    t0 = time.time()
    for d in range(split_d, n_uniq):
        if d - last >= RETRAIN_EVERY:
            m = didx < (d - EMBARGO)
            Xtr = torch.from_numpy(Xall[m]).to(DEVICE)
            ytr = torch.from_numpy(yall[m]).to(DEVICE)
            model = MLP(Xall.shape[1], h1, h2).to(DEVICE)
            opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
            lossf = nn.MSELoss()
            model.train()
            n = Xtr.shape[0]
            bs = 16384
            for _ in range(4):
                perm = torch.randperm(n, device=DEVICE)
                for i in range(0, n, bs):
                    b = perm[i:i + bs]
                    opt.zero_grad()
                    lossf(model(Xtr[b]), ytr[b]).backward()
                    opt.step()
            model.eval()
            last = d
        cur = didx == d
        if cur.sum() == 0:
            continue
        with torch.no_grad():
            preds[cur] = model(torch.from_numpy(Xall[cur]).to(DEVICE)).cpu().numpy()
    secs = time.time() - t0
    n_params = sum(p.numel() for p in model.parameters())
    return preds, n_params, secs


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    fund = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    f, fwd = build_features(close, volume, qav, tbqav, fund)
    data, names, dates = to_matrix(f, fwd)
    Xall = data[names].to_numpy(np.float32)
    yall = data["y"].to_numpy(np.float32)
    uniq = np.array(sorted(set(dates)))
    day_index = pd.Series(np.arange(len(uniq)), index=uniq)
    didx = day_index.loc[dates].to_numpy()
    split_d = int(day_index.loc[SPLIT])
    ret = close.pct_change().fillna(0.0)
    fwd5 = close.shift(-HORIZON) / close - 1.0

    print(f"device {DEVICE} | {len(yall):,} rows | {len(names)} features")
    print(f"hypothesis: 'bigger model = smarter'. Testing capacity scaling.\n")
    print(f"{'arch':<16} {'params':>10} {'train_s':>8} {'OOS Sharpe':>11} {'rank IC':>9} {'IC t':>7}")

    for h1, h2 in [(8, 4), (32, 16), (128, 64), (512, 256), (1024, 512)]:
        preds, n_params, secs = evaluate(Xall, yall, didx, len(uniq), split_d, h1, h2)
        valid = ~np.isnan(preds)
        s = pd.Series(preds[valid], index=pd.MultiIndex.from_arrays(
            [dates[valid], data.index.get_level_values(1)[valid]])).unstack()
        s = s.reindex(index=close.index, columns=close.columns)
        ranks = s.rank(axis=1, ascending=False)
        n = s.notna().sum(axis=1)
        kk = np.minimum(K, (n // 2).clip(lower=1))
        w = (ranks.le(kk, axis=0).astype(float) - ranks.gt(n - kk, axis=0).astype(float))
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        r = bt.portfolio_backtest(ret, w, funding=None, leverage_cap=1.0, asset_cap=1.0,
                                  fee_bps=5.0, slip_bps=2.0, ppy=PPY)
        o = bt.metrics(r["net"][r["net"].index >= SPLIT], PPY)
        ics = []
        for d in s.index:
            if d not in fwd5.index:
                continue
            j = pd.concat([s.loc[d], fwd5.loc[d]], axis=1).dropna()
            if len(j) > 10:
                ics.append(j.iloc[:, 0].corr(j.iloc[:, 1], method="spearman"))
        ics = pd.Series(ics).dropna()
        t = ics.mean() / ics.std() * np.sqrt(len(ics))
        print(f"{h1:>4}-{h2:<4}      {n_params:>10,} {secs:>8.1f} {o['sharpe']:>11.2f} "
              f"{ics.mean():>9.4f} {t:>7.2f}")

    print("\nreference: plain momentum OOS Sharpe ~1.59 | random would be ~0 minus costs")


if __name__ == "__main__":
    main()
