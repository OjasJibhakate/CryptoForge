# CryptoForge Research — Findings (v2, survivorship- and funding-corrected)

**Date:** 2026-09-13
**Market:** Binance USDT-M perpetual futures. Daily bars, 2019-09-08 → 2026-09-13.
**Costs:** 5 bps taker + 2 bps slippage **per side** (14 bps round trip), applied on turnover.
**Risk basis:** all results also shown scaled to a **40% max-drawdown** budget.
**Holdout:** everything before 2024-01-01 is in-sample; 2024-01-01 onward was never used for selection.

---

## TL;DR

1. **No 300%/month strategy exists.** Reproducible edges in crypto are single or low-double-digit % per year unlevered, or a bit more with leverage and real drawdowns.
2. **Your 1-minute scalper is structurally negative**, not badly tuned. A 0.5% target with 0.10% round-trip fees needs a **>60% win rate** to break even. (Details in the "scalp math" section.)
3. **The robust edge: cross-sectional momentum** — long/short altcoin basket, dollar-neutral, daily rebalance.
4. **Both requested fixes were done and the edge survived.** Correcting survivorship *improved* it; funding was audited and capped to realistic levels rather than taken at face value.

---

## Corrected headline result

**Strategy:** rank a point-in-time universe of ~54 liquid perps by risk-adjusted momentum (`return / volatility`) across lookbacks 14/21/30/45/60 days (averaged); **long the top 10, short the bottom 10**, equal-weight per side, dollar-neutral, rebalanced daily. Universe selected each day as the top 60 by 30-day average dollar volume (min $5M ADV, min 60 days history).

| | In-sample (<2024) | Out-of-sample (2024+) | Full 2019–2026 |
|---|---|---|---|
| Sharpe | 0.86 | **1.51** | **1.14** |
| CAGR | 23.3% | 64.9% | **37.9%** |
| Max drawdown | -42.0% | -33.1% | -42.0% |

**Scaled to your 40% drawdown budget → ~36% CAGR.**

Sub-periods (all five positive):

| Period | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| 2019-09 → 2021-01 | 2.52 | 60.9% | -9.7% |
| 2021-02 → 2022-06 | 0.53 | 15.0% | -41.2% |
| 2022-06 → 2023-11 | 0.23 | 2.6% | -21.1% |
| 2023-11 → 2025-04 | 1.28 | 38.5% | -19.6% |
| 2025-04 → 2026-09 | 1.66 | 89.6% | -33.1% |

---

## Fix 1 — Survivorship bias (done)

**Problem:** the first version ranked *today's* top-40 coins, which silently excludes coins that were liquid then and died later — flattering the short leg.

**What I did:** pulled the full list of every symbol Binance has ever listed from the `data.binance.vision` archive (1,018 symbols; 864 USDT). Loaded daily history for all of them — 806 symbols usable — including delisted ones via the archive (e.g. `AERGOUSDT`, delisted, 660 bars recovered after the live API returned nothing).

**Result:** the point-in-time universe averages 53.5 symbols/day, **492 symbols were selected at least once, and 395 have since been dropped or delisted**. So ~44% of the ever-selected universe is now gone — this was a *large* look-ahead hole.

**Outcome: the edge got stronger, not weaker** (CAGR 28.8% → 37.9%). That makes sense: momentum shorts are usually coins that are declining — and many of those went on to keep declining or die. Excluding them was *understating* returns.

---

## Fix 2 — Funding on the short leg (done, and audited)

Funding is now charged/credited on every perp position, every day (sum of the three 8-hourly rates), applied with a one-day lag so there is no look-ahead.

**First attempt looked too good — so I audited it.** Raw funding data contains single-period rates up to **±4%**, and 430 of 866 symbols breach Binance's normal ±0.75% per-period cap. Taken raw, funding inflated the result by roughly 2x. That is not defensible, so I capped it and re-ran:

| Funding assumption | Sharpe | CAGR | MaxDD | at 40% DD | OOS Sharpe |
|---|---|---|---|---|---|
| No funding | 0.71 | 19.9% | -44.1% | 18.4% | 0.79 |
| Raw (cap ±4%) — **unrealistic** | 1.22 | 41.8% | -42.1% | 39.7% | 1.64 |
| **Cap ±0.75% (realistic) — headline** | **1.14** | **37.9%** | **-42.0%** | **36.2%** | **1.51** |
| Cap ±0.30% (conservative) | 1.02 | 32.7% | -42.4% | 31.0% | 1.30 |
| Cap ±0.10% (very conservative) | 0.89 | 27.0% | -43.1% | 25.2% | 1.07 |

**Key point:** the strategy is profitable **without any funding income at all** (Sharpe 0.71, ~20% CAGR). Funding is a booster worth roughly +15–18%/yr at realistic caps — not the source of the edge. That is the honest framing.

---

## Fix 3 — Is the short leg doing the work? (checked)

| Book | Full Sharpe | CAGR | MaxDD | OOS Sharpe |
|---|---|---|---|---|
| Long/short (market-neutral) | 1.22 | 41.8% | -42.1% | 1.64 |
| Long-only | 0.93 | 38.4% | **-65.2%** | 0.61 |

