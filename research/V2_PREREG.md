# CryptoForge V2 — Pre-registered Search Protocol

*Declared 2026-09-23, BEFORE running. C1/C2 frozen and untouched; V2 lives only in
`research/v2_sweep.py` + `research/V2_RESULTS.md` and never overwrites production.
2026 is the untouched test: no V2 decision may use it.*

## 0. Non-goals

Maximum CAGR. Any search that ranks by CAGR alone manufactures a backtest monster.

## 1. Objective (fixed now)

Score = Sharpe − 1.5 × |MaxDD| − 2.0 × turnover − 0.5 × top5_share,
computed on walk-forward test folds only (definition §3). Tie-break: lower |MaxDD|.

## 2. Search space (fixed now — 120 configs, no additions after seeing results)

- L1 momentum (12): {14/21/30/45/60} × {equal, recency} × {vol-adjusted, return-only}
  + 3 alternates: short (7/14/21), medium (21/30/45), long (45/60/90/120)
- L2 funding (5): tilt strength {0, 0.5, 1.0} × z-window {7, 14}; plus funding-neutral
  (strength 0) and winsorized (|z|≤2) variants — folded into the 5, not extra
- L3 portfolio (4): k ∈ {5, 10, 15} + vol-weighted k=10
- L4 risk (5): vol-target {0.30, 0.45, 0.60} + RM-overlay + breaker {15%, 20%}
- Full factorial would be 12×5×4×5 = 1200: INSTEAD one-factor-at-a-time from the
  C2 center (12+4+3+4 = 23 configs) + 12 pre-declared pairs (tilt×k, tilt×regime,
  window×weighting, k×voltarget) = 35 configs. The 120 number in the title is the
  honest ceiling if pairs expand; the floor is 35. No sequential greed, no round 2.

## 3. Walk-forward (fixed now)

Folds (develop → test, 1-year step, costs + funding on every fold):

| fold | develop | test |
|---|---|---|
| F1 | 2019–2021 | 2022 |
| F2 | 2020–2022 | 2023 |
| F3 | 2021–2023 | 2024 |
| F4 | 2022–2024 | 2025 |
| FINAL | 2023–2025 | **2026 (untouched, reported once)** |

Selection uses F1–F4 test folds only. 2026 is reported once at the end and never
selects. 2024–2025 are inside develop windows — they are NOT independent OOS and
this protocol does not call them that; their role is stability evidence only.

## 4. Decision rules (fixed now)

- A config beats the C2-center only on F1–F4 mean Score with lower fold-std.
- Any config using 2026 before the final report voids the protocol.
- Results go to V2_RESULTS.md as HISTORICAL EVIDENCE (CONTAMINATED by construction
  — 2024–2025 were develop-visible). V2 never becomes production without its own
  forward paper run.
- If nothing beats the center robustly: report that. Null is a result.
