"""One-time ledger repair (FORWARD_PROTOCOL.md amendment 1). Idempotent.

The 2026-09-22 backfill wrote hypothetical fills and daily/target rows for
2026-09-16..20 into the live ledgers and trimmed the next live row's funding_pnl,
while account.json stayed on the real path (the book was not rebalanced on those
days). Replaying trades.csv then no longer reproduced the account, and
backfill.reconstruct() refused every cutoff.

This script moves the hypothetical rows to daily_backfill.csv / trades_backfill.csv /
targets_backfill.csv beside the live files, restores the trimmed funding_pnl from the
pre-backfill backup, checks IN MEMORY that the live ledger then rebuilds every logged
equity and account.json's positions, and only then writes (after a backup).

Usage: py -m paper.repair_ledger [--dry-run]
"""
import csv
import glob
import io
import os
import re
import shutil
import sys
from datetime import datetime, timezone

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import config as cfg
from . import ledger

PROFILES = ("baseline", "wave3")
ADJ = re.compile(r"adjusted (\d{4}-\d{2}-\d{2}): funding_pnl ([+-][\d.]+) -> ([+-][\d.]+)")


def _rows(path):
    if not os.path.exists(path):
        return [], []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return (rows[0], rows[1:]) if rows else ([], [])


def _text(header, rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _frame(text):
    return pd.read_csv(io.StringIO(text), encoding="utf-8") if text.strip() else pd.DataFrame()


def _original_funding(profile, date, adjusted_to):
    """Full-precision pre-backfill value from the state_backup_* copy, else None."""
    for d in sorted(glob.glob(os.path.join(cfg.BASE_DIR, "state_backup_*", profile, "daily.csv"))):
        hdr, rows = _rows(d)
        if "funding_pnl" not in hdr:
            continue
        i = hdr.index("funding_pnl")
        for r in rows:
            if r and r[0] == date and abs(float(r[i]) - adjusted_to) > 1e-3:
                return r[i]
    return None


def plan(profile):
    f = cfg.files(profile)
    th, trades = _rows(f["trades"])
    dh, daily = _rows(f["daily"])
    gh, targets = _rows(f["targets"])
    eh, events = _rows(f["events"])
    if any(e[1] == "LEDGER_REPAIR" for e in events if len(e) > 1):
        return None, "already repaired"
    ri, di, gi, fi = th.index("reason"), th.index("run_date"), gh.index("date"), dh.index("funding_pnl")
    hypo_dates = sorted({t[di] for t in trades if t[ri] == "backfill"})
    fixes = {}
    for e in events:
        m = ADJ.search(e[2]) if len(e) > 2 else None
        if m:
            date, before, after = m.group(1), float(m.group(2)), float(m.group(3))
            orig = _original_funding(profile, date, after) or m.group(2).lstrip("+")
            fixes[date] = (after, orig)
    if not hypo_dates and not fixes:
        return None, "nothing to repair"

    live_daily, hypo_daily = [], []
    for r in daily:
        if r[0] in hypo_dates:
            hypo_daily.append(r)
            continue
        if r[0] in fixes and abs(float(r[fi]) - fixes[r[0]][0]) < 1e-3:
            r = list(r)
            r[fi] = fixes[r[0]][1]
        live_daily.append(r)
    out = {
        "daily": _text(dh, live_daily),
        "trades": _text(th, [t for t in trades if t[ri] != "backfill"]),
        "targets": _text(gh, [g for g in targets if g[gi] not in hypo_dates]),
        "daily_backfill": _text(dh, hypo_daily),
        "trades_backfill": _text(th, [t for t in trades if t[ri] == "backfill"]),
        "targets_backfill": _text(gh, [g for g in targets if g[gi] in hypo_dates]),
    }
    summary = (f"moved {len(hypo_daily)} daily / {sum(t[ri] == 'backfill' for t in trades)} fill / "
               f"{sum(g[gi] in hypo_dates for g in targets)} target rows for {','.join(hypo_dates)} "
               f"to *_backfill.csv; restored funding_pnl "
               + ", ".join(f"{d} {a:+.4f} -> {o}" for d, (a, o) in fixes.items()))
    return out, summary


def main():
    dry = "--dry-run" in sys.argv
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for profile in PROFILES:
        out, summary = plan(profile)
        if out is None:
            print(f"[{profile}] {summary}")
            continue
        frames = (_frame(out["daily"]), _frame(out["trades"]), _frame(out["targets"]))
        v = ledger.verify(profile, frames=frames)
        print(f"[{profile}] {summary}")
        print(f"[{profile}] repaired ledger check: {v}")
        if not v["ok"]:
            print(f"[{profile}] VERIFICATION FAILED — nothing written")
            continue
        if dry:
            print(f"[{profile}] dry run — nothing written")
            continue
        pdir = cfg.profile_dir(profile)
        bdir = os.path.join(cfg.BASE_DIR, f"state_backup_{stamp}_repair", profile)
        os.makedirs(bdir, exist_ok=True)
        for fn in ("daily.csv", "trades.csv", "targets.csv", "events.csv", "account.json"):
            if os.path.exists(os.path.join(pdir, fn)):
                shutil.copy2(os.path.join(pdir, fn), os.path.join(bdir, fn))
        for name, text in out.items():
            path = os.path.join(pdir, f"{name}.csv")
            with open(path + ".tmp", "w", newline="", encoding="utf-8") as f:
                f.write(text)
            os.replace(path + ".tmp", path)
        with open(cfg.files(profile)["events"], "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                    "LEDGER_REPAIR", summary + f"; verified max equity error "
                                    f"${v['max_err']:.4f} over {v['n']} run dates, positions match"])
        print(f"[{profile}] written (backup: {bdir})")


if __name__ == "__main__":
    main()
