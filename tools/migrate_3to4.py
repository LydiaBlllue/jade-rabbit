#!/usr/bin/env python3
"""migrate_3to4.py — move a workspace from findata schema 3 to 4.

    python3 tools/migrate_3to4.py <workspace>

What changed in 4 (2026-09-10, FINANCE.md §8a, CLAUDE.md "The register's axes"):
  - Every row of `accounts.json` `accounts[]` is a balance item with five axes — `side`
    (asset / liability), `role` (grow / set-aside / buffer / none), `reach` (today / costs /
    spoken / locked / abroad), `value` (export / statement / stated) and, on a liability that sits
    on an asset, `against` (that asset's key). Each total the page shows reads exactly one axis,
    so a home, a mortgage or a pension is an ordinary row. Until now net worth was five words in
    `feeds` added up inside rebuild.py, and a mortgage holder got a net worth with the loan in it
    and the house nowhere.
  - `feeds` keeps only the flow words (Income, Spending, Cash flow, Repayments). The net-worth
    words it used to carry — Portfolio, Earmarked, Bank cash, Debts, Dry powder, the foreign
    label, fund labels — are derived into the axes and dropped.
  - `profile.json` becomes `"schema": 4`.

The axes are derived from what the row already says (kind, feeds, src), by the same function
the setup skill uses for a fresh row, so a migrated register and a scaffolded one agree. Check
the result on Records → Accounts; a row the derivation got wrong is one edit.

Safe to run twice: a workspace already at 4 is left alone.
"""
import json
import os
import sys

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOOL, ".claude", "skills", "setup", "scripts"))
from scaffold import default_axes, flow_feeds  # noqa: E402  one derivation, owned by setup


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    fd = lambda n: os.path.join(ws, "findata", n)
    if not os.path.exists(fd("profile.json")):
        print(f"no findata/profile.json under {ws}"); return 2
    prof = json.load(open(fd("profile.json"), encoding="utf-8"))
    have = int(prof.get("schema", 2))
    if have >= 4:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 3:
        print(f"findata/ is schema {have}; this script only moves 3 → 4 "
              f"(run migrate_{have}to{have + 1}.py first)"); return 2

    aj = json.load(open(fd("accounts.json"), encoding="utf-8"))
    for a in aj["accounts"]:
        ax = default_axes(a)
        # Rebuild the row in a stable order: the axes sit right after `src`, where a reader
        # looking for "what is this account" finds them.
        old_feeds = a.get("feeds", "")
        row = {}
        for k, v in a.items():
            if k in ("side", "role", "reach", "value", "against"):
                continue
            if k == "feeds":
                v = flow_feeds(v)
            row[k] = v
            if k == "src":
                row.update(ax)
        if "src" not in a:
            row.update(ax)
        a.clear(); a.update(row)
        print(f"  {a['key']:<18} {ax['side']:<9} {ax.get('role', '—'):<9} {ax.get('reach', '—'):<7} "
              f"{ax['value']:<9} feeds: {old_feeds!r} → {a.get('feeds', '')!r}")
    json.dump(aj, open(fd("accounts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("accounts.json"), "a", encoding="utf-8").write("\n")
    print(f"→ findata/accounts.json: {len(aj['accounts'])} rows given side / role / reach / value")

    prof["schema"] = 4
    json.dump(prof, open(fd("profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("profile.json"), "a", encoding="utf-8").write("\n")
    print("→ findata/profile.json: schema 4")
    print("now: rebuild.py --write, then the checkers; look at Records → Accounts once")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
