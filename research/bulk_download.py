import os
import sys
import io
import json
import time
import zipfile
import threading
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FAPI = "https://fapi.binance.com"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

COLS = ["timestamp", "open", "high", "low", "close", "volume",
        "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore"]
START_MS = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp() * 1000)
END_MS = int(time.time() * 1000)

_lock = threading.Lock()
_session = requests.Session()


def rest_klines(symbol):
    out = []
    cursor = START_MS
    while True:
        try:
            r = _session.get(f"{FAPI}/fapi/v1/klines",
                             params={"symbol": symbol, "interval": "1d",
                                     "startTime": cursor, "limit": 1500}, timeout=20)
        except Exception:
            return pd.DataFrame()
        if r.status_code != 200:
            return pd.DataFrame()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 1500:
            break
        cursor = batch[-1][0] + 1
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out, columns=COLS)
    return _clean(df)


def _clean(df):
    df = df.copy()
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].notna()]
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True).dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume", "qav", "tbbav", "tbqav"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).drop_duplicates("timestamp").sort_values("timestamp")
    keep = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].reset_index(drop=True)


def vision_months(symbol):
    keys = []
    token = None
    prefix = f"data/futures/um/monthly/klines/{symbol}/1d/"
    while True:
        params = {"prefix": prefix, "max-keys": 1000, "list-type": 2}
        if token:
            params["continuation-token"] = token
        try:
            r = _session.get(BUCKET, params=params, timeout=25)
            root = ET.fromstring(r.text)
        except Exception:
            break
        for c in root.iter(f"{NS}Contents"):
            k = c.find(f"{NS}Key")
            if k is not None and k.text.endswith(".zip"):
                keys.append(k.text)
        tr = root.find(f"{NS}IsTruncated")
        if tr is not None and tr.text == "true":
            nxt = root.find(f"{NS}NextContinuationToken")
            token = nxt.text if nxt is not None else None
            if not token:
                break
        else:
            break
    return keys


def vision_klines(symbol):
    frames = []
    for key in vision_months(symbol):
        try:
            r = _session.get(f"{BUCKET}/{key}", timeout=30)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            name = z.namelist()[0]
            df = pd.read_csv(z.open(name), header=None, names=COLS)
            frames.append(_clean(df))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def get_daily(symbol):
    path = os.path.join(DATA, f"{symbol}_1d.csv")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        return "cached"
    df = rest_klines(symbol)
    src = "rest"
    if df.empty:
        df = vision_klines(symbol)
        src = "vision"
    if df.empty:
        return "empty"
    df.to_csv(path, index=False)
    return src


def get_funding(symbol):
    path = os.path.join(DATA, f"{symbol}_funding.csv")
    if os.path.exists(path) and os.path.getsize(path) > 50:
        return "cached"
    out = []
    cursor = START_MS
    while True:
        try:
            r = _session.get(f"{FAPI}/fapi/v1/fundingRate",
                             params={"symbol": symbol, "startTime": cursor, "limit": 1000}, timeout=20)
        except Exception:
            break
        if r.status_code != 200:
            break
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 1000:
            break
        cursor = batch[-1]["fundingTime"] + 1
    if not out:
        return "empty"
    df = pd.DataFrame(out)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True).dt.tz_localize(None)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df[["timestamp", "fundingRate"]].drop_duplicates("timestamp").sort_values("timestamp")
    df.to_csv(path, index=False)
    return "ok"


def work(symbol):
    src = get_daily(symbol)
    fnd = get_funding(symbol) if src != "empty" else "skip"
    with _lock:
        print(f"{symbol:<22} daily={src:<7} funding={fnd}", flush=True)
    return src


if __name__ == "__main__":
    all_syms = json.load(open(os.path.join(DATA, "all_symbols.json")))
    targets = [s for s in all_syms if s.endswith("USDT") and "SETTLED" not in s]
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if limit:
        targets = targets[:limit]
    print(f"bulk download: {len(targets)} symbols")
    counts = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(work, s): s for s in targets}
        for i, f in enumerate(as_completed(futs)):
            try:
                src = f.result()
            except Exception as e:
                src = f"err:{e}"
            counts[src] = counts.get(src, 0) + 1
    print("DONE", counts)
