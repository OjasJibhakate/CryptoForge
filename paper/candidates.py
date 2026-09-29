"""Candidate registry: the frozen C1/C2 profiles (config.PROFILE_CFG) plus later ones.

C3 (FORWARD_PROTOCOL.md amendment 1, 2026-09-30) runs C2's exact rules
(strategy.wave3_weights, risk.apply_risk, PaperBroker, 5+2 bps costs) on a
crypto-only universe (Binance contractType PERPETUAL, underlyingType COIN) with
gross capped at 1.0x -- the book the backtests actually tested. Frozen by hash.

C1/C2 dispatch through here unchanged: for a frozen profile every function below
makes exactly the call engine.py made before (store.load_account,
market.load_market(), strategy.compute_targets).
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd

from . import config as cfg
from . import market, store, strategy

EXTRA_PROFILE_CFG = {
    "c3": {
        "label": "C3 (wave3 rules, crypto-only universe, 1.0x gross cap)",
        "strategy": "XS_MOMENTUM_FUNDING_REGIME_RM_CRYPTO_1X",
        "kind": "strategy",
        "funding_tilt": True,
        "regime": True,
        "risk_managed": True,
        "vol_target": None,
        "dd_breaker_trigger": 0.20,
        "universe": "crypto_only",
        "gross_cap": 1.0,
    },
}

ALL_PROFILES = tuple(cfg.PROFILES) + tuple(EXTRA_PROFILE_CFG)
EXINFO_PATH = os.path.join(cfg.BASE_DIR, "cache", "exchangeInfo.json")


def cfg_for(profile):
    if profile in cfg.PROFILE_CFG:
        return cfg.PROFILE_CFG[profile]
    if profile in EXTRA_PROFILE_CFG:
        return EXTRA_PROFILE_CFG[profile]
    raise ValueError(f"unknown profile {profile!r}; expected one of {ALL_PROFILES}")


def strategy_profiles():
    return tuple(p for p in ALL_PROFILES if cfg_for(p)["kind"] == "strategy")


def load_account(profile):
    """store.load_account for frozen profiles or existing accounts; otherwise a fresh
    in-memory account (written only when the engine saves after a real run)."""
    if profile in cfg.PROFILE_CFG or os.path.exists(cfg.files(profile)["account"]):
        return store.load_account(profile)
    pcfg = cfg_for(profile)
    return {
        "profile": profile,
        "strategy": pcfg["strategy"],
        "label": pcfg["label"],
        "initial_capital": cfg.INITIAL_CAPITAL,
        "cash": cfg.INITIAL_CAPITAL,
        "positions": {},
        "avg_entry": {},
        "start_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_utc": None,
        "last_run_date": None,
        "high_water_mark": cfg.INITIAL_CAPITAL,
        "breaker_active": False,
        "runs": 0,
    }


def contract_classes():
    """{symbol: [contractType, underlyingType, status]} from exchangeInfo, cached per
    UTC day. If the fetch fails, the last cached copy of any age is used."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cached = None
    if os.path.exists(EXINFO_PATH):
        try:
            with open(EXINFO_PATH, encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            cached = None
    if cached and cached.get("fetched_utc_date") == today:
        return cached["classes"]
    try:
        data = market._get("/fapi/v1/exchangeInfo") or {}
        classes = {s["symbol"]: [s.get("contractType"), s.get("underlyingType"), s.get("status")]
                   for s in data.get("symbols", [])}
        if not classes:
            raise RuntimeError("exchangeInfo returned no symbols")
        tmp = EXINFO_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched_utc_date": today, "classes": classes}, f)
        os.replace(tmp, EXINFO_PATH)
        return classes
    except market.RateLimited:
        raise
    except Exception:
        if cached:
            return cached["classes"]
        raise


def is_crypto(symbol, classes):
    c = classes.get(symbol)
    return bool(c) and c[0] == "PERPETUAL" and c[1] == "COIN"


def crypto_candidates():
    """Top CANDIDATE_POOL crypto USDT perpetuals by 24h quote volume. Unlike
    market.candidate_symbols() there is no UP/DOWN/BULL/BEAR suffix filter: on
    futures it only ever removed real coins (JUPUSDT, SYRUPUSDT)."""
    classes = contract_classes()
    tickers = market._get("/fapi/v1/ticker/24hr") or []
    rows = []
    for t in tickers:
        s = t.get("symbol", "")
        c = classes.get(s)
        if not s.endswith("USDT") or not c or c[0] != "PERPETUAL" or c[1] != "COIN" or c[2] != "TRADING":
            continue
        try:
            qv = float(t["quoteVolume"])
            last = float(t["lastPrice"])
        except (KeyError, ValueError, TypeError):
            continue
        if last > 0:
            rows.append((s, qv))
    if not rows:
        raise RuntimeError("no crypto perpetuals in ticker response")
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:cfg.CANDIDATE_POOL]]


def load_market(profile):
    if cfg_for(profile).get("universe") == "crypto_only":
        return market.load_market(candidate_pool=crypto_candidates())
    return market.load_market()


def compute_targets(close, volume, funding_panel, profile):
    if profile in cfg.PROFILE_CFG:
        return strategy.compute_targets(close, volume, funding_panel, profile)
    pcfg = cfg_for(profile)
    mask = strategy.pit_mask(close, volume)
    w = strategy.wave3_weights(close, mask, funding_panel, risk_managed=pcfg["risk_managed"])
    if w.empty:
        return pd.Series(dtype=float)
    row = w.iloc[-1]
    row = row[row.abs() > 1e-9]
    cap = pcfg.get("gross_cap")
    gross = float(row.abs().sum())
    if cap and gross > cap:
        row = row * (cap / gross)
    return row
