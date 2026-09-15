#!/usr/bin/env python3
"""sync.py — push the tool into a workspace, and never anything else.

The tool is this repository. A workspace is a folder somewhere else (an iCloud folder, say) that
holds one person's findata/, their inbox/ and archive/, their OWNER.md — and a copy of the tool.
This script refreshes that copy:

    python3 tools/sync.py <workspace>              # copy the tool in, then rebuild the dashboards
    python3 tools/sync.py <workspace> --check      # say what would change, touch nothing
    python3 tools/sync.py <workspace> --install-guard
        # also install a pre-commit hook in THIS repository that refuses to commit any staged
        # file containing an identifier from <workspace>/.private/deny.txt (a line starting with
        # ! names a file the check skips, e.g. !LICENSE for the authorship line)

What it copies: `.claude/` (the skills and the hook settings), `templates/dashboards/`, the three
governing documents, and `docs/` minus the demo screenshots. What it never touches: `findata/`,
`inbox/`, `archive/`, `dashboards/` (rebuild.py writes those), `OWNER.md`, `decisions/` (the
owner's dated history), `.private/`.

FINANCE.md is the one file with a seam: the prose is the tool's, the figures table is the
workspace's. The table is carried across from the workspace's own copy and the rebuild keeps it
current.

Why a copy and not a symlink or a git checkout inside the workspace: iCloud Drive corrupts `.git`
directories and does not carry symlinks to Windows. A copy is dull, and dull is what a sync should
be.
"""

import filecmp
import os
import re
import shutil
import stat
import subprocess
import sys

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNCED = [
    ".claude/skills",
    ".claude/settings.json",
    "templates/dashboards",
    "CLAUDE.md",
    "FINANCE.md",
    "DESIGN.md",
    "docs/pipeline.py",
    "docs/pipeline.svg",
    "docs/pipeline.drawio",
    "docs/hero.png",
    "docs/logo.svg",
    "docs/zh",            # the Chinese guide is the tool's, like README; screens/ stays the demo's
]
NEVER = ("findata", "inbox", "archive", "dashboards", "OWNER.md", "decisions", ".private")

OWNER_STUB = """# OWNER.md — this workspace's notes

> **This file is one person's** — yours. `CLAUDE.md` loads it with `@OWNER.md`. Everything that is
> about you rather than about the tool goes here: which bank does what, the traps your statements
> have, the decisions you make out loud and the mistakes that taught them. The tool's own
> instructions are in `CLAUDE.md`, `FINANCE.md` and `DESIGN.md`; nothing in those three is about
> anyone in particular. Keep it to what is true today; when a decision is replaced, move the old
> one, dated, into `decisions/` and leave a one-line pointer here.

- Reply in: English
- Banks:
- Broker:
"""

GUARD = """#!/bin/sh
# Installed by tools/sync.py --install-guard. Refuses a commit whose staged files contain any
# identifier from the owner's private deny list, which lives OUTSIDE this repository.
DENY="__DENY__"
[ -f "$DENY" ] || { echo "pre-commit guard: $DENY is missing — refusing to commit blind"; exit 1; }
python3 - "$DENY" <<'PY'
import subprocess, sys
lines = [l.rstrip("\\n") for l in open(sys.argv[1], encoding="utf-8")]
deny = [l for l in lines if l.strip() and not l.startswith(("#", "!"))]
skip = tuple(l[1:].strip() for l in lines if l.startswith("!"))
names = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"], capture_output=True).stdout
hits = []
for f in [x for x in names.decode().split("\\0") if x]:
    if f.startswith(skip):
        continue
    blob = subprocess.run(["git", "show", ":" + f], capture_output=True).stdout.decode("utf-8", "ignore")
    hits += [(f, d) for d in deny if d in blob]
if hits:
    for f, d in hits[:20]:
        print(f"  \\u2717 {f}: contains {d!r}")
    print(f"pre-commit guard: {len(hits)} hit(s) \\u2014 nothing committed")
    sys.exit(1)
PY
"""


