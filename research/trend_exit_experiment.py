import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import strategy_zoo as sz

MAX_HOLD = 60
LEV = 5


def simulate(C, H, M, entry, TP, stop=None, trend_exit=True, MA=None, MOM=None):
    """entry: bool T x A. Returns per-trade outcomes."""
    T, A = C.shape
    entry_px = np.where(entry, C, np.nan)
    open_mask = entry.copy()
    hold = np.zeros((T, A), np.int16)
    reason = np.zeros((T, A), np.int8)   # 1=take profit, 2=trend died, 3=stop

    for h in range(1, MAX_HOLD + 1):
        sl = slice(0, T - h)
        fut_h = H[h:]
        fut_c = C[h:]
        alive = open_mask[sl] & (hold[sl] == 0)
        if not alive.any():
            break
        tp = fut_h >= entry_px[sl] * (1 + TP)
        if stop is not None:
            sd = fut_c <= entry_px[sl] * (1 - stop)
        else:
            sd = np.zeros_like(tp)
        if trend_exit:
            td = (fut_c < MA[h:]) | (MOM[h:] <= 0)
        else:
            td = np.zeros_like(tp)
        fires = (tp | sd | td) & alive
        if fires.any():
            hold[sl][fires] = h
            r = np.zeros(fires.shape, np.int8)
            r = np.where(tp & fires, 1, r)
            r = np.where(sd & fires & (r == 0), 3, r)
            r = np.where(td & fires & (r == 0), 2, r)
            reason[sl][fires] = r[fires]
        open_mask[sl] &= ~fires

    idx = np.argwhere(entry)
    t, a = idx[:, 0], idx[:, 1]
    hh = hold[t, a]
    rr = reason[t, a]
    ep = C[t, a]
    end = np.minimum(t + MAX_HOLD, T - 1)
    ex = np.where(rr == 1, ep * (1 + TP), C[end, a])
    ex = np.where((rr == 0), C[end, a], ex)
    pr = ex / ep - 1.0
    ok = np.isfinite(pr) & (ep > 0)
    return t[ok], a[ok], hh[ok], rr[ok], pr[ok]


def report(name, t, a, hh, rr, pr, C, dates):
    n = len(t)
    won = pr > 0
    mr = np.clip(pr * LEV, -1.0, None)          # return on margin at 5x
    print(f"\n--- {name} ---")
    print(f"  trades {n:,} | win rate {won.mean()*100:5.2f}% | "
          f"exit mix  TP {np.mean(rr==1)*100:4.1f}% / trend {np.mean(rr==2)*100:4.1f}% / "
          f"stop {np.mean(rr==3)*100:4.1f}% / still-open {np.mean(rr==0)*100:4.1f}%")
    print(f"  avg win  {mr[won].mean()*100:+7.1f}% of margin  | avg loss {mr[~won].mean()*100:+7.1f}%  "
          f"| EXPECTANCY {mr.mean()*100:+6.2f}% per trade")
    print(f"  median hold {np.median(hh[hh>0]):.0f}d | worst trade {pr.min()*100:+.1f}% "
          f"({mr.min()*100:+.0f}% of margin)")
    daily = np.zeros(len(C))
    np.add.at(daily, np.minimum(t + np.maximum(hh, 1), len(C) - 1), (1.0 / 20.0) * mr)
    daily = np.clip(daily, -0.5, None)
    curve = (1 + pd.Series(daily, index=dates)).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    print(f"  portfolio max drawdown {dd*100:.1f}%  |  final {curve.iloc[-1]:.2f}x")
    return {"name": name, "n": n, "win_rate": won.mean(), "expectancy": mr.mean(),
            "avg_win": mr[won].mean(), "avg_loss": mr[~won].mean(), "max_dd": dd}


def main():
    close, volume, high, low = sz.load_all4()
    mask = sz.pit_mask(close, volume)
    C = close.to_numpy(float); H = high.to_numpy(float); M = mask.to_numpy(bool)
    V = volume.to_numpy(float)

    MA20 = pd.DataFrame(C).rolling(20).mean().to_numpy()
    MOM5 = (pd.DataFrame(C) / pd.DataFrame(C).shift(5) - 1).to_numpy()
    VOLMA = pd.DataFrame(V).rolling(20).mean().to_numpy()

    entry = (C > MA20) & (MOM5 > 0) & (V > VOLMA) & M & np.isfinite(MA20)
    print(f"'trending + volume' entries: {entry.sum():,} across {C.shape[1]} symbols x {C.shape[0]} days")
    print(f"exit signal: price closes below its 20d MA, or 5d momentum turns negative\n")
    print("=" * 78)

    rows = []
    rows.append(report("A. YOUR IDEA: trend entry, TP +3%, trend-death exit, NO stop",
                       *simulate(C, H, M, entry, 0.03, stop=None, MA=MA20, MOM=MOM5), C, close.index))
    rows.append(report("B. same but TP +5%",
                       *simulate(C, H, M, entry, 0.05, stop=None, MA=MA20, MOM=MOM5), C, close.index))
    rows.append(report("C. NO take-profit at all - only exit when the trend dies",
                       *simulate(C, H, M, entry, 99.0, stop=None, MA=MA20, MOM=MOM5), C, close.index))
    rows.append(report("D. classic: fixed -3% stop + 3% target (no trend logic)",
                       *simulate(C, H, M, entry, 0.03, stop=0.03, trend_exit=False, MA=MA20, MOM=MOM5), C, close.index))

    print("\n" + "=" * 78)
    print("\n=== SUMMARY (per-trade expectancy as % of margin at 5x) ===")
    for r in rows:
        print(f"  {r['name'][:58]:<58} {r['expectancy']*100:+7.2f}%   DD {r['max_dd']*100:7.1f}%")


if __name__ == "__main__":
    main()
