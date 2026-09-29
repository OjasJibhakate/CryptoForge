"""Rebuild a paper book from its own ledgers. Read-only.

trades.csv (fills), targets.csv (marks) and daily.csv (funding per run) are replayed
in run order with PaperBroker's exact accounting. Hypothetical backfill fills
(reason == "backfill") are excluded: they never touched the account. Each run's
equity is rebuilt from scratch and compared with the logged value, so any drift
between the ledgers and account.json is visible.
"""
import json
import os

import numpy as np
import pandas as pd

from . import config as cfg


def _read(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8")
    except Exception:
        return pd.DataFrame()


def load(profile):
    f = cfg.files(profile)
    daily, trades, targets = _read(f["daily"]), _read(f["trades"]), _read(f["targets"])
    if not trades.empty and "reason" in trades.columns:
        trades = trades[trades["reason"].astype(str) != "backfill"]
    return daily, trades, targets


def replay(profile, upto=None, frames=None):
    """(records, state). records: one row per run date (multiple runs on a date are
    merged, marks from the last run) with rebuilt vs logged equity, per-run long/short
    price P&L, funding, fees, slippage, traded notional, pre-rebalance equity and run
    time. state: cash, positions, avg_entry, marks, hwm after the last replayed date.
    frames=(daily, trades, targets) replays in-memory tables instead of the files."""
    daily, trades, targets = frames if frames is not None else load(profile)
    if frames is not None and not trades.empty and "reason" in trades.columns:
        trades = trades[trades["reason"].astype(str) != "backfill"]
    if daily.empty:
        return pd.DataFrame(), {}
    daily = daily.copy()
    daily["date"] = daily["date"].astype(str)
    dates = list(dict.fromkeys(daily["date"]))
    if upto is not None:
        dates = [d for d in dates if d <= str(upto)]
    fund = pd.to_numeric(daily["funding_pnl"], errors="coerce").fillna(0.0).groupby(daily["date"]).sum()
    logged = pd.to_numeric(daily["equity"], errors="coerce").groupby(daily["date"]).last()
    empty = pd.DataFrame(columns=["symbol", "price", "qty", "fee", "slippage", "notional", "timestamp"])
    tr_by = dict(tuple(trades.groupby(trades["run_date"].astype(str)))) if not trades.empty else {}
    tg_by = dict(tuple(targets.groupby(targets["date"].astype(str)))) if not targets.empty else {}

    cash, hwm = float(cfg.INITIAL_CAPITAL), float(cfg.INITIAL_CAPITAL)
    pos, avg, marks, rows = {}, {}, {}, []
    for d in dates:
        f, t = tr_by.get(d, empty), tg_by.get(d, empty)
        px = dict(zip(f["symbol"], pd.to_numeric(f["price"], errors="coerce")))
        px.update(zip(t["symbol"], pd.to_numeric(t["price"], errors="coerce")))
        long_pnl = short_pnl = 0.0
        for s, q in pos.items():
            if s in px and s in marks:
                if q > 0:
                    long_pnl += q * (px[s] - marks[s])
                else:
                    short_pnl += q * (px[s] - marks[s])
        fnd = float(fund.get(d, 0.0))
        cash += fnd
        eq_pre = cash + sum(q * px.get(s, marks.get(s, np.nan)) for s, q in pos.items())
        if np.isfinite(eq_pre):
            hwm = max(hwm, eq_pre)
        fee = slip = traded = 0.0
        for r in f.itertuples(index=False):
            p, dq = float(r.price), float(r.qty)
            old = pos.get(r.symbol, 0.0)
            new = old + dq
            cash -= dq * p + float(r.fee) + float(r.slippage)
            fee += float(r.fee)
            slip += float(r.slippage)
            traded += abs(float(r.notional))
            if abs(new) * p < cfg.MIN_ORDER_USD:
                pos[r.symbol], avg[r.symbol] = 0.0, 0.0
                continue
            if old == 0 or old * new < 0:
                avg[r.symbol] = p
            elif abs(new) > abs(old):
                prev = avg.get(r.symbol, p)
                avg[r.symbol] = (abs(old) * prev + abs(dq) * p) / (abs(old) + abs(dq))
            pos[r.symbol] = new
        pos = {k: v for k, v in pos.items() if abs(v) > 0}
        marks.update({s: px[s] for s in pos if s in px and np.isfinite(px[s])})
        equity = cash + sum(q * marks.get(s, np.nan) for s, q in pos.items())
        ts = pd.to_datetime(f["timestamp"], errors="coerce").min() if len(f) else pd.NaT
        rows.append(dict(date=d, equity=equity, logged_equity=float(logged.get(d, np.nan)),
                         equity_pre=eq_pre, cash=cash, long_pnl=long_pnl, short_pnl=short_pnl,
                         funding=fnd, fees=fee, slippage=slip, traded=traded,
                         n_pos=len(pos), run_ts=ts))
    state = {"cash": cash, "positions": dict(pos),
             "avg_entry": {k: v for k, v in avg.items() if k in pos},
             "marks": dict(marks), "hwm": hwm}
    return pd.DataFrame(rows).set_index("date"), state


def verify(profile, tol=0.50, frames=None):
    """Does the ledger rebuild every logged equity and the account's positions?"""
    rec, state = replay(profile, frames=frames)
    if rec.empty:
        return {"ok": True, "n": 0, "max_err": 0.0, "worst": None, "positions_match": True}
    err = (rec["equity"] - rec["logged_equity"]).abs()
    path = cfg.files(profile)["account"]
    acc = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    real = acc.get("positions", {})
    syms = set(real) | set(state["positions"])
    pos_ok = all(np.isclose(real.get(s, 0.0), state["positions"].get(s, 0.0), rtol=1e-6, atol=1e-9)
                 for s in syms)
    return {"ok": bool(err.max() <= tol and pos_ok), "n": len(rec), "max_err": float(err.max()),
            "worst": err.idxmax(), "positions_match": bool(pos_ok)}
