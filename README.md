# ⚡ CryptoForge

An end-to-end quantitative research and paper-trading system for Binance USDT-M perpetual
futures — built, tested, honestly measured, and running live on virtual capital.

> **The short version:** I built a research pipeline, tested ~50 strategies across five waves
> against 7 years of point-in-time data, rejected four separate machine-learning approaches, and
> ended up with a market-neutral cross-sectional momentum book at **Sharpe 1.33 / −38% max
> drawdown**. It runs two $10,000 paper accounts on a daily schedule, one of which tracks the
> original design and one the improved design, so improvements are measured rather than assumed.

📄 **[Case study / interview walkthrough →](CASE_STUDY.md)** — problem, approach, findings, and
what I'd do differently.

---

## Headline results

Point-in-time universe (806 symbols including delisted), daily bars 2019-09 → 2026-09,
costs of 5 bps taker + 2 bps slippage per side, funding charged, out-of-sample = everything
after 2024-01-01, which was never used for selection.

| Configuration | Sharpe | CAGR | Max DD | CAGR at a 40% DD budget |
|---|---|---|---|---|
| Buy & hold BTC | 0.59 | 18.5% | −78.9% | 14% |
| Original momentum baseline | 1.22 | 49.5% | −47.8% | 41% |
| **Final: funding tilt + regime filter + risk management** | **1.33** | ~33% | **−38.0%** | — |
| *Median professional quant crypto fund (117 funds)* | *1.53* | — | — | — |

The strategy is dollar-neutral: it holds ~10 longs and ~10 shorts and makes money from the
*spread*, not from market direction. It was positive in **all five** sub-periods tested.

---

## What this project actually demonstrates

Most portfolio projects show a backtest that looks great. This one is built around the opposite
discipline: **proving what does not work, and refusing to publish a number that cannot survive
scrutiny.**

### Four independent ML refutations

| Model | Out-of-sample Sharpe | vs momentum (1.59) |
|---|---|---|
| LightGBM ranker, 15 features, purged walk-forward | 0.30 | worse |
| PyTorch MLP on GPU, 18 features | −1.77 | worse |
| Architecture scaling, 193 → 544,769 params | −0.10 → −0.41 | no improvement |
| GPU model rank IC | −0.011 (t = −2.61) | reliably *wrong* |

The GPU model trains in **0.20 s per walk-forward retrain** on an RTX 4050 — the bottleneck was
never compute. It was signal. Reporting this honestly is the point.

### Bugs I found in my own work and fixed

- A **sign error** in a short-squeeze stress test that reported falling coins as losses (they are
  gains for a short). Caught it by checking the numbers against each other.
- A **look-ahead hole**: the first backtest used today's top-40 coins, silently excluding the 395
  symbols that were liquid once and later died. Fixing it *raised* returns — because shorting
  coins that go on to die is profitable.
- **Inflated funding data**: raw funding rates hit ±4% per period, well beyond Binance's ±0.75%
  cap. Left uncapped it roughly doubled reported returns. Capped and re-run.
- **Circuit-breaker mis-tuning**: a 15% trigger was active on 56% of historical days. Recalibrated
  to 20%.
- **An IP rate-limit ban** from my own bulk downloads — fixed with caching, request pacing, and
  explicit error handling.

### Research methodology

- **Survivorship-bias corrected** universe from the `data.binance.vision` archive
- **Purged / embargoed walk-forward** validation (no look-ahead across overlapping labels)
- **Out-of-sample holdout** never used for selection
- **Multiple-testing awareness** — Bonferroni-corrected t-statistics, reported as *marginal*
  rather than significant
- **Explicit cost modelling** — fees, slippage and funding on every rebalance
- **Margin and liquidation stress tests** — worst single-name squeeze: −11.7% of equity
- **Parameter-plateau checks** to distinguish a real effect from a curve-fit

---

## The journey

Full detail in [`research/REPORT.md`](research/REPORT.md) (Appendices I–V), the build history in
[`TIMELINE.md`](TIMELINE.md), and an interview-oriented walkthrough in [`CASE_STUDY.md`](CASE_STUDY.md).

| Wave | What was tested | Outcome |
|---|---|---|
| 1 | Trend, MA crossovers, Donchian, mean reversion, cross-sectional momentum, funding carry, intraday reversal | Only cross-sectional momentum survived out-of-sample |
| 2 | Order flow (taker-buy volume), lottery/skew, size, lead-lag, liquidity factors, ML ranker | Order flow is a real independent signal; ML fails |
| 3 | Combinations — funding tilt, BTC regime overlay | **Best configuration found** |
| 4 | Long-biased variants, risk-managed momentum, GPU neural nets | Long bias *hurts*; risk management works; GPU model fails |
| 5 | Calendar anomalies, capacity scaling, live deployment | No calendar alpha; capacity scaling refuted |

