#!/usr/bin/env python3
"""migrate_7to8.py — move a workspace from findata schema 7 to 8.

    python3 tools/migrate_7to8.py <workspace>

What changed in 8 (2026-09-10, FINANCE.md §3b / §8b):
  - A fund's standing contribution is a `saving` flow that names the fund (`to: <fund key>`),
    one row of `funds.json` `plan.flows` like every other line of the plan. The `monthly` and
    `monthlyNote` a fund used to carry are moved there: a fund with `monthly` > 0 gains a flow
    (named after the fund, its note carried over); a fund with 0 simply loses the two fields,
    and the page says "no standing contribution" on its own.
  - `profile.json` becomes "schema": 8.

Safe to run twice: a workspace already at 8 is left alone.
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
    if have >= 8:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 7:
        print(f"findata/ is schema {have}; this script only moves 7 → 8 (run tools/migrate.py)"); return 2

    fp = layout.path(ws, "funds.json")
    funds = json.load(open(fp, encoding="utf-8"))
    flows = funds.setdefault("plan", {}).setdefault("flows", [])
    for f in funds.get("funds", []):
        monthly = f.pop("monthly", 0) or 0
        note = f.pop("monthlyNote", None)
        for k in list(f):
            if k.startswith("zh_monthly"):
                f.pop(k)
        if monthly > 0 and not any(x.get("kind") == "saving" and x.get("to") == f.get("key") for x in flows):
            row = {"key": f"{f['key']}-in", "kind": "saving", "name": f.get("name") or f["key"],
                   "amount": monthly, "to": f["key"]}
            if note:
                row["note"] = note
            # after the allowance, where the waterfall puts it
            i = next((n + 1 for n, x in enumerate(flows) if x.get("kind") == "allowance"), len(flows))
            flows.insert(i, row)
            print(f"→ flow {row['key']}: ${monthly:,} a month to {f['name']}")
        elif monthly:
            print(f"· {f['name']} already has a flow; dropped its monthly")
        else:
            print(f"· {f['name']}: no standing contribution, fields dropped")
    dump(fp, funds)
    prof["schema"] = 8
    dump(pp, prof)
    print("→ profile.json schema 8")
    print("Now rebuild: python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
