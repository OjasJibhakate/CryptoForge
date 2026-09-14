import os
import sys
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 10


def load_all4():
    closes, vols, highs, lows = {}, {}, {}, {}
    for path in glob.glob(os.path.join(bt.DATA_DIR, "*_1d.csv")):
        sym = os.path.basename(path)[:-7]
        if not sym.endswith("USDT") or "SETTLED" in sym:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "close" not in df.columns or len(df) < 60:
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        closes[sym] = pd.to_numeric(df["close"], errors="coerce")
        vols[sym] = pd.to_numeric(df["volume"], errors="coerce")
        highs[sym] = pd.to_numeric(df["high"], errors="coerce") if "high" in df.columns else pd.to_numeric(df["close"], errors="coerce")
        lows[sym] = pd.to_numeric(df["low"], errors="coerce") if "low" in df.columns else pd.to_numeric(df["close"], errors="coerce")
    close = pd.DataFrame(closes).sort_index()
    return close, pd.DataFrame(vols).reindex(close.index), pd.DataFrame(highs).reindex(close.index), pd.DataFrame(lows).reindex(close.index)


def pit_mask(close, volume, top_n=60, min_adv=5e6, min_hist=60, adv_window=30):
    adv = (close * volume).rolling(adv_window).mean()
    hist = close.notna().cumsum()
    elig = (adv >= min_adv) & (hist >= min_hist) & close.notna()
    return (adv.where(elig).rank(axis=1, ascending=False).le(top_n) & elig).fillna(False)


