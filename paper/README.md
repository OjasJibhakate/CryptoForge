# CryptoForge Paper Desk

A paper-trading bot that runs the researched strategy — **dollar-neutral cross-sectional momentum**
on Binance USDT-M perpetual futures — against **persistent $10,000 virtual accounts** for one month.
Day 11 (2026-09-23): baseline **+6.4%**, wave3 **+9.4%**. Judge at month-end.

No exchange orders are ever placed. It reads public market data only.

---

## Strategy (one line)

Each day: rank a point-in-time universe of ~54 liquid perps by risk-adjusted momentum
(`return / volatility`, averaged over 14/21/30/45/60 days), **long the 10 strongest, short the
10 weakest**, dollar-neutral, and rebalance. Because it is dollar-neutral, market direction
largely cancels out — it makes money from the *spread* between strong and weak coins, in bull
and bear markets alike.

Backtest reference: ~38% CAGR with -42% max drawdown (2019–2026), Sharpe 1.14.
After the risk layer below, live exposure starts smaller than the backtest.

---

## Three desks

| Profile | What it is | Circuit breaker |
|---|---|---|
| `baseline` | ensemble momentum (14/21/30/45/60d, risk-adjusted), 10 long / 10 short | 15% |
| `wave3` | the same momentum **− funding tilt**, overlaid with a **soft BTC regime filter** (full size above the 200-day MA, half below) and a **risk-managed volatility overlay** | 20% |
| `copytrader` | a **replay of a Binance lead trader's published trade log**, not a live strategy — see below | — |

The two strategy desks are **independent $10,000 paper accounts**, same universe, same costs, same
risk shell, so the only difference is the signal. State lives in `paper/state/<profile>/`; neither
account ever resets and they do not share capital.

### The `copytrader` desk

Binance's own Mock Copy only runs inside their platform, so this desk does the next best thing: it
replays the lead trader's published trades into a virtual copier account, charging **0.1% per side
of lag slippage** and Binance's **10% profit share**, then charts it beside our two strategies.

Refresh it by re-copying the trader's trade history into `binance_trades.md` and re-running the
engine. It reads realised trades only — the trader's *open* positions are invisible, which is where
a hold-until-reversion strategy keeps its real risk.

It prints a capacity caveat every run, because it matters: the replayed position size grows with
the account, while the leader's actual median trade is tiny. **The edge is not available at size**,
which is why live copiers see far less than the headline ROI.


---

## Quick start

```bash
# 1. dependencies (already installed; kept for reference)
py -m pip install -r paper/requirements.txt

# 2. see target portfolios without trading
py -m paper.engine --profile wave3 --dry-run

# 3. run every profile (starts/refreshes both accounts)
py -m paper.engine --all --force

# 4. dashboard (A/B overview + per-account detail)
py -m streamlit run paper/dashboard.py
```

### Running it daily for the month

**Run it once per day, not multiple times.** The strategy rebalances daily; rerunning intraday
just re-trades toward the same target and burns fees. Funding is charged 3×/day but the engine
sums all funding since the last run, so one run captures all of it. The engine also refuses to
run twice on the same UTC date unless you pass `--force` — so keep `--force` out of the
scheduled job.

**Timing.** The trigger must be *after* the daily UTC candle closes (00:00 UTC) so the signal
uses a fully closed candle. India is UTC+5:30 with no DST, so:

| UTC | India (IST) |
|---|---|
| 00:06 | **05:36** |

Windows Task Scheduler triggers use **local** time, so the job is set to `05:36`.

**Option A — automatic setup (recommended):**

```powershell
powershell -ExecutionPolicy Bypass -File paper\setup_task.ps1
```

This registers a daily task at 05:36 local with "start when available" and "wake to run",
so a missed run (laptop asleep) catches up instead of being skipped. Run it now with
`Start-ScheduledTask -TaskName 'CryptoForge Paper Engine'`.

**Option B — plain schtasks equivalent:**

```bat
schtasks /Create /TN "CryptoForge Paper Engine" /TR "\"%CD%\paper\run_daily.bat\"" /SC DAILY /ST 05:36 /F
```

**Option C — loop mode** (keeps a terminal open, runs daily just after 00:05 UTC):

```bash
py -m paper.engine --loop
```

**What the scheduled run does:** `paper\run_daily.bat` runs the engine, appends full output to
`logs\engine_YYYY-MM-DD.log`, and — if the exit code is non-zero — appends the failure and the
day's log to `logs\errors.log`. Log file names use your **local** date; the account's own
day-stamp is UTC, so around midnight IST they can differ by one day. That is expected.

**Health check** (run any time, or schedule it for 05:50 local):

```bash
py -m paper.healthcheck
```

It prints last-run freshness, equity vs. the $10k start, high-water mark, breaker state,
position counts, the latest snapshot and recent errors, then exits non-zero if anything is
stale or wrong — so you can also wire it into a reminder.


