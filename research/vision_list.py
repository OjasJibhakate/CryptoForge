import os
import sys
import json
import time
import xml.etree.ElementTree as ET
import requests

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def list_prefix(prefix, delimiter="/"):
    out = []
    token = None
    pages = 0
    while True:
        params = {"prefix": prefix, "max-keys": 1000, "list-type": 2}
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        r = requests.get(BUCKET, params=params, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        pages += 1
        for cp in root.iter(f"{NS}CommonPrefixes"):
            p = cp.find(f"{NS}Prefix")
            if p is not None:
                out.append(p.text)
        for c in root.iter(f"{NS}Contents"):
            k = c.find(f"{NS}Key")
            if k is not None:
                out.append(k.text)
        truncated = root.find(f"{NS}IsTruncated")
        if truncated is not None and truncated.text == "true":
            nxt = root.find(f"{NS}NextContinuationToken")
            token = nxt.text if nxt is not None else None
            if not token:
                break
        else:
            break
        time.sleep(0.03)
    print(f"  (list_prefix {prefix}: {pages} pages, {len(out)} entries)")
    return out


if __name__ == "__main__":
    prefixes = list_prefix("data/futures/um/monthly/klines/", delimiter="/")
    symbols = sorted({p.rstrip("/").split("/")[-1] for p in prefixes})
    print(f"total ever-listed symbols: {len(symbols)}")
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "data", "all_symbols.json"), "w") as f:
        json.dump(symbols, f)
    usdt = [s for s in symbols if s.endswith("USDT") and "SETTLED" not in s]
    print(f"USDT-quoted symbols: {len(usdt)}")
    cur = []
    uni = os.path.join(here, "data", "universe.csv")
    if os.path.exists(uni):
        import pandas as pd
        cur = pd.read_csv(uni)["symbol"].tolist()
    have = set(cur)
    delisted_or_missing = [s for s in usdt if not os.path.exists(os.path.join(here, "data", f"{s}_1d.csv"))]
    print(f"USDT symbols with NO local 1d data yet: {len(delisted_or_missing)}")
    print("sample:", delisted_or_missing[:30])

