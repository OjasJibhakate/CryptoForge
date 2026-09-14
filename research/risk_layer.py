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
import survivorship as sv

SPLIT = pd.Timestamp("2024-01-01")


def risk_backtest(close, weights, funding, fee_bps=5.0, slip_bps=2.0,
                  vol_target=0.45, vol_window=30, per_name_cap=0.10,
                  dd_trigger=0.15, dd_recover=0.05, dd_scale=0.5, ppy=365):
    ret = close.pct_change().fillna(0.0)
    W = weights.reindex(index=close.index, columns=close.columns).fillna(0.0)
    base = (W.shift(1) * ret).sum(axis=1)
    rv = base.rolling(vol_window).std() * np.sqrt(ppy)
    vol_scale_s = (vol_target / rv).clip(upper=1.0).shift(1).fillna(1.0)

    Wn = W.to_numpy(float)
    Rn = ret.to_numpy(float)
    Fn = funding.reindex(index=close.index, columns=close.columns).fillna(0.0).to_numpy(float) if funding is not None else None
    vs = vol_scale_s.to_numpy(float)
    idx = close.index
    n, m = Wn.shape

    equity = 1.0
    hwm = 1.0
    breach = False
    prev_w = np.zeros(m)
    recs = []
    for i in range(1, n):
        w = np.clip(Wn[i - 1], -per_name_cap, per_name_cap)
        dd = equity / hwm - 1.0
        if not breach and dd <= -dd_trigger:
            breach = True
        elif breach and dd >= -dd_recover:
            breach = False
        gross_scale = dd_scale if breach else 1.0
        w = w * vs[i] * gross_scale

        day = float(np.dot(w, Rn[i]))
        turn = float(np.abs(w - prev_w).sum())
        cost = turn * (fee_bps + slip_bps) / 1e4
        fund = float(-np.dot(w, Fn[i])) if Fn is not None else 0.0
        net = day - cost + fund

        equity *= (1.0 + net)
        hwm = max(hwm, equity)
        prev_w = w
        recs.append((idx[i], net, equity, vs[i], gross_scale, breach, float(np.abs(w).sum())))
    return pd.DataFrame(recs, columns=["date", "net", "equity", "vol_scale", "gross_scale",
                                       "breach", "gross"]).set_index("date")


def compare(close, weights, funding, label, **kw):
    out = risk_backtest(close, weights, funding, **kw)
    net = out["net"]
    full = bt.metrics(net, 365)
    oos = bt.metrics(net[net.index >= SPLIT], 365)
    sc = bt.scaled_metrics(net, 0.40, 365)
    print(f"{label:<28} Sharpe {full['sharpe']:5.2f}  CAGR {full['cagr']*100:6.1f}%  "
          f"DD {full['max_dd']*100:7.1f}%  at40DD {sc['cagr']*100:6.1f}%  "
          f"OOS_sh {oos['sharpe']:5.2f}  gross {out['gross'].mean():.2f}  breach {int(out['breach'].sum())}d")
    return out


def main():
    close, volume = sv.load_all_panels()
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    w = sv.xs_weights(close, mask, k=10)
    funding = sv.funding_panel_all(close)
    print(f"panel {close.shape[1]} symbols x {len(close)} days\n")
    print("=== RISK LAYER ABLATION (each shown at its own 40% DD budget) ===")
    full = compare(close, w, funding, "baseline (no risk layer)", vol_target=99.0, per_name_cap=1.0, dd_trigger=1.0)
    compare(close, w, funding, "+ vol targeting", per_name_cap=1.0, dd_trigger=1.0)
    compare(close, w, funding, "+ per-name cap", vol_target=99.0, dd_trigger=1.0)
    compare(close, w, funding, "+ circuit breaker", vol_target=99.0, per_name_cap=1.0)
    fl = compare(close, w, funding, "FULL risk layer")

    print("\n=== VOL TARGET SENSITIVITY (full layer) ===")
    for vt in [0.25, 0.35, 0.45, 0.60, 99.0]:
        compare(close, w, funding, f"vol target {vt:.2f}", vol_target=vt)
    print("\n=== CIRCUIT BREAKER SENSITIVITY (full layer) ===")
    for trig in [0.10, 0.15, 0.20, 0.25, 1.0]:
        compare(close, w, funding, f"DD trigger {trig:.2f}", dd_trigger=trig)
    fl.to_csv(os.path.join(bt.DATA_DIR, "risk_layer_equity.csv"))
    print("\n5 worst days with full risk layer (%):")
    print((fl["net"].nsmallest(5) * 100).round(2).to_string())


if __name__ == "__main__":
    main()
