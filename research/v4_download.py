"""V4 data (research/V4_PREREG.md) from data.binance.vision. Resumable.

  py research/v4_download.py oi     # daily open-interest snapshots for universe symbol-days
  py research/v4_download.py spot   # spot daily closes for the carry test (B)

oi   -> research/data/oi/<SYM>.csv   last 5-minute metrics row of each UTC day
spot -> research/data/spot/<PERP_SYM>.csv   spot close in perp units (1000X perps map to X spot x1000)
"""
import io
import os
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
import strategy_zoo as sz
from strategy_zoo2 import load_full

ROOT = "https://data.binance.vision/data"
OI_DIR = os.path.join(bt.DATA_DIR, "oi")
SPOT_DIR = os.path.join(bt.DATA_DIR, "spot")
OI_START, OI_END = pd.Timestamp("2020-09-01"), pd.Timestamp("2026-08-23")
_local = threading.local()


def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


def fetch_zip(url):
    for i in range(4):
        try:
            r = session().get(url, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                return z.read(z.namelist()[0]).decode("utf-8", errors="replace")
        except Exception:
            pass
    raise RuntimeError(f"failed after retries: {url}")


def oi_tasks(mask):
    m = mask[(mask.index >= OI_START) & (mask.index <= OI_END)]
    need = {}
    for s in m.columns[m.any()]:
        days = m.index[m[s]]
        need[s] = sorted(set(days) | set(days - pd.Timedelta(days=3)))
        need[s] = [d for d in need[s] if OI_START <= d <= OI_END]
    return need


def oi_row(text):
    lines = [ln for ln in text.strip().splitlines() if ln and not ln.startswith("create_time")]
    return lines[-1].split(",") if lines else None


def run_oi():
    os.makedirs(OI_DIR, exist_ok=True)
    close, volume, *_ = load_full()
    need = oi_tasks(sz.pit_mask(close, volume))
    miss_path = os.path.join(OI_DIR, "_missing.txt")
    missing = set(open(miss_path).read().split()) if os.path.exists(miss_path) else set()
    have, tasks = {}, []
    for s, days in need.items():
        p = os.path.join(OI_DIR, f"{s}.csv")
        have[s] = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
        got = set(have[s]["date"]) if len(have[s]) else set()
        for d in days:
            ds = d.strftime("%Y-%m-%d")
            if ds not in got and f"{s},{ds}" not in missing:
                tasks.append((s, ds))
    print(f"OI: {len(need)} symbols, {sum(len(v) for v in need.values())} symbol-days needed, "
          f"{len(tasks)} to fetch", flush=True)
    cols = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
            "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
            "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
    new, lock = {}, threading.Lock()

    def job(t):
        s, ds = t
        text = fetch_zip(f"{ROOT}/futures/um/daily/metrics/{s}/{s}-metrics-{ds}.zip")
        return s, ds, (oi_row(text) if text else None)

    def flush():
        for s, rows in new.items():
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=["date"] + cols)
            out = pd.concat([have[s], df], ignore_index=True) if len(have[s]) else df
            have[s] = out.drop_duplicates("date").sort_values("date")
            have[s].to_csv(os.path.join(OI_DIR, f"{s}.csv"), index=False)
        new.clear()
        with open(miss_path, "w") as f:
            f.write("\n".join(sorted(missing)))

    done = 0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = [ex.submit(job, t) for t in tasks]
        for f in as_completed(futs):
            s, ds, row = f.result()
            with lock:
                if row and len(row) >= len(cols):
                    new.setdefault(s, []).append([ds] + row[:len(cols)])
                else:
                    missing.add(f"{s},{ds}")
                done += 1
                if done % 5000 == 0:
                    flush()
                    print(f"  {done}/{len(tasks)} fetched, {len(missing)} missing", flush=True)
    flush()
    print(f"OI done: {done} fetched, {len(missing)} missing", flush=True)


def run_spot():
    os.makedirs(SPOT_DIR, exist_ok=True)
    close, volume, *_ = load_full()
    m30 = sz.pit_mask(close, volume, top_n=30)
    syms = [s for s in m30.columns[m30.any()]]
    months = pd.period_range("2019-09", "2026-09", freq="M")
    print(f"spot: {len(syms)} perp symbols ever in top-30", flush=True)

    def candidates(s):
        out = [(s, 1.0)]
        if s.startswith("1000000"):
            out.append((s[7:], 1e6))
        elif s.startswith("1000"):
            out.append((s[4:], 1000.0))
        return out

    def month_rows(spot, per):
        text = fetch_zip(f"{ROOT}/spot/monthly/klines/{spot}/1d/{spot}-1d-{per}.zip")
        if not text:
            return []
        rows = []
        for ln in text.strip().splitlines():
            f = ln.split(",")
            if not f[0].isdigit():
                continue
            t = int(f[0])
            t = t // 1000 if t > 10 ** 14 else t  # 2025+ archives use microseconds
            rows.append((pd.Timestamp(t, unit="ms").normalize(), float(f[4])))
        return rows

    def job(s):
        p = os.path.join(SPOT_DIR, f"{s}.csv")
        if os.path.exists(p):
            return s, "cached"
        first = m30.index[m30[s]].min().to_period("M") - 1
        span = [per for per in months if per >= first]
        for spot, factor in candidates(s):
            rows = []
            for per in span:
                rows += month_rows(spot, str(per))
            if rows:
                df = pd.DataFrame(rows, columns=["date", "spot_close"]).drop_duplicates("date")
                df["spot_close"] *= factor
                df["spot_symbol"], df["factor"] = spot, factor
                df.sort_values("date").to_csv(p, index=False)
                return s, f"{spot} x{factor:g} ({len(df)} days)"
        return s, "no spot market"

    with ThreadPoolExecutor(max_workers=12) as ex:
        for f in as_completed([ex.submit(job, s) for s in syms]):
            s, msg = f.result()
            print(f"  {s:<18} {msg}", flush=True)


if __name__ == "__main__":
    {"oi": run_oi, "spot": run_spot}[sys.argv[1]]()
