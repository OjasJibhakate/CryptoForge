"""Is the C1/C2 edge real? (run 2026-09-30) DIAGNOSTIC ONLY — reuses the frozen
construction in research/tradeforge_audit.py; selects nothing, changes nothing.
Basis for FORWARD_PROTOCOL.md amendment 1 (C3, kill-rule references).

Stages:
  0. reproduce the audit (C1 1.17 / C2 1.56)
  1. per-year decomposition: long leg, short leg, funding, costs (drift-inclusive)
  2. alpha vs BTC (Newey-West)
  3. execution realism: drift-inclusive turnover + live funding timing
  4. robustness grid (full + 2023-onward)
  5. significance: PSR / deflated Sharpe for N trials, years of live data needed
  6. live consistency: where the 16-day paper result sits in the backtest distribution
"""
import glob
import math
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import strategy_zoo as sz  # noqa: E402
import tradeforge_audit as ta  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PPY = 365
CAP = 0.0075
t0 = time.time()


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- load (cached)
PKL = os.path.join(bt.DATA_DIR, "edge_verdict_panels.pkl")  # cache under research/data (gitignored)
KEEP = ("close", "volume", "mask", "fund_capped", "ret", "w_c1", "w_c2", "regime")
if os.path.exists(PKL):
    D = pickle.load(open(PKL, "rb"))
