"""Crazy-edge sweep: port of TradeForge's five live mechanisms + crypto-native
high-return anomaly families, all on the same panel/costs/split as the zoo.

Families:
  TF-M4 gap-UP fade SHORT        (open->close reversal of overnight gap)
  TF-M5 gap-DOWN bounce LONG     (mirror)
  TF-M1 liquidation crash fade   (buy the post-crash bounce, -8% guard)
  TF-M2 long-horizon momentum    (90d/180d/252d-21 formation, slow rebalance)
  LIST listing pop fade          (short the post-listing spike)
  LIQ  liquidation cascade fade  (fade the crash's final flush)
  FUND funding-extreme contrarian(long hated shorts / short crowded longs)
  BTC  alt lead-lag catch-up     (beta-implied vs actual, BTC leads)
  DOW  day-of-week / weekend     (buy the weekend grind, sell Monday open)
  TOD  overnight drift long      (close->open momentum continuation)

Selection on IN-SAMPLE only; judged on OUT-OF-SAMPLE (>=2024).
Costs: 5bps fee + 2bps slippage per side, funding included.
"""
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
from strategy_zoo2 import load_full

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 5


def ev(name, w, ret, fund):
    r = bt.portfolio_backtest(ret, w, funding=fund, leverage_cap=1.0, asset_cap=1.0,
                              fee_bps=5.0, slip_bps=2.0, ppy=PPY)
    net = r["net"]
    sc = bt.scaled_metrics(net, 0.40, PPY)
    return {"strategy": name,
            "is": bt.metrics(net[net.index < SPLIT], PPY)["sharpe"],
            "oos": bt.metrics(net[net.index >= SPLIT], PPY)["sharpe"],
            "full": bt.metrics(net, PPY)["sharpe"],
            "cagr": bt.metrics(net, PPY)["cagr"] * 100,
            "dd": bt.metrics(net, PPY)["max_dd"] * 100,
            "at40dd": sc["cagr"] * 100, "scale": sc["scale"],
            "turn": r["turnover"].mean()}


