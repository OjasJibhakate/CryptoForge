# CryptoForge — TradeForge-Standard Audit

*Candidates frozen. Nothing tuned, filtered, or changed because of these results.
C1 = baseline (paper/strategy.py ensemble + config vol-target/caps + risk breaker).
C2 = wave3 (C1 + 7d funding z-tilt + BTC200 regime 1.0/0.5 + own-90d-vol overlay
0.20/cap2x + 20% breaker). Reproduce: `python research/tradeforge_audit.py`;
comparison CSV: `research/tradeforge_audit_out.csv`.*

---

## 1. PIT / lookahead audit — PASS

Decision date D = daily close; engine trades 00:06 UTC D+1 on w(D) held from D+1
(shift(1)). Lineage:

| Input | Latest data used | Lag vs D |
|---|---|---|
| momentum 14/21/30/45/60d | closes through D−lb | ≥14d ✅ |
| 30d vol divisor | returns through D | 0d ✅ |
| 30d ADV universe | volume through D (trailing mean) | 0d ✅ |
| 60d history eligibility | closes through D (count) | 0d ✅ |
| k=10 rank | scores at D | 0d ✅ |
| 7d funding mean | payments with timestamp ≤ D (no ffill) | 0d ✅ |
| funding z-score | cross-section at D | 0d ✅ |
| BTC 200d MA | closes through D | 0d ✅ |
| own-90d-vol overlay | own returns through D−1 | 1d ✅ (extra lag) |
| vol-target realized vol | returns through D | 0d ✅ |
| funding charge | payments in (prev run, this run] | at run ✅ |

Universe is a per-day rank of trailing ADV among that day's eligible only;
delisted names persist via the vision archive (volume while listed, NaN after,
auto-excluded); 60-bar eligibility needs realized bars. **No future listing,
delisting, price, volume, or funding information enters any decision.**
Zero-dollar-volume cells (2.57%) are ineligible via ADV ≥ $5M.

## 2. OOS provenance — CONTAMINATED (both)

Git history is 10 commits, all 2026-09-14…23 (single squashed import): per-decision
commit dates do not exist. Design order comes from REPORT/TIMELINE: wave1 (25) →
wave2 (+25) → wave3 (tilt+regime) → wave4 (RM overlay), every step printing 2024+
OOS Sharpe (combo_final.py prints it). **C2's tilt, regime, RM overlay and k=10
were chosen with 2024+ visible. C1's risk shell was tuned in the same loop.**
Honest independent OOS = the live paper run only (currently 11 days: execution
evidence, not validation).

| Candidate | OOS status |
|---|---|
| C1 BASELINE | **CONTAMINATED** (weakly — naive baseline, less selection) |
| C2 WAVE3 | **CONTAMINATED** (strongly — assembled from OOS-ranked parts) |

## 3. Cost audit — PASS with a stated optimism

Binance USD-M VIP0 = 2 bps maker / 5 bps taker (−10% with BNB → 4.5 bps). A daily
L/S rebalance across ~20 alt names executes as **taker on entry and exit**, so 5 bps
is the correct base and maker (2 bps) is unattainable for this design.

| Fee regime (per side) | C1 Sharpe/CAGR | C2 Sharpe/CAGR |
|---|---|---|
| maker-ish 2+0.5 | 1.28 / 38.1% | 1.69 / 33.4% |
| taker+BNB 4.5+2 | 1.18 / 34.4% | 1.58 / 30.8% |
| **stated 5+2** | **1.17 / 33.9%** | **1.56 / 30.5%** |
| taker+wide 5+5 | 1.10 / 31.2% | 1.48 / 28.5% |
| stressed 10+5 | 0.98 / 26.9% | 1.34 / 25.4% |

Turnover 0.185 (C1) / 0.137 (C2) per day; costs are 17–19% of gross alpha — the
edge is not friction-fragile. **Stated optimism: 2 bps/side slippage** understates
spread+impact on $5–20M ADV names (selected median ADV is $120M, but the tail is
thin). Stressed rows bound it: still Sharpe ~1.0/1.3.

## 4. Funding audit — PASS with one flagged bias

2,680,529 observations, 866 symbols, earliest 2019-09-10; |rate| p50 0.005% / p99
0.219% / max 4.0%. Breaches are rare: >±0.75% is 0.17% of obs, >±0.30% is 0.64%.

| Assumption | C1 Sharpe / funding | C2 Sharpe / funding |
|---|---|---|
| UNCAPPED raw | 1.23 / +1,128 bps/yr | 1.65 / +1,494 bps/yr |
| **capped ±0.75% (live)** | **0.98 / +406** | **1.26 / +804** |
| capped ±0.30% | 0.92 / +244 | 1.13 / +557 |

P&L split at stated config (bps/yr) — C1: gross 2,831 − cost 472 + funding 954 =
net 3,313. C2: gross 1,825 − cost 350 + funding 1,345 = net 2,821. **Funding is
~30–48% of net: a booster, and the book is profitable without it.**

⚠️ **Flagged (frozen, not fixed): missing funding → 0.0.** Pre-listing days have no
funding file; the panel fills 0. The PIT mask means no position exists there either,
so the bias is small and one-directional (understates short-leg income for
post-2024 listings; 601/866 symbols start after 2024-01-01).

