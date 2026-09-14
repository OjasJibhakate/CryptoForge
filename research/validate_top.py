import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
import strategy_zoo as sz

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
N_TRIALS = 25


def net_of(close, w, fund, fee=5.0, slip=2.0):
    ret = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=fee, slip_bps=slip, ppy=PPY)
    return r["net"]


def subperiods(net, n=5):
    idx = net.index
    b = np.linspace(0, len(idx), n + 1).astype(int)
    out = []
    for i in range(n):
        seg = net.iloc[b[i]:b[i + 1]]
        m = bt.metrics(seg, PPY)
        out.append((str(idx[b[i]].date()), str(idx[b[i + 1] - 1].date()),
                    m["sharpe"], m["cagr"] * 100, m["max_dd"] * 100))
    return out


def tstat(net):
    oos = net[net.index >= SPLIT]
    m = bt.metrics(oos, PPY)
    years = len(oos) / PPY
    return m["sharpe"] * np.sqrt(years), years, m["sharpe"]


def main():
    close, volume, high, low = sz.load_all4()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mkt = ret.mean(axis=1)
    excess = ret.sub(mkt, axis=0)
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    hi60, lo60 = close.rolling(60).max(), close.rolling(60).min()

    def score_for(variant):
        if variant == "baseline":
            return mom_stack / vol30
        if variant == "funding_tilt":
            return sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask)
        if variant == "combo":
            return sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask) - 0.5 * sz.zs(vol30, mask)
        if variant == "in_range":
            return (close - lo60) / (hi60 - lo60).replace(0, np.nan)
        raise ValueError(variant)

    variants = ["baseline", "funding_tilt", "combo", "in_range"]
    nets = {}
    print("=== SUB-PERIOD ROBUSTNESS (k=10) ===")
    for v in variants:
        w = sz.xs(score_for(v), mask, k=10)
        net = net_of(close, w, fund)
        nets[v] = net
        m = bt.metrics(net, PPY)
        print(f"\n{v}: full Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:.1f}%  DD {m['max_dd']*100:.1f}%")
        for s, e, sh, cg, dd in subperiods(net):
            print(f"   {s} -> {e}: Sharpe {sh:5.2f}  CAGR {cg:7.1f}%  DD {dd:6.1f}%")

    print("\n=== PARAMETER STABILITY: k ===")
    rows = []
    for v in variants:
        sc = score_for(v)
        for k in [3, 5, 10, 15, 20, 30]:
            net = net_of(close, sz.xs(sc, mask, k=k), fund)
            m = bt.metrics(net, PPY)
            o = bt.metrics(net[net.index >= SPLIT], PPY)
            rows.append({"variant": v, "k": k, "is_sharpe": bt.metrics(net[net.index < SPLIT], PPY)["sharpe"],
                         "oos_sharpe": o["sharpe"], "full_sharpe": m["sharpe"],
                         "cagr": m["cagr"] * 100, "dd": m["max_dd"] * 100})
    pk = pd.DataFrame(rows)
    print(pk.round(2).to_string(index=False))
    print("\nmean OOS Sharpe by variant (plateau width):")
    print(pk.groupby("variant")[["is_sharpe", "oos_sharpe", "full_sharpe"]].agg(["mean", "min", "max"]).round(2).to_string())

    print("\n=== COST SENSITIVITY (k=10) ===")
    for v in variants:
        line = f"{v:<14}"
        for fee, slip in [(2, 1), (5, 2), (10, 5), (20, 10)]:
            m = bt.metrics(net_of(close, sz.xs(score_for(v), mask, k=10), fund, fee, slip), PPY)
            line += f"  {fee}+{slip}: Sh {m['sharpe']:.2f}/CAGR {m['cagr']*100:5.1f}%"
        print(line)

    print(f"\n=== MULTIPLE-TESTING CHECK ({N_TRIALS} strategies tried) ===")
    thr_bonf = 2.88
    print(f"Bonferroni threshold for 25 trials at 5%: |t| > {thr_bonf:.2f}")
    for v in variants:
        t, yrs, sh = tstat(nets[v])
        verdict = "PASSES" if t > thr_bonf else ("marginal" if t > 1.65 else "FAILS")
        print(f"  {v:<14} OOS Sharpe {sh:5.2f} over {yrs:.1f}y  ->  t = {t:5.2f}  [{verdict}]")

    print("\n=== COMBINED BOOK (top 3 blended, equal weight of weights) ===")
    wb = (sz.xs(score_for("funding_tilt"), mask, k=10)
          + sz.xs(score_for("combo"), mask, k=10)
          + sz.xs(score_for("in_range"), mask, k=10)) / 3.0
    net = net_of(close, wb, fund)
    m = bt.metrics(net, PPY)
    o = bt.metrics(net[net.index >= SPLIT], PPY)
    sc = bt.scaled_metrics(net, 0.40, PPY)
    print(f"blend: full Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:.1f}%  DD {m['max_dd']*100:.1f}%  "
          f"at40DD {sc['cagr']*100:.1f}%  OOS Sharpe {o['sharpe']:.2f}")
    for s, e, sh, cg, dd in subperiods(net):
        print(f"   {s} -> {e}: Sharpe {sh:5.2f}  CAGR {cg:7.1f}%  DD {dd:6.1f}%")
    pd.DataFrame({"net": net, "equity": (1 + net).cumprod()}).to_csv(os.path.join(bt.DATA_DIR, "blend_equity.csv"))


if __name__ == "__main__":
    main()
