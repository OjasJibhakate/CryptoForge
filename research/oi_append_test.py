"""Append-test for OI change as a wave3 overlay, on the only window where
positioning data exists: the last 30 days.

Compares, over the same 30-day window and the same names:
  A: wave3-style momentum sleeve (mom - funding tilt, k=10)
  B: A + OI-change tilt (the t=+4.23 IC signal)
  C: OI-change sleeve alone

Judged ONLY on risk-adjusted return over the window, with the honest caveat
that 30 days cannot validate anything -- this decides whether OI earns a
forward-paper slot, not whether it is an edge.
"""
import sys
import time
import requests
import numpy as np
import pandas as pd
import concurrent.futures

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
import strategy_zoo as sz

BASE = "https://fapi.binance.com"
K = 10


def get(path, symbol):
    try:
        r = requests.get(BASE + path, params={"symbol": symbol, "period": "1d",
                                              "limit": 31}, timeout=25)
        if r.status_code != 200:
            return pd.DataFrame()
        d = r.json()
        if not isinstance(d, list) or not d:
            return pd.DataFrame()
        df = pd.DataFrame(d)
        df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"]), unit="ms",
                                         utc=True).dt.tz_localize(None)
        return df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    except Exception:
        return pd.DataFrame()


def main():
    import glob, os
    syms = []
    for p in glob.glob(os.path.join("research", "data", "*_1df.csv")):
        s = os.path.basename(p)[:-8]
        if s.endswith("USDT") and "SETTLED" not in s:
            syms.append(s)

    def fetch(s):
        a = get("/futures/data/openInterestHist", s)
        if a is None or a.empty:
            return None
        return (s, pd.to_numeric(a["sumOpenInterestValue"], errors="coerce"))

    oi = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for f in concurrent.futures.as_completed({ex.submit(fetch, s): s for s in syms}):
            r = f.result()
            if r:
                oi[r[0]] = r[1]
    print(f"OI coverage: {len(oi)} symbols")
    OI = pd.DataFrame(oi).sort_index()
    oi_chg = OI.pct_change(3)

    closes, vols = {}, {}
    for s in OI.columns:
        p = os.path.join("research", "data", f"{s}_1d.csv")
        if not os.path.exists(p):
            p = os.path.join("research", "data", f"{s}_1df.csv")
        try:
            df = pd.read_csv(p, usecols=["timestamp", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True,
                                             format="ISO8601").dt.tz_localize(None)
            df = df.set_index("timestamp").sort_index()
            closes[s] = pd.to_numeric(df["close"], errors="coerce")
            vols[s] = pd.to_numeric(df["volume"], errors="coerce")
        except Exception:
            continue
    C = pd.DataFrame(closes).sort_index()
    V = pd.DataFrame(vols).reindex(C.index)

    # signals on FULL history first (rolling stats need it), then slice to window
    mask_full = sz.pit_mask(C, V)
    fund_full = sz.funding_panel(C)
    ret_full = C.pct_change()
    vol_full = ret_full.rolling(30).std()
    mom_stack_full = sum(C / C.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7_full = fund_full.rolling(7).mean()
    mom_full = sz.zs(mom_stack_full / vol_full, mask_full)
    ftilt_full = mom_full - sz.zs(f7_full, mask_full)

    idx = OI.index.intersection(C.index)
    print(f"overlap window: {idx.min().date()} -> {idx.max().date()} ({len(idx)} days)")
    mask = mask_full.loc[idx]
    fund = fund_full.loc[idx]
    ret = ret_full.loc[idx]
    ftilt = ftilt_full.loc[idx]
    oiz = sz.zs(oi_chg.loc[idx], mask)
    print(f"PIT names/day in window: {mask.sum(axis=1).mean():.1f}")

    print(f"\nwindow {idx.min().date()} -> {idx.max().date()} ({len(idx)} days)\n")
    for name, score in [("A: wave3 sleeve (mom-funding)", ftilt),
                        ("B: wave3 + OI tilt", ftilt + 0.5 * oiz),
                        ("C: OI change alone", oiz)]:
        w = sz.xs(score, mask, k=K)
        r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=365)
        m = bt.metrics(r["net"], 365)
        print(f"{name:<32} Sharpe {m['sharpe']:6.2f}  CAGR {m['cagr']*100:8.1f}%  "
              f"DD {m['max_dd']*100:7.1f}%  turn {r['turnover'].mean():.2f}")
    print("\nRead: 30 days cannot validate. B must beat A by a MARGIN to earn a paper slot.")


if __name__ == "__main__":
    main()
