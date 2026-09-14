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

TARGET = 0.03          # +3% take profit (their observed median win)
MAX_HOLD = 60          # days we are willing to hold waiting for recovery
LEV = 5                # their typical leverage
DROP = -0.03           # entry trigger: coin down 3% over 3 days


def main():
    close, volume, high, low = sz.load_all4()
    mask = sz.pit_mask(close, volume)
    C = close.to_numpy(float)
    H = high.to_numpy(float)
    L = low.to_numpy(float)
    M = mask.to_numpy(bool)
    T, A = C.shape
    print(f"panel {A} symbols x {T} days")

    ret3 = np.full_like(C, np.nan)
    ret3[3:] = C[3:] / C[:-3] - 1.0
    signal = (ret3 < DROP) & M & np.isfinite(C)
    print(f"signals (dip-buys): {signal.sum():,}")

    hold = np.zeros((T, A), np.int16)
    hit = np.zeros((T, A), bool)
    open_now = signal.copy()
    for h in range(1, MAX_HOLD + 1):
        fut_h = H[h:]
        tgt = C[:T - h] * (1.0 + TARGET)
        cond = (fut_h >= tgt) & open_now[:T - h]
        newly = cond & (hold[:T - h] == 0)
        hold[:T - h][newly] = h
        open_now[:T - h] &= ~cond

    sig_idx = np.argwhere(signal)
    t_idx, a_idx = sig_idx[:, 0], sig_idx[:, 1]
    h_vals = hold[t_idx, a_idx]
    won = h_vals > 0
    end_t = np.minimum(t_idx + MAX_HOLD, T - 1)
    entry_px = C[t_idx, a_idx]
    exit_px = np.where(won, entry_px * (1 + TARGET), C[end_t, a_idx])
    price_ret = exit_px / entry_px - 1.0
    valid = np.isfinite(price_ret) & np.isfinite(entry_px) & (entry_px > 0)
    t_idx, a_idx, h_vals, won, end_t = t_idx[valid], a_idx[valid], h_vals[valid], won[valid], end_t[valid]
    price_ret = price_ret[valid]
    n = len(t_idx)

    # 5x leverage: liquidation when the adverse move reaches ~1/leverage
    LIQ = 1.0 / LEV
    margin_ret = np.clip(price_ret * LEV, -1.0, None)
    liquidated = (price_ret <= -LIQ) & ~won

    print(f"\n=== THE STRATEGY: buy a 3% dip, take +3%, NO STOP LOSS, hold up to {MAX_HOLD}d ===")
    print(f"trades                : {n:,}")
    print(f"hit +3% target        : {won.mean()*100:.2f}%   <-- reproduces their ~95% win rate")
    print(f"never recovered       : {(~won).mean()*100:.2f}%")
    print(f"median hold to target : {np.median(h_vals[won]):.0f} day(s)")
    print(f"liquidated at {LEV}x     : {liquidated.mean()*100:.2f}% of ALL trades "
          f"({liquidated.sum():,} trades)")

    if (~won).sum():
        fr = price_ret[~won]
        print(f"\n--- the trades that did NOT recover (n={(~won).sum():,}) ---")
        print(f"  median terminal return : {np.median(fr)*100:+7.1f}%")
        print(f"  mean                   : {fr.mean()*100:+7.1f}%")
        print(f"  5th percentile         : {np.percentile(fr, 5)*100:+7.1f}%")
        print(f"  worst                  : {fr.min()*100:+7.1f}%")
        print(f"  share worse than -20% (a 5x margin wipeout): {(fr <= -LIQ).mean()*100:.1f}%")

    print(f"\n--- EXPECTANCY PER TRADE (in % of that trade's MARGIN, at {LEV}x) ---")
    print(f"  winners : {TARGET*LEV*100:+.1f}%")
    print(f"  losers  : {margin_ret[~won].mean()*100:+.1f}% (mean, floored at -100%)")
    print(f"  EXPECTANCY: {margin_ret.mean()*100:+.2f}% per trade")
    print(f"  breakeven win rate needed at this payoff: "
          f"{abs(margin_ret[~won].mean())/(TARGET*LEV+abs(margin_ret[~won].mean()))*100:.1f}% "
          f"(actual {won.mean()*100:.1f}%)")

    print(f"\n=== CAPITAL LOCK-UP (the real killer) ===")
    exit_day = np.where(won, t_idx + h_vals, np.minimum(t_idx + MAX_HOLD, T - 1))
    delta = np.zeros(T + 1)
    np.add.at(delta, t_idx, 1)
    np.add.at(delta, np.minimum(exit_day + 1, T), -1)
    open_ct = np.cumsum(delta[:T])
    print(f"  trades opened per day (avg)  : {n/T:.1f}")
    print(f"  positions open at once: avg {open_ct.mean():.0f} | median {np.median(open_ct):.0f} | max {open_ct.max():,}")
    losers_open = np.zeros(T)
    np.add.at(losers_open, np.where(won, 0, t_idx), 0)  # placeholder, counted below
    los_delta = np.zeros(T + 1)
    bad = ~won
    np.add.at(los_delta, t_idx[bad], 1)
    np.add.at(los_delta, np.minimum(exit_day[bad] + 1, T), -1)
    los_ct = np.cumsum(los_delta[:T])
    print(f"  STUCK LOSING positions open  : avg {los_ct.mean():.1f} | median {np.median(los_ct):.0f} | "
          f"max {los_ct.max():,} | >0 on {100*(los_ct>0).mean():.0f}% of days")
    print(f"  -> a losing trade occupies capital for up to {MAX_HOLD} days, and they accumulate.")

    print(f"\n=== EQUITY CURVE (5% of capital per trade, {LEV}x, loss floored at the allocation) ===")
    daily = np.zeros(T)
    alloc = 1.0 / 20.0
    for k in range(n):
        e = t_idx[k] + (h_vals[k] if won[k] else min(MAX_HOLD, T - 1 - t_idx[k]))
        daily[min(e, T - 1)] += alloc * margin_ret[k]
    daily = np.clip(daily, -0.99, None)
    curve = (1 + pd.Series(daily, index=close.index)).cumprod()
    dd = (curve / curve.cummax() - 1)
    print(f"  final equity multiplier : {curve.iloc[-1]:.2f}x")
    print(f"  max drawdown            : {dd.min()*100:.1f}%")
    wy = dd.groupby(dd.index.year).min()
    print("  worst drawdown by year  : " + "  ".join(f"{y}:{v*100:.0f}%" for y, v in wy.items()))

    print(f"\n=== SURVIVORSHIP ===")
    never = ~won
    nc = pd.Series(never).groupby(a_idx).mean()
    print(f"  symbols where >50% of dip-buys never recovered: {(nc > 0.5).sum()} of {nc.size}")


if __name__ == "__main__":
    main()
