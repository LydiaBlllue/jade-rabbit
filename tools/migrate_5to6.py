#!/usr/bin/env python3
"""migrate_5to6.py — move a workspace from findata schema 5 to 6.

    python3 tools/migrate_5to6.py <workspace>

What changed in 6 (2026-09-10, CLAUDE.md "How information is stored and reached"):
  - findata/ is three folders, one per layer of the information model, and the rule that
    decides where a file goes is who writes it:
        findata/register/   the owner's declarations (accounts, profile, funds, plan, rules,
                            merchants, tasks) — written by setup or out loud
        findata/ledgers/    the facts the import writes (every ledger CSV, spending, the broker
                            exports, banks, fx, foreign, cashflow)
        findata/history/    what each update left behind (imports, decisions, filings, the two
                            history files)
    The other two layers already had folders: evidence in inbox/ and archive/, derived pages in
    dashboards/. The folder is still findata/ (iCloud for Windows drops any folder named data).
  - Nothing inside a file changes. `ledger` and `documents[].into` in the register stay bare
    filenames; every script resolves them through layout.py.
  - profile.json becomes "schema": 6.

Safe to run twice: a workspace already at 6 is left alone. A file the layout does not know is
a ledger (the ledger CSVs are named in accounts.json, not in the layout).
"""
import json
import os
import shutil
import sys

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOOL, ".claude", "skills", "update-dashboard", "scripts"))
import layout  # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    fd = os.path.join(ws, "findata")
    flat_profile = os.path.join(fd, "profile.json")
    layered_profile = os.path.join(fd, "register", "profile.json")
    if os.path.exists(layered_profile) and not os.path.exists(flat_profile):
        have = int(json.load(open(layered_profile, encoding="utf-8")).get("schema", 6))
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if not os.path.exists(flat_profile):
        print(f"no findata/profile.json under {ws}"); return 2
    prof = json.load(open(flat_profile, encoding="utf-8"))
    have = int(prof.get("schema", 2))
    if have != 5:
        print(f"findata/ is schema {have}; this script only moves 5 → 6 "
              f"(run migrate_{have}to{have + 1}.py first)"); return 2

    layout.ensure(ws)
    moved = {f: 0 for f in layout.FOLDERS}
    for name in sorted(os.listdir(fd)):
        src = os.path.join(fd, name)
        if not os.path.isfile(src) or name.startswith("."):
            continue
        lay = layout.layer(name)
        dst = os.path.join(fd, lay, name)
        if os.path.exists(dst):
            print(f"  ✗ {lay}/{name} already exists; not overwriting"); return 1
        shutil.move(src, dst)
        moved[lay] += 1
        print(f"  {name:<28} → {lay}/")
    prof["schema"] = 6
    with open(os.path.join(fd, "register", "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(prof, fh, ensure_ascii=False, indent=2); fh.write("\n")
    print("→ findata/: " + ", ".join(f"{n} in {f}/" for f, n in moved.items()))
    print("→ findata/register/profile.json: schema 6")
    print("now: rebuild.py --write, then the checkers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
