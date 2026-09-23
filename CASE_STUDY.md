# CryptoForge — Case Study

*An interview walkthrough: the problem, the approach, what I found, and what I'd do differently.*

---

## The 30-second version

> "I inherited a retail crypto scalping bot that was losing money. Instead of tuning it, I built a
> research pipeline from scratch to test whether *any* strategy had an edge on 7 years of Binance
> perpetual data. I tested ~108 strategies across seven waves, corrected three separate sources
> of backtest overstatement, and rejected four machine-learning approaches — including a GPU neural
> net. What survived was a market-neutral momentum book at Sharpe 1.33 with a 38% max drawdown.
> The most valuable output wasn't the strategy, it was learning exactly what does *not* work and why."

---

## 1. The problem

I was handed a working but unprofitable system: a 1-minute scalping bot ("CryptoForge") with a
LightGBM model, a whale-order-book filter, and a paper-trading ledger that showed consistent losses.
The owner believed the fix was a better model.

**My first move was not to write code — it was to check whether the strategy was even viable.**

A symmetric 0.5% target / 0.5% stop with 0.10% round-trip fees has:

```
breakeven win rate = (target + cost) / (2 × target) = (0.005 + 0.001) / (0.010) = 60%
```

With realistic slippage (0.15% total), that becomes **65%**. The system's own documentation quoted
~28% model precision. It was never going to work — not because the model was bad, but because the
fee-to-target ratio is structurally hostile. **This reframing — from "improve the model" to "is the
architecture viable at all" — was the most important decision in the project.**

---

## 2. Approach

I built a research stack from first principles rather than extending the existing code:

| Component | Purpose |
|---|---|
| `data_fetch.py`, `bulk_download.py` | Universe + daily klines + funding for 864 symbols |
| `backtest.py` | Cost-aware backtester: fees, slippage, funding; Sharpe/DD/turnover/Calmar |
| `strategies.py` + zoos | Signal library, evaluated on one identical harness |
| `survivorship.py` | Point-in-time universe including delisted symbols |
| `gpu_model.py`, `ml_rank.py` | Machine-learning attempts with purged walk-forward |
| `paper/` | Live paper-trading desk with a swappable broker interface |

**Non-negotiable methodology choices:**
- In-sample = before 2024-01-01; **out-of-sample = after, never used for selection**
- Purged/embargoed walk-forward for anything ML (no overlap between labels and predictions)
- Real costs on every rebalance, funding charged on every perp position
- Tested many strategies, so I report **Bonferroni-corrected** significance, and label results
  *marginal* rather than significant