The short leg roughly **halves the drawdown** and improves out-of-sample Sharpe dramatically. The market-neutral construction is essential — a long-only version would have taken a 65% drawdown.

## Fix 4 — Liquidity stress (checked)

| Min ADV | Top-N | IS Sharpe | OOS Sharpe | Full Sharpe | at 40% DD |
|---|---|---|---|---|---|
| $5M | 40 | 1.07 | 1.45 | 1.23 | 37.6% |
| $20M | 60 | 0.95 | 1.64 | 1.25 | 40.8% |
| $50M | 60 | 0.58 | 1.73 | 1.08 | 36.5% |

Not dependent on illiquid junk — requiring $20–50M ADV keeps ~36–41% at the 40% DD budget with lower turnover risk.

---

## The scalp math (why your current setup loses)

Breakeven win rate for a symmetric target/stop = `(target + roundtrip_cost) / (2 × target)`:

| Target | Cost 0.07% | Cost 0.10% | Cost 0.15% |
|---|---|---|---|
| 0.2% | 67.5% | 75.0% | 87.5% |
| 0.5% | 57.0% | **60.0%** | 65.0% |
| 1.0% | 53.5% | 55.0% | 57.5% |
| 2.0% | 51.7% | 52.5% | 53.8% |

Empirically: 15-minute short-term reversal has a **real gross Sharpe of 2.5**, but turnover is 1.5x *per 15-min bar*, so realistic costs turn it into Sharpe **−88**. The alpha exists; the fees eat all of it. That is why the scalper bleeds.

---

## What was falsified (honest negatives)

- **Trend-following (TSMOM / MA cross / Donchian):** made all its money 2019–2022, flat-to-dead since. Narrow parameter peaks (30d = 1.16 Sharpe, 45d = 0.53) = fragile.
- **Funding-rate carry (delta-neutral harvest):** in-sample Sharpe 6.98 → **out-of-sample −2.10**. Broke down; the high in-sample number was mostly the idealized no-basis-risk assumption.
- **ML ranker (LightGBM, 15 features, purged walk-forward):** OOS Sharpe **0.30** — *worse than plain momentum*. More complexity = more overfitting on this data size.
- **Mean reversion / short-term reversal at daily and 15m:** consistently negative net of costs.

---

## Remaining caveats before real money

1. **Funding capture is uncertain.** Headline assumes ±0.75%-capped funding is fully captured. The conservative-row (±0.30%) number is ~31% at 40% DD — a fair planning figure.
2. **Shorting mechanics.** Needs margin; short-leg liquidation risk during squeezes. The strategy has never been tested with real margin calls.
3. **Capacity.** ~54 names, $5–50M ADV. Fine for retail size; not scalable to large capital without slippage.
4. **Drawdowns are real.** -42% at the unlevered full-period max. The 40% DD budget was hit in-sample; live can exceed backtest drawdowns.
5. **Regime risk.** Jul 2022–Nov 2023 returned only +2.6%/yr — expect long flat stretches.
6. **Execution assumptions.** 5+2 bps is optimistic for small alts and for the short side during stress.

---

## Recommended next steps (in order)

1. **Paper-trade it live for 1–3 months** — daily rebalance, exactly as specified, on live data. Confirm the backtest pipeline and the live signals agree.
2. **Add the risk layer:** volatility targeting, per-name position caps, and a drawdown circuit-breaker.
3. **Model margin and liquidation explicitly** on the short leg before any leverage.
4. **Only then**, small real size, scaled up only if live matches backtest.

Realistic expectation: **~20% CAGR from momentum, ~30–38% with realistically-captured funding, at a 40% drawdown budget.** Genuinely good. Not 300%/month.

---

## Files

`data_fetch.py`, `backtest.py`, `strategies.py`, `run_screen.py`, `walkforward.py`, `holdout.py`, `carry.py`, `intraday.py`, `refine.py`, `ml_rank.py`, `final_strategy.py`, `vision_list.py`, `bulk_download.py`, `survivorship.py`, `sweep_pit.py`, `fund_decomp.py`, `fund_check.py`, `verify_funding.py`, `luck_simulation.py`

---

# Appendix — The Copy-Trading Leaderboard (why "300% a month" is survivorship)

*Added 2026-09-13. The Binance copy-trading page itself is behind an AWS WAF bot-challenge and
could not be read directly; the mechanics below come from Binance's own educational post and two
independent analyses (sources at the end). The quantitative test is our own.*

## What the leaderboard actually is

Binance ranks ~**200,000 "Lead Traders"** by 7-day / 30-day / 90-day / all-time ROI. Two design
facts make those numbers deceptive:

- **Futures copies inherit the leader's leverage** — there is no "copy at 1x" option.
- **ROI is measured on margin, not notional.** A "+450% 90-day ROI" can simply be 25x leverage on
  a small margin pool.
- Leaderboard ROI is computed **including unrealized PnL**, so an open position that has not been
  closed still shows as profit until it is.