## 5. Universe / liquidity — PASS

Eligible/day 167.8, selected 53.5; ever eligible 735, ever selected 501. PIT rank
confirmed by construction. Selected-median ADV $120M vs all-cell median $11.9M —
the book fishes in the liquid end.

## 6. Short-leg / liquidation — SAFE at frozen 1×

| | C1 | C2 |
|---|---|---|
| gross avg / max | 0.94 / 1.00 | 0.63 / 2.00 (RM cap) |
| \|net\| avg / max | 0.000 / 0.000 | 0.002 / 2.000 |
| max per-name share of gross | 50% (thin day) / 5.5% mean; cap binds 1.3% of days | same |
| worst portfolio day | −9.9% | −9.7% |
| worst single-name day | −8.0% | −11.3% |

Cross-margin 1% MMR liquidates near −99% equity; worst observed day −10.5% leaves
>85% headroom. **The 15/20% breaker acts long before liquidation math binds at 1× —
it is a return smoother, not a solvency guard.** At any future leverage it becomes
load-bearing. Basket squeeze (all 10 shorts +30%) ≈ −14% equity.

⚠️ The 50% thin-day print: when the eligible universe collapses, k=10 per side can
concentrate. The 10% cap binds only 1.3% of days because it caps *weight units*,
not share-of-gross — worth restating as share-of-gross if leverage is ever added.
Frozen; not changed.

## 7. Strategy comparison (stated config, identical metrics)

| | C1 BASELINE | C2 WAVE3 |
|---|---|---|
| n / CAGR / vol | 2563 / 33.9% / 28.3% | 2563 / 30.5% / 18.0% |
| Sharpe (IS/OOS/full) | 1.17 / 1.64 / 1.17 | 1.56 / 1.85 / 1.56 |
| Sortino / Calmar | 1.84 / 1.03 | 2.58 / 1.16 |
| MaxDD / underwater days | −32.9% / 2253 | −26.3% / 2216 |
| Profit factor / win rate | 1.23 / 47.8% | 1.31 / 46.9% |
| 95% VaR / CVaR (daily) | −1.95% / −2.98% | −1.16% / −1.85% |
| Worst day | −8.23% | −4.74% |
| Turnover / fees / funding (bps/yr) | 0.185 / 472 / +954 | 0.137 / 350 / +1345 |
| Breaker days | 1286 (50%) | 985 (38%) |
| Long-leg CAGR / Sharpe | +28.6% / +0.74 | +17.6% / +0.62 |
| Short-leg CAGR / Sharpe | −11.5% / −0.05 | −6.2% / −0.02 |

**Both legs lose money standalone on the short side in return space** — the edge is
the *spread plus funding*, not either leg. Breaker-day counts (50%/38%) confirm the
REPORT finding: at 15/20% triggers it is a near-permanent half-size mode, i.e. a
lower-vol version of the book, not a tail guard. Frozen; not retuned.

## 8. Ablation — READ ONLY, exploratory

| Variant | Full Sharpe | CAGR | MaxDD | OOS |
|---|---|---|---|---|
| A. BASELINE | 1.15 | 45.3% | −47.2% | 1.57 |
| B. +funding tilt | 1.40 | 60.2% | −39.9% | 1.70 |
| C. +BTC regime | 1.34 | 44.8% | −34.3% | 1.75 |
| D. +RM overlay | 1.16 | 26.4% | −36.5% | 1.73 |
| E. WAVE3 combined | 1.41 | 33.7% | −32.3% | 1.84 |

Post-hoc and OOS-visible; **not used to change C2.**

## 9. Robustness

- Halves: C1 0.68→1.60, C2 1.41→1.71 (stronger late — momentum-typical, not decay).
- Losing year: both −0.8 (2022). BTC-bear: C1 +2.5%, C2 +7.1% CAGR — survives, thin.
- Tails: C1 worst-10 sum −60.1%, C2 −34.9%. Max losing streaks 9 / 13 days.
- Concentration: top-5 names 46% (C1) / 63% (C2) of total P&L — ALPACA, SOL, AVAX,
  FTM/PIPPIN, BCH/ADA/LINK. Real concentration in a 20-name book; single-name
  cap does not diversify P&L.

## 10. Live/paper separation

11-day paper (+6.4% / +9.4%) = execution evidence only (scheduler, fills, logs,
dashboard all work). n=11, no drawdown seen. Not validation.

---

## Final classification

| Candidate | Historical | OOS status |
|---|---|---|
| **C1 BASELINE** | **POSITIVE HISTORICAL BACKTEST** | **CONTAMINATED** |
| **C2 WAVE3** | **POSITIVE HISTORICAL BACKTEST** | **CONTAMINATED** |

The edge survives clean PIT data, realistic costs across five fee regimes, audited
funding (profitable even uncapped-to-conservative), and 1× liquidation math — but
**no result dated 2024+ in this repo is independent evidence**, because every design
choice was made with 2024+ visible. The only path to VALID is forward: the frozen
live paper run, judged at month-end and beyond, with no further tuning.
