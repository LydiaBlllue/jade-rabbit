#!/usr/bin/env python3
"""migrate_8to9.py — move a workspace from findata schema 8 to 9.

    python3 tools/migrate_8to9.py <workspace>

What changed in 9 (2026-09-10, CLAUDE.md "The data" / FINANCE.md §2):
  - `cashflow.json` is retired. Its monthly rows were sums of the typed ledgers copied out by the
    import, and nothing re-derived the copy; rebuild.py computes them at build now. Its footnotes
    went with the Cash flow page. Its `counterparty` (the person whose ledger the repaid column
    and D10 read) moves into the register: the `documents[]` row whose `into` is that ledger
    gains `"counterparty": <name>`.
  - `profile.json` becomes "schema": 9.

Safe to run twice: a workspace already at 9 is left alone.
"""
import json
import os
import sys

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOOL, ".claude", "skills", "update-dashboard", "scripts"))
import layout  # noqa: E402


def dump(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(path, "a", encoding="utf-8").write("\n")


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    pp = layout.path(ws, "profile.json")
    if not os.path.exists(pp):
        print(f"no profile.json under {ws}"); return 2
    prof = json.load(open(pp, encoding="utf-8"))
    have = int(prof.get("schema", 2))
    if have >= 9:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 8:
        print(f"findata/ is schema {have}; this script only moves 8 → 9 (run tools/migrate.py)"); return 2

    cfp = layout.path(ws, "cashflow.json")
    if os.path.exists(cfp):
        cf = json.load(open(cfp, encoding="utf-8"))
        cp = cf.get("counterparty") or {}
        if cp.get("name"):
            ap = layout.path(ws, "accounts.json")
            reg = json.load(open(ap, encoding="utf-8"))
            doc = next((x for x in reg.get("documents", []) if x.get("into") == cp.get("ledger")), None)
            if doc is None:
                print(f"  ✗ no document in accounts.json lands in {cp.get('ledger')!r}; add one for "
                      f"{cp['name']}'s ledger first, then run again")
                return 1
            doc["counterparty"] = cp["name"]
            dump(ap, reg)
            print(f"→ accounts.json document {doc['key']!r}: counterparty {cp['name']}")
        os.remove(cfp)
        print(f"− cashflow.json ({len(cf.get('rows', []))} rows; derived at build from now on)")
    prof["schema"] = 9
    dump(pp, prof)
    print("→ profile.json schema 9")
    print("Now rebuild: python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
