# CryptoForge — Every Strategy and Failure, Mapped

*All ~108 mechanisms tested across seven waves, one line each: what it is, the
verdict, and the reason. Costs everywhere: 5 bps fee + 2 bps slippage per side,
funding charged. Select on in-sample (<2024), judge on out-of-sample (≥2024).
"Consistent" = IS Sharpe > 0.5 AND OOS Sharpe > 0.5. Full evidence in
[REPORT.md](REPORT.md).*

**Legend:** ✅ live · 🟡 real but unaffordable/unproven · 🔴 dead

---

## The live book

| # | Strategy | IS | OOS | Verdict |
|---|---|---|---|---|
| 1 | ✅ XS momentum ensemble (14/21/30/45/60d, risk-adjusted, k=10, daily, dollar-neutral) | 0.93 | 1.59 | **baseline — live control** |
| 2 | ✅ momentum − funding tilt | 1.17 | 1.68 | best single improvement |
| 3 | ✅ tilt + soft BTC regime (1.0/0.5) + risk-managed vol overlay | 1.38 | 1.83 | **wave3 — live treatment** |

---

## Wave 1 — first screen (25 signals, `strategy_zoo.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 4 | XS momentum skip-5d | 0.72 | 1.23 | works, weaker than baseline |
| 5 | XS Sharpe momentum | 0.97 | 1.17 | works, weaker than tilt |
| 6 | XS residual momentum | — | ~1.0 | works, weaker than tilt |
| 7 | XS near-60d-high / in-range | 1.26 | 1.34 | works — momentum variant |
| 8 | XS trend + carry blend | 1.24 | 1.40 | works — momentum variant |
| 9 | XS combo (mom+carry+lowvol) | 1.40 | 1.42 | best IS, correlation makes it one bet |
| 10 | XS vol breakout z | 1.37 | 1.10 | works, higher turnover |
| 11 | XS funding carry alone | 1.21 | **−0.02** | tilt needs momentum; alone it breaks |
| 12 | XS reversal 1d / 5d / 10d | −1.4 | −0.7…−1.3 | crypto is a momentum regime at daily scale |
| 13 | XS low-vol (BAB) | −0.60 | 0.09 | no betting-against-beta in crypto |
| 14 | XS high-vol | — | neg | lottery names underperform, costs finish them |
| 15 | XS acceleration | — | neg | second derivative is noise |
| 16 | XS volume surge / volume z | — | ~0 | volume without direction is noise |
| 17 | TS momentum (long/short) | — | weak | cross-section beats time-series here |
| 18 | 15-min reversal (intraday) | gross 2.5 | **−88 net** | alpha real, 1.5×/bar turnover eats 100% |

