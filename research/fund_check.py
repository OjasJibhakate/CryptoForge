import os
import glob
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    rows = []
    for path in glob.glob(os.path.join(DATA, "*_funding.csv")):
        sym = os.path.basename(path)[:-12]
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        if df.empty:
            continue
        rows.append({"symbol": sym, "n": len(df), "mean": df["fundingRate"].mean(),
                     "min": df["fundingRate"].min(), "max": df["fundingRate"].max()})
    s = pd.DataFrame(rows)
    print(f"funding files: {len(s)}")
    print(f"global single-period rate: min {s['min'].min():.6f} max {s['max'].max():.6f}")
    print(f"\nTOP 10 by max single funding rate:")
    print(s.sort_values("max", ascending=False).head(10).round(6).to_string(index=False))
    print(f"\nTOP 10 by min single funding rate (most negative):")
    print(s.sort_values("min").head(10).round(6).to_string(index=False))
    bad = s[(s["max"] > 0.0075) | (s["min"] < -0.0075)]
    print(f"\nsymbols breaching +/-0.75% cap: {len(bad)}")
    print(bad.round(6).to_string(index=False))

    # daily-summed extremes
    daily_all = []
    for path in glob.glob(os.path.join(DATA, "*_funding.csv")):
        sym = os.path.basename(path)[:-12]
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        d = df.set_index("timestamp")["fundingRate"].resample("1D").sum()
        daily_all.append(d.rename(sym))
    daily = pd.DataFrame(daily_all)
    flat = daily.stack().dropna()
    print(f"\ndaily-summed funding: mean {flat.mean()*1e4:.3f} bps | median {flat.median()*1e4:.3f} bps")
    print(f"  p99 {flat.quantile(0.99)*1e4:.2f} | p99.9 {flat.quantile(0.999)*1e4:.2f} | max {flat.max()*1e4:.1f} bps")
    top = flat.sort_values(ascending=False).head(10)
    print("  top daily funding values:")
    for (d, sym), v in top.items():
        print(f"    {d.date()} {sym:<16} {v*1e4:9.1f} bps")


if __name__ == "__main__":
    main()
