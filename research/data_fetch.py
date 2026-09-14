import os
import time
import json
import requests
import pandas as pd

BASE = "https://fapi.binance.com"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CryptoForge-Research/1.0"})


def _get(path, params, retries=4):
    url = BASE + path
    for i in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (418, 429):
                time.sleep(2 ** i)
                continue
            r.raise_for_status()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return None


def get_top_perp_symbols(n=60, min_quote_volume=50_000_000):
    tickers = _get("/fapi/v1/ticker/24hr", {})
    rows = []
    for t in tickers:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        if "_" in s:
            continue
        if any(s.endswith(x) for x in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
            continue
        try:
            qv = float(t["quoteVolume"])
            last = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue
        if qv < min_quote_volume or last <= 0:
            continue
        rows.append({"symbol": s, "quote_volume": qv, "last": last})
    df = pd.DataFrame(rows).sort_values("quote_volume", ascending=False).reset_index(drop=True)
    return df.head(n)


def fetch_klines(symbol, interval, start_ms=None, end_ms=None, limit=1500):
    out = []
    cursor = start_ms
    while True:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if cursor is not None:
            params["startTime"] = cursor
        if end_ms is not None:
            params["endTime"] = end_ms
        batch = _get("/fapi/v1/klines", params)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < limit:
            break
        cursor = batch[-1][0] + 1
        if end_ms is not None and cursor >= end_ms:
            break
        time.sleep(0.06)
    if not out:
        return pd.DataFrame()
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore"]
    df = pd.DataFrame(out, columns=cols)
    for c in ["open", "high", "low", "close", "volume", "qav", "tbbav", "tbqav"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


END_MS = int(time.time() * 1000)
START_MS = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp() * 1000)


def cache_klines(symbol, interval):
    path = os.path.join(DATA_DIR, f"{symbol}_{interval}.csv")
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return pd.read_csv(path, parse_dates=["timestamp"])
    df = fetch_klines(symbol, interval, start_ms=START_MS, end_ms=END_MS)
    if df.empty:
        return df
    df.to_csv(path, index=False)
    return df


def cache_funding(symbol):
    path = os.path.join(DATA_DIR, f"{symbol}_funding.csv")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        return pd.read_csv(path, parse_dates=["timestamp"])
    out = []
    cursor = START_MS
    while True:
        batch = _get("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": cursor, "limit": 1000})
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 1000:
            break
        cursor = batch[-1]["fundingTime"] + 1
        time.sleep(0.05)
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df[["timestamp", "fundingRate"]].drop_duplicates("timestamp").sort_values("timestamp")
    df.to_csv(path, index=False)
    return df


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    intervals = sys.argv[2].split(",") if len(sys.argv) > 2 else ["1d"]
    uni = get_top_perp_symbols(n=n)
    uni.to_csv(os.path.join(DATA_DIR, "universe.csv"), index=False)
    print(f"Universe: {len(uni)} symbols, top vol ${uni['quote_volume'].iloc[0]/1e9:.1f}B")
    for interval in intervals:
        for i, sym in enumerate(uni["symbol"]):
            df = cache_klines(sym, interval)
            print(f"[{i+1}/{len(uni)}] {sym} {interval}: {len(df)} rows")
    for i, sym in enumerate(uni["symbol"]):
        df = cache_funding(sym)
        print(f"[{i+1}/{len(uni)}] {sym} funding: {len(df)} rows")
    print("DONE")