def zs(df, mask=None):
    if mask is not None:
        df = df.where(mask)
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def xs(score, mask, k=K, normalize=True):
    s = score.where(mask).replace([np.inf, -np.inf], np.nan)
    ranks = s.rank(axis=1, ascending=False)
    n = s.notna().sum(axis=1)
    kk = np.minimum(k, (n // 2).clip(lower=1))
    long = ranks.le(kk, axis=0)
    short = ranks.gt(n - kk, axis=0)
    w = long.astype(float) - short.astype(float)
    if normalize:
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return w


def funding_panel(close):
    ser = {}
    for sym in close.columns:
        p = os.path.join(bt.DATA_DIR, f"{sym}_funding.csv")
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_csv(p)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
            df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
            r = pd.to_numeric(df["fundingRate"], errors="coerce").clip(-0.0075, 0.0075)
            ser[sym] = r.resample("1D").sum()
        except Exception:
            continue
    return pd.DataFrame(ser).reindex(close.index).fillna(0.0)


def build_signals(close, high, low, volume, mask, fund):
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    vol60 = ret.rolling(60).std()
    mkt = ret.mean(axis=1)
    excess = ret.sub(mkt, axis=0)
    signals = {}

    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    signals["XS momentum (baseline)"] = lambda: xs(mom_stack / vol30, mask)

    mom_skip = close.shift(5) / close.shift(35) - 1.0
    signals["XS momentum skip-5d"] = lambda: xs(mom_skip / vol30, mask)

    signals["XS low-vol (BAB)"] = lambda: xs(-vol30, mask)
    signals["XS high-vol"] = lambda: xs(vol30, mask)
    signals["XS vol ratio (short-term)"] = lambda: xs(vol30 / vol60, mask)

    signals["XS reversal 1d"] = lambda: xs(-(close / close.shift(1) - 1.0), mask)
    signals["XS reversal 5d"] = lambda: xs(-(close / close.shift(5) - 1.0), mask)
    signals["XS reversal 10d"] = lambda: xs(-(close / close.shift(10) - 1.0), mask)

    signals["XS acceleration"] = lambda: xs((close / close.shift(5) - 1) - (close / close.shift(30) - 1), mask)

    hi60 = close.rolling(60).max()
    lo60 = close.rolling(60).min()
    signals["XS near 60d high"] = lambda: xs(close / hi60, mask)
    signals["XS far below high"] = lambda: xs(-close / hi60, mask)
    signals["XS position in range"] = lambda: xs((close - lo60) / (hi60 - lo60).replace(0, np.nan), mask)

    signals["XS volume surge"] = lambda: xs(volume.rolling(5).mean() / volume.rolling(30).mean().replace(0, np.nan), mask)
    signals["XS volume z-score"] = lambda: xs(zs(np.log1p(volume), mask).rolling(5).mean(), mask)

    vbreak = (close - close.rolling(20).mean()) / close.rolling(20).std().replace(0, np.nan)
    signals["XS vol breakout z"] = lambda: xs(vbreak, mask)

    f7 = fund.rolling(7).mean()
    signals["XS funding carry"] = lambda: xs(-f7, mask)
    signals["XS mom - funding tilt"] = lambda: xs(zs(mom_stack / vol30, mask) - zs(f7, mask), mask)
    signals["XS mom + low funding"] = lambda: xs((mom_stack / vol30) * (f7 <= f7.median(axis=1).values[:, None]).astype(float), mask)

    signals["XS residual momentum"] = lambda: xs(excess.rolling(30).sum() / excess.rolling(30).std(), mask)
    signals["XS Sharpe momentum"] = lambda: xs(ret.rolling(20).mean() / ret.rolling(20).std(), mask)

    signals["XS trend + carry blend"] = lambda: xs(zs(mom_stack / vol30, mask) - 0.5 * zs(f7, mask), mask)
    signals["XS combo (mom+carry+lowvol)"] = lambda: xs(zs(mom_stack / vol30, mask) - zs(f7, mask) - 0.5 * zs(vol30, mask), mask)

    signals["XS mom k=5"] = lambda: xs(mom_stack / vol30, mask, k=5)
    signals["XS mom k=20"] = lambda: xs(mom_stack / vol30, mask, k=20)

    tsmom = np.sign(close / close.shift(30) - 1.0) * (0.40 / (vol30 * np.sqrt(PPY)).replace(0, np.nan))
    signals["TS momentum (long/short)"] = lambda: tsmom.clip(-1, 1).where(mask).div(
        tsmom.clip(-1, 1).where(mask).abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)

    return signals


def evaluate(close, w, funding):
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    return {
        "is_sharpe": bt.metrics(net[net.index < SPLIT], PPY)["sharpe"],
        "oos_sharpe": bt.metrics(net[net.index >= SPLIT], PPY)["sharpe"],
        "full_sharpe": bt.metrics(net, PPY)["sharpe"],
        "full_cagr": bt.metrics(net, PPY)["cagr"] * 100,
        "full_dd": bt.metrics(net, PPY)["max_dd"] * 100,
        "at40dd": bt.scaled_metrics(net, 0.40, PPY)["cagr"] * 100,
        "turnover": r["turnover"].mean(),
    }


def main():
    close, volume, high, low = load_all4()
    mask = pit_mask(close, volume)
    fund = funding_panel(close)
    print(f"panel {close.shape[1]} symbols x {len(close)} days")
    print(f"avg PIT universe {mask.sum(axis=1)[mask.sum(axis=1)>0].mean():.1f}\n")

    sigs = build_signals(close, high, low, volume, mask, fund)
    rows = []
    for name, fn in sigs.items():
        try:
            w = fn()
            m = evaluate(close, w, fund)
            m["strategy"] = name
            rows.append(m)
        except Exception as e:
            print(f"  !! {name}: {e}")
    df = pd.DataFrame(rows)[["strategy", "is_sharpe", "oos_sharpe", "full_sharpe",
                             "full_cagr", "full_dd", "at40dd", "turnover"]]
    df.to_csv(os.path.join(bt.DATA_DIR, "strategy_zoo.csv"), index=False)

    print(f"=== {len(df)} STRATEGIES, ranked by IN-SAMPLE Sharpe (<2024) ===")
    print("(select on IS, judge on OOS — picking the OOS winner would be its own bias)\n")
    print(df.sort_values("is_sharpe", ascending=False).round(2).to_string(index=False))
    print("\n=== TOP 10 BY OUT-OF-SAMPLE SHARPE (>=2024) ===")
    print(df.sort_values("oos_sharpe", ascending=False).head(10).round(2).to_string(index=False))
    print("\n=== CONSISTENT: both IS and OOS Sharpe > 0.5 ===")
    good = df[(df.is_sharpe > 0.5) & (df.oos_sharpe > 0.5)].sort_values("oos_sharpe", ascending=False)
    print(good.round(2).to_string(index=False) if len(good) else "  none")


if __name__ == "__main__":
    main()
