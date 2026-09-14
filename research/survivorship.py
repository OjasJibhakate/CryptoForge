import os
import sys
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

DATA = bt.DATA_DIR
SPLIT = pd.Timestamp("2024-01-01")


def load_all_panels(skip_quotes=("USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH")):
    closes, vols = {}, {}
    for path in glob.glob(os.path.join(DATA, "*_1d.csv")):
        sym = os.path.basename(path)[:-7]
        if not sym.endswith("USDT") or "SETTLED" in sym:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "timestamp" not in df.columns or len(df) < 60:
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        if "close" not in df.columns or "volume" not in df.columns:
            continue
        closes[sym] = pd.to_numeric(df["close"], errors="coerce")
        vols[sym] = pd.to_numeric(df["volume"], errors="coerce")
    close = pd.DataFrame(closes).sort_index()
    volume = pd.DataFrame(vols).reindex(close.index)
    return close, volume


def pit_mask(close, volume, top_n=60, min_adv=5_000_000, min_hist=60, adv_window=30):
    dollar = close * volume
    adv = dollar.rolling(adv_window).mean()
    hist = close.notna().cumsum()
    eligible = (adv >= min_adv) & (hist >= min_hist) & close.notna()
    rank = adv.where(eligible).rank(axis=1, ascending=False)
    return rank.le(top_n) & eligible


def xs_weights(close, mask, lookbacks=(14, 21, 30, 45, 60), k=10, risk_adj=True, vol_window=30):
    ret = close.pct_change()
    vol = ret.rolling(vol_window).std()
    total = None
    for lb in lookbacks:
        mom = close / close.shift(lb) - 1.0
        score = (mom / vol) if risk_adj else mom
        score = score.replace([np.inf, -np.inf], np.nan).where(mask)
        ranks = score.rank(axis=1, ascending=False)
        n = score.notna().sum(axis=1)
        kk = np.minimum(k, (n // 2).clip(lower=1))
        long = ranks.le(kk, axis=0)
        short = ranks.gt(n - kk, axis=0)
        w = long.astype(float) - short.astype(float)
        gross = w.abs().sum(axis=1).replace(0.0, np.nan)
        w = w.div(gross, axis=0).fillna(0.0)
        total = w if total is None else total + w
    return total / len(lookbacks)


def funding_panel_all(close, cap=0.0075):
    series = {}
    for sym in close.columns:
        p = os.path.join(DATA, f"{sym}_funding.csv")
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_csv(p)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
            df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
            r = pd.to_numeric(df["fundingRate"], errors="coerce")
            if cap is not None:
                r = r.clip(-cap, cap)
            series[sym] = r.resample("1D").sum()
        except Exception:
            continue
    if not series:
        return pd.DataFrame(index=close.index)
    return pd.DataFrame(series).reindex(close.index).fillna(0.0)


def run(top_n=60, k=10, min_adv=5_000_000, include_funding=True, label=""):
    close, volume = load_all_panels()
    print(f"[{label}] panel: {close.shape[1]} symbols x {len(close)} days "
          f"({close.index.min().date()} -> {close.index.max().date()})")
    mask = pit_mask(close, volume, top_n=top_n, min_adv=min_adv)
    univ_size = mask.sum(axis=1)
    print(f"[{label}] avg point-in-time universe: {univ_size[univ_size > 0].mean():.1f} symbols "
          f"(min {int(univ_size[univ_size>0].min())}, max {int(univ_size.max())})")
    # how many symbols appear at least once, and how many are now dead
    ever = mask.any(axis=0).sum()
    last_seen = mask.apply(lambda c: c[c].index.max() if c.any() else pd.NaT)
    dead = ((last_seen < close.index.max() - pd.Timedelta(days=30)) & mask.any(axis=0)).sum()
    print(f"[{label}] symbols ever selected: {ever} | since dropped/delisted: {dead}")

    w = xs_weights(close, mask, k=k)
    ret = close.pct_change().fillna(0.0)
    funding = funding_panel_all(close) if include_funding else None
    r = bt.portfolio_backtest(ret, w, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=365)
    net = r["net"]
    ins = bt.metrics(net[net.index < SPLIT], 365)
    oos = bt.metrics(net[net.index >= SPLIT], 365)
    full = bt.metrics(net, 365)
    scaled = bt.scaled_metrics(net, 0.40, 365)
    print(f"[{label}] IS  Sharpe {ins['sharpe']:.2f}  CAGR {ins['cagr']*100:6.1f}%  DD {ins['max_dd']*100:6.1f}%")
    print(f"[{label}] OOS Sharpe {oos['sharpe']:.2f}  CAGR {oos['cagr']*100:6.1f}%  DD {oos['max_dd']*100:6.1f}%")
    print(f"[{label}] FULL Sharpe {full['sharpe']:.2f}  CAGR {full['cagr']*100:6.1f}%  DD {full['max_dd']*100:6.1f}%"
          f"  -> at40%DD CAGR {scaled['cagr']*100:.1f}% (x{scaled['scale']:.2f})")
    print(f"[{label}] funding contribution/day {r['funding'].mean()*1e4:+.3f} bps  "
          f"cost/day {r['cost'].mean()*1e4:.3f} bps  turnover {r['turnover'].mean():.3f}")
    idx = net.index
    bounds = np.linspace(0, len(idx), 6).astype(int)
    print(f"[{label}] sub-periods:")
    for i in range(5):
        seg = net.iloc[bounds[i]:bounds[i + 1]]
        m = bt.metrics(seg, 365)
        print(f"    {idx[bounds[i]].date()} -> {idx[bounds[i+1]-1].date()}: "
              f"Sharpe {m['sharpe']:5.2f}  CAGR {m['cagr']*100:7.1f}%  DD {m['max_dd']*100:6.1f}%")
    return net, mask, r


if __name__ == "__main__":
    run(label="PIT")
