"""Wave8/V3 sweep: pre-registered in V3_PREREG.md. Research-only; C1/C2 untouched.
Same walk-forward + objective machinery as V2 (F1-F4 select, 2026 reported once).
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

PPY = 365
K = 10
FOLDS = ["2022", "2023", "2024", "2025"]


def run_fold(w, ret, fund, year):
    mask = w.index.year == int(year)
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
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    mom = sz.zs(mom_stack / vol30, mask)
    f7 = fund.rolling(7).mean()
    f14 = fund.rolling(14).mean()
    fz7, fz14 = sz.zs(f7, mask), sz.zs(f14, mask)
    hist = close.notna().cumsum()
    btc = close["BTCUSDT"]
    btc5 = (btc / btc.shift(5) - 1.0).abs()
    attn = btc5 > 0.05
    beta = ret.rolling(60).corr(btc.pct_change()).fillna(1.0)
    tvol = volume / volume.rolling(30).mean().replace(0, np.nan)
    tcnt = np.log1p(ntr.rolling(5).mean())

    S = {}
    for tilt, fz, tag in [(1.5, fz7, "tilt1.5/w7"), (2.0, fz7, "tilt2.0/w7"),
                          (1.5, fz14, "tilt1.5/w14"), (2.0, fz14, "tilt2.0/w14")]:
        S[f"CARRY {tag}"] = lambda fz=fz, tilt=tilt: sz.xs(mom - tilt * fz, mask, k=K)
    for thr in [1.5, 2.0, 2.5]:
        S[f"CARRY extreme |z|>{thr}"] = (
            lambda thr=thr: sz.xs((mom - fz7) * (fz7.abs() > thr).astype(float), mask, k=K))
    for n in [5, 10, 21]:
        young = (hist <= n + 60)
        m5 = close / close.shift(5) - 1.0
        S[f"LIST ride first-{n}d"] = (
            lambda young=young, m5=m5: sz.xs(m5 * young.astype(float), mask, k=K))
        S[f"LIST fade first-{n}d"] = (
            lambda young=young, m5=m5: sz.xs(-m5 * young.astype(float), mask, k=K))
    for thr, tag in [(0.03, "3%"), (0.05, "5%")]:
        S[f"SQZ fade DOWN-{tag}"] = (
            lambda thr=thr: sz.xs((ret <= -thr).astype(float), mask, k=K))
        S[f"SQZ fade UP-{tag}"] = (
            lambda thr=thr: sz.xs((ret >= thr).astype(float) * -1 + 0, mask, k=K))
    # fade-up = short the up-day: score negative on up days
    for thr, tag in [(0.03, "3%"), (0.05, "5%")]:
        S[f"SQZ fade UP-{tag}"] = (
            lambda thr=thr: sz.xs(-(ret >= thr).astype(float), mask, k=K))
    for lb in [1, 3, 5]:
        bl = btc / btc.shift(lb) - 1.0
        cu = beta.mul(bl, axis=0) - (close / close.shift(lb) - 1.0)
        S[f"LEAD attn-gated {lb}d"] = (
            lambda cu=cu: sz.xs(cu * attn.values[:, None].astype(float)
                                if hasattr(attn, "values") else cu, mask, k=K))
    S["ATTN turnover-z"] = lambda: sz.xs(sz.zs(np.log1p(tvol), mask), mask, k=K)
    S["ATTN turnover-z + trend"] = lambda: sz.xs(
        sz.zs(np.log1p(tvol), mask) * ((close / close.shift(30) - 1.0) > 0).astype(float),
        mask, k=K)
    S["ATTN count-z"] = lambda: sz.xs(sz.zs(tcnt, mask), mask, k=K)
    S["ATTN count-z + trend"] = lambda: sz.xs(
        sz.zs(tcnt, mask) * ((close / close.shift(30) - 1.0) > 0).astype(float), mask, k=K)
    # C2-center reference (same construction as live)
    ftilt = mom - fz7
    wref = sz.xs(ftilt, mask, k=K)
    ma200 = btc.rolling(200).mean()
    reg = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=close.index).where(ma200.notna(), 1.0)
    wref = wref.mul(reg, axis=0)
    base = (wref.shift(1) * ret.fillna(0.0).reindex_like(wref)).sum(axis=1)
    rv = base.rolling(90).std() * np.sqrt(365)
    wref = wref.mul((0.20 / rv).clip(upper=2.0).shift(1).fillna(1.0), axis=0)
    S["C2-center-ref"] = lambda: wref

    retf = ret.fillna(0.0)
    print(f"{len(S)} configs x {len(FOLDS)} folds (2026 untouched)\n")
    rows = []
    W = {name: fn() for name, fn in S.items()}
    for name, w in W.items():
        ss, sh, dd, to = [], [], [], []
        for ty in FOLDS:
            s, h, d, t = run_fold(w, retf, fund, ty)
            ss.append(s)
            sh.append(h)
            dd.append(d)
            to.append(t)
        rows.append({"config": name, "score": float(np.mean(ss)),
                     "score_std": float(np.std(ss)), "sharpe": float(np.mean(sh)),
                     "dd": float(np.mean(dd)), "turn": float(np.mean(to)),
                     "folds": " ".join(f"{v:+.2f}" for v in ss)})
    df = pd.DataFrame(rows).sort_values("score", ascending=False)
    df.to_csv(os.path.join(bt.DATA_DIR, "wave8_sweep.csv"), index=False)
    print(df.round(3).to_string(index=False))
    best = df.iloc[0]
    ctr = df[df.config == "C2-center-ref"].iloc[0]
    print(f"\nBest: {best['config']} score {best['score']:.3f} (+/-{best['score_std']:.3f}) "
          f"vs C2-center {ctr['score']:.3f} (+/-{ctr['score_std']:.3f})")
    print("\n=== 2026 UNTOUCHED TEST — reported once, selects nothing ===")
    for name in [best["config"], "C2-center-ref"]:
        s, h, d, t = run_fold(W[name], retf, fund, "2026")
        print(f"  {name}: score {s:+.3f} | Sharpe {h:+.2f} | DD {d*100:.1f}% | turn {t:.3f}")


if __name__ == "__main__":
    main()