def tool_schema():
    """The findata shape this tool builds from, read out of rebuild.py so it is written once."""
    rb = open(os.path.join(TOOL, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py"),
              encoding="utf-8").read()
    m = re.search(r"^SCHEMA = (\d+)", rb, re.M)
    return int(m.group(1)) if m else None


def workspace_schema(ws):
    p = os.path.join(ws, "findata", "register", "profile.json")
    if not os.path.exists(p):
        p = os.path.join(ws, "findata", "profile.json")
    if not os.path.exists(p):
        return None
    import json
    return int(json.load(open(p, encoding="utf-8")).get("schema", 2))


def differs(a, b):
    if os.path.isdir(a):
        if not os.path.isdir(b):
            return True
        cmp = filecmp.dircmp(a, b)
        return bool(cmp.left_only or cmp.right_only or cmp.diff_files) or \
            any(differs(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)
    return not (os.path.exists(b) and filecmp.cmp(a, b, shallow=False))


def figures_block(text):
    m = re.search(r'<!-- LINT:FIGURES.*?<!-- LINT:FIGURES:END -->\n', text, re.S)
    return m.group(0) if m else None


def main(argv):
    if len(argv) < 2 or argv[1].startswith("--"):
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    check = "--check" in argv
    if not os.path.isdir(os.path.join(ws, "findata")) and not check:
        os.makedirs(ws, exist_ok=True)
    print(f"=== sync {TOOL} → {ws}" + ("  (check only)" if check else ""))
    # A tool that builds a newer findata shape than the workspace has must not be copied in:
    # rebuild.py would refuse, the hook would fail on every edit, and the page would go stale
    # with nothing saying why. The migration is one command, named here.
    have, want = workspace_schema(ws), tool_schema()
    if have is not None and want is not None and have != want:
        if have < want:
            print(f"  ✗ the workspace's findata/ is schema {have}; this tool builds schema {want}.\n"
                  f"    Run: python3 tools/migrate.py \"{ws}\"   (every step from {have} to {want}), then sync again. Nothing copied.")
        else:
            print(f"  ✗ the workspace's findata/ is schema {have}, newer than this tool ({want}). Nothing copied.")
        return 1
    changed = []
    for rel in SYNCED:
        src, dst = os.path.join(TOOL, rel), os.path.join(ws, rel)
        if not os.path.exists(src):
            print(f"  ⚠ the tool has no {rel}"); continue
        if rel == "FINANCE.md" and os.path.exists(dst):
            # the seam: the tool's prose around the workspace's own figures table
            tool_text = open(src, encoding="utf-8").read()
            mine = figures_block(open(dst, encoding="utf-8").read())
            theirs = figures_block(tool_text)
            new_text = tool_text.replace(theirs, mine) if (mine and theirs) else tool_text
            if new_text != open(dst, encoding="utf-8").read():
                changed.append(rel)
                if not check:
                    open(dst, "w", encoding="utf-8").write(new_text)
            continue
        if differs(src, dst):
            changed.append(rel)
            if not check:
                if os.path.isdir(src):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
    for rel in changed:
        print(f"  {'·' if check else '→'} {rel}")
    if not changed:
        print("  ✓ the workspace already has this tool")
    for rel in NEVER:
        pass  # listed for the reader: nothing here is written by this script

    owner = os.path.join(ws, "OWNER.md")
    if not os.path.exists(owner) and not check:
        open(owner, "w", encoding="utf-8").write(OWNER_STUB)
        print("  → OWNER.md (empty stub — it is yours to fill)")
    for d in ("inbox", "archive"):
        if not check:
            os.makedirs(os.path.join(ws, d), exist_ok=True)

    if "--install-guard" in argv:
        deny = os.path.join(ws, ".private", "deny.txt")
        hook = os.path.join(TOOL, ".git", "hooks", "pre-commit")
        if not os.path.isdir(os.path.dirname(hook)):
            print("  ⚠ this tool is not a git checkout; no guard to install")
        elif not os.path.exists(deny):
            print(f"  ⚠ {deny} does not exist; write it first (one identifier per line)")
        else:
            open(hook, "w", encoding="utf-8").write(GUARD.replace("__DENY__", deny))
            os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  → pre-commit guard installed, reading {deny}")

    if check:
        return 0
    rb = os.path.join(ws, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py")
    if os.path.isdir(os.path.join(ws, "findata")) and os.path.exists(rb):
        print()
        subprocess.run([sys.executable, rb, ws, "--write"], check=False)
    else:
        print("  (no findata/ yet — say \"set this up\" in the workspace to run the setup skill)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