def main():
    close, volume, high, low, qav, tbqav, ntr = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    o = close.shift(1)  # prev close ~ open proxy on daily bars
    gap = close / o - 1.0  # overnight gap proxy = daily return (daily bars)

    S = {}

    # ---- TF-M4: gap-UP fade SHORT (top gaps, fade during the day) ----
    g = gap.where(mask)
    for lo, hi in [(0.03, 0.10), (0.05, 0.15), (0.03, 1.0)]:
        qual = (g >= lo) & (g <= hi)
        sc = -g * qual.astype(float)
        S[f"M4 gap-up fade {int(lo*100)}-{int(hi*100 if hi<1 else 100)}%"] = (
            lambda sc=sc: sz.xs(sc, mask, k=K))

    # ---- TF-M5: gap-DOWN bounce LONG ----
    for lo, hi in [(0.03, 0.10), (0.05, 0.15), (0.03, 1.0)]:
        qual = (g <= -lo) & (g >= -hi)
        sc = -g * qual.astype(float)
        S[f"M5 gap-down bounce {int(lo*100)}-{int(hi*100 if hi<1 else 100)}%"] = (
            lambda sc=sc: sz.xs(sc, mask, k=K))

    # both directions at once
    S["M4+M5 gap book (both sides)"] = lambda: sz.xs(
        -g * (((g.abs() >= 0.03)) & ((g.abs() <= 0.10))).astype(float), mask, k=K)

    # ---- TF-M1: liquidation crash fade ----
    crash = (-(close / close.shift(1) - 1.0)).where(mask)
    for thr in [0.08, 0.10, 0.15]:
        qual = (ret <= -thr)
        S[f"M1 crash fade -{int(thr*100)}%"] = (
            lambda qual=qual: sz.xs(qual.astype(float), mask, k=K))
    # crash + volume confirmation (panic = crash on huge volume)
    vsurge = volume / volume.rolling(30).mean().replace(0, np.nan)
    S["M1 crash fade + vol surge"] = lambda: sz.xs(
        ((ret <= -0.08) & (vsurge >= 2.0)).astype(float), mask, k=K)

    # ---- TF-M2: long-horizon momentum (slow, quarterly turnover) ----
    for lb, skip in [(90, 21), (180, 21), (252, 21), (252, 63)]:
        mom = close / close.shift(lb) - 1.0
        mom_skip = close.shift(skip) / close.shift(lb) - 1.0
        S[f"M2 JT {lb}-{skip} slow momentum"] = (
            lambda ms=mom_skip: sz.xs(ms / vol30, mask))

    # ---- LIST: listing pop fade ----
    hist = close.notna().cumsum()
    age = hist.where(mask)
    # newly listed: first 5 / 10 / 21 days in universe -> short
    for n in [5, 10, 21]:
        young = (hist <= n + 60)
        mom5 = close / close.shift(5) - 1.0
        S[f"LIST fade first-{n}d pop"] = (
            lambda young=young, mom5=mom5: sz.xs(-mom5 * young.astype(float), mask, k=K))

    # ---- LIQ: liquidation cascade fade (deep flush + long wick = exhaustion) ----
    rng = (high - low) / close.replace(0, np.nan)
    lower_wick = (close - low) / (high - low).replace(0, np.nan)
    S["LIQ flush fade (deep red, long lower wick)"] = lambda: sz.xs(
        ((ret <= -0.05) & (lower_wick >= 0.6)).astype(float), mask, k=K)
    S["LIQ range explosion fade"] = lambda: sz.xs(
        -rng.where((rng >= rng.rolling(30).mean() * 2).fillna(False)), mask, k=K)

    # ---- FUND: funding-extreme contrarian ----
    f7 = fund.rolling(7).mean()
    fz = sz.zs(f7, mask)
    for thr in [1.5, 2.0, 2.5]:
        S[f"FUND fade |z|>{thr}"] = (
            lambda thr=thr, fz=fz: sz.xs(-fz * (fz.abs() > thr).astype(float), mask, k=K))

    # ---- BTC lead-lag catch-up ----
    btc = close["BTCUSDT"] if "BTCUSDT" in close.columns else close.mean(axis=1)
    btc_ret = btc.pct_change()
    btc_mom5 = btc / btc.shift(5) - 1.0
    beta = ret.rolling(60).corr(btc_ret).mul(
        vol30.div(ret.rolling(60).std(), fill_value=np.nan)).fillna(1.0)
    catchup = beta.mul(btc_mom5, axis=0) - (close / close.shift(5) - 1.0)
    S["BTC lead-lag catch-up"] = lambda: sz.xs(catchup, mask, k=K)
    for lb in [1, 3]:
        bl = btc / btc.shift(lb) - 1.0
        cu = beta.mul(bl, axis=0) - (close / close.shift(lb) - 1.0)
        S[f"BTC catch-up {lb}d"] = lambda cu=cu: sz.xs(cu, mask, k=K)

    # ---- DOW: day-of-week / weekend ----
    dow = pd.Series(close.index.dayofweek, index=close.index)
    fri_ret = ret.where(dow == 4)
    S["DOW long Friday drift"] = lambda: sz.xs(
        fri_ret.rolling(4).mean().reindex(close.index).ffill(), mask, k=K)
    mon_gap = (close / close.shift(3) - 1.0).where(dow == 0)  # Fri->Mon
    S["DOW fade Monday gap"] = lambda: sz.xs(-mon_gap.fillna(0.0), mask, k=K)

    # ---- TOD: overnight drift continuation ----
    S["TOD continuation (hold winners 1d)"] = lambda: sz.xs(
        close / close.shift(2) - 1.0, mask, k=K)

    print(f"panel {close.shape[1]} symbols x {len(close)} days\n")
    rows = []
    for name, fn in S.items():
        try:
            rows.append(ev(name, fn(), ret.fillna(0.0), fund))
        except Exception as e:
            print(f"  !! {name}: {e}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(bt.DATA_DIR, "crazy_sweep.csv"), index=False)
    cols = ["strategy", "is", "oos", "full", "cagr", "dd", "at40dd", "scale", "turn"]

    print("=== ranked by IN-SAMPLE Sharpe (select here; judge on OOS) ===")
    print(df.sort_values("is", ascending=False).head(20)[cols].round(2).to_string(index=False))
    print("\n=== TOP 15 BY OUT-OF-SAMPLE (>=2024) ===")
    print(df.sort_values("oos", ascending=False).head(15)[cols].round(2).to_string(index=False))
    print("\n=== CONSISTENT: IS>0.5 AND OOS>0.5 ===")
    good = df[(df["is"] > 0.5) & (df["oos"] > 0.5)].sort_values("oos", ascending=False)
    print(good[cols].round(2).to_string(index=False) if len(good) else "  none")
    print(f"\nBonferroni |t| for {len(df)} trials: IS {2.0 + 0.0:.2f} (ref only)")


if __name__ == "__main__":
    main()
