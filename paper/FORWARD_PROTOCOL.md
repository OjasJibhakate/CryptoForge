# Forward Validation Protocol

*Accepted 2026-09-23. Candidates frozen (see CANDIDATES_FROZEN.md). Unseen future
data decides. No tuning, no edits, no retrospective reclassification.*

## Language (fixed)

- Historical backtest = positive historical evidence
- 2024+ historical OOS = contaminated
- Pre-freeze paper (through 2026-09-23) = execution evidence only
- Forward period from 2026-09-24 = clean validation dataset

## Frozen

Strategy logic (`strategy.py risk.py config.py market.py broker.py`), hashed in
CANDIDATES_FROZEN.md. `freeze_manifest.py --check` gates every report.
Diagnostics/logging (`engine.py store.py`) may only gain additive logging —
no rule, sizing, cost, or risk logic changes.

## Live diagnostics (logged every run from 2026-09-24)

Gross long P&L, gross short P&L, spread P&L, funding P&L, fees, slippage, net,
turnover, exposure (gross/net/long/short counts), margin utilization,
top-1/3/5 concentration, breaker activations, missing-funding events (explicit
flag + symbol list; treated as 0.0, never as truth).

## Cost stress (reported, never switched)

Base 5 bps fee + 2 bps slippage vs stress 10 + 5. Production assumptions stay
5+2 regardless of which scenario reads nicer.

## Concentration

Reported as top-1 / top-3 / top-5 / remaining every checkpoint. 20 names are not
assumed diversified. Flag top-5 increases >10pp over the historical baseline
(45.6% C1 / 63.0% C2).

## Checkpoints

Month-end is the first checkpoint, not final proof. Each report covers the 9 items:

1. sample size 2. net performance 3. realized costs 4. realized funding
5. drawdown 6. concentration 7. execution deviations 8. operational failures
9. comparison with the frozen historical baseline

Generate with: `python -m paper.checkpoint --from 2026-09-24`
