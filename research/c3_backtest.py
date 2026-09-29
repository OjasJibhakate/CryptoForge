"""C3 historical baseline: C2 restricted to crypto (COIN) perpetuals, gross capped at 1.0x.

Why C3 exists (paper/FORWARD_PROTOCOL.md, amendment 1): C2's backtest evidence is a
crypto-only book at <=1.0x gross (Binance TradFi perps first list 2025-12; every
backtest uses leverage_cap=1.0), but the live C2 book trades ~40% TradFi perps and has
no gross cap. C3 is the live implementation that matches the evidence. Its rules are
C2's rules; only the universe filter and the gross cap differ. Nothing here selects on
performance -- 2026 is reported, not used.

Two conventions are reported:
  audit      = research/tradeforge_audit.py as published (target-to-target turnover,
               funding by calendar day)
  realistic  = drift-inclusive turnover + live funding timing (the 00:00 UTC print is
               paid by the position held BEFORE the 00:06 rebalance)

Usage:  py research/c3_backtest.py
"""
import json
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
import tradeforge_audit as ta

PPY = 365
CAP = 0.0075
HERE = os.path.dirname(os.path.abspath(__file__))


def non_coin_symbols():
    with open(os.path.join(HERE, "tradfi_symbols.json"), encoding="utf-8") as f:
        snap = json.load(f)
    return set(snap["tradfi"]) | set(snap["non_coin_perpetual"])


def c3_weights(D, excluded):
    close, volume, ret, fund, regime = D["close"], D["volume"], D["ret"], D["fund_capped"], D["regime"]
    crypto = [c for c in close.columns if c not in excluded]
    mask = sz.pit_mask(close[crypto], volume[crypto]).reindex(columns=close.columns, fill_value=False)
    vol30 = ret.rolling(30).std()
    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    ftilt = sz.zs(mom_stack / vol30, mask) - sz.zs(fund.rolling(7).mean(), mask)
    raw = sz.xs(ftilt, mask, k=ta.K).mul(regime, axis=0)
    base = (raw.shift(1) * ret.fillna(0.0).reindex_like(raw)).sum(axis=1)
    rm = (0.20 / (base.rolling(90).std() * np.sqrt(365))).clip(upper=2.0).shift(1).fillna(1.0)
    return raw.mul(rm, axis=0), mask


def live_timing_funding(close, symbols):
    first, rest = {}, {}
    for s in symbols:
        p = os.path.join(bt.DATA_DIR, f"{s}_funding.csv")
        if not os.path.exists(p):
            continue
        f = pd.read_csv(p)
        f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        f = f.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        r = pd.to_numeric(f["fundingRate"], errors="coerce").clip(-CAP, CAP)
        is_first = (r.index - r.index.normalize()) < pd.Timedelta(minutes=6)
        first[s] = r[is_first].resample("1D").sum()
        rest[s] = r[~is_first].resample("1D").sum()
    ff = pd.DataFrame(first).reindex(index=close.index, columns=close.columns).fillna(0.0)
    fr = pd.DataFrame(rest).reindex(index=close.index, columns=close.columns).fillna(0.0)
    return fr + ff.shift(-1).fillna(0.0)


def realistic(r, ret, f_live, fee=5.0, slip=2.0):
    w = r["weights"]
    px = (w * ret).sum(axis=1)
    drifted = (w * (1 + ret)).div(1 + px, axis=0)
    turn = (w.shift(-1).fillna(0.0) - drifted).abs().sum(axis=1).shift(1).fillna(w.abs().sum(axis=1))
    fnd = -(w * f_live.reindex_like(w).fillna(0.0)).sum(axis=1)
    cost = turn * (fee + slip) / 1e4
    return pd.DataFrame({"net": px - cost + fnd, "price": px, "funding": fnd, "cost": cost, "turn": turn})


def notional_top5(w):
    a = w.abs()
    g = a.sum(axis=1).replace(0, np.nan)
    top = a.apply(lambda row: row.nlargest(5).sum(), axis=1)
    return float((top / g).dropna().mean())


def sharpe(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(PPY)) if len(x) > 2 and x.std() > 0 else float("nan")


def main():
    D = ta.build_all()
    ret = D["ret"].fillna(0.0)
    fund = D["fund_capped"]
    excluded = non_coin_symbols()
    w_c3, mask_c3 = c3_weights(D, excluded)
    books = {
        "C1": ta.run_book(D["w_c1"], ret, fund, 5.0, 2.0, vol_tgt=0.45, breaker=0.15),
        "C2": ta.run_book(D["w_c2"], ret, fund, 5.0, 2.0, breaker=0.20),
        "C3": ta.run_book(w_c3, ret, fund, 5.0, 2.0, breaker=0.20),
    }
    held = sorted(set().union(*[set(r["weights"].columns[(r["weights"] != 0).any()]) for r in books.values()]))
    f_live = live_timing_funding(D["close"], held)
    close = D["close"]
    print(f"panel {close.shape[1]} symbols x {len(close)} days ({close.index.min().date()} -> "
          f"{close.index.max().date()}); non-coin symbols excluded from C3: {len(excluded)}")

    print("\n            audit convention                       | realistic execution")
    print("       Sharpe  CAGR    MaxDD   turn   fund bps/yr  | Sharpe  CAGR    MaxDD   turn   top5 notional")
    ref = {}
    for k, r in books.items():
        m = bt.metrics(r["net"], PPY)
        z = realistic(r, ret, f_live)
        mz = bt.metrics(z["net"], PPY)
        t5 = notional_top5(r["weights"])
        ref[k] = dict(sharpe=mz["sharpe"], max_dd=mz["max_dd"], turn=z["turn"].mean(), top5=t5)
        print(f"  {k}  {m['sharpe']:6.2f} {m['cagr'] * 100:6.1f}% {m['max_dd'] * 100:7.1f}% "
              f"{r['turnover'].mean():6.3f}  {r['funding'].mean() * PPY * 1e4:+8.0f}     | "
              f"{mz['sharpe']:6.2f} {mz['cagr'] * 100:6.1f}% {mz['max_dd'] * 100:7.1f}% "
              f"{z['turn'].mean():6.3f}   {t5 * 100:5.1f}%")

    print("\nper-year realistic Sharpe (price / funding %/yr):")
    for k, r in books.items():
        z = realistic(r, ret, f_live)
        cells = []
        for y, g in z.groupby(z.index.year):
            if y < 2020:
                continue
            a = PPY / len(g)
            cells.append(f"{y}: {sharpe(g.net):+.2f} ({g.price.sum() * a * 100:+.0f}/{g.funding.sum() * a * 100:+.0f})")
        print(f"  {k}  " + " | ".join(cells))

    held_c3 = books["C3"]["weights"]
    tf_cols = [c for c in held_c3.columns if c in excluded]
    print(f"\nC3 non-coin exposure check: max share of gross in excluded symbols = "
          f"{float((held_c3[tf_cols].abs().sum(axis=1) / held_c3.abs().sum(axis=1).replace(0, np.nan)).max() or 0):.4f}")
    print(f"C3 max gross {held_c3.abs().sum(axis=1).max():.3f}x (cap 1.0)")
    same = (books["C2"]["net"] - books["C3"]["net"]).abs()
    print(f"C2 vs C3 identical before 2025-12-01: {bool(same[same.index < '2025-12-01'].max() < 1e-12)}")

    print("\nKILL-RULE REFERENCES (realistic convention): "
          + " | ".join(f"{k} Sharpe {v['sharpe']:.2f} maxDD {v['max_dd'] * 100:.1f}%" for k, v in ref.items()))


if __name__ == "__main__":
    main()
