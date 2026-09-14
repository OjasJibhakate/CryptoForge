import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

PERIODS_PER_YEAR = {"1h": 24 * 365, "4h": 6 * 365, "1d": 365, "15m": 96 * 365, "5m": 288 * 365, "1m": 1440 * 365}


def load_klines(symbol, interval):
    path = os.path.join(DATA_DIR, f"{symbol}_{interval}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def load_funding(symbol):
    path = os.path.join(DATA_DIR, f"{symbol}_funding.csv")
    if not os.path.exists(path):
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df["fundingRate"]


def price_panel(symbols, interval, field="close"):
    out = {}
    for s in symbols:
        df = load_klines(s, interval)
        if not df.empty:
            out[s] = df[field]
    panel = pd.DataFrame(out).sort_index()
    return panel


def funding_daily_panel(symbols, index):
    out = {}
    for s in symbols:
        f = load_funding(s)
        if f.empty:
            continue
        daily = f.resample("1D").sum()
        out[s] = daily
    if not out:
        return pd.DataFrame(index=index)
    panel = pd.DataFrame(out).reindex(index).fillna(0.0)
    return panel


def metrics(returns, ppy=365):
    r = pd.Series(returns).dropna()
    if len(r) < 5 or r.std() == 0:
        return {"cagr": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_dd": 0.0,
                "calmar": 0.0, "vol": 0.0, "n": len(r)}
    equity = (1 + r).cumprod()
    years = len(r) / ppy
    cagr = equity.iloc[-1] ** (1 / years) - 1 if years > 0 and equity.iloc[-1] > 0 else -1.0
    vol = r.std() * np.sqrt(ppy)
    sharpe = (r.mean() * ppy) / vol if vol > 0 else 0.0
    downside = r[r < 0].std() * np.sqrt(ppy)
    sortino = (r.mean() * ppy) / downside if downside and downside > 0 else 0.0
    peak = equity.cummax()
    dd = (equity / peak - 1)
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
            "calmar": calmar, "vol": vol, "n": len(r)}


def portfolio_backtest(asset_returns, target_weights, funding=None, fee_bps=5.0,
                       slip_bps=2.0, ppy=365, leverage_cap=None, asset_cap=None):
    idx = asset_returns.index
    w = target_weights.reindex(index=idx, columns=asset_returns.columns).fillna(0.0)
    if asset_cap is not None:
        w = w.clip(-asset_cap, asset_cap)
    if leverage_cap is not None:
        gross = w.abs().sum(axis=1)
        scale = np.where(gross > leverage_cap, leverage_cap / gross.replace(0, np.nan), 1.0)
        w = w.mul(pd.Series(scale, index=idx).fillna(1.0), axis=0)
    w_held = w.shift(1).fillna(0.0)
    gross_ret = (w_held * asset_returns).sum(axis=1)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    cost = turnover * (fee_bps + slip_bps) / 1e4
    funding_cost = pd.Series(0.0, index=idx)
    if funding is not None and not funding.empty:
        f = funding.reindex(index=idx).fillna(0.0)
        common = f.columns.intersection(w_held.columns)
        funding_cost = -(w_held[common] * f[common]).sum(axis=1)
    net = gross_ret - cost + funding_cost
    return {"net": net, "gross": gross_ret, "cost": cost, "funding": funding_cost,
            "turnover": turnover, "weights": w_held}


def scale_to_dd(returns, target_dd=0.40):
    m = metrics(returns)
    if m["max_dd"] == 0 or not np.isfinite(m["max_dd"]):
        return 1.0
    return min(target_dd / abs(m["max_dd"]), 20.0)


def scaled_metrics(returns, target_dd=0.40, ppy=365, cap=20.0):
    scale = min(scale_to_dd(returns, target_dd), cap)
    m = metrics(pd.Series(returns) * scale, ppy=ppy)
    m["scale"] = scale
    return m


def single_asset_signal(df, signal, fee_bps=5.0, slip_bps=2.0, allow_short=True, ppy=365):
    close = df["close"]
    ret = close.pct_change().fillna(0.0)
    sig = signal.reindex(close.index).fillna(0.0)
    if not allow_short:
        sig = sig.clip(lower=0.0)
    return portfolio_backtest(ret.to_frame("asset"),
                              sig.clip(-1, 1).to_frame("asset"),
                              fee_bps=fee_bps, slip_bps=slip_bps, ppy=ppy)


def summarize(name, result, ppy=365):
    m = metrics(result["net"], ppy=ppy)
    m["gross_cagr"] = metrics(result["gross"], ppy=ppy)["cagr"]
    m["avg_turnover"] = result["turnover"].mean()
    m["name"] = name
    return m


def fmt(m):
    return (f"{m['name']:<34} CAGR {m['cagr']*100:8.2f}%  Sharpe {m['sharpe']:6.2f}  "
            f"MaxDD {m['max_dd']*100:7.2f}%  Calmar {m['calmar']:5.2f}  "
            f"turn {m['avg_turnover']:.3f}")