### The finding that matters most

A 0.5% scalp target with 0.10% round-trip fees requires a **>60% win rate** just to break even.
Empirically, 15-minute mean-reversion has a real *gross* Sharpe of 2.5 — but its turnover is 1.5×
per 15-minute bar, so realistic costs turn that into **−88**. The alpha exists; the fees eat all
of it. This is why high-frequency retail scalping loses, and it is a structural result, not a
tuning problem.

---

## Architecture

```
paper/                      Live paper-trading desk (profile-aware, multi-account)
  config.py                 All parameters; per-profile settings
  market.py                 Binance data with caching + rate-limit handling
  strategy.py               Point-in-time universe, momentum, funding tilt, regime filter
  risk.py                   Volatility targeting, per-name caps, drawdown circuit-breaker
  broker.py                 PaperBroker behind a swappable Broker interface
  store.py                  Persistent account state + trade/daily/target/event logs
  engine.py                 Daily engine: mark-to-market → target → risk → rebalance → log
  copytrader.py             Replays a lead trader's log into a virtual copier account
  dashboard.py              Streamlit desk: three-way overview, positions, trades, drawdown

research/                   Research pipeline
  data_fetch.py             Universe + klines + funding
  bulk_download.py          864 symbols incl. delisted (REST + archive fallback)
  bulk_full.py              Same, keeping order-flow columns
  backtest.py               Cost-aware backtester and metrics
  strategy_zoo.py           Wave 1: 25 signals
  strategy_zoo2.py          Wave 2: 25 more incl. order flow
  survivorship.py           Point-in-time universe backtest
  combo_final.py            Wave 3: combinations -> the final candidate
  long_bias.py              Wave 4: long bias, risk-managed momentum
  gpu_model.py              Wave 4: PyTorch walk-forward MLP on GPU
  capacity_test.py          Does model size help? (no)
  calendar_effects.py       Wave 5: day-of-week / turn-of-month (dead)
  risk_layer.py             Risk-layer ablation
  margin_stress.py          Short-leg squeeze / liquidation analysis
  luck_simulation.py        Why leaderboards show +300%/month (survivorship)
  copy_trader_analysis.py   Parses & audits a lead trader's published trade log
  hold_loser_simulation.py  The "no stop, hold until it recovers" family, 7 years
  trend_exit_experiment.py  Take-profit vs trend-death exit (let winners run)
  trend_veto.py             Per-coin trend veto on wave3 (rejected)
  REPORT.md                 Full findings, Appendices I–V

crypto_live_bot.py          Original 1-minute scalper (the starting point, and why it failed)
dashboard.py                Original Streamlit UI
```

---

## Running it

```bash
py -m pip install -r paper/requirements.txt

# research pipeline (downloads data, runs backtests)
py research/survivorship.py          # point-in-time backtest
py research/combo_final.py           # final candidate + variants
py research/risk_layer.py            # risk-layer ablation

# live paper desk
py -m paper.engine --all --force     # run both accounts
py -m paper.engine --all --status    # account summaries
py -m paper.healthcheck              # health check, exits non-zero on problems
py -m streamlit run paper/dashboard.py
```

Credentials (if you wire up a real exchange) are read from environment variables — see
`cryptoforge_master.py`. **No keys are stored in this repository.**

---

## Tech stack

Python 3.13 · pandas · NumPy · LightGBM · PyTorch (CUDA) · scikit-learn · Streamlit · Plotly ·
ccxt · requests · Windows Task Scheduler

---

## Honest limitations

- **Paper trading only.** No real orders are placed. Shorting carries margin and liquidation risk
  that is modelled but not experienced.
- **30 days is not evidence.** Two accounts have been live for days, not years. The backtest is
  the evidence; the live run is a pipeline test.
- **Funding capture is uncertain.** The headline assumes realistically-capped funding is fully
  captured; a conservative assumption reduces returns materially.
- **Capacity is retail-scale.** ~54 names at $5–50M ADV. Not scalable to large capital.
- **Cost-sensitive.** The edge degrades materially above ~10 bps per side.
- **This does not beat professional quant funds.** It sits near the median. That is the honest
  ceiling, and claims of 300%/month are survivorship bias — demonstrated quantitatively in
  `research/luck_simulation.py`.

---

## Why this is worth showing

It is not a project that says "look how much money I made." It is a project that says: *I can
form a hypothesis, test it against reality with the right safeguards, find my own mistakes, kill
my own ideas when the data says so, and explain the result to a non-specialist.* That is what
quantitative research actually is.
