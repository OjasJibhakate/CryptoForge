import os
import json
import csv
from datetime import datetime, timezone

from . import config as cfg


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_account(profile):
    path = cfg.files(profile)["account"]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    pcfg = cfg.cfg_for(profile)
    return {
        "profile": profile,
        "strategy": pcfg["strategy"],
        "label": pcfg["label"],
        "initial_capital": cfg.INITIAL_CAPITAL,
        "cash": cfg.INITIAL_CAPITAL,
        "positions": {},
        "avg_entry": {},
        "start_utc": _now_iso(),
        "last_run_utc": None,
        "last_run_date": None,
        "high_water_mark": cfg.INITIAL_CAPITAL,
        "breaker_active": False,
        "runs": 0,
    }


def save_account(profile, acc):
    path = cfg.files(profile)["account"]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2)
    os.replace(tmp, path)


def _append(path, header, row):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerow(row)


def log_trades(profile, fills, run_date):
    path = cfg.files(profile)["trades"]
    for fl in fills:
        _append(path,
                ["timestamp", "run_date", "symbol", "side", "qty", "price",
                 "notional", "fee", "slippage", "reason"],
                [_now_iso(), run_date, fl["symbol"], fl["side"], round(fl["qty"], 8),
                 round(fl["price"], 8), round(fl["notional"], 4),
                 round(fl["fee"], 6), round(fl["slippage"], 6), fl["reason"]])


def log_daily(profile, snap):
    path = cfg.files(profile)["daily"]
    _append(path,
            ["date", "equity", "cash", "gross_notional", "net_notional",
             "n_long", "n_short", "funding_pnl", "fees", "drawdown", "breaker",
             "vol_scale", "gross_scale", "return_pct", "fee_pnl", "slip_pnl",
             "long_pnl", "short_pnl", "spread_pnl", "turnover",
             "margin_util", "top1_share", "top3_share", "top5_share",
             "missing_funding"],
            [snap["date"], round(snap["equity"], 4), round(snap["cash"], 4),
             round(snap["gross_notional"], 4), round(snap["net_notional"], 4),
             snap["n_long"], snap["n_short"], round(snap["funding_pnl"], 6),
             round(snap["fees"], 6), round(snap["drawdown"], 6),
             int(snap["breaker"]), round(snap["vol_scale"], 4),
             round(snap["gross_scale"], 4), round(snap["return_pct"], 6),
             round(snap.get("fee_pnl", 0.0), 6), round(snap.get("slip_pnl", 0.0), 6),
             round(snap.get("long_pnl", 0.0), 6), round(snap.get("short_pnl", 0.0), 6),
             round(snap.get("spread_pnl", 0.0), 6), round(snap.get("turnover", 0.0), 6),
             round(snap.get("margin_util", 0.0), 6),
             round(snap.get("top1_share", 0.0), 6), round(snap.get("top3_share", 0.0), 6),
             round(snap.get("top5_share", 0.0), 6),
             snap.get("missing_funding", "")])


def log_targets(profile, run_date, weights, prices):
    path = cfg.files(profile)["targets"]
    for sym, w in weights.items():
        _append(path,
                ["date", "symbol", "target_weight", "price"],
                [run_date, sym, round(float(w), 6), round(float(prices.get(sym, 0.0)), 8)])


def log_event(profile, kind, message):
    path = cfg.files(profile)["events"]
    _append(path, ["timestamp", "kind", "message"], [_now_iso(), kind, message])
