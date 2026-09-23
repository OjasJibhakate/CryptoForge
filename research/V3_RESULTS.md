# CryptoForge V3 — Out-of-the-Box Results (historical, contaminated)

*Protocol pre-declared in V3_PREREG.md. 25 configs, walk-forward F1–F4 select,
2026 reported once and selecting nothing. C1/C2 untouched.*

## The verdict up front: the center wins — nothing out-of-the-box survives

| Rank | Config | Fold score | 2026 |
|---|---|---|---|
| 1 | **C2-center-ref** | **+0.11 ± 1.07** | **+1.48, Sharpe 2.02** |
| 2–5 | CARRY stronger tilts (1.5/2.0 × w7/14) | −0.26…−0.31 | — |
| 6+ | everything else | −1.0…−6.3 | — |

**Every challenger loses on folds AND would have lost.** No 2026 tiebreak needed —
there is nothing to tiebreak. Null, decisively.

## The crazy claims, stress-tested honestly

1. **"Funding arbitrage prints 50%+"** — pushing the tilt to 1.5–2.0x scores
   −0.26…−0.31 vs center +0.11, with 30–50% more turnover. Extreme-only carry
   (|z|>1.5/2/2.5) scores −2.97…−3.51 with DD −83…−91%. The carry claim dies as a
   cross-sectional trade: concentration + turnover eat it. (Textbook cash-and-carry
   with spot hedge is a different trade, untested here — stated as the boundary.)
2. **"The Binance effect"** — ride AND fade both die: ride −2.9…−3.5, fade
   −3.7…−4.0. Futures-listing momentum is not tradeable in either direction on
   daily bars. Both articles are right about different legs (spikes happen, then
   98% dump) and neither leg is a trade after costs.
3. **Long/short squeeze asymmetry** — both directions die HARD: fade DOWN −5.8…−6.3
   (turnover 1.3–1.4/day), fade UP −4.95…−5.02. The asymmetry thesis is irrelevant
   because fading volatility in EITHER direction bleeds — the-creash continuation
   beats the bounce, and costs finish both.
4. **"BTC leads" (attention-gated retry)** — −2.05…−2.49 across 1/3/5d. Gating on
   attention does not resurrect the lead-lag. Third burial (wave2, wave6, now).
5. **Attention/turnover** — turnover-z −2.7, count-z −1.0…−1.2. Volume without
   direction is noise, with or without trend filters.

## What this means

V2's lesson repeats one level louder: **the C2 center is the local optimum of
everything honest tried so far.** Two consecutive pre-registered searches (V2's 26,
V3's 25) with walk-forward discipline both end at the frozen book. The next honest
step is not a fourth search — it is letting the forward live run speak.

Status: HISTORICAL EVIDENCE (CONTAMINATED by construction). No production change.

Sources:
- [Funding Rate Arbitrage: Delta-Neutral Strategy Guide (SafeAlloc)](https://safealloc.app/knowledge-base/funding-rate-arbitrage)
- [Crypto Perpetual Funding Rate Arbitrage: Strategy and Risk](https://tradernewbie.com/blog/2026-07-01-crypto-perpetual-funding-rate-arbitrage)
- [The Binance Effect (ainvest)](https://www.ainvest.com/news/binance-effect-exchange-listings-supercharge-altcoin-gains-2601/)
- [Is the Binance Effect Dead? (dev.to)](https://dev.to/lado_okhotnikov/is-the-binance-effect-dead-why-new-listings-no-longer-guarantee-profits-34i8)
- [The Binance Effect Is Dead: 98% dump post-listing (ourcryptotalk)](https://ourcryptotalk.com/blog/binance-effect-reversal-token-listing-performance)
- [Liquidation Cascades Explained (Bitsgap)](https://bitsgap.com/blog/liquidation-cascades-explained)
- [Short Squeeze vs Long Squeeze detection (riskstate)](https://riskstate.ai/blog/crypto-short-squeeze-long-squeeze-detection)
- [Crypto carry — BIS Working Paper 1087](https://www.bis.org/publications/working-paper-1087-crypto-carry)
