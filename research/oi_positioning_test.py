"""OI + positioning test: can public futures positioning data sharpen the wave3 book?

Data (public, no key): openInterestHist, globalLongShortAccountRatio,
takerlongshortRatio, topLongShortPositionRatio. Binance serves only the last
~30 days of these, so this is a 30-bar diagnostic, not a 7-year backtest.

Two questions:
  Q1 (descriptive): does the positioning signal MOVE with next-day direction
      at all over the last 30 days? (correlation; no selection)
  Q2 (honest): even if it did, would 30 bars be enough to prove anything?

Signals, cross-sectionally z-scored each day:
  oi_chg     : 3d change in open interest (position build-up)
  crowded    : extreme long-account ratio faded (crowded longs underperform)
  taker      : taker buy/sell ratio change (aggressive flow)
"""
import sys
import time
import requests
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://fapi.binance.com"
PERIOD = "1d"
LIMIT = 31


def get(path, symbol):
    try:
        r = requests.get(BASE + path, params={"symbol": symbol, "period": PERIOD,
                                              "limit": LIMIT}, timeout=25)
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
    import strategy_zoo as sz
    syms = []
    for p in glob.glob(os.path.join("research", "data", "*_1df.csv")):
        s = os.path.basename(p)[:-8]
        if s.endswith("USDT") and "SETTLED" not in s:
            syms.append(s)
    print(f"trying positioning pull for {len(syms)} symbols (public endpoints, 30d each) ...")
    import concurrent.futures

    def fetch(s):
        a = get("/futures/data/openInterestHist", s)
        if a is None or a.empty:
            return None
        b = get("/futures/data/globalLongShortAccountRatio", s)
        c = get("/futures/data/takerlongshortRatio", s)
        if b is None or b.empty or c is None or c.empty:
            return None
        return (s,
                pd.to_numeric(a["sumOpenInterestValue"], errors="coerce"),
                pd.to_numeric(b["longShortRatio"], errors="coerce"),
                pd.to_numeric(c["buySellRatio"], errors="coerce"))

    oi, gl, tk = {}, {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch, s): s for s in syms}
        done = 0
        for f in concurrent.futures.as_completed(futs):
            done += 1
            r = f.result()
            if r:
                oi[r[0]], gl[r[0]], tk[r[0]] = r[1], r[2], r[3]
            if done % 100 == 0:
                print(f"  {done}/{len(syms)} tried, {len(oi)} with full data ...", flush=True)
    ok = len(oi)
    if ok < 10:
        print("VERDICT: coverage too thin for even a diagnostic. Thread closed.")
        return

    OI = pd.DataFrame(oi).sort_index()
    GL = pd.DataFrame(gl).sort_index()
    TK = pd.DataFrame(tk).sort_index()

    # closes for the same window
    closes = {}
    for s in OI.columns:
        p = os.path.join("research", "data", f"{s}_1df.csv")
        try:
            df = pd.read_csv(p, usecols=["timestamp", "close"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True,
                                             format="ISO8601").dt.tz_localize(None)
            df = df.set_index("timestamp").sort_index()
            closes[s] = pd.to_numeric(df["close"], errors="coerce")
        except Exception:
            continue
    C = pd.DataFrame(closes).sort_index()
    idx = OI.index.intersection(C.index)
    OI, GL, TK, C = OI.loc[idx], GL.loc[idx], TK.loc[idx], C.loc[idx]
    fwd = C.pct_change().shift(-1)  # next-day return

    def xcorr(sig, name):
        s = sig.sub(sig.mean(axis=1), axis=0).div(sig.std(axis=1).replace(0, np.nan), axis=0)
        f = fwd.sub(fwd.mean(axis=1), axis=0).div(fwd.std(axis=1).replace(0, np.nan), axis=0)
        paired = (s * f).stack().dropna()
        n = len(paired)
        ic = paired.mean()
        t = ic * np.sqrt(max(n - 1, 1))
        print(f"  {name:<34} IC {ic:+.4f}  t {t:+5.2f}  n={n}")
        return ic, t

    print(f"\n=== Q1: signal vs NEXT-DAY return, {len(idx)} days x {len(OI.columns)} names ===")
    oi_chg = OI.pct_change(3)
    xcorr(oi_chg, "OI 3d change -> next day")
    xcorr(-GL, "fade crowded longs -> next day")
    tk_chg = TK.pct_change(3)
    xcorr(tk_chg, "taker buy/sell 3d change -> next day")
    print("\n=== Q2: power ===")
    print(f"  30 days is ~30 independent day-clusters. Significance needs |t|>2.")
    print(f"  Even a perfect read of this window could not clear a gate.")
    print(f"  VERDICT: diagnostic only. Do not append positioning to wave3 on this.")


if __name__ == "__main__":
    main()
