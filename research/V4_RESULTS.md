# CryptoForge V4 — Results (pre-registered, run once)

*Protocol: [V4_PREREG.md](V4_PREREG.md), committed 519427b on 2026-09-30 01:47 IST before any
V4 data was downloaded. Tests: `research/v4_tests.py`, data: `research/v4_download.py`. One run,
2026-09-30. Nothing below was tuned after the fact.*

## Verdicts

| Lead | Verdict | One line |
|---|---|---|
| A. Open-interest positioning | **FAIL** | Wave 6's t = +4.23 was a 30-day fluke: over six years the day-ahead sign is reversed, and OI itself carries nothing once price is removed |
| B. Hedged funding carry | **PASS (B1 only)** | BTC+ETH spot-long / perp-short: +8.5%/yr on capital, max DD −1.1%, 6/6 years positive — but only +3.4% in 2025 and +0.8% in 2026 so far, below a USDT savings rate |
| C. Order-flow sleeve | **FAIL** | Cuts drawdown but misses the Sharpe bar in the first half and loses 0.68 in the second |

## A. Open-interest positioning (new data: 6 years of 5-minute OI, 80.5% of universe symbol-days)

| Test | Result |
|---|---|
| A1 OI value 3d change → next day | rank IC **−0.0145**, NW t **−3.19** (wrong sign vs wave 6's +0.057) |
| by year | 2021 −0.067 · 2022 −0.029 · 2023 −0.029 · 2024 −0.028 · 2025 +0.005 · 2026 +0.027 |
| A1b(i) OI contracts (price-free) | IC −0.0023, t −0.57 — **no positioning signal** |
| A1b(ii) residual on 3d price return | IC +0.0145, t +3.48; 3d price return alone IC −0.035, t −7.44 |
| A2 daily L/S | Sharpe **−0.70**, CAGR −28%, max DD −88% (turnover eats it) |
| A2w weekly L/S | Sharpe +1.16, CAGR +39%, max DD −31%, final 12m +1.97, corr with C3 +0.23 |
| A3 blend with C3 (A2w) | first half 0.88 vs C3 1.01 ✗, second half 2.02 vs 1.64 ✓ |

**Reading.** The A1 signal is mostly a price effect: OI *value* moves with price, and the strong
term is 3-day price reversal (t −7.4), which daily-bar costs have already killed in wave 1.
Positioning measured in contracts predicts nothing. The recent positive IC (2025–26) is the
regime wave 6 happened to sample. A2w's standalone weekly result is the one interesting number,
but it contradicts the day-ahead sign, fails the pre-registered combination test, and was
seen here — it is not a candidate. If ever pursued, it needs its own pre-registration judged on
future paper data only.

## B. Hedged funding carry (254 spot/perp pairs; FTT dropped as mismapped)

Capital = 1.5 × hedged notional (spot paid in full + perp margin at 2×); idle capital earns 0.

| Book | Net %/yr on capital | Sharpe | Max DD | Positive years 2020–25 | Funding | Costs |
|---|---|---|---|---|---|---|
| **B1 BTC+ETH static** | **+8.5%** | 8.62 | −1.1% | **6/6** | +8.3%/yr | 0.04%/yr |
| B2 rotating top-5 | +6.0% | 3.10 | −5.6% | 3/6 ✗ | +11.6%/yr | 5.50%/yr |

B1 by year: 2020 +15.2% · 2021 +25.4% · 2022 +1.6% · 2023 +5.4% · 2024 +8.7% · 2025 +3.4% ·
2026 YTD +0.8%. B2 by year: 2020 +11.8% · 2021 +38.1% · 2022 −3.2% · 2023 −1.5% · 2024 +6.1% ·
2025 −3.6% · 2026 YTD −1.8%.

**Reading.** Hedged carry is real and extremely steady on BTC/ETH, and it is a *bull-market*
yield: most of the 8.5% came in 2020–21. In 2025–26 it earns less than parking USDT in savings,
so it is a tool to switch on when funding is rich, not a profit engine today. Chasing the
richest alt funding (B2) loses to costs and to funding that flips once you arrive. The Sharpe of
8.6 overstates live reality: unmodeled are exchange risk, perp margin top-ups in sharp rallies,
and intraday basis moves that daily closes hide.

## C. Order-flow sleeve (contaminated evidence)

| | First half | Second half | Max DD |
|---|---|---|---|
| C3 alone | 1.14 | 1.88 | −32.3% |
| 50/50 C3 + weekly OFI sleeve | 1.33 | 1.20 | −24.6% |

OFI sleeve alone: Sharpe 0.68, corr with C3 +0.40. Misses the +0.2 bar by 0.01 in the first
half and loses 0.68 in the second. It lowers drawdown, but so would simply holding less C3.

## What V4 means

Three genuinely new leads, tested with discipline: one pass, and that pass is a low-yield
hedge that currently earns less than a savings account. The price/volume and positioning data
available to this project have been searched thoroughly (~115 mechanisms plus V2/V3/V4). The best
edge remains C3, and it can only be confirmed by its forward run under the kill rules.