If a day is missed, the bot simply rebalances the next time it runs — the account keeps its
equity and never resets.

### Other commands

```bash
py -m paper.engine --status                      # baseline summary
py -m paper.engine --profile wave3 --status      # wave3 summary
py -m paper.engine --all --status                # both
py -m paper.engine --all --force                 # run now even if already run today
py -m paper.backfill                             # replay missed days after downtime
```

### Backfilling missed days

If the machine was off and days were skipped, run:

```bash
py -m paper.backfill
```

It detects dates missing from `daily.csv` and replays each one the way
`engine.run_once` would have, with three honest differences:

- **Fills execute at the day's last closed daily close**, not the live tick
  price the engine would have seen (a few bps of difference, unavoidable).
- **Signals only use closes available on that date** — same as live, no look-ahead.
- **Funding uses real historical funding payments** inside each run window, and
  the first live row after a gap gets its `funding_pnl` trimmed so payments
  credited by backfilled rows are not counted twice
  (logged as a `BACKFILL_ADJUST` event — equity stays untouched).

Existing live rows are never re-priced. Nothing in `account.json` changes;
the book still matches the last live run. Backups land in `state_backup_*`;
`--to YYYY-MM-DD` limits the replay range.

### API rate limits

Binance bans an IP for a few minutes if you hammer it. `market.py` therefore caches daily klines
under `paper/cache/` for `CF_CACHE_TTL_HOURS` (default 4h), pauses between requests, and raises a
clear `RateLimited` error instead of failing silently. Do not bulk-download while the engine is
about to run.

---

## Architecture (modular, swap-in-a-real-exchange ready)

| File | Role |
|---|---|
| `config.py` | All parameters in one place (capital, universe, risk, fees) |
| `market.py` | Public Binance data: tickers, daily klines, funding, live prices |
| `strategy.py` | Point-in-time universe + ensemble momentum → target weights |
| `risk.py` | Volatility targeting, per-name caps, drawdown circuit-breaker |
| `broker.py` | `PaperBroker` (mock fills, fees, slippage, funding) behind a `Broker` interface |
| `store.py` | Persistent account JSON + trade/daily/target/event CSVs |
| `engine.py` | The daily engine: mark-to-market → target → risk → rebalance → log |
| `dashboard.py` | Streamlit desk: equity, drawdown, positions, trades, events |

**To go live later:** implement a `BinanceBroker(Broker)` in `broker.py` exposing
`equity()`, `positions()` and `rebalance()`, then point `engine.py` at it. Nothing else changes.

---

## Risk layer

1. **Volatility targeting** — scales gross exposure down when the portfolio's realised
   annualised volatility rises above `VOL_TARGET_ANNUAL` (default 45%). It only de-risks,
   never levers up.
2. **Per-name cap** — no single coin may exceed `PER_NAME_CAP` (default 10%) of gross exposure.
   The strategy naturally sizes ~5% per name, so this only binds when the universe thins out —
   exactly when a single rug-pull would hurt most.
3. **Drawdown circuit-breaker** — at a 15% drawdown from the high-water mark, gross exposure is
   halved until it recovers to within 5%. This de-risks *symmetrically* (both legs), preserving
   dollar-neutrality. There is an optional `BLOCK_NEW_SHORTS_ON_BREACH` flag (default off) —
   it is off because blocking only shorts would leave the book net-long and add directional risk
   in a crash, which is the opposite of what a circuit-breaker is for.

---

## What gets logged

`paper/state/`

- `account.json` — cash, positions, average entry, high-water mark, breaker state, run count
- `trades.csv` — every fill: symbol, side, qty, price, notional, fee, slippage, reason
- `daily.csv` — daily snapshot: equity, cash, gross/net notional, long/short counts,
  funding P&L, fees, drawdown, vol scale, gross scale
- `targets.csv` — the target weights each day (to compare against the backtest)

---

## Honest expectations

- **One month is a tiny sample.** 30 daily observations cannot distinguish skill from luck.
  Even a great strategy can have a losing month — the backtest had a stretch that made
  +2.6% over ~17 months. Judge the *process*, not one month's number.
- **The risk layer makes live exposure smaller than the backtest** (roughly 0.7x right now,
  because current market vol is ~57% vs the 45% target). Expect proportionally smaller
  P&L and drawdown.
- **Costs are modelled, not real.** 5 bps fee + 2 bps slippage per side. Real fills on small alts
  and on the short side can be worse.
- **Shorting carries margin/liquidation risk** that this paper engine does not simulate.
- **Funding** is applied at the real rates (capped at ±0.75% per period). It is a genuine
  tailwind (~+15%/yr in backtest) but it is not the source of the edge — the momentum edge
  stands on its own without it.

## Resetting

Delete `paper/state/baseline/` (or `paper/state/wave3/`) and run
`py -m paper.engine --profile <name> --force` to restart that account fresh. Deleting the other
profile's folder does not affect it. To clear the market-data cache, delete `paper/cache/`.
