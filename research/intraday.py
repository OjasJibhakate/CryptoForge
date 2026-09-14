import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

VAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Crypto_Historical_Vault")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT", "1000PEPEUSDT"]


def load_vault(symbol, tail_rows=800_000):
    path = os.path.join(VAULT, f"{symbol}_MASTER_1M.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, usecols=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=["timestamp"]).drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df.tail(tail_rows)


def resample(df, rule):
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()


def breakeven_table():
    print("\n=== WHY 0.5% SCALPING IS STRUCTURALLY NEGATIVE ===")
    print("breakeven win rate = (target + cost) / (2 * target), symmetric target/stop")
    rows = []
    for target in [0.002, 0.005, 0.010, 0.020]:
        for cost in [0.0007, 0.0010, 0.0015]:
            be = (target + cost) / (2 * target)
            rows.append({"target": f"{target*100:.1f}%", "roundtrip_cost": f"{cost*100:.2f}%",
                         "breakeven_winrate": f"{be*100:.1f}%"})
    print(pd.DataFrame(rows).to_string(index=False))


def intraday_test(rule="15min"):
    print(f"\n=== INTRADAY TEST ({rule}) ===")
    panels = {}
    highs, lows = {}, {}
    for s in SYMBOLS:
        raw = load_vault(s)
        if raw.empty:
            continue
        r = resample(raw, rule)
        panels[s] = r["close"]
        highs[s] = r["high"]
        lows[s] = r["low"]
    close = pd.DataFrame(panels).sort_index()
    high = pd.DataFrame(highs).sort_index()
    low = pd.DataFrame(lows).sort_index()
    print(f"loaded {close.shape[1]} assets, {len(close)} {rule} bars "
          f"({close.index.min()} -> {close.index.max()})")
    ret = close.pct_change().fillna(0.0)
    ppy = bt.PERIODS_PER_YEAR.get({"15min": "15m", "1h": "1h", "1min": "1m"}.get(rule, "1h"), 365 * 24)

    def wbt(w, fee, slip):
        r = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=ppy)
        return r["net"]

    cands = {
        "XS Rev 1-bar": st_rev(close, 1),
        "XS Rev 4-bar": st_rev(close, 4),
        "XS Mom 20-bar": st_xsmom(close, 20),
        "TS Rev (single)": st_tsrev(close, 1),
    }
    for name, w in cands.items():
        for fee, slip, tag in [(0, 0, "zero-cost"), (5, 2, "realistic")]:
            net = wbt(w, fee, slip)
            m = bt.metrics(net, ppy)
            print(f"{name:<18} {tag:<10} Sharpe {m['sharpe']:6.2f}  CAGR {m['cagr']*100:9.1f}%  "
                  f"MaxDD {m['max_dd']*100:8.1f}%  turn {w.diff().abs().sum(axis=1).mean():.3f}")


def st_rev(close, lookback):
    mom = close / close.shift(lookback) - 1
    ranks = mom.rank(axis=1, ascending=False)
    n = mom.notna().sum(axis=1)
    k = max(1, close.shape[1] // 3)
    long = ranks.le(k)
    short = ranks.gt(n - k, axis=0)
    w = short.astype(float) - long.astype(float)
    return w.div(2 * k).fillna(0.0)


def st_xsmom(close, lookback):
    return -st_rev(close, lookback)


def st_tsrev(close, lookback):
    mom = close / close.shift(lookback) - 1
    return (-np.sign(mom)).fillna(0.0)


if __name__ == "__main__":
    breakeven_table()
    for rule in ["1h", "15min"]:
        intraday_test(rule)
