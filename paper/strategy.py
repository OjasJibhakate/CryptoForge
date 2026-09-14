import numpy as np
import pandas as pd

from . import config as cfg


def pit_mask(close, volume, top_n=None, min_adv=None, min_hist=None):
    top_n = top_n or cfg.UNIVERSE_TOP_N
    min_adv = cfg.MIN_ADV_USD if min_adv is None else min_adv
    min_hist = cfg.MIN_HISTORY_DAYS if min_hist is None else min_hist
    adv = (close * volume).rolling(cfg.ADV_WINDOW).mean()
    hist = close.notna().cumsum()
    eligible = (adv >= min_adv) & (hist >= min_hist) & close.notna()
    rank = adv.where(eligible).rank(axis=1, ascending=False)
    return (rank.le(top_n) & eligible).fillna(False)


def _zscore(df, mask):
    d = df.where(mask)
    return d.sub(d.mean(axis=1), axis=0).div(d.std(axis=1).replace(0, np.nan), axis=0)


def _long_short(score, mask, k=None, normalize=True):
    k = k or cfg.K_PER_SIDE
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


def ensemble_weights(close, mask, lookbacks=None, k=None, vol_window=None):
    lookbacks = lookbacks or cfg.LOOKBACKS
    k = k or cfg.K_PER_SIDE
    vol_window = vol_window or cfg.VOL_WINDOW
    ret = close.pct_change()
    vol = ret.rolling(vol_window).std()
    total = None
    for lb in lookbacks:
        mom = close / close.shift(lb) - 1.0
        score = (mom / vol).replace([np.inf, -np.inf], np.nan).where(mask)
        w = _long_short(score, mask, k=k)
        total = w if total is None else total + w
    return total / len(lookbacks)


def wave3_weights(close, mask, funding_panel, k=None, risk_managed=False):
    lookbacks = cfg.LOOKBACKS
    ret = close.pct_change()
    vol = ret.rolling(cfg.VOL_WINDOW).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in lookbacks) / len(lookbacks)
    score = _zscore(mom_stack / vol, mask)
    if funding_panel is not None and not funding_panel.empty:
        f7 = funding_panel.reindex(index=close.index, columns=close.columns).fillna(0.0).rolling(7).mean()
        score = score - _zscore(f7, mask)
    w = _long_short(score, mask, k=k)
    if "BTCUSDT" in close.columns:
        btc = close["BTCUSDT"]
        ma = btc.rolling(cfg.REGIME_MA).mean()
        overlay = pd.Series(np.where(btc > ma, 1.0, cfg.REGIME_SOFT), index=close.index)
        overlay = overlay.where(ma.notna(), 1.0)
        w = w.mul(overlay, axis=0)
    if risk_managed:
        base = (w.shift(1) * ret.fillna(0.0).reindex_like(w)).sum(axis=1)
        rv = base.rolling(cfg.RM_LOOKBACK).std() * np.sqrt(365)
        scale = (cfg.RM_TARGET_VOL / rv).clip(upper=cfg.RM_MAX_SCALE).shift(1).fillna(1.0)
        w = w.mul(scale, axis=0)
    return w


def compute_targets(close, volume, funding_panel, profile):
    pcfg = cfg.cfg_for(profile)
    mask = pit_mask(close, volume)
    if pcfg["funding_tilt"] or pcfg["regime"]:
        weights = wave3_weights(close, mask, funding_panel, risk_managed=pcfg.get("risk_managed", False))
    else:
        weights = ensemble_weights(close, mask)
    if weights.empty:
        return pd.Series(dtype=float)
    w = weights.iloc[-1]
    return w[w.abs() > 1e-9]


def realized_portfolio_vol(close, weights_row, lookback=None):
    lookback = lookback or cfg.VOL_WINDOW
    ret = close.pct_change()
    cols = [c for c in weights_row.index if c in ret.columns]
    if not cols:
        return 0.0
    port = (ret[cols] * weights_row[cols]).sum(axis=1)
    return float(port.tail(lookback).std() * np.sqrt(365))
