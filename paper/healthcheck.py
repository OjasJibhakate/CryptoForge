import os
import sys
import json
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from paper import candidates, killrules, ledger
from paper import config as cfg

MAX_STALE_HOURS = 26.0
OK, WARN, KILL = 0, 1, 2


def _read_csv(path):
    if os.path.exists(path) and os.path.getsize(path) > 3:
        try:
            return pd.read_csv(path, encoding="utf-8")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def check(profile):
    """Print a profile's health; return OK / WARN / KILL."""
    pcfg = candidates.cfg_for(profile)
    files = cfg.files(profile)
    problems = []
    acc = None
    if os.path.exists(files["account"]):
        with open(files["account"], encoding="utf-8") as f:
            acc = json.load(f)

    print(f"--- {profile} : {pcfg['label']} ---")
    if acc is None:
        print("  STATUS: WARN — no account.json yet (engine has never run this profile)")
        return WARN
    daily = _read_csv(files["daily"])
    trades = _read_csv(files["trades"])
    retired = acc.get("retired")

    last_run = acc.get("last_run_utc")
    age_h = None
    if last_run:
        age_h = (datetime.now(timezone.utc).replace(tzinfo=None)
                 - datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
        if age_h > MAX_STALE_HOURS and not retired:
            problems.append(f"last run {age_h:.1f}h ago (> {MAX_STALE_HOURS:.0f}h)")
    else:
        problems.append("no last_run_utc")

    equity = float(daily["equity"].iloc[-1]) if not daily.empty else None
    initial = acc.get("initial_capital", cfg.INITIAL_CAPITAL)
    n_pos = len(acc.get("positions", {}))

    print(f"  runs {acc.get('runs')} | last run {last_run}"
          + (f" ({age_h:.1f}h ago)" if age_h is not None else ""))
    if retired:
        print(f"  RETIRED {retired.get('date')}: {retired.get('reason')}")
    if equity is not None:
        print(f"  equity ${equity:,.2f}  ({(equity/initial-1)*100:+.2f}%)   hwm ${acc.get('high_water_mark',0):,.2f}")
    print(f"  breaker {'ACTIVE' if acc.get('breaker_active') else 'inactive'} | positions {n_pos}")
    if not daily.empty:
        last = daily.iloc[-1]
        print(f"  last {last['date']}: long {int(last['n_long'])} short {int(last['n_short'])} | "
              f"gross ${float(last['gross_notional']):,.0f} net ${float(last['net_notional']):,.0f} | "
              f"funding ${float(last['funding_pnl']):+.4f} fees ${float(last['fees']):.4f}")
    if not trades.empty:
        print(f"  {len(trades)} fills, fees ${trades['fee'].sum():,.2f}")

    if equity is not None and equity <= 0:
        problems.append("equity <= 0")
    if n_pos == 0 and pcfg.get("kind") != "copy_sim" and not retired:
        problems.append("no open positions")

    severity = OK
    if pcfg.get("kind") == "strategy":
        v = ledger.verify(profile)
        print(f"  ledger: {'reconciles' if v['ok'] else 'DOES NOT RECONCILE'} "
              f"(max equity error ${v['max_err']:.4f} over {v['n']} runs, "
              f"positions {'match' if v['positions_match'] else 'DIFFER'})")
        if not v["ok"]:
            problems.append("ledger does not rebuild account.json — see paper/ledger.py")
        if not daily.empty:
            k = killrules.evaluate(profile, daily, acc)
            print(f"  kill rules: {k['status']}")
            for ln in k["lines"]:
                print(f"     {ln}")
            if k["status"] == "KILL":
                print(f"  !!! KILL RULE TRIGGERED — retire with: "
                      f"py -m paper.engine --profile {profile} --retire \"<rule, date>\"")
                severity = KILL
            elif k["status"] == "WARN":
                problems.append("kill-rule warning (W1)")

    if problems:
        for p in problems:
            print("   !", p)
        severity = max(severity, WARN)
    print("  STATUS:", {OK: "OK", WARN: "WARN", KILL: "KILL"}[severity])
    return severity


def main():
    print("=" * 64)
    print("CRYPTOFORGE PAPER ENGINE — HEALTH CHECK")
    print("=" * 64)
    worst = OK
    for p in candidates.ALL_PROFILES:
        worst = max(worst, check(p))
        print()
    err = os.path.join(os.path.dirname(cfg.BASE_DIR), "logs", "errors.log")
    if os.path.exists(err):
        print(f"errors.log exists ({os.path.getsize(err)} bytes) — tail:")
        with open(err, encoding="utf-8", errors="replace") as f:
            for ln in f.readlines()[-6:]:
                print("   ", ln.rstrip())
    print("=" * 64)
    print("OVERALL:", {OK: "OK", WARN: "WARN", KILL: "KILL"}[worst])
    return worst


if __name__ == "__main__":
    sys.exit(main())
