import os
import sys
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import survivorship as sv


def load_funding_raw(cap=None):
    series = {}
    for path in glob.glob(os.path.join(bt.DATA_DIR, "*_funding.csv")):
        sym = os.path.basename(path)[:-12]
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        r = pd.to_numeric(df["fundingRate"], errors="coerce")
        if cap is not None:
            r = r.clip(-cap, cap)
        r.index = pd.DatetimeIndex(df["timestamp"])
        d = r.resample("1D").sum()
        series[sym] = d
    return pd.DataFrame(series)


def eval_case(close, mask, w, funding, label):
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=365)
    net = r["net"]
    full = bt.metrics(net, 365)
    oos = bt.metrics(net[net.index >= pd.Timestamp("2024-01-01")], 365)
    sc = bt.scaled_metrics(net, 0.40, 365)
    print(f"  {label:<28} Sharpe {full['sharpe']:5.2f}  CAGR {full['cagr']*100:6.1f}%  "
          f"DD {full['max_dd']*100:6.1f}%  at40DD {sc['cagr']*100:6.1f}%  OOS_sh {oos['sharpe']:.2f}  "
          f"fund {r['funding'].mean()*1e4:+.2f}bps/d")


def main():
    close, volume = sv.load_all_panels()
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    w = sv.xs_weights(close, mask, k=10)
    idx = close.index
    print("funding cap sensitivity (single-period rate cap):")
    eval_case(close, mask, w, None, "NO funding")
    for cap, name in [(0.04, "raw (cap +-4%)"), (0.0075, "cap +-0.75%"),
                      (0.003, "cap +-0.30%"), (0.001, "cap +-0.10%")]:
        f = load_funding_raw(cap=cap).reindex(idx).fillna(0.0)
        eval_case(close, mask, w, f, name)


if __name__ == "__main__":
    main()
