"""Copy-simulation desk.

Binance's own Mock Copy only runs inside their platform, so this desk does the next
best thing: it replays a lead trader's published trade log into a virtual copier
account, charging realistic frictions, so the copier's experience can be compared
against our own strategies in the same dashboard.

Assumptions (deliberately conservative and stated in the output):
  * the copier mirrors each trade at a fixed fraction of equity
  * the copier cannot enter instantly -> LAG_SLIPPAGE per side, scaled by leverage
  * Binance charges a 10% profit share on profitable trades
  * the copier never sees the trader's unrealised positions, so this only measures
    what was *realised* -- the hidden open risk is invisible by construction

Refresh it by re-copying the trader's trade history into binance_trades.md.
"""
import os
import re
import numpy as np
import pandas as pd

from . import config as cfg

TRADE_FILE = os.path.join(cfg.BASE_DIR, "..", "binance_trades.md")
INITIAL = 10_000.0
ALLOC = 0.05            # fraction of equity allocated per copied trade
LAG_SLIPPAGE = 0.001    # 0.1% per side, for entering/exiting behind the leader
PROFIT_SHARE = 0.10
MAX_CONCURRENT = 20     # capital guard: at most 20 positions funded at once
PROFILE = "copytrader"


def _num(s):
    if s is None:
        return np.nan
    s = str(s).replace(",", "").replace("USDT", "").replace("+", "").strip()
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else np.nan


def parse_trades(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [l.strip() for l in f.readlines()]
    opens = [i for i, l in enumerate(lines) if l == "Opened"]
    recs = []
    for k, i in enumerate(opens):
        end = opens[k + 1] if k + 1 < len(opens) else len(lines)
        r = {"opened": lines[i + 1] if i + 1 < end else None}
        for j in range(i + 1, end):
            if lines[j] == "Entry Price":
                r["entry"] = _num(lines[j + 1])
            elif lines[j] == "Closing PNL":
                r["pnl"] = _num(lines[j + 1])
            elif lines[j] == "Avg. Close Price":
                r["close"] = _num(lines[j + 1])
            elif lines[j] == "Max. Open Interest":
                r["size"] = _num(lines[j + 1])
            elif lines[j] == "Closed" and j + 1 < end and re.match(r"^\d{4}-\d{2}-\d{2}", lines[j + 1]):
                r["closed"] = lines[j + 1]
        for j in range(i - 1, max(i - 14, -1), -1):
            if lines[j] in ("Short", "Long") and "side" not in r:
                r["side"] = lines[j]
            if re.match(r"^\d+x$", lines[j]) and "lev" not in r:
                r["lev"] = int(lines[j].rstrip("x"))
            if lines[j].endswith("USDT") and "symbol" not in r:
                r["symbol"] = lines[j]
        recs.append(r)
    df = pd.DataFrame(recs)
    for c in ["entry", "close", "pnl", "size"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["opened"] = pd.to_datetime(df.get("opened"), errors="coerce")
    df["closed"] = pd.to_datetime(df.get("closed"), errors="coerce")
    return df.dropna(subset=["exit_ret"] if "exit_ret" in df else ["entry", "close"])


def simulate():
    df = parse_trades(TRADE_FILE)
    if df.empty:
        return None
    df["direction"] = np.where(df["side"] == "Short", -1.0, 1.0)
    df["price_ret"] = df["direction"] * (df["close"] - df["entry"]) / df["entry"]
    df["lev"] = df["lev"].fillna(5).clip(1, 50)
    df = df[np.isfinite(df["price_ret"])].sort_values("closed").reset_index(drop=True)

    equity = INITIAL
    rows = []
    for _, t in df.iterrows():
        gross = t["price_ret"] * t["lev"]
        cost = 2 * LAG_SLIPPAGE * t["lev"]
        net = gross - cost
        if net > 0:
            net -= net * PROFIT_SHARE
        pnl = equity * ALLOC * net
        equity += pnl
        rows.append({"closed": t["closed"], "symbol": t["symbol"], "side": t["side"],
                     "lev": t["lev"], "price_ret": t["price_ret"], "net_on_margin": net,
                     "pnl": pnl, "equity": equity})
    sim = pd.DataFrame(rows)

    prog = cfg.files(PROFILE)
    acc = {
        "profile": PROFILE,
        "strategy": "COPY_SIMULATION",
        "label": cfg.cfg_for(PROFILE)["label"],
        "initial_capital": INITIAL,
        "cash": equity,
        "positions": {},
        "avg_entry": {},
        "start_utc": str(df["opened"].min()),
        "last_run_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_date": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
        "high_water_mark": float(sim["equity"].cummax().max()),
        "breaker_active": False,
        "runs": 1,
        "source_trades": len(df),
        "note": "Replay of the lead trader's published log with lag slippage + 10% profit share. "
                "Realised PnL only; their open positions are not visible.",
    }
    import json
    with open(prog["account"], "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2)

    daily = sim.groupby(sim["closed"].dt.date).agg(
        equity=("equity", "last"), fees=("pnl", lambda s: 0.0)).reset_index()
    daily.columns = ["date", "equity", "fees"]
    daily["cash"] = daily["equity"]
    daily["gross_notional"] = 0.0
    daily["net_notional"] = 0.0
    daily["n_long"] = 0
    daily["n_short"] = 0
    daily["funding_pnl"] = 0.0
    daily["drawdown"] = daily["equity"] / daily["equity"].cummax() - 1
    daily["breaker"] = 0
    daily["vol_scale"] = 1.0
    daily["gross_scale"] = 1.0
    daily["return_pct"] = daily["equity"] / INITIAL - 1
    daily[["date", "equity", "cash", "gross_notional", "net_notional", "n_long", "n_short",
           "funding_pnl", "fees", "drawdown", "breaker", "vol_scale", "gross_scale",
           "return_pct"]].to_csv(prog["daily"], index=False, encoding="utf-8")

    tr = sim.rename(columns={"closed": "timestamp", "price_ret": "trader_move",
                             "net_on_margin": "copier_on_margin"})
    tr["run_date"] = tr["timestamp"].dt.date
    tr["side"] = tr["side"].str.upper()
    tr["qty"] = 0.0
    tr["price"] = 0.0
    tr["notional"] = 0.0
    tr["fee"] = 0.0
    tr["slippage"] = LAG_SLIPPAGE
    tr["reason"] = "copy_sim"
    tr[["timestamp", "run_date", "symbol", "side", "qty", "price", "notional", "fee",
        "slippage", "reason", "trader_move", "copier_on_margin", "pnl", "equity"]].to_csv(
        prog["trades"], index=False, encoding="utf-8")

    end_alloc = equity * ALLOC
    med_leader = float((df["size"] * df["entry"]).median())
    print(f"[{PROFILE}] replays the leader's REALISED trades with {LAG_SLIPPAGE*100:.1f}%/side lag "
          f"slippage and the {PROFIT_SHARE:.0%} profit share.")
    print(f"[{PROFILE}] CAVEAT - capacity: implied size grows to ${end_alloc:,.0f}/trade by the end, "
          f"vs the leader's median of ~${med_leader:,.0f}.")
    print(f"[{PROFILE}] this edge is not available at size, and copiers who join after the run-up "
          f"do not get it. Treat the figure as an upper bound, not a forecast.")
    return acc
