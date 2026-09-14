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
K = 10


def xs_long(score, mask, k=K):
    s = score.where(mask)
    ranks = s.rank(axis=1, ascending=False)
    n = s.notna().sum(axis=1)
    kk = np.minimum(k, n.clip(lower=1))
    w = ranks.le(kk, axis=0).astype(float)
    return w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def xs_ls(score, mask, k=K):
    s = score.where(mask)
    ranks = s.rank(axis=1, ascending=False)
    n = s.notna().sum(axis=1)
    kk = np.minimum(k, (n // 2).clip(lower=1))
    long = ranks.le(kk, axis=0).astype(float)
    short = ranks.gt(n - kk, axis=0).astype(float)
    long = long.div(long.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    short = short.div(short.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    return long, short


def long_heavy(score, mask, long_frac, k=K):
    long, short = xs_ls(score, mask, k)
    w = long * long_frac - short * (1.0 - long_frac)
    return w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def main():
    close, volume, high, low = sz.load_all4()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    score = mom_stack / vol30
    f7 = fund.rolling(7).mean()
    ftilt = sz.zs(score, mask) - sz.zs(f7, mask)
    btc = close["BTCUSDT"]
    ma200 = btc.rolling(200).mean()
    reg = pd.Series(np.where(btc > ma200, 1.0, 0.5), index=btc.index)

    def ev(name, w, fee=5.0, slip=2.0):
        r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=2.0,
                                  asset_cap=1.0, fee_bps=fee, slip_bps=slip, ppy=PPY)
        net = r["net"]
        m = bt.metrics(net, PPY)
        o = bt.metrics(net[net.index >= SPLIT], PPY)
        i = bt.metrics(net[net.index < SPLIT], PPY)
        sc = bt.scaled_metrics(net, 0.40, PPY)
        print(f"{name:<36} IS {i['sharpe']:5.2f}  OOS {o['sharpe']:5.2f}  full {m['sharpe']:5.2f}  "
              f"CAGR {m['cagr']*100:6.1f}%  DD {m['max_dd']*100:7.1f}%  at40DD {sc['cagr']*100:6.1f}%  "
              f"net_exp {w.sum(axis=1).mean():+.2f}")
        return net

    print("=== BENCHMARKS ===")
    bh = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    bh["BTCUSDT"] = 1.0
    ev("BTC buy & hold", bh, fee=0, slip=0)
    ew = pd.DataFrame(1.0 / close.shape[1], index=close.index, columns=close.columns)
    ev("equal-weight basket", ew, fee=0, slip=0)

    print("\n=== LONG-BIASED VARIANTS (user request: favour long over short) ===")
    ev("L/S 50/50 (current)", long_heavy(score, mask, 0.5))
    ev("long-heavy 60/40", long_heavy(score, mask, 0.6))
    ev("long-heavy 75/25", long_heavy(score, mask, 0.75))
    ev("long-heavy 90/10", long_heavy(score, mask, 0.9))
    ev("long-only", long_heavy(score, mask, 1.0))
    ev("long-only + regime", xs_long(score, mask).mul(reg, axis=0))
    ev("long-only ftilt + regime", xs_long(ftilt, mask).mul(reg, axis=0))
    ev("long-only top20", xs_long(score, mask, k=20))
    ev("long-only BTC regime filter", xs_long(score, mask).mul((btc > ma200).astype(float), axis=0))

    print("\n=== RISK-MANAGED MOMENTUM (Barroso & Santa-Clara style) ===")
    for lb in [30, 60, 90]:
        wb = long_heavy(score, mask, 0.5)
        base_ret = (wb.shift(1) * ret.fillna(0.0)).sum(axis=1)
        rv = base_ret.rolling(lb).std() * np.sqrt(PPY)
        scale = (0.20 / rv).clip(upper=2.0).shift(1).fillna(1.0)
        ev(f"risk-managed L/S lb={lb}", wb.mul(scale, axis=0))

    print("\n=== LONG-ONLY + RISK MANAGEMENT ===")
    wl = xs_long(ftilt, mask).mul(reg, axis=0)
    base_ret = (wl.shift(1) * ret.fillna(0.0)).sum(axis=1)
    for lb in [30, 60]:
        rv = base_ret.rolling(lb).std() * np.sqrt(PPY)
        scale = (0.25 / rv).clip(upper=2.0).shift(1).fillna(1.0)
        ev(f"long-only ftilt+regime RM lb={lb}", wl.mul(scale, axis=0))

    print("\n=== BEHAVIORAL REVERSAL (lowest price in formation period) ===")
    form_low = close.rolling(30).min()
    beh = (close - form_low) / form_low.replace(0, np.nan)
    ev("behavioral low-anchor L/S", long_heavy(-beh, mask, 0.5))

    print("\n=== COST CHECK on long-heavy 75/25 (turnover lower than L/S?) ===")
    for fee, slip in [(5, 2), (10, 5), (20, 10)]:
        ev(f"long-heavy 75/25 cost {fee}+{slip}", long_heavy(score, mask, 0.75), fee=fee, slip=slip)


if __name__ == "__main__":
    main()
