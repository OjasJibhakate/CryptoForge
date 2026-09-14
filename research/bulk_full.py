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

RAW = ["timestamp", "open", "high", "low", "close", "volume",
       "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore"]
KEEP = ["timestamp", "open", "high", "low", "close", "volume", "qav", "tbqav", "num_trades"]

START_MS = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp() * 1000)
_session = requests.Session()
_lock = threading.Lock()


def _prep(df):
    df = df.copy()
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].notna()]
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True).dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume", "qav", "tbqav", "num_trades"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).drop_duplicates("timestamp").sort_values("timestamp")
    return df[[c for c in KEEP if c in df.columns]].reset_index(drop=True)


def rest_full(symbol):
    out = []
    cursor = START_MS
    while True:
        try:
            r = _session.get(f"{FAPI}/fapi/v1/klines",
                             params={"symbol": symbol, "interval": "1d", "startTime": cursor, "limit": 1500},
                             timeout=20)
        except Exception:
            return pd.DataFrame()
        if r.status_code != 200:
            return pd.DataFrame()
        b = r.json()
        if not isinstance(b, list) or not b:
            break
        out.extend(b)
        if len(b) < 1500:
            break
        cursor = b[-1][0] + 1
    if not out:
        return pd.DataFrame()
    return _prep(pd.DataFrame(out, columns=RAW))


def vision_full(symbol):
    keys, token = [], None
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
            nx = root.find(f"{NS}NextContinuationToken")
            token = nx.text if nx is not None else None
            if not token:
                break
        else:
            break
    frames = []
    for key in keys:
        try:
            r = _session.get(f"{BUCKET}/{key}", timeout=30)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=RAW, on_bad_lines="skip")
            frames.append(_prep(df))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def work(symbol):
    path = os.path.join(DATA, f"{symbol}_1df.csv")
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return "cached"
    df = rest_full(symbol)
    src = "rest"
    if df.empty:
        df = vision_full(symbol)
        src = "vision"
    if df.empty:
        return "empty"
    df.to_csv(path, index=False)
    return src


if __name__ == "__main__":
    syms = json.load(open(os.path.join(DATA, "all_symbols.json")))
    targets = [s for s in syms if s.endswith("USDT") and "SETTLED" not in s]
    counts = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(work, s): s for s in targets}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = f"err"
            counts[r] = counts.get(r, 0) + 1
    print("DONE", counts)
