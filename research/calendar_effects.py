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


def tstat(x):
    x = pd.Series(x).dropna()
    if len(x) < 5 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std() * np.sqrt(len(x)))


def main():
    close, volume, high, low = sz.load_all4()
    btc = close["BTCUSDT"].dropna()
    r = btc.pct_change().dropna()
    IS = r[r.index < SPLIT]
    OOS = r[r.index >= SPLIT]
    print(f"BTC daily returns: {len(r)} days ({r.index.min().date()} -> {r.index.max().date()})\n")

    print("=== DAY-OF-WEEK EFFECT (mean daily return, bps) ===")
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    print(f"{'day':<5} {'IS bps':>9} {'IS t':>7} | {'OOS bps':>9} {'OOS t':>7}")
    for d in range(7):
        a = IS[IS.index.dayofweek == d] * 1e4
        b = OOS[OOS.index.dayofweek == d] * 1e4
        print(f"{names[d]:<5} {a.mean():9.1f} {tstat(a):7.2f} | {b.mean():9.1f} {tstat(b):7.2f}")

    print("\n=== WEEKEND vs WEEKDAY ===")
    for lab, m in [("weekday (Mon-Fri)", r.index.dayofweek < 5), ("weekend (Sat-Sun)", r.index.dayofweek >= 5)]:
        a = (IS[IS.index.dayofweek < 5] if lab.startswith("weekday") else IS[IS.index.dayofweek >= 5]) * 1e4
        b = (OOS[OOS.index.dayofweek < 5] if lab.startswith("weekday") else OOS[OOS.index.dayofweek >= 5]) * 1e4
        print(f"{lab:<20} IS {a.mean():7.1f} bps (t {tstat(a):5.2f}) | OOS {b.mean():7.1f} bps (t {tstat(b):5.2f})")

    print("\n=== VOLATILITY BY DAY (annualised %) ===")
    for d in range(7):
        v = IS[IS.index.dayofweek == d].std() * np.sqrt(PPY) * 100
        vo = OOS[OOS.index.dayofweek == d].std() * np.sqrt(PPY) * 100
        print(f"  {names[d]}: IS {v:6.1f}%  OOS {vo:6.1f}%")

    print("\n=== TURN-OF-MONTH ===")
    a = IS[((IS.index.day <= 3) | (IS.index.day >= 28))] * 1e4
    b = OOS[((OOS.index.day <= 3) | (OOS.index.day >= 28))] * 1e4
    c = IS[~((IS.index.day <= 3) | (IS.index.day >= 28))] * 1e4
    d2 = OOS[~((OOS.index.day <= 3) | (OOS.index.day >= 28))] * 1e4
    print(f"turn-of-month       IS {a.mean():7.1f} bps (t {tstat(a):5.2f}) | OOS {b.mean():7.1f} bps (t {tstat(b):5.2f})")
    print(f"rest of month       IS {c.mean():7.1f} bps (t {tstat(c):5.2f}) | OOS {d2.mean():7.1f} bps (t {tstat(d2):5.2f})")

    print("\n=== TRADEABLE TEST: time BTC with the IS weekday sign ===")
    is_mean = IS.groupby(IS.index.dayofweek).mean()
    good_days = set(is_mean[is_mean > 0].index)
    print(f"  IS-positive weekdays: {[names[i] for i in sorted(good_days)]}")
    pos = pd.Series(0.0, index=r.index)
    pos[r.index.dayofweek.isin(list(good_days))] = 1.0
    net = (pos.shift(1) * r).dropna()
    oos = net[net.index >= SPLIT]
    m = bt.metrics(oos, PPY)
    base = bt.metrics(OOS, PPY)
    print(f"  OOS: weekday-timed BTC Sharpe {m['sharpe']:.2f} CAGR {m['cagr']*100:6.1f}% DD {m['max_dd']*100:6.1f}%")
    print(f"  OOS: buy & hold BTC      Sharpe {base['sharpe']:.2f} CAGR {base['cagr']*100:6.1f}% DD {base['max_dd']*100:6.1f}%")


if __name__ == "__main__":
    main()
