# FROZEN CANDIDATES — do not modify strategy code

*Effective 2026-09-23. C1 (baseline) and C2 (wave3) are frozen exactly as implemented
in the files below. The forward live/paper period is the clean validation dataset.
No strategy rules, lookbacks, portfolio construction, risk targets, funding model,
position caps, or DD breakers may change because of backtest or live results.*

## Frozen strategy code (sha256)

Frozen (strategy logic — any change invalidates validation): `strategy.py`,
`risk.py`, `config.py`, `market.py`, `broker.py`.
Diagnostics/logging (additive logging only — no rule, sizing, cost, or risk
logic may change there): `engine.py`, `store.py`.

<!-- FROZEN-HASHES - one "file : hash" per line, read by freeze_manifest.py
strategy.py : 86262bc932837af366818563e147a984d79c0dd4b943b7efc4028ad084b78cf9
risk.py : 0df4ad2caae915123ec81a280e373a6136ab4c6b80e030ce9f7e44fea5a2770b
config.py : e4145dd8ae4a2951dac6cf019c425b09added6425c35b76ce4f7f6a30772820e
market.py : 6940d07edd900144ba1c526eca2d99d1277e79c3337e93819ef711ebfdeb8b25
broker.py : 372eba35a1a690955a333789b29a3ffdca25ab100d4927267c6de6cb0342f3fe
engine.py : 2d3dd0e4dc04696995da41becb25b44952815fa9f7f2920ca1205e2afc604205
store.py : a92badbc7d9c2c6ba1f1e4b06ac10349e35979a8e08ece6e6a34ad6cfba46530
-->

| File | Role in the frozen design |
|---|---|
| `strategy.py` | C1 ensemble (14/21/30/45/60d ÷ vol30, k=10 L/S) + C2 funding tilt, BTC200 regime, RM overlay |
| `config.py` | lookbacks, k, caps, vol targets, breaker triggers, fees |
| `risk.py` | vol targeting (down-only), per-name cap, breaker halve-till-recover |
| `market.py` | PIT universe inputs, klines cache, funding fetch, live prices |
| `broker.py` | fills, fees, slippage, funding application |
| `engine.py` | run order: mark → funding → risk → rebalance → log |
| `store.py` | ledger formats |

## Frozen parameters

C1 BASELINE: ensemble lookbacks (14,21,30,45,60), vol window 30, k=10/side,
vol-target 0.45 (down-only), per-name cap 0.10, DD breaker 15% halve till DD > −5%.
C2 WAVE3: C1 + 7d funding z-tilt + BTC200 regime 1.0/0.5 + own-90d-vol overlay
0.20/cap 2.0 lagged 1d + DD breaker 20%. Costs 5 bps fee + 2 bps slippage/side.
Funding ±0.75% cap, missing → 0.0 with event flag (known bias, frozen).

## What MAY change (operations/diagnostics only)

- diagnostics, reports, dashboard views, health checks (read-only additions)
- logging detail (new CSV columns must be additive; existing columns immutable)
- scheduler/backfill tooling that replays the frozen rules (no rule changes)

## What MUST NEVER change during validation

strategy rules, lookbacks, portfolio construction, risk targets, funding model,
position caps, DD breakers, cost assumptions in the production run.

## Verification

`python paper/freeze_manifest.py --check` recomputes hashes and fails non-zero on
any drift. Run it before every checkpoint report.
