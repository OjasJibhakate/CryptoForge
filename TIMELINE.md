# Project Timeline & Decision Log

A chronological record of how CryptoForge was built, what was tried, what was rejected, and why.
Times are UTC; the operator is in India (IST = UTC+5:30).

---

## Phase 0 — Starting point

The workspace began as a collection of retail scalping bots
(`crypto_live_bot.py`, `crypto_swing_bot.py`, `crypto_trend_bot.py`) plus a 1-minute
"Meta-Brain" LightGBM model and an original Streamlit dashboard.

**Audit finding:** none of them were profitable, and the reason turned out to be structural, not a
tuning problem — documented in Phase 1.

---

## Phase 1 — Why the existing approach loses (2026-09-13)

**Built:** a cost-aware research pipeline from scratch — `data_fetch.py` (universe, klines,
funding), `backtest.py` (fees + slippage + funding, Sharpe/DD/turnover), `strategies.py`.

**Tested:** 25 signals — time-series momentum, MA crossovers, Donchian breakouts, mean reversion,
cross-sectional momentum and reversal, funding carry, ML ranking.

**Key results:**
- The breakeven win rate for a 0.5% target with 0.10% round-trip fees is **60%**. At 0.15% costs
  including slippage, **65%**. The Meta-Brain's own documented precision was ~28%.
- 15-minute mean-reversion has a genuine *gross* Sharpe of 2.5, but turnover of 1.5× per bar
  turns it into **−88** net. **The alpha is real; the costs consume all of it.**
- Trend-following made all its money in 2019–2022 and has been flat since; its parameter plateau
  is a narrow spike (`lookback=30 → 1.16`, `45 → 0.53`).

**Conclusion:** the 1-minute scalping architecture is structurally negative. Abandoned it.

---

## Phase 2 — Making the backtest honest

Three separate corrections, each of which changed the answer:

1. **Survivorship bias.** The first version ranked *today's* top-40 coins — silently excluding every
   symbol that was liquid once and later died. Rebuilt the universe from the `data.binance.vision`
   archive: **1,018 symbols ever listed, 806 with usable history**, loaded via REST with an archive
   fallback for delisted ones. Result: 492 symbols ever selected, **395 since dropped or delisted**.
   Fixing this *raised* returns (CAGR 28.8% → 37.9%) — because shorting coins that later collapse
   is profitable, and excluding them had been understating the edge.

2. **Funding data audit.** Raw funding rates reached **±4% per period**, far beyond Binance's
   ±0.75% cap, and 430 of 866 symbols breached it. Left uncapped, funding roughly doubled the
   reported return. Capped to realistic levels and re-run:
   *no funding* → Sharpe 0.71, ~20% CAGR; *realistic cap* → Sharpe 1.14, ~38%.

3. **Holdout and walk-forward.** In-sample = pre-2024; out-of-sample = 2024 onward, never used for
   selection. Purged/embargoed walk-forward for anything ML.

---

## Phase 3 — The copy-trading detour

Investigated claims of traders earning 300%/month on the Binance copy-trading leaderboard.
The page is behind a bot-wall, but the mechanism is documented — and I tested it quantitively.

**`luck_simulation.py`:** 20,000 zero-skill traders on the real 492-coin panel, random daily
long/short at various leverage.

- At 25× leverage, **1.2% of traders show a "+300% month"** — scaled to Binance's ~200,000 lead
  traders, that is **~2,400 accounts with no skill involved**.
- **It does not persist:** correlation between month-1 and month-2 returns = **−0.01**. Month-1
  top 20% performed the same as month-1 bottom 20% in month 2. At 25×, only **4.5%** of the cohort
  was even solvent to trade month 2.

**External calibration:** a public backtest of funding-rate/basis arbitrage over 47 months of
Binance BTCUSDT found **~6.97% annually (6.57% after costs)** — the strategy most often sold as
easy money. Across **117 quant crypto hedge funds the median Sharpe is 1.53**.

---

## Phase 4 — Live paper desk (baseline)

**Built** the `paper/` package: profile-aware accounts, `PaperBroker` behind a swappable `Broker`
interface, risk layer (vol targeting, per-name caps, drawdown circuit-breaker), persistent state,
CSV ledgers, Streamlit dashboard with equity/drawdown/positions/trades.