- Parameter-plateau checks (a real effect survives moving the parameter; a curve-fit doesn't)

---

## 3. What I found

### 3.1 Three corrections that each changed the answer

**(a) Survivorship bias.** The obvious implementation ranks *today's* top coins — silently
excluding every symbol that was liquid once and died. I rebuilt the universe from the
`data.binance.vision` archive (REST for live symbols, archive zips as fallback for delisted ones):
**1,018 symbols ever listed, 806 usable.** Of the 492 ever selected, **395 have since been dropped
or delisted.**

Fixing it *raised* returns (CAGR 28.8% → 37.9%) — because shorting coins that later collapse is
profitable, and excluding them had been understating the edge. **A bias that flatters the backtest
is not the only kind; this one was hiding performance.**

**(b) Inflated funding data.** Raw funding rates hit **±4% per period**, well beyond Binance's
±0.75% cap — and 430 of 866 symbols breached it. Left uncapped, funding roughly doubled reported
returns. Capped and re-run: without funding Sharpe 0.71 (~20% CAGR); with realistic cap Sharpe 1.14.

**(c) Structural costs on high-frequency signals.** 15-minute mean-reversion has a genuine *gross*
Sharpe of **2.5**. But turnover is ~1.5× per bar, so realistic costs turn it into **−88**. The
alpha is real; the costs consume 100% of it. This is the single cleanest explanation of why retail
scalping loses.

### 3.2 Seven waves of strategy testing

| Wave | Tested | Outcome |
|---|---|---|
| 1 | Trend, MA cross, Donchian, mean reversion, XS momentum, funding carry | Only XS momentum survived OOS |
| 2 | Order flow (taker-buy), lottery/skew, size, lead-lag, liquidity | Order flow is a real independent signal |
| 3 | Combinations: funding tilt, BTC regime overlay | **Best configuration** |
| 4 | Long-biased variants, risk-managed momentum, GPU nets | Long bias hurts; risk mgmt works; GPU fails |
| 5 | Calendar anomalies, model capacity, live deployment | No calendar alpha; capacity scaling refuted |
| 6 | 5 live stock strategies ported + 20 crypto anomalies; OI positioning; leverage | Stock edges don't transfer (crypto never closes); OI predicts (archive it); 3× → 177% at −76% DD |
| 7 | CTREND trend factor, squeeze, lottery, deep value, idiosyncratic vol | Only CTREND consistent — and it's momentum in disguise |

**The three findings that mattered most:**

1. **Order flow is genuinely predictive** — taker-buy pressure earns Sharpe 1.26 on its own. It's
   the only signal in the project *not* derived from price, and it matches the 2026 academic
   literature ("order flow has a permanent effect on cryptocurrency returns").

2. **A soft BTC regime filter is the cheapest drawdown reduction available.** Trade full size while
   BTC is above its 200-day MA, half size below. Max drawdown fell from −47% to −25%, and
   out-of-sample Sharpe *rose*. It's a weather-vane, not a forecast.

3. **A funding tilt converts a cost into a tailwind.** Ranking on momentum *minus* recent funding
   means the book ends up *earning* funding instead of paying it. Roughly doubled risk-adjusted
   return.

### 3.3 Four machine-learning refutations

| Approach | OOS Sharpe | Note |
|---|---|---|
| LightGBM ranker (15 features, purged WF) | 0.30 | worse than momentum |
| PyTorch MLP on GPU (18 features) | −1.77 | rank IC −0.011, t = −2.61 |
| Architecture scaling (193 → 544,769 params) | −0.10 → −0.41 | no improvement at any size |
| *momentum (reference)* | *+1.59* | — |

The GPU model trained in **0.20 s per walk-forward retrain** — compute was never the constraint.
The largest models were *reliably wrong*, not merely noisy. **Four independent attempts, four
failures. The bottleneck is signal, not model capacity.** I also showed a 1B-parameter model
wouldn't fit in 6 GB of VRAM, and that capacity scaling makes results *worse*.

### 3.4 The copy-trading reality check

Asked whether the +300%/month traders on Binance's copy-trading leaderboard were real, I simulated
**20,000 zero-skill traders** on the real 492-coin panel:

- At 25× leverage, **1.2% show a "+300% month"** — scaled to ~200,000 lead traders, that's
  **~2,400 accounts, with no skill involved**.
- **It doesn't persist:** month-1 vs month-2 return correlation = **−0.01**. Month-1 top 20%
  performed identically to month-1 bottom 20% in month 2. At 25×, only **4.5%** of the cohort was
  still solvent for month 2.

**Calibration:** a public 47-month backtest of Binance funding/basis arbitrage found **~6.97%/yr**;
across **117 quant crypto funds the median Sharpe is 1.53**. Our 1.33-1.57 sits at that frontier —
which is exactly where an honest retail system should top out.

---

## 4. The result

**Final strategy:** dollar-neutral cross-sectional momentum on ~54 liquid perpetuals. Long the 10
strongest, short the 10 weakest, rebalanced daily. Score = risk-adjusted momentum, tilt-adjusted by
funding; whole book scaled by a soft BTC regime filter and a volatility overlay.

| | Sharpe | CAGR | Max DD |
|---|---|---|---|
| Buy & hold BTC | 0.59 | 18.5% | −78.9% |
| Original baseline | 1.22 | 49.5% | −47.8% |
| **Final (funding tilt + regime + risk management)** | **1.33** | ~33% | **−38.0%** |
| *Median professional quant crypto fund* | *1.53* | — | — |

Positive in **all five** sub-periods. Margin stress-tested: worst single-name squeeze −11.7% of
equity; liquidation requires ~99% loss at the leverage actually needed (1.0×, i.e. none).

**Deployed** as three $10,000 paper accounts (baseline control, wave3 treatment, plus a
copy-trader replay as reference) on a daily scheduled run at 05:36 IST, with a Streamlit
dashboard and a health check. Day 11: baseline **+6.4%**, wave3 **+9.4%**. Day-2: the
improved account *earned* $0.84 in funding while the baseline *paid* $1.51 — a structural
gap that is mechanical, not luck.

---

## 5. What I'd do differently

- **Test the viability arithmetic before building anything.** The fee-vs-target breakeven took
  three lines of maths and would have saved the original system entirely.
- **Correct for survivorship from day one.** I got a flattering number first and had to throw it
  away. Universe construction should be step one, not step five.
- **Isolate variables.** The live A/B tests a *bundle* (tilt + regime + risk management), so it
  can't attribute the improvement. I'd add accounts that vary one lever at a time.
- **Model margin and liquidation explicitly** before any real capital — currently approximated.
- **The size factor is untested properly.** The literature (Liu/Tsyvinski/Wu) finds a robust size
  effect, but I only had a liquidity proxy, not market-cap data.
- **One month of paper trading is a pipeline test, not evidence.** I'd want a full cycle including
  a sustained drawdown before trusting it.

---

## 6. Likely interview questions

**"Did you actually make money?"**
"Not the point, and I'd push back on the framing. I built and validated a research process, and it
produced a strategy with a genuine, small, out-of-sample edge — Sharpe 1.33, roughly at the median
of professional quant crypto funds. Anyone showing you 300%/month is showing you survivorship bias,
and I have a simulation that demonstrates exactly that."

**"Why not just use a bigger model?"**
"I tested it rather than assuming. 2,800× more parameters produced no improvement, and the largest
models had *negative* rank IC with t-statistics around −3, meaning reliably wrong. I also showed a
1B-parameter model wouldn't fit in 6 GB of VRAM. The constraint is the signal-to-noise ratio in
daily crypto returns, not compute."

**"How do you know the backtest isn't overfit?"**
"Three ways. First, a genuine out-of-sample period from 2024 onward that was never used for
selection. Second, parameter plateaus — the regime filter works at MA 50 through 365, which a
curve-fit wouldn't. Third, I tested ~108 strategies, so I apply Bonferroni-corrected thresholds and
describe the result as *marginal*, not proven. Every dead strategy is mapped with its reason in
research/STRATEGIES.md."

**"What was your biggest mistake?"**
"I published a flattering number before correcting for survivorship bias. My first backtest ranked
today's top coins, which silently deleted 395 symbols that were once liquid and then died. Fixing
it changed the answer — and taught me that universe construction is a research decision, not a
data-loading detail."

**"What's the most interesting thing you learned?"**
"That the alpha in high-frequency mean-reversion is real — gross Sharpe 2.5 — and transaction costs
still consume all of it. It's a clean demonstration that most retail strategies fail on frictions,
not on prediction. That reframed the whole project toward lower-turnover, cross-sectional ideas."

---

## 7. Reproducing it

```bash
py -m pip install -r paper/requirements.txt

py research/survivorship.py     # point-in-time backtest (survivorship corrected)
py research/combo_final.py      # final candidate + variants
py research/risk_layer.py       # risk-layer ablation
py research/gpu_model.py        # GPU model (needs CUDA)
py research/luck_simulation.py  # the copy-trading survivorship demonstration

py -m paper.engine --all --status
py -m paper.healthcheck
py -m streamlit run paper/dashboard.py
```

Full findings: [`research/REPORT.md`](research/REPORT.md) (Appendices I–VII).
Every strategy mapped: [`research/STRATEGIES.md`](research/STRATEGIES.md).
Build history: [`TIMELINE.md`](TIMELINE.md).

**Stack:** Python 3.13 · pandas · NumPy · LightGBM · PyTorch (CUDA) · scikit-learn · Streamlit ·
Plotly · ccxt · Windows Task Scheduler
