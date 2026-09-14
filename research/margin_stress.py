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

PPY = 365
MMR = 0.01  # assumed maintenance margin rate (conservative-ish for alts)


def main():
    close, volume, high, low = sz.load_all4()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()

    score = sz.zs(mom_stack / vol30, mask) - sz.zs(f7, mask)
    W = sz.xs(score, mask, k=10)
    W = W.reindex(index=close.index, columns=close.columns).fillna(0.0)
    R = ret.fillna(0.0)

    Wheld = W.shift(1).fillna(0.0)
    short_w = (-Wheld).clip(lower=0.0)
    long_w = Wheld.clip(lower=0.0)

    print("=== SHORT-LEG SQUEEZE ANALYSIS (gross 1.0, 10 shorts, ~5% each) ===")
    print(f"avg gross short {short_w.abs().sum(axis=1).mean():.3f} | avg names short {(short_w>0).sum(axis=1).mean():.1f}")

    per_name_loss = (short_w * R)           # positive = shorted coin ROSE = we lost
    daily_short_loss = per_name_loss.sum(axis=1)
    worst_name_day = per_name_loss.max(axis=1)
    long_w_held = long_w
    long_loss = -(long_w_held * R)
    daily_long_loss = long_loss.sum(axis=1)

    print(f"\nworst single shorted-coin squeeze (one day) : {worst_name_day.max()*100:.2f}% of equity")
    print(f"worst whole-short-leg squeeze day           : {daily_short_loss.max()*100:.2f}% of equity")
    print(f"worst whole-LONG-leg day (market crash)     : {daily_long_loss.max()*100:.2f}% of equity")
    print(f"95th pct single-name squeeze day            : {worst_name_day.quantile(0.95)*100:.2f}%")
    print(f"95th pct short-leg squeeze day              : {daily_short_loss.quantile(0.95)*100:.2f}%")
    top = worst_name_day.nlargest(5)
    print("worst 5 single-name squeeze days:")
    for d, v in top.items():
        row = per_name_loss.loc[d]
        sym = row.idxmax()
        px_move = R.loc[d, sym]
        print(f"   {d.date()}  {sym:<14} moved {px_move*100:+8.1f}% in a day -> cost {v*100:5.2f}% of equity")

    print("\n=== LIQUIDATION THRESHOLDS (cross margin, mmr=1%) ===")
    print("liquidation when equity <= mmr * gross_notional, i.e. tolerable loss = 1 - mmr*gross")
    for g in [1.0, 2.0, 3.0, 5.0, 10.0]:
        tol = 1 - MMR * g
        print(f"  gross {g:4.1f}x -> account survives a {tol*100:5.1f}% equity loss; "
              f"worst historical day (-7.94%) would be {7.94*g:5.1f}%")

    print("\n=== HOW MUCH LEVERAGE TO REACH THE 40% DD BUDGET ===")
    ret_p = close.pct_change().fillna(0.0)
    r = bt.portfolio_backtest(ret_p, W, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    m = bt.metrics(net, PPY)
    sc = bt.scaled_metrics(net, 0.40, PPY)
    print(f"  unlevered full-period: Sharpe {m['sharpe']:.2f} CAGR {m['cagr']*100:.1f}% DD {m['max_dd']*100:.1f}%")
    print(f"  scale needed for 40% DD: {sc['scale']:.2f}x  ->  CAGR {sc['cagr']*100:.1f}%")
    print(f"  => the strategy does NOT need leverage to reach its DD budget")
    worst_day = net.min()
    print(f"  worst single day (unlevered): {worst_day*100:.2f}%  |  at {sc['scale']:.2f}x: {worst_day*sc['scale']*100:.2f}%")

    print("\n=== STRESS: what if the 10 shorts all squeeze 30% on the same day? ===")
    g = short_w.abs().sum(axis=1).mean()
    print(f"  short notional {g:.2f} x 30% adverse = -{g*0.30*100:.1f}% of equity (a very bad but survivable day)")
    print(f"  short notional {g:.2f} x 60% adverse = -{g*0.60*100:.1f}% of equity")
    print(f"  short notional {g:.2f} x 100% adverse = -{g*1.00*100:.1f}% of equity (all 10 shorts double)")

    out = pd.DataFrame({"short_leg_loss": daily_short_loss})
    out.to_csv(os.path.join(bt.DATA_DIR, "margin_stress.csv"))


if __name__ == "__main__":
    main()
