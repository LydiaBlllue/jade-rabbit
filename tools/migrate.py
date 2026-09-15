#!/usr/bin/env python3
"""migrate.py — bring a workspace's findata/ up to the schema this tool builds, one step at a time.

    python3 tools/migrate.py <workspace>

Reads the workspace's schema from profile.json (a file with none is schema 2), reads the tool's
from rebuild.py, and runs tools/migrate_<n>to<n+1>.py for every step in between, stopping at the
first one that fails. A workspace already current is left alone. Each step is its own script so
it can still be read, and run, on its own.
"""
import json
import os
import re
import subprocess
import sys

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tool_schema():
    rb = open(os.path.join(TOOL, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py"),
              encoding="utf-8").read()
    m = re.search(r"^SCHEMA = (\d+)", rb, re.M)
    return int(m.group(1)) if m else None


def workspace_schema(ws):
    for p in (os.path.join(ws, "findata", "register", "profile.json"),
              os.path.join(ws, "findata", "profile.json")):
        if os.path.exists(p):
            return int(json.load(open(p, encoding="utf-8")).get("schema", 2))
    return None


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    have, want = workspace_schema(ws), tool_schema()
    if have is None:
        print(f"no findata/profile.json under {ws}"); return 2
    if want is None:
        print("the tool's rebuild.py names no SCHEMA"); return 2
    if have >= want:
        print(f"findata/ is schema {have}; the tool builds {want}. Nothing to do."); return 0
    print(f"=== migrate {ws}: schema {have} → {want}")
    for n in range(have, want):
        step = os.path.join(TOOL, "tools", f"migrate_{n}to{n + 1}.py")
        if not os.path.exists(step):
            print(f"  ✗ no tools/migrate_{n}to{n + 1}.py — the tool cannot move a schema-{n} workspace")
            return 1
        print(f"--- {n} → {n + 1}")
        rc = subprocess.run([sys.executable, step, ws]).returncode
        if rc:
            print(f"  ✗ step {n} → {n + 1} failed (exit {rc}); stopped here")
            return rc
    print(f"=== findata/ is schema {want}. Now sync the tool in, or rebuild.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
