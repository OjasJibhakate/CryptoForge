import numpy as np
import pandas as pd


def _ann_vol(returns, lookback, ppy=365):
    return returns.rolling(lookback).std() * np.sqrt(ppy)


def tsmom(close, lookback=30, vol_lookback=30, target_vol=0.40, max_size=3.0):
    ret = close.pct_change()
    mom = close / close.shift(lookback) - 1.0
    sig = np.sign(mom)
    rv = _ann_vol(ret, vol_lookback).replace(0.0, np.nan)
    size = (target_vol / rv).clip(upper=max_size)
    return (sig * size).fillna(0.0)


def ma_cross(close, fast=20, slow=60):
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    return np.sign(f - s).fillna(0.0)


def donchian(close, high, low, n=55):
    up = close > high.rolling(n).max().shift(1)
    dn = close < low.rolling(n).min().shift(1)
    sig = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    sig = sig.mask(up, 1.0).mask(dn, -1.0)
    return sig.ffill().fillna(0.0)


def mean_reversion(close, n=7, z_cap=3.0):
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std().replace(0.0, np.nan)
    z = (close - ma) / sd
    return (-z.clip(-z_cap, z_cap) / z_cap).fillna(0.0)


def xs_momentum(close, lookback=30, k=5, vol_lookback=30, target_vol=0.40):
    mom = close / close.shift(lookback) - 1.0
    ranks = mom.rank(axis=1, ascending=False)
    n = mom.notna().sum(axis=1)
    long = ranks.le(k)
    short = ranks.gt(n - k, axis=0)
    w = long.astype(float) - short.astype(float)
    ret = close.pct_change()
    rv = _ann_vol(ret, vol_lookback).replace(0.0, np.nan)
    size = (target_vol / rv).clip(upper=3.0)
    w = w * size / (2 * k)
    return w.fillna(0.0)


def xs_reversal(close, lookback=7, k=5, vol_lookback=30, target_vol=0.40):
    return -xs_momentum(close, lookback=lookback, k=k, vol_lookback=vol_lookback, target_vol=target_vol)


def funding_carry(funding, k=5):
    f = funding.rolling(3).mean()
    ranks = f.rank(axis=1, ascending=False)
    n = f.notna().sum(axis=1)
    short = ranks.le(k)
    long = ranks.gt(n - k, axis=0)
    w = long.astype(float) - short.astype(float)
    return w.div(2 * k).fillna(0.0)


def carry_short_only(funding, k=5):
    f = funding.rolling(3).mean()
    ranks = f.rank(axis=1, ascending=False)
    short = ranks.le(k).astype(float)
    return -short.div(k).fillna(0.0)


def vol_breakout_1m(close, high, low, n=20):
    up = close > high.rolling(n).max().shift(1)
    return up.astype(float).replace(0.0, np.nan).ffill().fillna(0.0)
