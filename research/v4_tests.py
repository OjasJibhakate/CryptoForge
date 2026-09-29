"""V4 tests, implemented exactly as pre-registered in research/V4_PREREG.md (commit 519427b,
2026-09-30 01:47 IST, before any V4 data was downloaded). Run once; every result is published.

Needs: py research/v4_download.py oi && py research/v4_download.py spot
Usage: py research/v4_tests.py
"""
import glob
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
import c3_backtest as c3
import strategy_zoo as sz
import tradeforge_audit as ta
from strategy_zoo2 import load_full

PPY = 365
A_START, A_END = pd.Timestamp("2020-09-04"), pd.Timestamp("2026-08-23")
SPOT_BPS, PERP_BPS = 12.0, 7.0  # per side: fee + slippage
CAPITAL_MULT = 1.5
verdicts = {}


def nw_t(x, lags=5):
    x = np.asarray(pd.Series(x).dropna(), float)
    n = len(x)
    if n < 10:
        return float("nan")
    e = x - x.mean()
    s = e @ e / n
    for L in range(1, lags + 1):
        s += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean() / np.sqrt(s / n))


def m(series):
    s = series.dropna()
    k = bt.metrics(s, PPY)
    return k["sharpe"], k["cagr"] * 100, k["max_dd"] * 100


def rank_ic(sig, fwd, mask, min_names=10):
    s = sig.where(mask)
    f = fwd.where(mask & s.notna())
    s = s.where(f.notna())
    ok = s.notna().sum(axis=1) >= min_names
    ic = s[ok].rank(axis=1).corrwith(f[ok].rank(axis=1), axis=1)
    return ic.dropna()


def weekly(w, start):
    """Hold the weights set on every 7th day from `start` (targets constant in between)."""
    days = w.index[w.index >= start]
    reb = days[::7]
    out = w.loc[reb].reindex(w.index).ffill().fillna(0.0)
    out.loc[out.index < start] = 0.0
    return out


def book(w, ret, fund, fee=5.0, slip=2.0):
    return bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                                 fee_bps=fee, slip_bps=slip, ppy=PPY)["net"]


def check(name, cond, detail):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}: {detail}")
    return bool(cond)


