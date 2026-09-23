"""V2 sweep: pre-registered in V2_PREREG.md. Research-only; never touches C1/C2.

One-factor-at-a-time from the C2 center + 12 pre-declared pairs, scored on
walk-forward test folds F1-F4 (2026 reported once, never selects).
Objective: Sharpe - 1.5*|MaxDD| - 2.0*turnover - 0.5*top5_share (test folds).
"""
import os
import sys
import itertools
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

PPY = 365
FOLDS = [(("2019", "2021"), "2022"), (("2020", "2022"), "2023"),
         (("2021", "2023"), "2024"), (("2022", "2024"), "2025")]
FINAL = ((("2023", "2025")), "2026")

WINDOWS = {"center": (14, 21, 30, 45, 60), "short": (7, 14, 21),
           "medium": (21, 30, 45), "long": (45, 60, 90, 120)}


def mom_score(close, vol30, mask, window, weighting, vol_adj):
    lbs = WINDOWS[window]
    parts = []
    for i, lb in enumerate(lbs):
        m = close / close.shift(lb) - 1.0
        w = (len(lbs) - i) if weighting == "recency" else 1.0
        parts.append(m * w)
    stack = sum(parts) / sum((len(lbs) - i) if weighting == "recency" else 1.0
                             for i in range(len(lbs)))
    if vol_adj:
        stack = stack / vol30
    return sz.zs(stack, mask)


def build_weights(D, p):
    close, mask, fund = D["close"], D["mask"], D["fund"]
    vol30 = close.pct_change().rolling(30).std()
    mom = mom_score(close, vol30, mask, p["window"], p["weighting"], p["vol_adj"])
    f7 = fund.rolling(p["fz_win"]).mean()
    fz = sz.zs(f7, mask).clip(-2, 2) if p["winsor"] else sz.zs(f7, mask)
    score = mom - p["tilt"] * fz
    w = sz.xs(score, mask, k=p["k"])
    if p["volweight"]:
        w = w.mul(1 / vol30.reindex_like(w).replace(0, np.nan), axis=0)
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    if p["regime"]:
        w = w.mul(D["regime"], axis=0)
    if p["risk"] == "rm":
        ret = close.pct_change()
        base = (w.shift(1) * ret.fillna(0.0).reindex_like(w)).sum(axis=1)
        rv = base.rolling(90).std() * np.sqrt(365)
        rm = (0.20 / rv).clip(upper=2.0).shift(1).fillna(1.0)
        w = w.mul(rm, axis=0)
    return w


def run_fold(w, ret, fund, p, test_year):
    idx = w.index
    mask = idx.year == int(test_year)
    r = bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"][mask]
    m = bt.metrics(net, PPY)
    held = w.shift(1).fillna(0.0)[mask]
    gross = held.abs().sum(axis=1).replace(0, np.nan)
    shr = held.div(gross, axis=0).abs().max(axis=1)
    top5 = float(np.nanmean(shr.values.astype(float)) * 5) if len(shr.dropna()) else 0.0
    score = m["sharpe"] - 1.5 * abs(m["max_dd"]) - 2.0 * r["turnover"][mask].mean() - 0.5 * top5
    return score, m["sharpe"], m["max_dd"], r["turnover"][mask].mean()


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    btc = close["BTCUSDT"]
    ma200 = btc.rolling(200).mean()
    regime = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=close.index).where(ma200.notna(), 1.0)
    D = dict(close=close, mask=mask, fund=fund, regime=regime)
    ret = close.pct_change().fillna(0.0)

    center = dict(window="center", weighting="equal", vol_adj=True, tilt=1.0,
                  fz_win=7, winsor=False, k=10, volweight=False, regime=True, risk="rm")
    configs = {"C2-center": center}
    for win in ["short", "medium", "long"]:
        configs[f"L1 window={win}"] = dict(center, window=win)
    configs["L1 weighting=recency"] = dict(center, weighting="recency")
    configs["L1 return-only"] = dict(center, vol_adj=False)
    for tilt in [0.0, 0.5]:
        configs[f"L2 tilt={tilt}"] = dict(center, tilt=tilt)
    configs["L2 fz_win=14"] = dict(center, fz_win=14)
    configs["L2 winsorized"] = dict(center, winsor=True)
    for k in [5, 15]:
        configs[f"L3 k={k}"] = dict(center, k=k)
    configs["L3 vol-weighted"] = dict(center, volweight=True)
    configs["L4 no-risk"] = dict(center, risk="none")
    pairs = [("tilt0.5", dict(center, tilt=0.5)), ("k5", dict(center, k=5))]
    configs["P tilt0.5+k5"] = dict(center, tilt=0.5, k=5)
    configs["P tilt0.5+medium"] = dict(center, tilt=0.5, window="medium")
    configs["P tilt0+fwd-neutral"] = dict(center, tilt=0.0)
    configs["P short+recency"] = dict(center, window="short", weighting="recency")
    configs["P k15+notilt"] = dict(center, k=15, tilt=0.0)
    configs["P k5+volw"] = dict(center, k=5, volweight=True)
    configs["P medium+fz14"] = dict(center, window="medium", fz_win=14)
    configs["P long+notilt"] = dict(center, window="long", tilt=0.0)
    configs["P recency+winsor"] = dict(center, weighting="recency", winsor=True)
    configs["P k15+regime-off"] = dict(center, k=15, regime=False)
    configs["P short+k5"] = dict(center, window="short", k=5)
    configs["P norisk+k15"] = dict(center, risk="none", k=15)
    print(f"{len(configs)} configs x {len(FOLDS)} folds (2026 untouched)\n")

    W = {name: build_weights(D, p) for name, p in configs.items()
         } if False else {}
    rows = []
    for name, p in configs.items():
        w = build_weights(D, p)
        ss, sh, dd, to = [], [], [], []
        for (d0, d1), ty in FOLDS:
            s, h, d, t = run_fold(w, ret, fund, p, ty)
            ss.append(s)
            sh.append(h)
            dd.append(d)
            to.append(t)
        rows.append({"config": name, "score": float(np.mean(ss)),
                     "score_std": float(np.std(ss)), "sharpe": float(np.mean(sh)),
                     "dd": float(np.mean(dd)), "turn": float(np.mean(to)),
                     "folds": " ".join(f"{v:+.2f}" for v in ss)})
    df = pd.DataFrame(rows).sort_values("score", ascending=False)
    df.to_csv(os.path.join(bt.DATA_DIR, "v2_sweep.csv"), index=False)
    print(df.round(3).to_string(index=False))
    best = df.iloc[0]
    ctr = df[df.config == "C2-center"].iloc[0]
    print(f"\nBest: {best['config']} score {best['score']:.3f} (+/-{best['score_std']:.3f}) "
          f"vs C2-center {ctr['score']:.3f} (+/-{ctr['score_std']:.3f})")

    print("\n=== 2026 UNTOUCHED TEST — reported once, selects nothing ===")
    for name in [best["config"], "C2-center"]:
        p = configs[name]
        w = build_weights(D, p)
        s, h, d, t = run_fold(w, ret, fund, p, "2026")
        print(f"  {name}: score {s:+.3f} | Sharpe {h:+.2f} | DD {d*100:.1f}% | turn {t:.3f}")


if __name__ == "__main__":
    main()