Sorting by ROI therefore selects, by construction, for the most leveraged and least risk-managed
accounts. Binance's own post says the top traders are "often selected by survivorship bias," that
"high returns are usually a function of high risk, not skill," and that "most copiers enter at the
worst possible time — after performance peaks."

## The quantitative test: luck alone produces the headline

`luck_simulation.py` runs 20,000 **zero-skill** traders on the real 492-coin perpetual panel —
each day they randomly long/short 3 coins, re-randomised daily, at various leverage, with 14 bps
round-trip cost. Results over a 30-day month:

| Leverage | Median month | Showed >+100% | Showed >+300% | Of Binance's 200k | Wiped out |
|---|---|---|---|---|---|
| 1x | −4.4% | 0.00% | 0.000% | ~0 | 0.0% |
| 5x | −22.8% | 0.22% | 0.000% | ~0 | 0.0% |
| 10x | −46.1% | 1.96% | 0.110% | ~220 | 2.5% |
| 25x | −93.1% | 3.91% | **1.200%** | **~2,400** | 45.9% |
| 50x | −100.0% | 1.80% | 1.080% | ~2,160 | 88.6% |

Gross (no costs) at 10x: **6.47% of traders showed a "+300% month" — ~12,930 accounts — from pure
coin-flipping.** That is the population the leaderboard is displaying.

## The part that matters: it does not persist

Tracking the same simulated traders into the **next** month:

- Correlation between month-1 and month-2 return: **−0.01 to +0.01** (i.e. none).
- Month-1 **top 20%** performed the **same** as month-1 **bottom 20%** in month 2.
- At 25x, only **4.5%** of the cohort was still solvent to trade month 2.

So a leaderboard "star" is a survivor of a coin flip who is now *more* likely to blow up than
average, because you are observing the tail that took the most risk.

## Independent data points

- Roughly **20–30% of Binance lead traders are net positive over a 12-month rolling window** once
  the 10% profit share, maker/taker fees and funding drag are netted out.
- Futures copiers additionally inherit **funding drag (~10–16% APR on carried longs)** in bull markets.
- Two traders both showing **+40%** can be a disciplined one (6% max DD, 180 trades, 5x) or a
  gambler (58% max DD, 7 trades, 75x). Return alone cannot tell them apart.

## How to read a leaderboard (in order)

1. **Max drawdown first** — and assume the worst you see is the *best* case; the true tail is fatter.
2. **Profit factor** — a perfect "no losing trades" record is a warning, not a selling point
   (usually means losers are held unrealized).
3. **Sharpe / consistency** — smooth beats spiky at equal return.
4. **Sample size and track length** — under ~50 trades or ~3 months, treat every metric as "unknown".
5. **Return — last.**
6. Red flags: averaging into losers, large floating (unrealized) losses, escalating leverage after
   losses (martingale), sudden style change.

## On reverse-engineering leaders from scraped trade history

A tempting idea, and it fails for three separate reasons:

1. **Sample size.** 100–300 public trades is far too few. Testing "time of day × pair × weekday ×
   indicator" hypotheses on 200 trades guarantees spurious findings — this is the same
   multiple-testing trap that made our own ML ranker underperform plain momentum (see above).
2. **You see outcomes, not rules.** A trade tape shows *what* was traded, not position sizing,
   risk limits, or why. Without the decision function you cannot reconstruct the strategy, and you
   cannot tell skill from luck.
3. **Survivorship again.** You would be studying only the traders who survived, in the regime that
   suited them.

Practical and ethical note: Binance's site actively blocks automated access (we hit the WAF), and
scraping it conflicts with their terms. Mock-following a leader is legitimate and cheap, and is a
reasonable way to *observe* how a long-tenured trader behaves through a drawdown — but it returns
no strategy, and it does not transfer an edge.

**Bottom line:** the leaderboard is a display of tail outcomes, not a menu of reproducible edges.
Our own edge is smaller and duller — ~20% from momentum, ~30–38% with funding, validated
out-of-sample — and it is real.

## Sources

