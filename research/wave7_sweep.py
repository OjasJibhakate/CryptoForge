"""Wave 7 sweep: fresh hypotheses from literature + market-structure reasoning.

Families (all same panel/costs/split: IS=<2024 select, OOS=>=2024 judge):
  SQZ  short-squeeze continuation (high funding + rising OI + rally -> chase)
  SES  session-momentum timing (US-open drift, Asia-range breakout proxy)
  LOT  lottery revisited (MAX, skewness, fresh-high chasing WITH trend filter)
  VAL  deep-value (far-from-high + funding washed out + seller exhaustion)
  CTR  CTREND-style multi-horizon trend aggregation (MA-spread stack)
  IVO  idiosyncratic-vol pricing (high residual vol longs)
  LVO  low-vol revisited in recent regime only (2022+ formation)
  BETA beta anomaly (low-beta longs, high-beta shorts)
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

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 10


def ev(name, w, ret, fund):
    r = bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    sc = bt.scaled_metrics(net, 0.40, PPY)
    return {"strategy": name,
            "is": bt.metrics(net[net.index < SPLIT], PPY)["sharpe"],
            "oos": bt.metrics(net[net.index >= SPLIT], PPY)["sharpe"],
            "full": bt.metrics(net, PPY)["sharpe"],
            "cagr": bt.metrics(net, PPY)["cagr"] * 100,
            "dd": bt.metrics(net, PPY)["max_dd"] * 100,
            "at40dd": sc["cagr"] * 100, "scale": sc["scale"],
            "turn": r["turnover"].mean()}


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    rng = (high - low) / close.replace(0, np.nan)
    dvol = close * volume

    f7 = fund.rolling(7).mean()
    fz = sz.zs(f7, mask)
    tbr = (tbqav / qav.replace(0, np.nan)).clip(0.2, 0.8)
    tbr_chg = tbr.rolling(3).mean() - tbr.rolling(20).mean()

    btc = close["BTCUSDT"] if "BTCUSDT" in close.columns else close.mean(axis=1)
    btc_ret = btc.pct_change()
    beta = ret.rolling(60).corr(btc_ret).fillna(1.0)
    resid = ret.sub(beta.mul(btc_ret, axis=0), axis=0)
    ivol = resid.rolling(30).std()

    S = {}
    # ---- SQZ: crowded shorts + rising OI + price already rallying -> chase ----
    oi_proxy = (tbqav / qav.replace(0, np.nan))
    for fz_thr, lb in [(1.5, 7), (2.0, 7), (1.5, 14)]:
        mom = close / close.shift(lb) - 1.0
        sc = ((fz > fz_thr) & (mom > 0)).astype(float) * mom
        S[f"SQZ squeeze-chase fz>{fz_thr} {lb}d"] = (
            lambda sc=sc: sz.xs(sc, mask, k=K))
    # squeeze reversal: fade the exhausted squeeze (crowded + stalled)
    mom5 = close / close.shift(5) - 1.0
    S["SQZ fade exhausted squeeze"] = lambda: sz.xs(
        ((fz > 2.0) & (mom5 < 0)).astype(float) * (-mom5), mask, k=K)

    # ---- SES: session proxies on daily bars ----
    # overnight-vs-day split: (open~prev close -> today's range position)
    daypos = (close - low) / (high - low).replace(0, np.nan)
    S["SES chase strong daily closes"] = lambda: sz.xs(daypos.rolling(5).mean(), mask, k=K)
    S["SES fade weak daily closes"] = lambda: sz.xs(
        (1 - daypos).rolling(5).mean() * -1, mask, k=K)
    # range expansion continuation
    S["SES range-expansion chase"] = lambda: sz.xs(
        (rng / rng.rolling(30).mean().replace(0, np.nan)).rolling(3).mean()
        * (close / close.shift(3) - 1.0), mask, k=K)

    # ---- LOT revisited ----
    max20 = ret.rolling(20).max()
    S["LOT short high-MAX"] = lambda: sz.xs(-max20, mask, k=K)
    S["LOT short high-MAX + uptrend only"] = lambda: sz.xs(
        -max20 * ((close / close.shift(60) - 1.0) > 0).astype(float), mask, k=K)
    S["LOT short positive skew"] = lambda: sz.xs(-ret.rolling(20).skew(), mask, k=K)
    hi60 = close.rolling(60).max()
    S["LOT fade fresh 60d highs"] = lambda: sz.xs(
        -((close >= hi60 * 0.995).astype(float) * (close / close.shift(20) - 1.0)), mask, k=K)

    # ---- VAL: deep value + washed-out funding + seller exhaustion ----
    dist_hi = close / hi60
    for q in [0.3, 0.5]:
        qual = (dist_hi <= dist_hi.quantile(q, axis=1).values[:, None])
        S[f"VAL deep-value q{int(q*100)}"] = (
            lambda qual=qual: sz.xs(qual.astype(float) * -(close / close.shift(30) - 1.0),
                                    mask, k=K))
    S["VAL washed-out funding longs"] = lambda: sz.xs(
        ((fz < -1.5) & (mom5 < -0.05)).astype(float) * (-mom5), mask, k=K)
    S["VAL seller exhaustion (vol dries after fall)"] = lambda: sz.xs(
        ((close / close.shift(20) - 1.0 < -0.15)
         & (volume < volume.rolling(30).mean())).astype(float), mask, k=K)

    # ---- CTR: CTREND-style multi-horizon MA-spread stack ----
    ctrend = sum((close - close.rolling(n).mean()) / close.rolling(n).std().replace(0, np.nan)
                 for n in (5, 10, 20, 40, 60)) / 5.0
    S["CTR MA-spread stack"] = lambda: sz.xs(ctrend, mask, k=K)
    S["CTR stack + volume weight"] = lambda: sz.xs(
        ctrend * np.log1p(volume / volume.rolling(30).mean().replace(0, np.nan)), mask, k=K)

    # ---- IVO / LVO / BETA ----
    S["IVO long high idiosyncratic vol"] = lambda: sz.xs(ivol, mask, k=K)
    S["IVO high ivol + trend filter"] = lambda: sz.xs(
        ivol * ((close / close.shift(30) - 1.0) > 0).astype(float), mask, k=K)
    S["LVO long low vol (full sample)"] = lambda: sz.xs(-vol30, mask, k=K)
    S["BETA long low beta"] = lambda: sz.xs(-beta, mask, k=K)
    S["BETA high beta + uptrend"] = lambda: sz.xs(
        beta * ((close / close.shift(30) - 1.0) > 0).astype(float), mask, k=K)

    # ---- OFI change (fresh leg, not the level tested in wave 2) ----
    S["OFI change 3v20 (retest)"] = lambda: sz.xs(
        sz.zs(tbr_chg, mask), mask, k=K)

    print(f"panel {close.shape[1]} symbols x {len(close)} days | {len(S)} signals\n")
    rows = []
    for name, fn in S.items():
        try:
            rows.append(ev(name, fn(), ret.fillna(0.0), fund))
        except Exception as e:
            print(f"  !! {name}: {e}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(bt.DATA_DIR, "wave7_sweep.csv"), index=False)
    cols = ["strategy", "is", "oos", "full", "cagr", "dd", "at40dd", "scale", "turn"]
    print("=== ranked by IN-SAMPLE (select here; judge on OOS) ===")
    print(df.sort_values("is", ascending=False).head(20)[cols].round(2).to_string(index=False))
    print("\n=== TOP 15 BY OOS (>=2024) ===")
    print(df.sort_values("oos", ascending=False).head(15)[cols].round(2).to_string(index=False))
    print("\n=== CONSISTENT: IS>0.5 AND OOS>0.5 ===")
    good = df[(df["is"] > 0.5) & (df["oos"] > 0.5)].sort_values("oos", ascending=False)
    print(good[cols].round(2).to_string(index=False) if len(good) else "  none")


if __name__ == "__main__":
    main()
