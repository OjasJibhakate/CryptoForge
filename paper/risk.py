import numpy as np
import pandas as pd

from . import config as cfg


def apply_vol_target(weights, realized_vol, target=None):
    target = cfg.VOL_TARGET_ANNUAL if target is None else target
    if realized_vol is None or realized_vol <= 0 or not np.isfinite(realized_vol):
        return weights, 1.0
    scale = float(min(1.0, target / realized_vol))
    return weights * scale, scale


def apply_per_name_cap(weights, cap=None):
    cap = cfg.PER_NAME_CAP if cap is None else cap
    return weights.clip(-cap, cap)


def update_circuit_breaker(equity, hwm, breached, dd_trigger):
    dd = equity / hwm - 1.0 if hwm > 0 else 0.0
    if not breached and dd <= -dd_trigger:
        breached = True
    elif breached and dd >= -cfg.DD_BREAKER_RESUME:
        breached = False
    gross_scale = cfg.DD_BREAKER_GROSS_SCALE if breached else 1.0
    return breached, gross_scale, dd


def apply_risk(weights, equity, hwm, breached, realized_vol, dd_trigger,
               current_weights=None, vol_target="default"):
    info = {}
    if vol_target is None:
        w = weights
        info["vol_scale"] = 1.0
    else:
        target = cfg.VOL_TARGET_ANNUAL if vol_target == "default" else vol_target
        w, vol_scale = apply_vol_target(weights, realized_vol, target=target)
        info["vol_scale"] = vol_scale
    info["realized_vol"] = realized_vol
    w = apply_per_name_cap(w)
    breached, gross_scale, dd = update_circuit_breaker(equity, hwm, breached, dd_trigger)
    info["breached"] = breached
    info["drawdown"] = dd
    info["gross_scale"] = gross_scale
    w = w * gross_scale
    if breached and cfg.BLOCK_NEW_SHORTS_ON_BREACH and current_weights is not None:
        cur = current_weights.reindex(w.index).fillna(0.0)
        tightening_short = (w < cur) & (w < 0)
        w = w.mask(tightening_short, cur)
        info["blocked_new_shorts"] = int(tightening_short.sum())
    info["gross_after_risk"] = float(w.abs().sum())
    return w, info
