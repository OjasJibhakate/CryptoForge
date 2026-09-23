# CryptoForge V3 — Out-of-the-Box Protocol (pre-registered, before running)

*Declared 2026-09-23. C1/C2 frozen and untouched; V3 lives only in
`research/wave8_sweep.py` + `research/V3_RESULTS.md`. 2026 is the untouched test:
reported once, selects nothing.*

## Crazy claims being stress-tested (with verdicts reported honestly either way)

1. **"Funding-rate arbitrage prints 50%+"** — outright carry-halvest: long the most
   negative-funding names / short the most positive (delta kept neutral by the
   k/k book, NOT hedged spot — tests whether the carry claim survives as a
   cross-sectional trade, not a textbook cash-and-carry).
2. **"The Binance effect"** — listing pop: articles claim +500% spikes AND that
   "98% dump post-listing". Both directions tested: ride the first-N-day momentum
   vs fade it. Our futures files start at futures-listing (not spot announcement),
   so this tests the tradeable leg, stated as a limitation.
3. **"Long squeezes cascade harder than short squeezes"** — asymmetry test: fade
   violent down-days vs fade violent up-days, separately. A short's loss is
   unbounded (forced covering is urgent); a long's is bounded (liquidation is
   voluntary-ish). If the asymmetry is real, down-fades beat up-fades.
4. **"BTC leads, alts follow"** — second lead-lag attempt with a twist: only trade
   the catch-up when BTC's own move is large (|5d| > 5%, attention regime), silent
   otherwise. Prior failure was unconditional; conditioning on attention is new.
5. **"Attention/turnover predicts"** — abnormal turnover (volume vs 30d mean) and
   trade-count spikes as long signals, with and without trend filters.

## Space (fixed now — 24 configs, no additions)

- CARRY directional (4): funding-tilt strengths {1.5, 2.0} × z-win {7, 14}
- CARRY extreme-only (3): trade only |z|>1.5 / 2.0 / 2.5 names
- LIST ride vs fade (6): first {5, 10, 21}d × {ride, fade}
- SQZ asymmetry (4): fade down {3, 5}% vs fade up {3, 5}%
- LEAD attention-gated (3): BTC|5d|>5% gate × catch-up {1, 3, 5}d
- ATTN turnover (4): turnover z / count z × {raw, trend-filtered}

## Objective, folds, rules — identical to V2

Score = Sharpe − 1.5|DD| − 2.0·turn − 0.5·top5 on test folds F1–F4
(2022/23/24/25); 2026 reported once, selects nothing. A config beats the C2-center
reference only on F1–F4 mean Score with lower fold-std. Null is a result. V2's
lesson stands: a fold-winner that loses on 2026 is a rejection, not a discovery.
