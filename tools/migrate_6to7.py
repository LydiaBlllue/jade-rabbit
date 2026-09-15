#!/usr/bin/env python3
"""migrate_6to7.py — move a workspace from findata schema 6 to 7.

    python3 tools/migrate_6to7.py <workspace>

What changed in 7 (2026-09-10, FINANCE.md §7 / §8a):
  - `rules.json` loses `exclude`. The list of set-aside accounts said the same thing as
    `role: set-aside` in the register, and the Investing pages now read the axis. The list is
    checked against the register before it goes: a name in it that the register does not mark
    set-aside is reported, not silently dropped.
  - `profile.json` becomes "schema": 7.

Safe to run twice: a workspace already at 7 is left alone.
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
    if have >= 7:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 6:
        print(f"findata/ is schema {have}; this script only moves 6 → 7 (run tools/migrate.py)"); return 2

    rp = layout.path(ws, "rules.json")
    rules = json.load(open(rp, encoding="utf-8"))
    if "exclude" in rules:
        listed = set(rules["exclude"].get("accounts", []))
        reg = json.load(open(layout.path(ws, "accounts.json"), encoding="utf-8"))
        marked = {a.get("label") or a["name"] for a in reg["accounts"]
                  if a.get("role") == "set-aside" and a.get("value") == "export"}
        if listed != marked:
            print(f"  ✗ rules.json lists {sorted(listed)} but the register marks {sorted(marked)} "
                  f"set-aside — settle the register first (accounts.json role), then run again")
            return 1
        del rules["exclude"]
        dump(rp, rules)
        print(f"− rules.json exclude ({', '.join(sorted(listed)) or 'empty'}): the register's role axis says it")
    prof["schema"] = 7
    dump(pp, prof)
    print("→ profile.json schema 7")
    print("Now rebuild: python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