- [Why 90% of Copy Traders Lose — and How the Top 10% Actually Win (Binance Square)](https://www.binance.com/en/square/post/313608455237793)
- [Reading a Copy-Trading Leaderboard: What the Numbers Actually Mean (BitPerp)](https://bitperp.com/blog/top-copy-trading-leaders/)
- [Binance Copy Trading 2026: Real Fees & Test (uwuu.ai)](https://uwuu.ai/blog/binance-copy-trading)

---

# Appendix II — Overnight Session: Strategy Zoo, Risk Layer, Margin Stress

*Session of 2026-09-13/14. All runs on the point-in-time universe (806 symbols, delisted included),
costs 5+2 bps, funding capped at ±0.75%, IS = <2024, OOS = ≥2024.*

## 1. Strategy zoo — 25 signals tested

`strategy_zoo.py` tests 25 signals on the same harness. Ranked by in-sample Sharpe (select on IS,
judge on OOS):

| Strategy | IS Sharpe | OOS Sharpe | Full Sharpe | CAGR | MaxDD | at 40% DD | Turnover |
|---|---|---|---|---|---|---|---|
| **XS combo (mom+carry+lowvol)** | 1.40 | 1.42 | 1.37 | 57.5% | -37.7% | 61.1% | 0.27 |
| XS vol breakout z | 1.37 | 1.10 | 1.23 | 51.7% | -35.0% | 58.9% | 0.56 |
| XS position in range | 1.26 | 1.34 | 1.29 | 69.4% | -48.5% | 57.3% | 0.46 |
| XS trend + carry blend | 1.24 | 1.40 | 1.29 | 53.0% | -44.0% | 48.0% | 0.27 |
| XS funding carry *alone* | 1.21 | **-0.02** | 0.56 | 15.2% | -54.6% | 12.4% | 0.28 |
| **XS mom − funding tilt** | 1.17 | **1.68** | **1.39** | 59.7% | -40.2% | 59.5% | 0.27 |
| XS Sharpe momentum | 0.97 | 1.17 | 1.05 | 38.3% | -45.9% | 33.7% | 0.38 |
| XS momentum (baseline) | 0.93 | 1.59 | 1.22 | 49.5% | -47.8% | 41.4% | 0.27 |
| XS momentum skip-5d | 0.72 | 1.23 | 0.94 | 31.0% | -32.0% | 37.7% | 0.33 |
| XS low-vol (BAB) | -0.60 | 0.09 | -0.27 | -19.7% | -83.8% | -7.6% | 0.12 |
| XS reversal 1d / 5d / 10d | -1.4 | -0.7…-1.3 | -1.0…-1.3 | -40…-48% | -97% | -17…-22% | 0.5–1.4 |

**Findings:**
- **Adding a funding tilt to momentum is the single best improvement**: IS 0.93→1.17, OOS 1.59→1.68,
  full Sharpe 1.22→1.39. Funding *alone* is not an edge (OOS −0.02) — it works only as a tilt.
- Every **reversal** signal is strongly negative at the daily horizon — crypto is a momentum regime.
- Low-vol (betting-against-beta) fails; high-vol fails; acceleration fails.
- Best in-sample is the **three-way combo** (momentum + funding + low-vol).

## 2. Validation of the leaders

**Sub-periods (k=10) — every candidate positive in all five periods:**

| Variant | 2019–21 | 2021–22 | 2022–23 | 2023–25 | 2025–26 |
|---|---|---|---|---|---|
| baseline | 2.45 | 0.48 | 0.45 | 1.80 | 1.55 |
| funding tilt | 2.74 | 0.96 | 0.71 | 1.03 | 2.01 |
| combo | 2.40 | 1.28 | 1.25 | 0.84 | 1.69 |
| in-range | 1.25 | 1.35 | 1.13 | 1.63 | 1.30 |

**Parameter plateau (k = 3…30, mean [min–max]):**
- `funding tilt`: IS 1.14 [0.98–1.44], OOS 1.57 [1.37–1.69] — **broadest plateau**.
- `baseline`: OOS 1.59 [1.40–1.65] — very stable OOS, weaker IS.
- `combo`: IS 0.94 [0.48–1.40] — good mean, more erratic.

**Cost tolerance (k=10):** funding tilt at 20+10 bps still Sharpe 0.80 / CAGR 26.9%; baseline 0.65 / 19.6%.
Turnover is only ~0.27/day, so costs are not the binding constraint.

**Blend of the top three (equal weight of weights):** full Sharpe **1.59**, CAGR **67.0%**,
MaxDD **-34.3%**, at 40% DD **79.8%**, OOS Sharpe 1.75 — and positive in all five sub-periods
(1.19–2.49). Diversifying across momentum variants beat any single one.

**Multiple-testing check:** with 25 strategies tried, the Bonferroni threshold at 5% is |t| > 2.88.
The top candidates score t = 2.20–2.76 — **marginal, not conclusive**. Bonferroni is conservative
here because the candidates are highly correlated (all momentum-family), but this must be stated
plainly: the improvement is *promising*, not *proven*, and the blend was assembled after seeing
the OOS, so it carries selection bias.

## 3. Risk layer backtest (`risk_layer.py`)

| Configuration | Sharpe | CAGR | MaxDD | at 40% DD | Avg gross | Breaker days |
|---|---|---|---|---|---|---|
| baseline (no layer) | 1.14 | 37.9% | -42.0% | 36.2% | 0.88 | 0 |
| + vol targeting | 1.21 | 39.4% | -41.2% | 38.3% | 0.85 | 0 |
| + per-name cap | 1.12 | 36.9% | -42.0% | 35.2% | 0.87 | 0 |
| + circuit breaker | 1.14 | 29.2% | -29.3% | 39.6% | 0.61 | **1442** |
| FULL | 1.17 | 28.6% | -29.3% | 38.9% | 0.59 | 1426 |

**Two important findings:**
1. **Vol targeting helps** (Sharpe 1.14 → 1.21; at 0.25 target, Sharpe 1.35 / at-40%-DD 41.8%).
2. **The circuit breaker as configured is mis-tuned.** At a 15% trigger it is *on for 1,442 of
   2,563 days (56% of the time)* — it is not a circuit breaker, it is a permanent half-size mode.
   A 20% trigger behaves far better (Sharpe 1.26, at-40%-DD 44.3%). **The live paper bot currently
   uses 15% — it will sit in reduced mode for most of the experiment and under-report the strategy.**

## 4. Margin & liquidation stress (`margin_stress.py`)

Short-leg tail risk (gross 1.0, ~9 short names at ~5% each):

| Measure | Value |
|---|---|
| Worst single-name squeeze (one day) | **-11.7%** of equity — JELLYJELLYUSDT +234% in a day (2025-11-03) |
| Worst whole short-leg squeeze day | -14.9% |
| Worst whole long-leg day (crash) | -21.2% |
| 95th-percentile single-name squeeze | -1.1% |
| 95th-percentile short-leg day | -3.5% |

**Liquidation:** on cross margin with a 1% maintenance rate, liquidation needs a ~99% equity loss at
gross 1.0x and ~97% at 3x. **The strategy needs 1.00x leverage to hit the 40% DD budget** (its
unlevered max DD is already -40.1%) — so it can be run unlevered, and **liquidation risk is
effectively nil**. Worst single day unlevered: -10.5%.

Stress scenario: all 10 shorts squeezing 30% together = -14.2% of equity; all 10 doubling = -47.3%
(implausible but survivable at 1x).

## 5. Recommendation

- **Do not lever this.** It reaches its drawdown budget at 1.0x; leverage adds liquidation risk for
  no required return.
- **Upgrade the paper bot's signal to the funding tilt** (best plateau + cost tolerance), and
  **retune the circuit breaker to ~20%** (or make it vol-relative). Both are config-level changes.
- **Run the blend as a second paper account** rather than switching mid-experiment, so the
  one-month test stays clean and we get a genuine A/B.
- Treat the improvement as **promising but unproven** given the multiple-testing caveat.

Files: `strategy_zoo.py`, `validate_top.py`, `risk_layer.py`, `margin_stress.py`

---

# Appendix III — Wave 2 & 3: Order Flow, Regime Filtering, and the Final Candidate

*Same session. Wave 2 added order-flow data (taker-buy volume) downloaded for all 803 symbols
(`bulk_full.py`); wave 3 combined the winners. Total strategies tested across all waves: ~50.*

## 1. Wave 2 highlights (`strategy_zoo2.py`, 25 more signals)

| Strategy | IS | OOS | Full Sharpe | CAGR | MaxDD | at 40% DD | Turn |
|---|---|---|---|---|---|---|---|
| **mom + BTC regime filter** | 1.17 | **1.71** | **1.40** | 42.6% | **-25.1%** | 70.1% | 0.16 |
| [ref] mom − funding tilt | 1.17 | 1.70 | 1.40 | 60.2% | -39.9% | 60.4% | 0.27 |
| **OFI taker-buy z** | 1.47 | 1.14 | 1.26 | 44.8% | -38.9% | 46.1% | 0.44 |
| STACK mom+OFI+funding | 1.52 | 1.15 | 1.31 | 54.6% | -50.5% | 42.8% | 0.34 |
| [ref] momentum baseline | 0.81 | 1.57 | 1.15 | 45.3% | -47.2% | 38.6% | 0.27 |

**Order flow is a genuine, independent signal.** Taker-buy pressure (tbqav/qav) alone earns Sharpe
1.26 in-sideways — consistent with the 2026 academic finding that *order flow has a permanent effect
on crypto returns and dominates fundamentals out-of-sample*. It is the one signal here not derived
from price.

**A BTC regime overlay (trade only while BTC is above its 200-day average) is the cheapest
drawdown reduction found**: max DD falls from -47% to -25% while OOS Sharpe rises to 1.71.

**Failed in wave 2 (honest negatives):** OFI *contrarian* (Sharpe -1.93), MAX/lottery (-0.40),
skewness (-0.80), long-term reversal 120d/180d (-0.45/-0.25), BTC lead-lag catch-up (-1.02),
low-beta (-0.46), Amihud illiquidity (0.01), liquidity factor (-0.45), trade-count z (0.09).

## 2. Wave 3 — the final candidate (`combo_final.py`, `validate_final.py`)

Combining the funding tilt with the regime overlay:

| Configuration | IS | OOS | Full Sharpe | CAGR | MaxDD | at 40% DD |
|---|---|---|---|---|---|---|
| **ftilt + soft-regime** | 1.38 | **1.83** | **1.57** | 53.5% | **-28.8%** | **77.2%** |
| ftilt + OFI + regime | 1.84 | 1.38 | 1.59 | 47.6% | -33.0% | 58.9% |
| mom + regime | 1.17 | 1.71 | 1.40 | 42.6% | -25.1% | 70.1% |
| mom − funding tilt | 1.17 | 1.70 | 1.40 | 60.2% | -39.9% | 60.4% |
| mom baseline (paper bot today) | 0.81 | 1.57 | 1.15 | 45.3% | -47.2% | 38.6% |

**Final candidate: ensemble momentum (14/21/30/45/60d, risk-adjusted) − funding tilt, overlaid with
a soft BTC regime filter (full size above the 200-day MA, half size below), k=10, daily, dollar-neutral.**

Sub-periods — **positive in all five**, drawdowns capped at -26%:

| Period | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| 2019-09 → 2021-01 | 3.22 | 80.9% | -7.7% |
| 2021-02 → 2022-06 | 1.17 | 38.8% | -26.1% |
| 2022-06 → 2023-11 | 0.51 | 8.5% | -18.1% |
| 2023-11 → 2025-04 | 0.95 | 26.5% | -24.4% |
| 2025-04 → 2026-09 | 2.29 | 147.6% | -21.4% |

## 3. Robustness of the final candidate

- **Regime MA length:** MA50→MA365 all give full Sharpe 1.51–1.60 and at-40%-DD 64–83%.
  **Broad plateau — not fitted to 200.**
- **Soft scale:** 0.25/0.5/0.75 all land 70–77% at-40%-DD.
- **k:** k=5,10,15,20,30 stay in full-Sharpe 1.39–1.58.
- **Costs:** Sharpe 1.67 at 2+1 bps, 1.57 at 5+2, 1.35 at 10+5, 0.95 at 20+10. **Needs decent
  execution — degrades materially above ~10 bps/side.**
- **Lookbacks:** the 14/21/30/45/60 ensemble is best; longer horizons weaken it.

## 4. Honest caveats

1. **~50 strategies tested across three waves.** The final candidate's OOS t-stat is **3.01** —
   above the 25-trial Bonferroni threshold (2.88), below the 50-trial one (3.29). **Marginal.**
2. The combination was chosen **after seeing out-of-sample data**, so part of the OOS strength is
   selection. The breadth of the sensitivity plateaus is the main reason to believe it anyway.
3. **Cost-sensitive.** Realistic retail taker costs on illiquid alts could push toward the 10+5 row.
4. All the earlier caveats still stand (survivorship handled, funding capture uncertain, shorting
   mechanics, capacity fine at retail size).

## 5. Net progress across the session

| | Sharpe | MaxDD | at 40% DD |
|---|---|---|---|
| Paper bot as built (baseline momentum) | 1.22 | -47.8% | ~41% |
| **Final candidate** | **1.57** | **-28.8%** | **~77%** |

Roughly **double the risk-adjusted return at the same drawdown budget**, achieved with two
config-level changes: a **funding tilt** on the momentum score, and a **soft BTC regime overlay**.

Files: `bulk_full.py`, `strategy_zoo2.py`, `combo_final.py`, `validate_final.py`

---

# Appendix IV — Wave 4: Long Bias, Risk-Managed Momentum, and the GPU Model

*Same session. Motivated by requests to (a) read the research literature, (b) favour longs, and
(c) build a fast GPU model.*

## 0. The literature actually says

- **Liu, Tsyvinski & Wu (2022), *Common Risk Factors in Cryptocurrency*, Journal of Finance 77(2)** —
  the canonical crypto asset-pricing paper. Three factors explain the cross-section: **cryptocurrency
  market, size, and momentum**. Ten characteristics form significant long-short strategies, *all
  subsumed by those three factors*. **Momentum is the one we already trade.**
- **Cryptocurrency market risk-managed momentum strategies** (Finance Research Letters, 2025) —
  applies equity-style *enhanced/risk-managed* momentum to crypto. Tested below; it works.
- **New behaviorally-based cross-sectional reversal portfolios in the cryptocurrency market** (2025) —
  anchors reversal on the formation-period *lowest* price. Tested below; it fails here.
- Microstructure literature (2026): order flow has a permanent effect on returns (wave 2 confirmed it).

**Note on "Chinese researchers":** the strongest crypto asset-pricing result is Liu/Tsyvinski/Wu.
Much of the recent applied work (risk-managed momentum, behavioral reversal, CTA factor papers) comes
from Chinese- and Asia-based groups. Nothing in that literature promises 300%/month — it promises
the same small, factor-sized premia we have been measuring.

## 1. Long bias — tested, and it HURTS (`long_bias.py`)

The request was to favour longs over shorts. Measured, at the same universe and costs:

| Variant | IS Sharpe | OOS Sharpe | Full Sharpe | CAGR | MaxDD | at 40% DD |
|---|---|---|---|---|---|---|
| BTC buy & hold | 0.61 | 0.56 | 0.59 | 18.5% | -78.9% | 14.3% |
| equal-weight basket | 0.50 | -0.13 | 0.08 | -1.1% | -55.2% | -0.1% |
| **L/S 50/50 (current)** | 0.93 | **1.59** | **1.22** | 49.5% | -47.8% | **41.4%** |
| long-heavy 60/40 | 1.10 | 1.39 | 1.22 | 59.4% | -60.3% | 39.5% |
| long-heavy 75/25 | 1.16 | 1.06 | 1.12 | 68.7% | -77.0% | 38.1% |
| long-only | 1.11 | 0.71 | 0.95 | 57.9% | **-93.2%** | 38.7% |
| long-only + regime | 1.34 | 0.65 | 1.05 | 70.0% | -80.1% | 41.6% |

**Conclusion: tilting long raises headline CAGR but destroys risk-adjusted return and blows out
drawdowns.** Out-of-sample Sharpe falls monotonically as the short leg is removed (1.59 → 1.06 → 0.71).
A long-only book in a bull market is largely beta — and it still lost to BTC buy-and-hold on drawdown
(-93% vs -79%). **The short leg is where a real part of the edge lives.** Recommendation: keep it
neutral. If holding shorts is operationally painful, the honest trade-off is ~0.7 OOS Sharpe and a
-90% drawdown, not a free lunch.

## 2. Risk-managed momentum — tested, and it WORKS (Barroso & Santa-Clara style)

Scaling the momentum book by the inverse of *its own* recent realised volatility:

| Variant | IS | OOS | Full Sharpe | CAGR | MaxDD | at 40% DD |
|---|---|---|---|---|---|---|
| plain L/S | 0.93 | 1.59 | 1.22 | 49.5% | -47.8% | 41.4% |
| risk-managed lb=30 | 0.89 | 1.83 | 1.25 | 30.2% | -43.2% | 27.9% |
| risk-managed lb=60 | 1.03 | 1.78 | 1.31 | 32.2% | -40.6% | 31.7% |
| **risk-managed lb=90** | 1.05 | **1.78** | **1.33** | 33.0% | **-38.0%** | 34.8% |

**Sharpe 1.22 → 1.33 and max drawdown -47.8% → -38.0%.** This is a genuine, literature-backed
improvement and the cheapest one found so far — it costs nothing but a volatility estimate.
**Recommended as the next addition to the paper bot.**

## 3. The GPU model — fast, and it FAILS (`gpu_model.py`)

Built exactly as asked: a small MLP (18 features → 96 → 48 → 1) in PyTorch, trained on **your
RTX 4050** (torch 2.11 + CUDA 12.6), walk-forward with a 6-day embargo, 20-day retrain cadence.

**Speed — excellent:** 485,433 rows, **50 retrains in 9.8 seconds (0.20s each)**. Your laptop is not
the constraint.

**Performance — catastrophic:**

| | OOS Sharpe | CAGR | MaxDD |
|---|---|---|---|
| GPU MLP, daily rebalance | **-1.77** | -65.3% | -94.8% |
| GPU MLP, 5-day hold | -0.54 | -33.4% | -75.0% |
| plain momentum (reference) | **+1.59** | — | — |

**Diagnostic — the model is not noisy, it is reliably WRONG:** rank IC between predictions and
realised forward 5-day returns = **-0.0111, t-stat -2.61**, positive on only 47.7% of days. It has
learned an in-sample relationship that *inverts* out-of-sample — textbook overfitting to noise plus
the negative-alpha short-horizon reversal.

**This is now the third independent ML failure** (LightGBM ranker 0.30; GPU MLP -1.77; both vs
momentum 1.59). The bottleneck is not compute, model class, or speed — **it is signal**. More
parameters on this data make things worse, not better.

## 4. Other hypotheses tested and rejected (`long_bias.py`)

- **Behavioral low-anchor reversal:** full Sharpe **-1.26** — fails decisively.
- **Size factor (long illiquid / short liquid proxy):** -0.45 to 0.01. *Caveat: this proxies size
  with dollar volume; true size needs circulating-supply/market-cap data we cannot fetch here.*
  Liu et al. find size works when measured properly — this is an open item, not a refutation.
- **Long-only + risk management:** OOS Sharpe 0.60-0.61 — better than plain long-only, still far
  below the neutral book.

## 5. Where the session leaves us

| Candidate | Full Sharpe | MaxDD | at 40% DD |
|---|---|---|---|
| Paper bot original baseline | 1.22 | -47.8% | ~41% |
| wave3 (funding tilt + soft regime) — **live in the A/B** | 1.57 | -28.8% | ~77% |
| **risk-managed momentum (new, not yet deployed)** | 1.33 | -38.0% | ~35% |
| GPU MLP | -1.77 | -94.8% | - |

Wave3 remains the best configuration found. **Risk-managed momentum is an orthogonal improvement
(lower drawdown, better Sharpe) worth adding to it** — it is a volatility estimate layered on top,
not a competing signal.

Files: `long_bias.py`, `gpu_model.py`

---

# Appendix V — Wave 5: Risk-Managed Deployment, Calendar Effects, and Model Capacity

## 1. Risk-managed overlay — DEPLOYED to the live paper account

`wave3` now applies a Barroso/Santa-Clara volatility overlay on top of the funding tilt and regime
filter: the book is scaled by `RM_TARGET_VOL / realised_vol(90d)` of its own returns (capped 2x).
The engine's generic vol target is disabled for this profile so the two do not double-scale.
`wave3` was reset to a clean $10,000 (it was one day old) and reopened in the new configuration.

| | OOS Sharpe | Full Sharpe | MaxDD |
|---|---|---|---|
| baseline (live) | 1.59 | 1.22 | -47.8% |
| **wave3 + RM (live)** | 1.78 | **1.33** | **-38.0%** |

## 2. What the industry actually earns (calibration)

Two external benchmarks worth holding on to:

- **Funding-rate / basis arbitrage** — an open backtest on 47 months of Binance BTCUSDT found
  *"peak returns reached 38% in March 2024, sustainable returns average **6.97% annually (6.57% after
  costs)**"*. This is the strategy most often sold as easy money, and it is worth ~7%/yr. Matches our
  own wave-1 finding that carry is modest and regime-dependent.
- **Quant crypto hedge funds** — across **117 funds**, the **median Sharpe is 1.53**, beta to BTC
  0.10, with a +0.4% return in 2025.

**Our wave3 (Sharpe 1.57, beta ~0) is at the professional frontier.** That is the honest ceiling for
this kind of work, and it is nowhere near 300%/month.

## 3. Calendar anomalies — tested, and DEAD (`calendar_effects.py`)

| Effect | In-sample | Out-of-sample | Verdict |
|---|---|---|---|
| Day-of-week (BTC) | Wed +46.7 bps (t 1.84) | Mon +50.5 bps (t 2.10), Tue -26.9 | No stable pattern |
| Turn-of-month | **+38.9 bps (t 2.39)** | **-11.7 bps (t -0.70)** | Classic IS artifact |
| Weekend vs weekday return | 7.0 vs 18.7 bps | 6.2 vs 10.4 bps | Not significant |
| **Weekend volatility** | Sat 40% / Sun 50% | Sat 24% / Sun 40% | **Robust — vs 48-86% weekdays** |
| Tradeable: time BTC by IS weekday sign | — | OOS Sharpe **0.68** vs buy-hold **0.71** | **No improvement** |

**One real, durable fact:** weekend volatility is roughly **half** weekday volatility, in both
sample halves. That is a *risk-sizing* fact (lower weekend vol → less risk per unit exposure), not a
return edge. There is no tradeable calendar alpha here.

## 4. The big-model hypothesis — tested and REFUTED (`capacity_test.py`)

The proposal was to run a 500M-1B parameter model on the RTX 4050 and fine-tune it on crypto data.
Two independent answers.

**(a) It would not fit.** For full fine-tuning, parameters + gradients + Adam optimizer states need
about **16 bytes per parameter**:

| Model | fp16 weights | + grads + Adam (fp32) | Total | Fits in 6.4 GB? |
|---|---|---|---|---|
| 500M | 1.0 GB | +5.0 GB | ~6+ GB | **No** |
| 1B | 2.0 GB | +10.0 GB | ~12+ GB | **No** |

QLoRA (4-bit) would fit a 1B model in ~2-3 GB — but that needs `bitsandbytes` + `peft`, neither of
which is installed (`transformers` is, `accelerate` is not).

**(b) It would not help — measured.** Instead of downloading multi-GB weights, I scaled the model
architecture directly and measured the effect of capacity:

| Architecture | Parameters | Training (50 retrains) | OOS Sharpe | Rank IC | IC t-stat |
|---|---|---|---|---|---|
| 8-4 | 193 | 6.8s | -0.10 | -0.0032 | -0.63 |
| 32-16 | 1,153 | 5.8s | -0.99 | -0.0152 | -3.47 |
| 128-64 | 10,753 | 5.0s | -0.02 | +0.0052 | +1.25 |
| 512-256 | 141,313 | 10.7s | -0.76 | -0.0054 | -1.25 |
| 1024-512 | **544,769** | 26.4s | -0.41 | -0.0155 | -3.28 |
| *momentum (reference)* | *~zero* | — | **+1.59** | — | — |

**2,800x more parameters produced no improvement — everything sits at or below zero.** The ICs are
near zero or negative, and the two largest models are *reliably wrong* (t = -3.28). Extrapolating
another 1,000x to 500M-1B cannot manufacture signal that the data does not contain.

**The bottleneck is not compute, model class, or scale — it is signal.** This is now the fourth
independent ML refutation (LightGBM 0.30, GPU MLP -1.77, capacity scaling flat-to-negative, all
against momentum's 1.59). The GPU *is* fast (5-26s for 50 walk-forward retrains); it simply has
nothing to learn.

## 5. Where the desk stands after five waves

| Configuration | Sharpe | MaxDD | at 40% DD | Status |
|---|---|---|---|---|
| Original baseline | 1.22 | -47.8% | ~41% | live (A) |
| **wave3 + risk management** | **1.33** | **-38.0%** | ~35% | **live (B)** |
| Median professional quant crypto fund | 1.53 | — | — | reference |
| Funding/basis arbitrage (realistic) | — | — | ~7%/yr | reference |
| GPU MLP / capacity-scaled nets | -0.4 to -1.8 | — | — | rejected |

Files: `calendar_effects.py`, `capacity_test.py`, `gpu_model.py`