else:
    full = ta.build_all()
    D = {k: full[k] for k in KEEP}
    pickle.dump(D, open(PKL, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
close, mask, fund, regime = D["close"], D["mask"], D["fund_capped"], D["regime"]
ret = D["ret"].fillna(0.0)
log(f"panel {close.shape[1]} syms x {len(close)} days "
    f"({close.index.min().date()} -> {close.index.max().date()}), load {time.time() - t0:.0f}s")


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):  # Acklam's approximation, plenty for this use
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    q = math.sqrt(-2 * math.log(min(p, 1 - p)))
    if p < 0.02425:
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def sharpe(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(PPY)) if len(x) > 2 and x.std() > 0 else float("nan")


def nw_ols(y, x=None, lags=5):
    y = np.asarray(y, float)
    X = np.ones((len(y), 1)) if x is None else np.column_stack([np.ones(len(y)), np.asarray(x, float)])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    u = y - X @ b
    n = len(y)
    Xu = X * u[:, None]
    S = Xu.T @ Xu / n
    for L in range(1, lags + 1):
        G = Xu[L:].T @ Xu[:-L] / n
        S += (1 - L / (lags + 1)) * (G + G.T)
    Q = np.linalg.inv(X.T @ X / n)
    se = np.sqrt(np.diag(Q @ S @ Q / n))
    return b, b / se


# ---------------------------------------------------------------- 0. reproduce
r1 = ta.run_book(D["w_c1"], ret, fund, 5.0, 2.0, vol_tgt=0.45, breaker=0.15)
r2 = ta.run_book(D["w_c2"], ret, fund, 5.0, 2.0, breaker=0.20)
BOOKS = {"C1": r1, "C2": r2}
log("\n0. REPRODUCE AUDIT (5+2 bps, funding capped per event at 0.75%)")
for k, r in BOOKS.items():
    m = bt.metrics(r["net"], PPY)
    log(f"   {k}: Sharpe {m['sharpe']:.2f}  CAGR {m['cagr'] * 100:.1f}%  MaxDD {m['max_dd'] * 100:.1f}%  "
        f"turnover {r['turnover'].mean():.3f}")

# ---------------------------------------------------------------- funding timing panels
held_any = sorted(set(r1["weights"].columns[(r1["weights"] != 0).any()]) |
                  set(r2["weights"].columns[(r2["weights"] != 0).any()]))
first, rest = {}, {}
for s in held_any:
    p = os.path.join(bt.DATA_DIR, f"{s}_funding.csv")
    if not os.path.exists(p):
        continue
    f = pd.read_csv(p)
    f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    f = f.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    r_ = pd.to_numeric(f["fundingRate"], errors="coerce").clip(-CAP, CAP)
    is_first = (r_.index - r_.index.normalize()) < pd.Timedelta(minutes=6)
    first[s] = r_[is_first].resample("1D").sum()
    rest[s] = r_[~is_first].resample("1D").sum()
f_first = pd.DataFrame(first).reindex(index=close.index, columns=close.columns).fillna(0.0)
f_rest = pd.DataFrame(rest).reindex(index=close.index, columns=close.columns).fillna(0.0)
# live: position held on day D (set ~00:06 D) pays 08:00 D, 16:00 D and 00:00 D+1
f_live = f_rest + f_first.shift(-1).fillna(0.0)
log(f"   funding timing panels built for {len(first)} ever-held symbols ({time.time() - t0:.0f}s)")


def decompose(r, fee=5.0, slip=2.0, fund_mult=1.0, live_timing=True, drift=True):
    w = r["weights"]  # held weights (after caps / vol target / breaker)
    px = (w * ret).sum(axis=1)
    longp = (w.clip(lower=0) * ret).sum(axis=1)
    shortp = (w.clip(upper=0) * ret).sum(axis=1)
    fpan = f_live if live_timing else fund.reindex_like(w).fillna(0.0)
    fnd = -(w * fpan.reindex_like(w).fillna(0.0)).sum(axis=1) * fund_mult
    if drift:
        grow = w * (1 + ret)
        drifted = grow.div((1 + px), axis=0)
        turn = (w.shift(-1).fillna(0.0) - drifted).abs().sum(axis=1).shift(1).fillna(w.abs().sum(axis=1))
    else:
        turn = r["turnover"]
    cost = turn * (fee + slip) / 1e4
    net = px - cost + fnd
    return pd.DataFrame({"net": net, "price": px, "long": longp, "short": shortp,
                         "funding": fnd, "cost": cost, "turn": turn})


# ---------------------------------------------------------------- 1. per-year
log("\n1. PER-YEAR DECOMPOSITION (%/yr, simple sums; costs drift-inclusive 5+2; live funding timing)")
DEC = {k: decompose(r) for k, r in BOOKS.items()}
for k, d in DEC.items():
    log(f"   {k}  year   Sharpe   net%   long%  short%  price%  fund%  cost%  turn/d")
    for y, g in d.groupby(d.index.year):
        a = PPY / len(g)
        log(f"        {y}  {sharpe(g.net):+6.2f} {g.net.sum() * a * 100:+7.1f} {g.long.sum() * a * 100:+7.1f} "
            f"{g.short.sum() * a * 100:+7.1f} {g.price.sum() * a * 100:+7.1f} {g.funding.sum() * a * 100:+6.1f} "
            f"{-g.cost.sum() * a * 100:+6.1f}  {g.turn.mean():.3f}")

# ---------------------------------------------------------------- 2. alpha vs BTC
log("\n2. ALPHA vs BTC (daily OLS, Newey-West t, 5 lags)")
btc = ret["BTCUSDT"]
for k, d in DEC.items():
    for lab, sl in (("2019-2026", slice(None)), ("2023+", slice("2023-01-01", None))):
        y = d.net.loc[sl]
        b, t = nw_ols(y.values, btc.loc[y.index].values)
        bp, tp = nw_ols(d.price.loc[sl].values - d.cost.loc[sl].values, btc.loc[y.index].values)
        log(f"   {k} {lab:<9}: alpha {b[0] * PPY * 100:+6.1f}%/yr (t {t[0]:+.2f}) beta {b[1]:+.2f} (t {t[1]:+.2f})"
            f" | ex-funding alpha {bp[0] * PPY * 100:+6.1f}%/yr (t {tp[0]:+.2f})")

# ---------------------------------------------------------------- 3/4. robustness grid
log("\n3/4. ROBUSTNESS GRID — net Sharpe (full | 2023+ | 2025+), CAGR full")
SCEN = [
    ("audit as published (bt turnover, bt funding timing)", dict(live_timing=False, drift=False)),
    ("+ drift-inclusive turnover", dict(live_timing=False, drift=True)),
    ("+ live funding timing  [REALISTIC BASE]", dict(live_timing=True, drift=True)),
    ("realistic, costs 10+5", dict(fee=10.0, slip=5.0)),
    ("realistic, funding x0.5", dict(fund_mult=0.5)),
    ("realistic, NO funding (momentum only)", dict(fund_mult=0.0)),
]
for k, r in BOOKS.items():
    for lab, kw in SCEN:
        d = decompose(r, **kw)
        n = d.net
        cagr = (1 + n).prod() ** (PPY / len(n)) - 1
        log(f"   {k} {lab:<52} {sharpe(n):+5.2f} | {sharpe(n.loc['2023':]):+5.2f} | "
            f"{sharpe(n.loc['2025':]):+5.2f}   CAGR {cagr * 100:+6.1f}%")

# ex-top-5 P&L names (rebuild weights with those names removed from the universe)
log("\n   ex-top-5 P&L contributors (names removed from universe, weights rebuilt):")
vol30 = close.pct_change().rolling(30).std()
mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0


def c1_w(m):
    return sz.xs(mom_stack / vol30, m, k=10)


def c2_w(m):
    ftilt = sz.zs(mom_stack / vol30, m) - sz.zs(fund.rolling(7).mean(), m)
    raw = sz.xs(ftilt, m, k=10).mul(regime, axis=0)
    base = (raw.shift(1) * ret.reindex_like(raw)).sum(axis=1)
    rm = (0.20 / (base.rolling(90).std() * np.sqrt(365))).clip(upper=2.0).shift(1).fillna(1.0)
    return raw.mul(rm, axis=0)


for k, r, builder, kw in (("C1", r1, c1_w, dict(vol_tgt=0.45, breaker=0.15)),
                          ("C2", r2, c2_w, dict(breaker=0.20))):
    contrib = (r["weights"] * ret).sum().sort_values(ascending=False)
    top5 = list(contrib.head(5).index)
    rr = ta.run_book(builder(mask & ~mask.columns.isin(top5)), ret, fund, 5.0, 2.0, **kw)
    d = decompose(rr)
    log(f"   {k} without {','.join(top5)}: Sharpe {sharpe(d.net):+.2f} | 2023+ {sharpe(d.net.loc['2023':]):+.2f}"
        f" | momentum-only {sharpe(d.net - d.funding):+.2f}")

# ---------------------------------------------------------------- 5. significance
log("\n5. SIGNIFICANCE on the REALISTIC BASE (daily net)")
for k, d in DEC.items():
    x = d.net.values
    T = len(x)
    sr = x.mean() / x.std()
    sk = float(pd.Series(x).skew())
    ku = float(pd.Series(x).kurt()) + 3.0
    denom = math.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr * sr, 1e-12))
    _, tnw = nw_ols(x)
    out = [f"   {k}: SR {sr * math.sqrt(PPY):.2f}/yr, skew {sk:+.2f}, kurt {ku:.1f}, NW t {tnw[0]:+.2f} | "
           f"deflated-Sharpe prob:"]
    for N in (1, 10, 50, 160):
        if N == 1:
            sr0 = 0.0
        else:
            g = 0.5772156649
            sr0 = math.sqrt(1.0 / T) * ((1 - g) * norm_ppf(1 - 1 / N) + g * norm_ppf(1 - 1 / (N * math.e)))
        dsr = norm_cdf((sr - sr0) * math.sqrt(T - 1) / denom)
        out.append(f"N={N}: {dsr * 100:.0f}%")
    log(" ".join(out))
    for true_sr in (sr * math.sqrt(PPY), 0.5 * sr * math.sqrt(PPY)):
        log(f"      live years needed for t=2 if true Sharpe is {true_sr:.2f}: {(2 / true_sr) ** 2:.1f}")

# ---------------------------------------------------------------- 6. live consistency
log("\n6. LIVE CONSISTENCY: percentile of the paper result among all backtest windows of equal length")
LIVE = {"C1": {"16d (from 09-13)": -0.0013, "6d fwd (09-23 close->09-29)": 9986.54 / 10636.97 - 1},
        "C2": {"16d (from 09-13)": 0.0181, "6d fwd (09-23 close->09-29)": 10181.01 / 10940.85 - 1}}
for k, d in DEC.items():
    lr = np.log1p(d.net)
    for lab, v in LIVE[k].items():
        n = 16 if lab.startswith("16") else 6
        win = np.expm1(lr.rolling(n).sum().dropna())
        pct = (win < v).mean() * 100
        log(f"   {k} {lab:<28} live {v * 100:+6.2f}% -> {pct:4.0f}th percentile "
            f"(backtest median {win.median() * 100:+.2f}%, P(loss) {(win < 0).mean() * 100:.0f}%)")

log(f"\ndone in {time.time() - t0:.0f}s")
