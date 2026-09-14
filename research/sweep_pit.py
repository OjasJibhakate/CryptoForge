import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import survivorship as sv

SPLIT = pd.Timestamp("2024-01-01")


def main():
    close, volume = sv.load_all_panels()
    ret = close.pct_change().fillna(0.0)
    funding = sv.funding_panel_all(close)
    print(f"panel {close.shape[1]} symbols x {len(close)} days\n")
    rows = []
    for min_adv in [5e6, 20e6, 50e6]:
        for top_n in [40, 60]:
            mask = sv.pit_mask(close, volume, top_n=top_n, min_adv=min_adv)
            w = sv.xs_weights(close, mask, k=10)
            r = bt.portfolio_backtest(ret, w, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                                      fee_bps=5.0, slip_bps=2.0, ppy=365)
            net = r["net"]
            full = bt.metrics(net, 365)
            oos = bt.metrics(net[net.index >= SPLIT], 365)
            ins = bt.metrics(net[net.index < SPLIT], 365)
            sc = bt.scaled_metrics(net, 0.40, 365)
            rows.append({"min_adv": f"${min_adv/1e6:.0f}M", "top_n": top_n,
                         "IS_sh": ins["sharpe"], "OOS_sh": oos["sharpe"], "full_sh": full["sharpe"],
                         "full_cagr": full["cagr"] * 100, "full_dd": full["max_dd"] * 100,
                         "at40dd": sc["cagr"] * 100, "turn": r["turnover"].mean(),
                         "fund_bps": r["funding"].mean() * 1e4, "cost_bps": r["cost"].mean() * 1e4})
    df = pd.DataFrame(rows)
    print(df.round(2).to_string(index=False))
    df.to_csv(os.path.join(bt.DATA_DIR, "pit_sweep.csv"), index=False)

    print("\n=== WITHOUT funding (to isolate funding's contribution) ===")
    for min_adv in [5e6, 20e6]:
        mask = sv.pit_mask(close, volume, top_n=60, min_adv=min_adv)
        w = sv.xs_weights(close, mask, k=10)
        for use_f in [False, True]:
            r = bt.portfolio_backtest(ret, w, funding=(funding if use_f else None),
                                      leverage_cap=1.0, asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=365)
            m = bt.metrics(r["net"], 365)
            print(f"  adv=${min_adv/1e6:.0f}M funding={'on ' if use_f else 'off'}: "
                  f"Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:6.1f}%  DD {m['max_dd']*100:6.1f}%")

    print("\n=== LONG-ONLY vs LONG/SHORT (is the short leg doing the work?) ===")
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    w = sv.xs_weights(close, mask, k=10)
    for name, ww in [("long/short", w), ("long-only", w.clip(lower=0))]:
        r = bt.portfolio_backtest(ret, ww, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                                  fee_bps=5.0, slip_bps=2.0, ppy=365)
        m = bt.metrics(r["net"], 365)
        o = bt.metrics(r["net"][r["net"].index >= SPLIT], 365)
        print(f"  {name:<11}: full Sharpe {m['sharpe']:.2f} CAGR {m['cagr']*100:6.1f}% DD {m['max_dd']*100:6.1f}%"
              f" | OOS Sharpe {o['sharpe']:.2f}")


if __name__ == "__main__":
    main()
