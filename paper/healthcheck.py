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

from paper import config as cfg

MAX_STALE_HOURS = 26.0


def _read_csv(path):
    if os.path.exists(path) and os.path.getsize(path) > 3:
        try:
            return pd.read_csv(path, encoding="utf-8")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def check(profile):
    files = cfg.files(profile)
    problems = []
    acc = None
    if os.path.exists(files["account"]):
        with open(files["account"], encoding="utf-8") as f:
            acc = json.load(f)
    else:
        problems.append("no account.json — engine has never run")

    daily = _read_csv(files["daily"])
    trades = _read_csv(files["trades"])

    print(f"--- {profile} : {cfg.cfg_for(profile)['label']} ---")
    if acc is None:
        print("  STATUS: FAIL — no state")
        for p in problems:
            print("   -", p)
        return False

    last_run = acc.get("last_run_utc")
    age_h = None
    if last_run:
        age_h = (datetime.now(timezone.utc).replace(tzinfo=None)
                 - datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
        if age_h > MAX_STALE_HOURS:
            problems.append(f"last run {age_h:.1f}h ago (> {MAX_STALE_HOURS:.0f}h)")
    else:
        problems.append("no last_run_utc")

    equity = float(daily["equity"].iloc[-1]) if not daily.empty else None
    initial = acc.get("initial_capital", cfg.INITIAL_CAPITAL)
    n_pos = len(acc.get("positions", {}))

    print(f"  runs {acc.get('runs')} | last run {last_run}"
          + (f" ({age_h:.1f}h ago)" if age_h is not None else ""))
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
    if n_pos == 0:
        problems.append("no open positions")

    if problems:
        for p in problems:
            print("   !", p)
        print("  STATUS: WARN")
        return False
    print("  STATUS: OK")
    return True


def main():
    print("=" * 64)
    print("CRYPTOFORGE PAPER ENGINE — HEALTH CHECK")
    print("=" * 64)
    ok_all = True
    for p in cfg.PROFILES:
        ok_all &= check(p)
        print()
    err = os.path.join(os.path.dirname(cfg.BASE_DIR), "logs", "errors.log")
    if os.path.exists(err):
        print(f"errors.log exists ({os.path.getsize(err)} bytes) — tail:")
        with open(err, encoding="utf-8", errors="replace") as f:
            for ln in f.readlines()[-6:]:
                print("   ", ln.rstrip())
    print("=" * 64)
    print("OVERALL:", "OK" if ok_all else "WARN")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
