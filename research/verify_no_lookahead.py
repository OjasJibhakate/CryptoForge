import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import survivorship as sv


def main():
    close, volume = sv.load_all_panels()
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    w = sv.xs_weights(close, mask, k=10)
    funding = sv.funding_panel_all(close)
    ret = close.pct_change().fillna(0.0)
    print("lag sensitivity (extra days of delay before the signal is tradeable):")
    for extra in [0, 1, 2, 3]:
        ww = w.shift(extra) if extra else w
        r = bt.portfolio_backtest(ret, ww, funding=funding, leverage_cap=1.0, asset_cap=1.0,
                                  fee_bps=5.0, slip_bps=2.0, ppy=365)
        m = bt.metrics(r["net"], 365)
        print(f"  extra lag {extra}d: Sharpe {m['sharpe']:5.2f}  CAGR {m['cagr']*100:6.1f}%  DD {m['max_dd']*100:6.1f}%")

    print("\nplacebo test (signals randomly permuted across assets each day):")
    rng = np.random.default_rng(0)
    rand = pd.DataFrame(rng.standard_normal(w.shape), index=w.index, columns=w.columns).where(mask.astype(bool))
    r = bt.portfolio_backtest(ret, rand.clip(-1, 1) * 0.1, funding=None, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=365)
    m = bt.metrics(r["net"], 365)
    print(f"  random long/short: Sharpe {m['sharpe']:5.2f}  CAGR {m['cagr']*100:6.1f}%  DD {m['max_dd']*100:6.1f}%")


if __name__ == "__main__":
    main()
