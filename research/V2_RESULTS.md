# CryptoForge V2 — Walk-Forward Results (historical evidence, contaminated)

*Protocol pre-declared in V2_PREREG.md before running. 26 configs (C2-center +
one-factor variants + 10 pairs), scored on test folds F1–F4 (2022–2025), 2026
reported once and selecting nothing. Objective: Sharpe − 1.5|DD| − 2.0·turn −
0.5·top5 on test folds. C1/C2 production untouched.*

## Fold scores (test-fold Score per config)

Best on F1–F4: **L2 tilt=0.0 (funding-neutral) 0.238 ± 1.146** vs C2-center
0.108 ± 1.073. Margin +0.13 against fold-std ~1.1 — **not a robust win.**

Fold pattern (F1 F2 F3 F4): tilt=0.0 goes −1.29 −0.32 +0.83 +1.74; C2-center goes
−1.18 −0.49 +0.42 +1.68. The "win" is F3–F4 momentum-regime luck, not structure.

## 2026 untouched test (reported once, selects nothing)

| Config | Score | Sharpe | DD | Turn |
|---|---|---|---|---|
| C2-center (with funding tilt) | **+1.48** | **+2.02** | −13.3% | 0.107 |
| L2 tilt=0.0 (fold-winner) | +0.71 | +1.32 | −17.4% | 0.115 |

**The fold-winner loses on unseen 2026 by 0.77.** The tilt — the thing the folds
barely rejected — is exactly what wins forward. This is the walk-forward working
as designed: it caught a selection that would not have survived.

## Layer verdicts

- L1 windows: short/long/return-only decisively worse (long −0.65, return-only
  −0.57). Medium −0.16 ≈ noise. Recency weighting −0.05: nothing.
- L2 funding: tilt 0.0/0.5/winsor/fz14 all within ±0.16 of center on folds;
  2026 says keep the tilt. No change justified.
- L3 portfolio: k=5 (+0.04 folds, −0.07 2026-implied) and k=15 (−0.14) are noise
  around k=10. Vol-weighting −0.15 with 0.248 turnover: pays more, gets less.
- L4 risk: no-risk −0.07 — the overlay earns its keep; keep it.

## Decision

**No config beats the C2 center robustly. Null is the result.** V2 produces no
production change. The 2026 gap (tilt wins forward after folds doubted it) is
recorded as stability evidence FOR the frozen tilt, not as a tuning signal —
using it to change anything would void the protocol and re-contaminate.

Status: HISTORICAL EVIDENCE (CONTAMINATED by construction — 2024–2025 were
develop-visible). V2 never becomes production without its own forward paper run.
