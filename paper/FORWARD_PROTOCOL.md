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

Generate with: `python -m paper.checkpoint` (each book's own forward window).

---

## Amendment 1 — 2026-09-30 (after 6 forward days; C1/C2 rules unchanged)

The five frozen C1/C2 files are byte-identical (`freeze_manifest.py --check`). Nothing
below changes how C1 or C2 trade. It adds a candidate, fixes reporting, and fixes one
tool that had corrupted the ledger.

### Known deviations of the live C1/C2 books (documented, not fixed; frozen)

- **TradFi perps.** `market.candidate_symbols()` does not filter Binance
  `TRADIFI_PERPETUAL` contracts (stocks, ETFs, metals, oil), which first listed in
  2025-12. They are ~33–50% of live gross, almost all short. The backtest was
  crypto-only before 2026 and ~20% TradFi at most in 2026. Live ex-ante BTC beta is
  +0.1 to +0.4 vs ~0 in the backtest.
- **C2 gross is uncapped live** (RM overlay up to 2.0×); every backtest caps it at 1.0×.
  The overlay asked for >1.0× on 13% of backtest days.
- **Suffix filter** (UP/DOWN/BULL/BEAR) drops the real coins JUPUSDT and SYRUPUSDT; the
  backtest kept them.

### C3 added (frozen from its first run)

C3 = C2's exact rules on a crypto-only universe (`contractType PERPETUAL`,
`underlyingType COIN`, no suffix filter) with gross capped at 1.0×: the book the
backtests actually tested. Code: `candidates.py`, hashed with the C1/C2 files.
Historical baseline (`research/c3_backtest.py`, realistic execution): Sharpe 1.62,
CAGR 31.8%, max DD −26.5%; before 2026 it equals C2 except for excluding the
BTCDOM/DEFI index perps. C3 was **not** chosen for its 2026 backtest (2.79 vs C2 1.98);
2026 is reported, not used. C3's forward window starts at its first run.

### Kill rules (pre-registered; `killrules.py`, hashed)

Thresholds from backtests only, set before C3's first run and before C1/C2's first
month-end checkpoint.

| Rule | Trigger | Action |
|---|---|---|
| K1 | drawdown from account high-water mark ≤ backtest worst (C1 −33.3%, C2 −26.5%, C3 −26.5%) | KILL |
| K2 | at forward day 90/180/365/730: z = (live Sharpe − backtest Sharpe) / √((1 + SR²/2)/years) < −2.0 (backtest SR: C1 1.14, C2 1.53, C3 1.62) | KILL |
| W1 | C2/C3 funding P&L over trailing 90 forward days ≤ 0 | WARN (review) |

A KILL is executed by hand: `py -m paper.engine --profile <p> --retire "<rule, date>"`
(settles funding, closes the book at live prices, marks the account retired). Returns
alone cannot confirm or reject these edges before ~1.7 (C2) to ~3.1 (C1) years of
forward data; K2's looks are spaced so the family-wise false-kill rate stays near 8%.

### Reporting fixes (checkpoint, engine diagnostics)

- Window drawdown now starts from the pre-window equity; drawdown from the account
  high-water mark is reported alongside (the 2026-09-29 report showed −4.8% for a
  −6.1% window; true −7.75% / −9.64% from HWM).
- Leg P&L comes from a ledger replay (`ledger.py`) and must reconcile with the equity
  change. The legacy `long_pnl`/`short_pnl` columns are unrealized-vs-average-entry
  totals and are kept unchanged; new `long_pnl_day`/`short_pnl_day` are per-run flows.
- `missing_funding` (legacy, kept) lists positions opened in the same run, which cannot
  have a funding print: every flag through 2026-09-29 was a false positive. The new
  `missing_funding_held` column and the MISSING_FUNDING event cover carried positions only.
- Concentration compares notional top-5 with the backtest's notional top-5 (26.2%); the
  historical 45.6%/63.0% figures are P&L shares and are shown only for reference.
- Annualization uses elapsed calendar time; Sharpe is withheld below 30 returns.
- New diagnostics columns: `run_utc`, `hours_since_prev`, `tradfi_share`, `beta_btc`.
  `store.py` widens older CSV headers instead of breaking readers.

### Ledger repair and backfill

The 2026-09-22 backfill wrote hypothetical Sep 16–20 rows into the live ledgers and
trimmed Sep 21 funding while `account.json` stayed on the real path. The hypothetical
rows now live in `*_backfill.csv`; Sep 21 funding is restored (108.490108 / 192.613392).
The live ledger rebuilds every logged equity within $0.0001 and matches `account.json`
positions (`repair_ledger.py`, event LEDGER_REPAIR). `backfill.py` now only ever writes
`*_backfill.csv`.

### Scheduler

`run_daily.bat` clears the kline cache before each run (the 2026-09-28 run used a
23:38 UTC snapshot as the Sep 27 close), runs the health check (exit 2 = KILL), and
commits `paper/state` locally after each run. It never pushes.
