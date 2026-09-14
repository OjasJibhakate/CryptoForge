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
from strategy_zoo2 import load_full

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
N_TRIALS_TOTAL = 50


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    tbr = (tbqav / qav.replace(0, np.nan)).clip(0.2, 0.8)

    mom = sz.zs(mom_stack / vol30, mask)
    ftilt = mom - sz.zs(f7, mask)
    ofi = sz.zs(tbr.rolling(5).mean(), mask)
    lowvol = -sz.zs(vol30, mask)
    btc = close["BTCUSDT"]
    ma200 = btc.rolling(200).mean()
    regime = (btc > ma200).astype(float)
    regime_soft = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=btc.index)

    def ev(name, score, k=10, overlay=None):
        w = sz.xs(score, mask, k=k)
        if overlay is not None:
            w = w.mul(overlay, axis=0)
        r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)
        return name, r["net"], w

    cands = [
        ("mom (baseline)", mom, None),
        ("mom - funding tilt", ftilt, None),
        ("mom + OFI", mom + ofi, None),
        ("mom + regime", mom, regime),
        ("mom soft-regime (1/0.5)", mom, regime_soft),
        ("ftilt + OFI", ftilt + ofi, None),
        ("ftilt + regime", ftilt, regime),
        ("ftilt + soft-regime", ftilt, regime_soft),
        ("ftilt + OFI + regime", ftilt + ofi, regime),
        ("ftilt + OFI + soft-regime", ftilt + ofi, regime_soft),
        ("ftilt + OFI - lowvol + soft-regime", ftilt + ofi - 0.5 * lowvol, regime_soft),
    ]

    print(f"=== WAVE 3: COMBINATIONS ({close.shape[1]} symbols) ===\n")
    results = {}
    rows = []
    for name, score, ov in cands:
        nm, net, w = ev(name, score, overlay=ov)
        results[nm] = net
        m = bt.metrics(net, PPY)
        o = bt.metrics(net[net.index >= SPLIT], PPY)
        i = bt.metrics(net[net.index < SPLIT], PPY)
        sc = bt.scaled_metrics(net, 0.40, PPY)
        rows.append({"strategy": nm, "is": i["sharpe"], "oos": o["sharpe"], "full": m["sharpe"],
                     "cagr": m["cagr"] * 100, "dd": m["max_dd"] * 100, "at40dd": sc["cagr"] * 100,
                     "scale": sc["scale"]})
    df = pd.DataFrame(rows).sort_values("at40dd", ascending=False)
    print(df.round(2).to_string(index=False))

    print("\n=== BLENDS of the top 4 (weight-averaged, no selection on k) ===")
    top = ["ftilt + OFI + soft-regime", "ftilt + soft-regime", "ftilt + OFI", "mom + OFI"]
    wb = None
    for nm, score, ov in cands:
        if nm in top:
            w = sz.xs(score, mask, k=10)
            if ov is not None:
                w = w.mul(ov, axis=0)
            wb = w if wb is None else wb + w
    wb = wb / len(top)
    r = bt.portfolio_backtest(ret.fillna(0.0), wb, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    blend_net = r["net"]
    m = bt.metrics(blend_net, PPY)
    o = bt.metrics(blend_net[blend_net.index >= SPLIT], PPY)
    sc = bt.scaled_metrics(blend_net, 0.40, PPY)
    print(f"BLEND: full Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:.1f}%  DD {m['max_dd']*100:.1f}%  "
          f"at40DD {sc['cagr']*100:.1f}%  OOS {o['sharpe']:.2f}")

    for label, net in [("ftilt + OFI + soft-regime", results["ftilt + OFI + soft-regime"]),
                       ("BLEND", blend_net)]:
        print(f"\nsub-periods — {label}:")
        idx = net.index
        b = np.linspace(0, len(idx), 6).astype(int)
        for j in range(5):
            seg = net.iloc[b[j]:b[j + 1]]
            sm = bt.metrics(seg, PPY)
            print(f"   {idx[b[j]].date()} -> {idx[b[j+1]-1].date()}: Sharpe {sm['sharpe']:5.2f}  "
                  f"CAGR {sm['cagr']*100:7.1f}%  DD {sm['max_dd']*100:6.1f}%")

    print(f"\n=== MULTIPLE-TESTING: now ~{N_TRIALS_TOTAL} strategies tried across wave 1+2 ===")
    print(f"Bonferroni threshold |t| > {2.88:.2f} (25 trials) / {3.29:.2f} (50 trials)")
    for nm in ["ftilt + OFI + soft-regime", "ftilt + soft-regime", "ftilt + OFI", "mom + OFI"]:
        net = results[nm]
        oos = net[net.index >= SPLIT]
        t = bt.metrics(oos, PPY)["sharpe"] * np.sqrt(len(oos) / PPY)
        print(f"  {nm:<34} OOS t = {t:5.2f}  {'PASS' if t > 3.29 else 'marginal'}")

    pd.DataFrame({"net": blend_net, "equity": (1 + blend_net).cumprod()}).to_csv(
        os.path.join(bt.DATA_DIR, "wave3_blend_equity.csv"))


if __name__ == "__main__":
    main()
