#!/usr/bin/env python3
"""PostToolUse hook: lint whichever side of the workspace was just edited.

Reads the hook payload on stdin, works out which file was written, and runs the
matching linter. Never blocks — findings come back as context so they get fixed
in the same turn instead of shipping.
"""
import json, os, re, subprocess, sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# Find the workspace by a landmark, not by counting "..". 2026-09-08 the skills moved from
# <root>/skills/ to <root>/.claude/skills/, one level deeper -- ROOT silently became <root>/.claude,
# the linter ran there, and every ledger came back "missing". It still exited 0, so the hook went
# on reporting success about a directory with no data in it. Counting parents encodes a layout;
# looking for findata/ and dashboards/ encodes the thing that actually defines the workspace.
def _find_root(start):
    d = start
    while True:
        if all(os.path.isdir(os.path.join(d, x)) for x in ("findata", "dashboards")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.path.abspath(os.path.join(start, "..", "..", ".."))   # last resort
        d = up

ROOT = _find_root(SCRIPTS)
DASH = [next(("dashboards/" + n for n in ("ly_finance_dashboard.html", "finance_dashboard.html")
              if os.path.exists(os.path.join(ROOT, "dashboards", n))), "dashboards/finance_dashboard.html")]
# An older workspace may still have the second file until its next rebuild removes it.
if os.path.exists(os.path.join(ROOT, "dashboards", "investment_dashboard.html")):
    DASH.append("dashboards/investment_dashboard.html")

def run(script, args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    return p.returncode, (p.stdout + p.stderr).strip()

def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0
    ti, tr = d.get("tool_input") or {}, d.get("tool_response") or {}
    path = ti.get("file_path") or (tr.get("filePath") if isinstance(tr, dict) else "") or ""
    path = path.replace("\\", "/")

    jobs = []
    # S4 compares the dashboards against DESIGN.md and README.md, so drift can be introduced
    # from either side: editing the dashboard, or editing the document that describes it.
    # Both entrances run the same linter.
    if re.search(r"/dashboards/[^/]+\.html$", path) or re.search(r"/(DESIGN|README)\.md$", path):
        jobs.append(("DESIGN.md", "check_design.py", DASH))
    if "/findata/" in path:
        jobs.append(("findata", "check_data.py", ["."]))
    if not jobs:
        return 0

    reports, worst = [], 0
    for label, script, args in jobs:
        try:
            code, out = run(script, args)
        except Exception as e:
            reports.append(f"{label} lint could not run: {e}"); continue
        worst = max(worst, code)
        reports.append(out)

    body = "\n".join(reports)
    if worst:                      # something is actually broken
        msg = "Lint found errors — see the report and fix before calling this done."
    elif re.search(r"\d+ warn", body) and not re.search(r"0 error, 0 warn", body):
        msg = "Lint passed with warnings."
    else:
        return 0                   # clean: stay quiet, the edit was fine

    print(json.dumps({
        "suppressOutput": True,
        "systemMessage": msg,
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": body},
    }))
    return 0

if __name__ == "__main__":
    sys.exit(main())
