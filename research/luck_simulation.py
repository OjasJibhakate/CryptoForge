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
import survivorship as sv

N_TRADERS = 20_000
LEAD_TRADERS_ON_BINANCE = 200_000
DAYS_M1 = 30
DAYS_M2 = 30
K_COINS = 3
FEE_BPS = 7.0


def get_returns():
    close, volume = sv.load_all_panels()
    mask = sv.pit_mask(close, volume, top_n=60, min_adv=5e6)
    ever = close.columns[mask.any(axis=0)]
    px = close[ever].sort_index()
    ret = px.pct_change().fillna(0.0)
    return ret


def simulate(R, leverage, n=N_TRADERS, days=DAYS_M1, seed=1, costs=True, k=K_COINS):
    R = np.asarray(R, dtype=float)
    rng = np.random.default_rng(seed)
    T, A = R.shape
    t0 = rng.integers(0, max(T - days - DAYS_M2, 1))
    eq = np.ones(n)
    eq_m1 = np.ones(n)
    for step in range(days):
        t = t0 + step
        idx = rng.integers(0, A, size=(n, k))
        sign = rng.choice([-1.0, 1.0], size=(n, k))
        w = sign * (leverage / k)
        day = (R[t][idx] * w).sum(axis=1)
        if costs:
            turn = np.abs(w).sum(axis=1) * 2.0
            day = day - turn * FEE_BPS / 1e4
        eq = eq * (1.0 + day)
        eq = np.maximum(eq, 0.0)
        if step == DAYS_M1 - 1:
            eq_m1 = eq.copy()
    return eq_m1, eq


def report(leverage, eq_m1, eq_full):
    r1 = eq_m1 - 1.0
    frac300 = float((r1 > 3.0).mean())
    frac100 = float((r1 > 1.0).mean())
    blown = float((eq_m1 < 0.05).mean())
    exp300 = frac300 * LEAD_TRADERS_ON_BINANCE
    print(f"leverage {leverage:>3}x | month1 median {np.median(r1)*100:8.1f}% | "
          f">+100%: {frac100*100:6.2f}% | >+300%: {frac300*100:6.3f}% "
          f"(~{exp300:,.0f} of {LEAD_TRADERS_ON_BINANCE:,} lead traders) | "
          f"wiped out: {blown*100:5.1f}%")
    surv = eq_m1 > 0.05
    if surv.sum() >= 100:
        r2 = eq_full[surv] / np.maximum(eq_m1[surv], 1e-9) - 1.0
        c = float(np.corrcoef(r1[surv], r2)[0, 1])
        hi = r1[surv] >= np.quantile(r1[surv], 0.8)
        lo = r1[surv] <= np.quantile(r1[surv], 0.2)
        print(f"            | month2 (survivors only): corr(m1,m2) = {c:+.2f} | "
              f"month-1 top-20% -> median month2 {np.median(r2[hi])*100:+.1f}%  vs  "
              f"bottom-20% -> {np.median(r2[lo])*100:+.1f}%")
    else:
        print(f"            | month2: too few survivors to measure")
    return {"leverage": leverage, "med_m1": np.median(r1), "pct_100": frac100,
            "pct_300": frac300, "exp_300": exp300, "blown": blown}


def main():
    R = get_returns()
    print(f"panel: {R.shape[1]} assets x {R.shape[0]} days | "
          f"{N_TRADERS:,} random traders, k={K_COINS} coins, daily re-randomised\n")
    print("=== WITH realistic costs (14 bps round trip on gross) ===")
    rows = []
    for L in [1, 3, 5, 10, 25, 50]:
        a, b = simulate(R, L, costs=True, days=DAYS_M1 + DAYS_M2)
        rows.append(report(L, a, b))
    print("\n=== GROSS (no costs) — the pure luck distribution ===")
    rows_g = []
    for L in [1, 5, 10, 25, 50]:
        a, b = simulate(R, L, costs=False, seed=7, days=DAYS_M1 + DAYS_M2)
        rows_g.append(report(L, a, b))
    pd.DataFrame(rows + rows_g).to_csv(os.path.join(bt.DATA_DIR, "luck_simulation.csv"), index=False)

    print("\n=== KEY NUMBER ===")
    a, b = simulate(R, 25, costs=False, seed=7, days=DAYS_M1 + DAYS_M2)
    r1 = a - 1.0
    frac = (r1 > 3).mean()
    print(f"At 25x with zero skill, {frac*100:.2f}% of traders turn $1 into $4+ in one month.")
    print(f"Scaled to Binance's ~200,000 lead traders, that is ~{int(frac*200000):,} accounts "
          f"showing a '+300% month' — with no skill involved whatsoever.")
    surv = a > 0.05
    r2 = b[surv] / np.maximum(a[surv], 1e-9) - 1.0
    if surv.sum() >= 100:
        c = float(np.corrcoef(r1[surv], r2)[0, 1])
        print(f"Those same 'star' traders next month: correlation between month-1 and month-2 "
              f"return = {c:+.2f} (i.e. none).")
        print(f"Only {surv.mean()*100:.1f}% of the 25x cohort was still alive to trade month 2.")


if __name__ == "__main__":
    main()
