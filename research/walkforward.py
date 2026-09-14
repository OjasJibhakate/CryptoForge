import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import strategies as st

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")


def build(interval, symbols=None):
    if symbols is None:
        symbols = pd.read_csv(UNIVERSE)["symbol"].tolist()[:45]
    close = bt.price_panel(symbols, interval, "close")
    high = bt.price_panel(symbols, interval, "high")
    low = bt.price_panel(symbols, interval, "low")
    keep = close.columns[close.notna().sum() > 250]
    return close[keep], high[keep], low[keep]


def backtest_weights(close, interval, w, funding=None, target_dd=0.40):
    ret = close.pct_change().fillna(0.0)
    ppy = bt.PERIODS_PER_YEAR[interval]
    r = bt.portfolio_backtest(ret, w, funding=funding, leverage_cap=1.0,
                              asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=ppy)
    return r["net"], ppy


def subperiods(net, ppy, n=5):
    idx = net.index
    bounds = np.linspace(0, len(idx), n + 1).astype(int)
    out = []
    for i in range(n):
        seg = net.iloc[bounds[i]:bounds[i + 1]]
        m = bt.metrics(seg, ppy)
        m["start"] = str(idx[bounds[i]].date())
        m["end"] = str(idx[bounds[i + 1] - 1].date())
        out.append(m)
    return pd.DataFrame(out)[["start", "end", "cagr", "sharpe", "max_dd", "vol"]]


def param_sweep(close, interval, fn, params, ppy):
    ret = close.pct_change().fillna(0.0)
    rows = []
    for p in params:
        w = fn(close, **p)
        r = bt.portfolio_backtest(ret, w, leverage_cap=1.0, asset_cap=1.0, ppy=ppy)
        m = bt.metrics(r["net"], ppy)
        rows.append({"params": str(p), "sharpe": m["sharpe"], "cagr": m["cagr"],
                     "max_dd": m["max_dd"], "turnover": r["turnover"].mean()})
    return pd.DataFrame(rows)


def report(name, net, ppy):
    from backtest import metrics, scaled_metrics
    full = metrics(net, ppy)
    scaled = scaled_metrics(net, 0.40, ppy)
    print(f"\n--- {name} ---")
    print(f"FULL: Sharpe {full['sharpe']:.2f} | CAGR {full['cagr']*100:.1f}% | "
          f"MaxDD {full['max_dd']*100:.1f}% | at40%DD CAGR {scaled['cagr']*100:.1f}% (x{scaled['scale']:.2f})")
    sp = subperiods(net, ppy, 5)
    for _, row in sp.iterrows():
        print(f"  {row['start']} -> {row['end']}: CAGR {row['cagr']*100:7.1f}%  "
              f"Sharpe {row['sharpe']:5.2f}  MaxDD {row['max_dd']*100:6.1f}%")
    return sp


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "1d"
    close, high, low = build(interval)
    ppy = bt.PERIODS_PER_YEAR[interval]
    print(f"interval={interval} assets={close.shape[1]} {close.index.min().date()}->{close.index.max().date()}")

    print("\n==== PARAM SENSITIVITY: TSMOM lookback (1d) ====")
    print(param_sweep(close, interval, lambda c, lookback: st.tsmom(c, lookback),
                      [{"lookback": x} for x in [10, 20, 30, 45, 60, 90, 120]], ppy).to_string(index=False))

    print("\n==== PARAM SENSITIVITY: MA cross ====")
    print(param_sweep(close, interval, lambda c, fast, slow: st.ma_cross(c, fast, slow),
                      [{"fast": f, "slow": s} for f, s in
                       [(10, 30), (20, 60), (30, 90), (50, 100), (50, 200), (100, 200)]], ppy).to_string(index=False))

    for nm, w in [("TSMOM 30d", st.tsmom(close, 30)),
                  ("MA 50/200", st.ma_cross(close, 50, 200)),
                  ("Donchian 55", st.donchian(close, high, low, 55)),
                  ("XS Mom 30d", st.xs_momentum(close, 30, 5))]:
        net, _ = backtest_weights(close, interval, w)
        report(nm, net, ppy)