## Wave 2 — order flow and factors (25 more, `strategy_zoo2.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 19 | 🟡 OFI taker-buy z | 1.47 | 1.14 | **real independent signal** — only non-price source; left out of wave3 on turnover |
| 20 | OFI change 3v20 | — | — | level works, change is noise |
| 21 | OFI contrarian | — | −1.93 | fading aggressive flow bleeds |
| 22 | OFI divergence | — | weak | spread of two goods is not a third good |
| 23 | MAX lottery (short high max) | — | −0.40 | retested dead twice |
| 24 | skewness / kurtosis shorts | — | −0.80 | higher moments don't price |
| 25 | long-term reversal 120d/180d | — | −0.45/−0.25 | no multi-month reversion |
| 26 | BTC lead-lag catch-up | — | −1.02 | BTC lead is HFT-scale, not daily |
| 27 | low beta / defensive | — | −0.46 | defensive posture in a momentum book |
| 28 | Amihud illiquidity | — | 0.01 | dollar-volume proxy, not true size |
| 29 | liquidity factor | — | −0.45 | liquid names don't underperform enough |
| 30 | trade-count z | — | 0.09 | activity without direction |
| 31 | funding contrarian extremes | — | weak | squeezes eat contrarians (see #71) |
| 32 | funding change 3v20 | — | weak | change of carry is noise |
| 33 | mom + hard BTC regime | 1.17 | 1.71 | works — soft version kept instead |
| 34 | mom + market-vol scaling | — | — | helps, RM overlay does it better |

## Wave 3 — combinations (`combo_final.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 35 | ✅ ftilt + soft-regime | 1.38 | 1.83 | **final candidate** |
| 36 | ftilt + OFI + soft-regime | 1.84 | 1.38 | strong but heavier turnover; blend candidate |
| 37 | mom + regime variants | 1.17 | 1.71 | strong; tilt adds the rest |
| 38 | top-4 blend | — | 1.75 | diversifies, carries selection bias |

## Wave 4 — long bias, risk management, GPU (`long_bias.py`, `gpu_model.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 39 | long-heavy 60/40, 75/25 | 1.10–1.16 | 1.39→1.06 | headline CAGR up, Sharpe down, DD explodes |
| 40 | long-only (+ regime) | 1.11–1.34 | 0.65–0.71 | DD −80…−93%: beta, not edge |
| 41 | ✅ risk-managed momentum (lb=90) | 1.05 | 1.78 | adopted — cheapest Sharpe/DD improvement |
| 42 | behavioral low-anchor reversal | — | −1.26 | fails decisively |
| 43 | LightGBM ranker (15 feat, purged WF) | — | 0.30 | **ML refutation 1**: worse than momentum |
| 44 | PyTorch MLP on GPU (18 feat) | — | −1.77 | **ML refutation 2**: reliably wrong (IC t=−2.61) |
| 45 | per-coin trend veto (MA20/50/100/200) | — | ≤1.37 | redundant — ranking already exits fades |

## Wave 5 — calendar, capacity (`calendar_effects.py`, `capacity_test.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 46 | turn-of-month | +38.9bps (t 2.39) | −11.7bps | textbook IS artifact |
| 47 | day-of-week timing | Wed +46.7bps | Mon +50.5 / Tue −26.9 | no stable pattern |
| 48 | weekend vol timing | robust (half vol) | robust | risk-sizing fact, not return edge |
| 49 | 500M–1B param model | — | — | doesn't fit 6GB VRAM (**refutation 3a**) |
| 50 | capacity scaling 193→544k params | — | −0.10→−0.41 | flat-to-negative (**refutation 3b/4**) |
| 51 | take-profit +3/+5% with trend exit | — | — | caps upside, keeps downside: 5× expectancy loss |
| 52 | no-take-profit trend exit | — | — | letting winners run wins — built into wave3 |

## Copy-trading investigations

| # | Claim | Test | Verdict |
|---|---|---|---|
| 53 | "300%/month leaders are skilled" | 20k zero-skill traders, luck sim | 1.2% show +300% at 25× → ~2,400 accounts; month-2 corr −0.01 |
| 54 | "95% win-rate trader is copyable" | trade-log audit + 7-yr hold-loser sim | 92.6% reproduced mechanically; 6% liquidated at 5×; median loser −35% |
| 55 | "copy-trader replay compounds" | copytrader desk replay | +943% but 57× capacity gap — upper bound, not forecast |

## Wave 6 — TradeForge ports + anomalies (`crazy_sweep.py`)

| # | Strategy | IS | OOS | Why it died |
|---|---|---|---|---|
| 56–58 | M4 gap-UP fade SHORT (3–10/5–15/3–100%) | −0.39…0.24 | −0.92…−0.42 | crypto never closes — no overnight gap to fade |
| 59–61 | M5 gap-DOWN bounce LONG | −0.94…−0.20 | −0.55…−0.07 | same — no open to bounce off |
| 62 | M4+M5 gap book | −0.39 | −0.92 | dead both ways |
| 63–65 | M1 crash fade (−8/−10/−15%) | −0.37…−0.30 | +0.15…+0.49 | inconsistent; dips go to −35% median |
| 66 | M1 crash + vol surge | 0.57 | 0.23 | clears nothing |
| 67–70 | M2 slow momentum (90/180/252d) | −0.28…+0.64 | −0.30…+0.29 | fast momentum dialled down |
| 71–73 | LIST fade first-5/10/21d pop | −0.43… | −0.04… | listing pops don't fade reliably |
| 74–75 | LIQ flush fade / range explosion | 0.87/−0.22 | 0.48/−0.19 | clears nothing; DD −88% |
| 76–78 | FUND fade \|z\|>1.5/2/2.5 | 0.78…1.27 | 0.41…0.42 | squeeze shape; DD −100% |
| 79–81 | BTC catch-up 1d/3d/5d | — | <0.3 | HFT-scale lead, retested dead |
| 82–83 | DOW Friday drift / Monday fade | 0.00/−0.39 | 0.00/0.10 | no weekday structure |
| 84 | TOD continuation | 0.22 | −0.30 | dead |
| 85 | 🟡 OI 3d change → next day | IC +0.057 | t=+4.23 | **predicts — but only 30d of data; archive it** |
| 86 | fade crowded longs / taker change | IC ~0 | t<1 | positioning carries nothing |
| 87 | OI tilt appended to wave3 | — | Sharpe 5.47→4.63 | hurts on the 30d window — do not append |
| 88–95 | leverage 1x/1.5x/2x/3x + vol-targets + RM | — | — | 3× → 177% CAGR at −76% DD; 88% in-budget. Live stays 1× |

## Wave 7 — literature-led hunt (`wave7_sweep.py`)

| # | Strategy | IS | OOS | Why it died / lived |
|---|---|---|---|---|
| 96–97 | CTR MA-spread stack (+ vol weight) | 1.24/1.12 | 0.94/0.85 | consistent — **but +0.58 corr with momentum, blend adds 0, 2.3× turnover. Momentum in disguise.** |
| 98–99 | SQZ squeeze-chase / fade-exhausted | −0.54…0.31 | −0.33…0.39 | chasing crowded shorts loses |
| 100–101 | SES session proxies | −0.20…−0.04 | −0.42…0.08 | daily bars can't see sessions |
| 102–105 | LOT (MAX/skew/fresh highs) | −0.45…0.69 | −0.44…−0.09 | dead third time |
| 106–108 | VAL deep value / washed-out / exhaustion | −0.38…0.01 | −0.86…−0.50 | catching knives bleeds — decisively |
| 109–110 | IVO high ivol (± trend) | 0.69/0.47 | −0.09/−0.25 | dead OOS |
| 111–112 | LVO / BETA low | −0.49/−0.41 | +0.07/−0.44 | dead |

---

## Scoreboard

| | Count |
|---|---|
| Mechanisms tested | **~108** |
| Live (in the book) | 3 (momentum, funding tilt, regime+RM) |
| Real but shelved (OI, OFI level) | 2 |
| Dead | ~103 |

*The kill rate is the credential. Anyone can show a backtest that worked; this file
shows ~103 that didn't, with the reason attached to each.*
