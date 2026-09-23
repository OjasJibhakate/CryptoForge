"""Freeze manifest: hash the frozen strategy files, embed into CANDIDATES_FROZEN.md.

Usage:
    python paper/freeze_manifest.py           # compute + embed hashes
    python paper/freeze_manifest.py --check   # verify, exit non-zero on drift
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_FILES = ["strategy.py", "risk.py", "config.py", "market.py", "broker.py"]
DIAG_FILES = ["engine.py", "store.py"]
MANIFEST = os.path.join(HERE, "CANDIDATES_FROZEN.md")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def current():
    out = {}
    for fn in FROZEN_FILES:
        out[fn] = sha(os.path.join(HERE, fn))
    return out


def cur_diag(fn):
    return sha(os.path.join(HERE, fn))


def embedded():
    with open(MANIFEST, encoding="utf-8") as f:
        lines = f.read().splitlines()
    out = {}
    for fn in FROZEN_FILES:
        pat = re.compile(rf"^\s*{re.escape(fn)}\s*:\s*([0-9a-f]{{64}}|PENDING)\s*$")
        out[fn] = next((m.group(1) for ln in lines if (m := pat.match(ln))), None)
    return out


def main():
    check = "--check" in sys.argv
    cur = current()
    emb = embedded()
    if check:
        ok = True
        for fn in FROZEN_FILES:
            if emb.get(fn) in (None, "PENDING"):
                print(f"  {fn}: NO EMBEDDED HASH — run freeze_manifest.py first")
                ok = False
            elif emb[fn] != cur[fn]:
                print(f"  {fn}: DRIFT — embedded {emb[fn][:12]}.. vs current {cur[fn][:12]}..")
                ok = False
            else:
                print(f"  {fn}: frozen {cur[fn][:12]}..")
        for fn in DIAG_FILES:
            print(f"  {fn}: diagnostics (logged {cur_diag(fn)[:12]}.., not freeze-gated)")
        print("FROZEN: OK" if ok else "FROZEN: DRIFT DETECTED")
        sys.exit(0 if ok else 1)
    with open(MANIFEST, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for fn, h in cur.items():
        pat = re.compile(rf"^(\s*{re.escape(fn)}\s*:\s*)([0-9a-f]{{64}}|PENDING)(\s*)$")
        lines = [pat.sub(rf"\g<1>{h}\g<3>", ln) for ln in lines]
        print(f"  {fn}: {h[:12]}..")
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("manifest updated")


if __name__ == "__main__":
    main()
