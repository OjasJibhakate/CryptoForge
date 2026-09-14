import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import survivorship as sv


def main():
    close, volume = sv.load_all_panels()
    funding = sv.funding_panel_all(close)
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    w = sv.xs_weights(close, mask, k=10)
    w_held = w.shift(1).fillna(0.0)
    f = funding.reindex(index=w_held.index, columns=w_held.columns).fillna(0.0)

    long_w = w_held.clip(lower=0.0)
    short_w = (-w_held).clip(lower=0.0)
    fund_from_shorts = (short_w * f).sum(axis=1)
    fund_paid_longs = (long_w * f).sum(axis=1)
    net_fund = fund_from_shorts - fund_paid_longs

    print(f"avg gross long  {long_w.sum(axis=1).mean():.3f}")
    print(f"avg gross short {short_w.sum(axis=1).mean():.3f}")
    print(f"avg funding rate of LONG leg  {((long_w*f).sum(axis=1)/long_w.sum(axis=1).replace(0,np.nan)).mean()*1e4:7.3f} bps/day")
    print(f"avg funding rate of SHORT leg {((short_w*f).sum(axis=1)/short_w.sum(axis=1).replace(0,np.nan)).mean()*1e4:7.3f} bps/day")
    print(f"funding INCOME from shorts  {fund_from_shorts.mean()*1e4:7.3f} bps/day  ({fund_from_shorts.mean()*365*100:.1f}%/yr)")
    print(f"funding PAID on longs       {fund_paid_longs.mean()*1e4:7.3f} bps/day  ({fund_paid_longs.mean()*365*100:.1f}%/yr)")
    print(f"NET funding                 {net_fund.mean()*1e4:7.3f} bps/day  ({net_fund.mean()*365*100:.1f}%/yr)")

    print("\nraw funding-rate distribution (all symbols, all days):")
    fr = funding.replace(0, np.nan).stack().dropna()
    print(f"  mean {fr.mean()*1e4:.3f} bps/day | median {fr.median()*1e4:.3f} "
          f"| p90 {fr.quantile(0.9)*1e4:.2f} | max {fr.max()*1e4:.1f} bps/day")
    print(f"  fraction positive: {(fr>0).mean()*100:.1f}%")

    print("\nfunding income with a capture haircut:")
    ret = close.pct_change().fillna(0.0)
    base = bt.portfolio_backtest(ret, w, funding=None, leverage_cap=1.0, asset_cap=1.0, ppy=365)["net"]
    for h in [1.0, 0.5, 0.25, 0.0]:
        net = base + net_fund * h
        m = bt.metrics(net, 365)
        print(f"  capture {h*100:3.0f}%: Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:6.1f}%  DD {m['max_dd']*100:6.1f}%")


if __name__ == "__main__":
    main()
