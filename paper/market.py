import os
import time
import requests
import pandas as pd

from . import config as cfg

_session = requests.Session()
_session.headers.update({"User-Agent": "CryptoForge-Paper/1.0"})

CACHE_DIR = os.path.join(cfg.BASE_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL_HOURS = float(os.environ.get("CF_CACHE_TTL_HOURS", "4"))
REQUEST_PAUSE = 0.08


class RateLimited(RuntimeError):
    pass


def _get(path, params=None, retries=4):
    for i in range(retries):
        try:
            r = _session.get(cfg.BASE_URL + path, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data.get("code") == -1003:
                    raise RateLimited(data.get("msg", "rate limited"))
                return data
            if r.status_code in (418, 429):
                time.sleep(2 ** i)
                continue
            r.raise_for_status()
        except RateLimited:
            raise
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1.0 * (i + 1))
    raise RateLimited(f"{path} unavailable after {retries} attempts")


def candidate_symbols():
    tickers = _get("/fapi/v1/ticker/24hr") or []
    if not isinstance(tickers, list) or not tickers:
        raise RuntimeError("ticker endpoint returned no data")
    rows = []
    for t in tickers:
        s = t.get("symbol", "")
        if not s.endswith("USDT") or "_" in s:
            continue
        if any(s.endswith(x) for x in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
            continue
        try:
            qv = float(t["quoteVolume"])
            last = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue
        if last <= 0:
            continue
        rows.append({"symbol": s, "quote_volume": qv, "last": last})
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no eligible symbols in ticker response")
    df = df.sort_values("quote_volume", ascending=False)
    return df.head(cfg.CANDIDATE_POOL)["symbol"].tolist()


def _cache_path(symbol, limit):
    return os.path.join(CACHE_DIR, f"{symbol}_1d_{limit}.csv")


def _cache_fresh(path):
    if not os.path.exists(path):
        return False
    age_h = (time.time() - os.path.getmtime(path)) / 3600.0
    return age_h < CACHE_TTL_HOURS


def daily_klines(symbol, limit=None, use_cache=True):
    limit = limit or cfg.KLINES_LIMIT
    path = _cache_path(symbol, limit)
    if use_cache and _cache_fresh(path):
        try:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
            return df
        except Exception:
            pass
    data = _get("/fapi/v1/klines", {"symbol": symbol, "interval": "1d", "limit": limit})
    if not data:
        return pd.DataFrame()
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore"]
    df = pd.DataFrame(data, columns=cols)
    df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"]), unit="ms", utc=True).dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume", "qav", "tbqav", "num_trades"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    try:
        df.to_csv(path, index=False)
    except Exception:
        pass
    time.sleep(REQUEST_PAUSE)
    return df


def load_market(candidate_pool=None):
    symbols = candidate_pool or candidate_symbols()
    closes, volumes = {}, {}
    for s in symbols:
        try:
            df = daily_klines(s)
        except RateLimited:
            raise
        if df.empty or len(df) < cfg.MIN_HISTORY_DAYS:
            continue
        closes[s] = df.set_index("timestamp")["close"]
        volumes[s] = df.set_index("timestamp")["volume"]
    close = pd.DataFrame(closes).sort_index()
    volume = pd.DataFrame(volumes).reindex(close.index)
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    close = close[close.index < today]
    volume = volume.reindex(close.index)
    return close, volume


def live_prices(symbols=None):
    data = _get("/fapi/v1/ticker/price") or []
    prices = {d["symbol"]: float(d["price"]) for d in data if "price" in d}
    if symbols is None:
        return prices
    return {s: prices[s] for s in symbols if s in prices}


def funding_since(symbol, start_ms):
    out = []
    cursor = int(start_ms)
    while True:
        data = _get("/fapi/v1/fundingRate",
                    {"symbol": symbol, "startTime": cursor, "limit": 1000})
        if not data:
            break
        out.extend(data)
        if len(data) < 1000:
            break
        cursor = data[-1]["fundingTime"] + 1
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True).dt.tz_localize(None)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce").clip(-cfg.FUNDING_CAP, cfg.FUNDING_CAP)
    return df[["timestamp", "fundingRate"]].drop_duplicates("timestamp").sort_values("timestamp")


def funding_daily_recent(symbols, days=None, index=None):
    days = days or cfg.FUNDING_SIGNAL_DAYS
    start = int((pd.Timestamp.now(tz="UTC").tz_localize(None) - pd.Timedelta(days=days)).timestamp() * 1000)
    series = {}
    for s in symbols:
        try:
            df = funding_since(s, start)
        except RateLimited:
            raise
        if df.empty:
            continue
        series[s] = df.set_index("timestamp")["fundingRate"].resample("1D").sum()
        time.sleep(REQUEST_PAUSE)
    if not series:
        return pd.DataFrame(index=index)
    out = pd.DataFrame(series)
    if index is not None:
        out = out.reindex(index).fillna(0.0)
    return out
