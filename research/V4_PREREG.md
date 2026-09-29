# CryptoForge V4 — Pre-registered tests of three open leads

*Declared 2026-09-30, committed BEFORE any V4 data is downloaded or any result is seen.
One construction per test (plus at most one declared variant), fixed pass rules, run once.
C1/C2/C3 are frozen and untouched; a pass only earns a new paper candidate under a new
protocol amendment. Results go to V4_RESULTS.md whatever they say.*

Why these three: after ~160 configurations on daily price/volume data (V2 and V3 both null),
only leads that use **information the backtests never used**, or a **construction never
tried**, are worth a test. Evidence base: `research/edge_verdict.py` (since 2023 the backtested
return is mostly funding; momentum alone is not significant).

Common rules: PIT top-60 universe (`strategy_zoo.pit_mask`), costs 5 bps fee + 2 bps slippage
per perp side (spot: 10 + 2), funding capped at ±0.75% per event, leverage cap 1.0 on
dollar-neutral books, `backtest.portfolio_backtest` accounting. Stress row at 10 + 5 bps
reported for every book. Newey-West t-stats use 5 lags.

---

## A. Open-interest positioning (new data)

Wave 6 (#85) found OI 3-day change → next-day return, IC +0.057, t = +4.23, on the 30 days
the API serves. Binance's bulk archive (`data/futures/um/daily/metrics`) holds 5-minute OI back
to 2020-09-01, so it can now be tested properly.

- **Data.** Per symbol-day, the last 5-minute row of the UTC day (`sum_open_interest`,
  `sum_open_interest_value`), for every day a symbol is in the PIT universe and 3 days before.
- **Window.** 2020-09-04 → 2026-08-23. Wave 6's discovery window (2026-08-24 onward) is
  excluded from every statistic.
- **A1 (primary, as found).** signal = OI value (USD) 3-day % change, cross-sectional
  z-score within the universe; target = next-day close-to-close return. Daily Spearman rank IC;
  mean IC and NW t-stat.
- **A1b (mechanism, reported, not selected).** (i) OI in contracts (price-free) 3-day change;
  (ii) A1's signal residualized on the 3-day price return each day. Tells positioning apart from
  short-term momentum.
- **A2 (tradeable).** Dollar-neutral long top-10 / short bottom-10 by A1's signal, daily
  rebalance, funding included. **Declared variant A2w:** same signal, rebalanced every 7 days
  and held.
- **A3 (combination, only if A2 or A2w passes).** 50/50 gross blend with C3's backtest
  weights vs C3 alone.
- **Pass (all required):** A1 NW t ≥ 3.0 with the same sign in ≥ 4 of the 6 calendar years
  2021–2026; A2 or A2w net Sharpe ≥ 1.0 over the window and > 0 in its final 12 months;
  daily-return correlation with C3 < 0.5; A3 blend Sharpe above C3 alone in both halves of
  the window.

## B. Hedged funding carry (construction never tested)

Long spot + short perpetual on the same coin, equal notional: earns funding, hedges price.
V3 named it untested. Spot daily klines from `data/spot/monthly/klines` (1000X perps map to X
spot × 1000; a pairing whose median |spot − perp| / perp > 1% is dropped as mismapped).

- **Capital model.** capital = 1.5 × hedged notional (spot fully paid + perp margin at 2×).
  Idle capital earns 0. Returns are on capital. Daily P&L per pair on notional:
  spot return − perp return + funding received (00:00 UTC print paid by the position held
  before the rebalance, as live).
- **B1 (majors, static).** BTC and ETH, half the notional each, always on.
- **B2 (rotating).** Every 7 days, among pairs in the PIT top-30 by perp ADV that have spot,
  hold the top 5 by trailing 14-day mean daily funding, equal notional, only if that mean > 0
  (otherwise the slot stays in cash). Held 7 days. Costs charged on every notional change.
- **Pass (either book, all required):** net return on capital ≥ 5%/yr (≈ USDT savings rate);
  Sharpe ≥ 1.5; max drawdown no worse than −10%; positive in ≥ 5 of the 6 full years
  2020–2025. Unmodeled and stated: perp margin top-ups when a short rallies, exchange risk.

## C. Order-flow sleeve (contaminated — data already seen in waves 2–3)

Wave 2 #19 (taker-buy ratio z, OOS 1.14) was left out of wave3 on turnover; stacking it into
the score was tested and lost. The one untried construction is a **separate slow sleeve**.

- **Signal exactly as wave 2:** tbr = tbqav / qav clipped to [0.2, 0.8], 5-day mean, z-score in
  universe; long top-10 / short bottom-10; rebalanced every 7 days and held.
- **Book:** 50/50 gross blend with C3's backtest weights, vs C3 alone.
- **Pass:** blend Sharpe ≥ C3 Sharpe + 0.2 in BOTH halves of 2020-01 → 2026-09 and blend max
  drawdown no worse than C3's. Even a pass is contaminated evidence: paper candidate only.

---

## Multiple testing

V4 = 3 leads, 8 reported tests (A1, A1b×2, A2, A2w, A3, B1, B2, C). Every result is published.
A single "pass" among them is weaker evidence than it looks; the pass rules above are set
stricter than t = 2 for that reason. No further variants after results are seen.