def main():
    D = ta.build_all()
    close, volume, mask, fund = D["close"], D["volume"], D["mask"], D["fund_capped"]
    ret = D["ret"].fillna(0.0)
    raw_ret = close.pct_change()
    _, _, _, _, qav, tbqav, _ = load_full()
    w_c3, _ = c3.c3_weights(D, c3.non_coin_symbols())
    net_c3 = book(w_c3, ret, fund)
    print(f"panel {close.shape[1]} x {len(close)} ({close.index.min().date()} -> {close.index.max().date()})")

    # ------------------------------------------------------------------ A
    print("\n" + "=" * 78 + "\nA. OPEN-INTEREST POSITIONING (new data)\n" + "=" * 78)
    oiv, oic = {}, {}
    for p in glob.glob(os.path.join(bt.DATA_DIR, "oi", "*.csv")):
        df = pd.read_csv(p, parse_dates=["date"]).set_index("date")
        s = os.path.basename(p)[:-4]
        oiv[s] = pd.to_numeric(df["sum_open_interest_value"], errors="coerce")
        oic[s] = pd.to_numeric(df["sum_open_interest"], errors="coerce")
    OIV = pd.DataFrame(oiv).reindex(index=close.index, columns=close.columns)
    OIC = pd.DataFrame(oic).reindex(index=close.index, columns=close.columns)
    win = (close.index >= A_START) & (close.index <= A_END)
    mA = mask.copy()
    mA.loc[~win] = False
    cov = (OIV.notna() & mA).sum().sum() / mA.sum().sum()
    print(f"OI coverage of universe symbol-days in window: {cov * 100:.1f}%")

    sig = OIV / OIV.shift(3) - 1.0
    sig = sig.replace([np.inf, -np.inf], np.nan)
    fwd = raw_ret.shift(-1)
    ic = rank_ic(sig, fwd, mA)
    t1 = nw_t(ic)
    yr = ic.groupby(ic.index.year).mean()
    print(f"A1  OI value 3d change -> next day: mean rank IC {ic.mean():+.4f}, NW t {t1:+.2f}, "
          f"{len(ic)} days")
    print("    by year: " + " | ".join(f"{y}: {v:+.4f}" for y, v in yr.items()))
    sgn = np.sign(ic.mean())
    same = int((np.sign(yr.loc[2021:2026]) == sgn).sum())

    ic_c = rank_ic((OIC / OIC.shift(3) - 1.0).replace([np.inf, -np.inf], np.nan), fwd, mA)
    print(f"A1b(i)  OI contracts 3d change (price-free): IC {ic_c.mean():+.4f}, NW t {nw_t(ic_c):+.2f}")
    p3 = close / close.shift(3) - 1.0
    zs_sig, zs_p3 = sz.zs(sig, mA), sz.zs(p3, mA)
    beta = (zs_sig * zs_p3).sum(axis=1) / (zs_p3 ** 2).sum(axis=1).replace(0, np.nan)
    resid = zs_sig - zs_p3.mul(beta, axis=0)
    ic_r = rank_ic(resid, fwd, mA)
    ic_p = rank_ic(p3, fwd, mA)
    print(f"A1b(ii) residual after 3d price return:   IC {ic_r.mean():+.4f}, NW t {nw_t(ic_r):+.2f} "
          f"(3d price return alone: IC {ic_p.mean():+.4f}, t {nw_t(ic_p):+.2f})")

    wA = sz.xs(sz.zs(sig, mA), mA, k=10)
    wAw = weekly(wA, A_START)
    res = {}
    for lab, w in (("A2 daily", wA), ("A2w weekly", wAw)):
        n = book(w, ret, fund)[win]
        n_s = book(w, ret, fund, 10.0, 5.0)[win]
        last12 = n[n.index > A_END - pd.Timedelta(days=365)]
        corr = float(n.corr(net_c3[win]))
        sh, cg, dd = m(n)
        res[lab] = dict(net=n, sharpe=sh, last12=m(last12)[0], corr=corr, w=w)
        print(f"{lab:<11} net Sharpe {sh:+.2f}  CAGR {cg:+.1f}%  MaxDD {dd:.1f}%  | stress 10+5 Sharpe "
              f"{m(n_s)[0]:+.2f} | final 12m Sharpe {m(last12)[0]:+.2f} | corr with C3 {corr:+.2f}")

    print("A verdict:")
    a_ok = check("A1 NW t >= 3.0", abs(t1) >= 3.0 and sgn > 0, f"t {t1:+.2f}")
    a_ok &= check("A1 same sign >= 4 of 6 years (2021-2026)", same >= 4, f"{same}/6")
    tradeable = [k for k, v in res.items() if v["sharpe"] >= 1.0 and v["last12"] > 0 and v["corr"] < 0.5]
    for k, v in res.items():
        check(f"{k}: Sharpe >= 1.0, final 12m > 0, corr < 0.5",
              k in tradeable, f"{v['sharpe']:+.2f} / {v['last12']:+.2f} / {v['corr']:+.2f}")
    a_ok &= bool(tradeable)
    if tradeable:
        pick = "A2 daily" if "A2 daily" in tradeable else tradeable[0]
        blend = book(0.5 * w_c3 + 0.5 * res[pick]["w"], ret, fund)[win]
        alone = net_c3[win]
        half = blend.index[len(blend) // 2]
        b1, b2 = m(blend[:half])[0], m(blend[half:])[0]
        c1_, c2_ = m(alone[:half])[0], m(alone[half:])[0]
        a_ok &= check("A3 blend beats C3 in both halves", b1 > c1_ and b2 > c2_,
                      f"blend {b1:+.2f}/{b2:+.2f} vs C3 {c1_:+.2f}/{c2_:+.2f}")
    else:
        print("   [SKIP] A3 (only run if A2 or A2w passes)")
    verdicts["A"] = a_ok

    # ------------------------------------------------------------------ B
    print("\n" + "=" * 78 + "\nB. HEDGED FUNDING CARRY (long spot + short perp)\n" + "=" * 78)
    spot = {}
    for p in glob.glob(os.path.join(bt.DATA_DIR, "spot", "*.csv")):
        df = pd.read_csv(p, parse_dates=["date"]).drop_duplicates("date").set_index("date")
        spot[os.path.basename(p)[:-4]] = pd.to_numeric(df["spot_close"], errors="coerce")
    S = pd.DataFrame(spot).reindex(index=close.index)
    P = close.reindex(columns=S.columns)
    gap = ((S - P).abs() / P).median()
    good = gap[gap <= 0.01].index
    print(f"spot pairs: {S.shape[1]} downloaded, {len(good)} kept (median |spot-perp|/perp <= 1%); "
          f"dropped: {', '.join(gap[gap > 0.01].index[:12])}")
    S, P = S[good], P[good]
    f_live = c3.live_timing_funding(close, list(good))[good]
    h = (S.pct_change() - P.pct_change() + f_live).where(S.notna() & P.notna() & S.shift(1).notna()
                                                           & P.shift(1).notna())
    both = S.notna() & P.notna()

    def carry(Wt, label):
        Wt = Wt.where(both, 0.0).fillna(0.0)
        held = Wt.shift(1).fillna(0.0)
        gross = (held * h.fillna(0.0)).sum(axis=1)
        cost = (Wt - Wt.shift(1).fillna(0.0)).abs().sum(axis=1) * (SPOT_BPS + PERP_BPS) / 1e4
        net = (gross - cost)
        start = Wt.abs().sum(axis=1).gt(0).idxmax()
        net = net[net.index >= start]
        sh, cg, dd = m(net)
        yrs = net.groupby(net.index.year).apply(lambda s: (1 + s).prod() - 1)
        inv = (held.abs().sum(axis=1) > 0)[net.index].mean()
        fund_part = (held * f_live.fillna(0.0)).sum(axis=1)[net.index].mean() * PPY * 100
        print(f"{label}: net {cg:+.1f}%/yr on capital, Sharpe {sh:+.2f}, MaxDD {dd:.1f}%, "
              f"invested {inv * 100:.0f}% of days, funding {fund_part:+.1f}%/yr, "
              f"costs {cost[net.index].mean() * PPY * 100:.2f}%/yr")
        print("    by year: " + " | ".join(f"{y}: {v * 100:+.1f}%" for y, v in yrs.items()))
        full = yrs.loc[2020:2025]
        ok = check(f"{label}: >=5%/yr, Sharpe >=1.5, MaxDD >= -10%, >=5 of 6 years positive",
                   cg >= 5 and sh >= 1.5 and dd >= -10 and int((full > 0).sum()) >= 5,
                   f"{cg:+.1f}% / {sh:+.2f} / {dd:.1f}% / {int((full > 0).sum())}/{len(full)}")
        return ok

    unit = 1.0 / CAPITAL_MULT
    W1 = pd.DataFrame(0.0, index=close.index, columns=good)
    for s in ("BTCUSDT", "ETHUSDT"):
        if s in W1.columns:
            W1[s] = unit / 2
    b1 = carry(W1, "B1 BTC+ETH static")

    m30 = sz.pit_mask(close, volume, top_n=30).reindex(columns=good, fill_value=False) & both
    f14 = fund.reindex(columns=good).rolling(14).mean()
    W2 = pd.DataFrame(0.0, index=close.index, columns=good)
    reb = close.index[close.index >= pd.Timestamp("2020-01-01")][::7]
    for d in reb:
        cand = f14.loc[d].where(m30.loc[d]).dropna()
        cand = cand[cand > 0].sort_values(ascending=False).head(5)
        W2.loc[d, cand.index] = unit / 5
    W2 = W2.loc[reb].reindex(close.index).ffill().fillna(0.0)
    b2 = carry(W2, "B2 rotating top-5 carry")
    verdicts["B"] = b1 or b2

    # ------------------------------------------------------------------ C
    print("\n" + "=" * 78 + "\nC. ORDER-FLOW SLEEVE (contaminated: data seen in waves 2-3)\n" + "=" * 78)
    tbr = (tbqav / qav.replace(0, np.nan)).clip(0.2, 0.8)
    w_ofi = weekly(sz.xs(sz.zs(tbr.rolling(5).mean(), mask), mask, k=10), pd.Timestamp("2020-01-01"))
    cwin = close.index >= pd.Timestamp("2020-01-01")
    blend = book(0.5 * w_c3 + 0.5 * w_ofi, ret, fund)[cwin]
    alone = net_c3[cwin]
    ofi_only = book(w_ofi, ret, fund)[cwin]
    half = blend.index[len(blend) // 2]
    print(f"OFI sleeve alone (weekly): Sharpe {m(ofi_only)[0]:+.2f}, corr with C3 {ofi_only.corr(alone):+.2f}")
    b_h = (m(blend[:half])[0], m(blend[half:])[0])
    c_h = (m(alone[:half])[0], m(alone[half:])[0])
    print(f"blend Sharpe by half {b_h[0]:+.2f}/{b_h[1]:+.2f} vs C3 {c_h[0]:+.2f}/{c_h[1]:+.2f}; "
          f"MaxDD blend {m(blend)[2]:.1f}% vs C3 {m(alone)[2]:.1f}%")
    verdicts["C"] = check("C: blend >= C3 + 0.2 in both halves, MaxDD not worse",
                          b_h[0] >= c_h[0] + 0.2 and b_h[1] >= c_h[1] + 0.2 and m(blend)[2] >= m(alone)[2],
                          f"{b_h[0] - c_h[0]:+.2f} / {b_h[1] - c_h[1]:+.2f}")

    print("\n" + "=" * 78)
    print("V4 VERDICTS: " + " | ".join(f"{k}: {'PASS' if v else 'FAIL'}" for k, v in verdicts.items()))


if __name__ == "__main__":
    main()
