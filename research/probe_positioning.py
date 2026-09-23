"""Probe Binance PUBLIC futures-data endpoints (no API key needed):
  /futures/data/openInterestHist, globalLongShortAccountRatio,
  takerlongshortRatio, topLongShortPositionRatio.
Checks depth, history length, and symbol coverage for a backtest.
"""
import sys
import requests
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://fapi.binance.com"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "FAKEUSDT"]


def get(path, params):
    r = requests.get(BASE + path, params=params, timeout=20)
    print(f"{path} {params.get('symbol')} period={params.get('period')} limit={params.get('limit')} -> {r.status_code}")
    if r.status_code != 200:
        print("   ", r.text[:200])
        return None
    try:
        d = r.json()
    except Exception as e:
        print("   json fail", e)
        return None
    if isinstance(d, dict):
        print("   dict keys:", list(d.keys())[:5], str(d)[:150])
        return None
    df = pd.DataFrame(d)
    print(f"    rows={len(df)} cols={list(df.columns)}")
    if len(df):
        print("    first:", df.iloc[0].to_dict())
        print("    last :", df.iloc[-1].to_dict())
    return df


for s in SYMS[:5]:
    get("/futures/data/openInterestHist", {"symbol": s, "period": "1d", "limit": 500})
print()
for s in SYMS[:2]:
    get("/futures/data/globalLongShortAccountRatio", {"symbol": s, "period": "1d", "limit": 500})
    get("/futures/data/takerlongshortRatio", {"symbol": s, "period": "1d", "limit": 500})
    get("/futures/data/topLongShortPositionRatio", {"symbol": s, "period": "1d", "limit": 500})
print()
get("/futures/data/openInterestHist", {"symbol": "FAKEUSDT", "period": "1d", "limit": 10})
get("/fapi/v1/allForceOrders", {"limit": 5})