**Operational setup:** `run_daily.bat` with dated logs and an error log, `healthcheck.py`
(exits non-zero on problems), and a Windows Task Scheduler job at **05:36 IST (00:06 UTC)** with
*start-when-available* and *wake-to-run*.

**Two bugs caught by testing:** equity was reported *before* fees were deducted; and Windows
default encoding crashed CSV writes on non-ASCII tickers.

---

## Phase 5 — Wave 2 & 3: the real improvement

**Wave 2 (25 more signals), using newly-downloaded order-flow data** (taker-buy volume for all
803 symbols, consistent with the 2026 literature that order flow has a *permanent* effect on
returns):

- **Order flow works on its own** — Sharpe 1.26, the only signal not derived from price.
- **A soft BTC regime filter** (full size above the 200-day MA, half below) was the cheapest
  drawdown reduction found: −47% → −25% max drawdown.

**Wave 3 (combinations):** momentum **− funding tilt**, overlaid with the regime filter:

| | Sharpe | MaxDD | at 40% DD |
|---|---|---|---|
| baseline | 1.22 | −47.8% | ~41% |
| **wave3** | **1.57** | **−28.8%** | **~77%** |

Validated across MA lengths 50–365 (broad plateau, not fitted to 200), k = 5–30, and cost levels.

**Deployed as a second live account** so the improvement is measured, not assumed — the original
baseline keeps running untouched as the control.

---

## Phase 6 — Wave 4: long bias, risk management, and the GPU model

- **Long bias — tested and rejected.** OOS Sharpe falls monotonically as the short leg is removed
  (1.59 → 1.06 → 0.71), and max drawdown explodes (−47.8% → −93.2%). The short leg is where a real
  part of the edge lives.
- **Risk-managed momentum — tested and adopted** (Barroso/Santa-Clara): Sharpe 1.22 → 1.33,
  drawdown −47.8% → −38.0%. Layered onto wave3 and deployed.
- **GPU neural network — built and refuted.** A PyTorch MLP on an RTX 4050 trains in **0.20 s per
  walk-forward retrain**, and produces an OOS Sharpe of **−1.77** with a rank IC of **−0.011
  (t = −2.61)** — reliably *wrong*, not merely noisy.

---

## Phase 7 — Wave 5: last hypotheses

- **Calendar anomalies: dead.** Turn-of-month looked significant in-sample (+38.9 bps, t = 2.39)
  and vanished out-of-sample (−11.7 bps). Day-of-week showed no stable pattern. Timing BTC by the
  in-sample weekday sign scored OOS Sharpe 0.68 vs buy-and-hold 0.71 — no improvement.
  *One robust fact survived:* weekend volatility is roughly **half** weekday volatility — a
  risk-sizing input, not a return edge.
- **"Run a 500M–1B parameter model": refuted twice over.** Full fine-tuning needs ~16 bytes per
  parameter (12+ GB for 1B) against 6.4 GB of VRAM — it does not fit. And capacity scaling showed
  **2,800× more parameters produced no improvement** (193 → 544,769 params; all at or below zero
  Sharpe). The bottleneck is signal, not compute.
- **Deployed** the risk-managed overlay and reset wave3 to a clean account.

---

## Current state

| Account | Configuration | Purpose |
|---|---|---|
| `baseline` | original ensemble momentum, 15% breaker | control |
| `wave3` | funding tilt + soft BTC regime + risk management, 20% breaker | treatment |

Both run on $10,000 virtual capital, daily at **05:36 IST**, never resetting. The scheduled task
has executed successfully (`LastTaskResult: 0`) with no errors logged.

**Day-2 observation:** wave3 earned **+$0.84** in funding while baseline **paid −$1.51** — a ~$5/day
structural cost gap that is a mechanical consequence of the design, not luck. Turnover also fell
(6 fills vs 49).

---

## What I would do next

1. **Model short-leg margin and liquidation explicitly** before any real capital.
2. **Extend the live run** — 30 days is a pipeline test, not evidence.
3. **Test the size factor properly**, which needs circulating-supply / market-cap data.
4. **Isolate the A/B levers** — the current waves test a bundle (tilt + regime + risk management),
   not each component separately.
