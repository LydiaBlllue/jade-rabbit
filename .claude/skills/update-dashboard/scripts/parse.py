#!/usr/bin/env python3
"""parse.py — read one statement with its parser and say whether it reconciles.

    python3 .claude/skills/update-dashboard/scripts/parse.py <file> --doc "<documents[].key>"
    python3 .claude/skills/update-dashboard/scripts/parse.py <file> --parser rbc_visa
    ... --json            # the full result (rows and all) as JSON on stdout, for the import step

Step 1 of the update-dashboard skill runs this on every file preflight named. Exit 0 means the
rows are in and they reconcile; 1 means the file was read but does not reconcile, or a layout
the parser does not know — read that one by hand; 3 means pypdf is missing and every file is
read by hand. Nothing here writes to findata/: the rows come back to the import, which does.

`--doc` looks the parser up in accounts.json (`documents[].parser`), so the register is the
only place a file is tied to a parser.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # the skill folder: parsers/ is a package there
from parsers import parse, ParserUnavailable, ParseError, NAMES  # noqa: E402
sys.path.insert(0, HERE)
import layout  # noqa: E402


def find_root(start):
    p = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(p, "findata")):
            return p
        q = os.path.dirname(p)
        if q == p:
            return None
        p = q


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--doc", help="documents[].key in accounts.json; its `parser` field names the parser")
    ap.add_argument("--parser", choices=NAMES)
    ap.add_argument("--json", action="store_true", help="print the whole result as JSON")
    ap.add_argument("--root", default=".", help="the workspace (default: found upward from here)")
    a = ap.parse_args(argv)

    name = a.parser
    if not name and a.doc:
        root = find_root(a.root) or find_root(HERE)
        if not root:
            print("  ✗ no workspace (a folder with findata/) found"); return 1
        reg = json.load(open(layout.path(root, "accounts.json"), encoding="utf-8"))
        doc = next((d for d in reg.get("documents", []) if d.get("key") == a.doc), None)
        if not doc:
            print(f"  ✗ no document {a.doc!r} in accounts.json"); return 1
        name = doc.get("parser")
        if not name:
            print(f"  · document {a.doc!r} has no parser; read it by hand"); return 1
    if not name:
        print("  ✗ say which parser: --doc <key> or --parser <name>"); return 1

    try:
        res = parse(a.file, name)
    except ParserUnavailable as e:
        print(f"  · {e}"); return 3
    except ParseError as e:
        print(f"  ✗ {name}: {e} — read {os.path.basename(a.file)} by hand"); return 1

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        parts = res.get("accounts") or [res]
        for r in parts:
            ok = r["reconcile"]["ok"]
            print(f"  {'✓' if ok else '✗'} {name} · account …{r.get('account')} · "
                  f"{r['period']['from']} → {r['period']['to']} · {len(r['rows'])} rows")
            print(f"     {r['reconcile']['detail']}")
    return 0 if res["reconcile"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
