#!/usr/bin/env python3
"""migrate_2to3.py — move a workspace from findata schema 2 to 3.

    python3 tools/migrate_2to3.py <workspace>

What changed in 3 (2026-09-10):
  - `alerts.json` is retired. It held the sentences the last import wrote about the investing
    side, and the page showed them as "Rule status" for as long as they sat there — a report
    from one day, read as the state of things months later. They become the `noticed` list of
    one record in `imports.json`, dated by the newest investment snapshot (or today).
  - `imports.json` is new: one record per "update dashboards" — the files, what changed, what
    was noticed, what was decided without asking, what the owner was asked. The report the
    import writes is a rendering of it, and Data → Updates lists them.
  - `decisions.json` is new: the queue of things waiting for the owner to confirm (a merchant
    seen for the first time, an e-Transfer typed by default, a file nobody could name). Starts
    empty; the next import fills it.
  - `profile.json` gains `"schema": 3`, which rebuild.py and tools/sync.py check.

Safe to run twice: a workspace already at 3 is left alone.
"""
import datetime
import json
import os
import sys


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    fd = lambda n: os.path.join(ws, "findata", n)
    if not os.path.exists(fd("profile.json")):
        print(f"no findata/profile.json under {ws}"); return 2
    prof = json.load(open(fd("profile.json"), encoding="utf-8"))
    have = int(prof.get("schema", 2))
    if have >= 3:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 2:
        print(f"findata/ is schema {have}; this script only moves 2 → 3"); return 2

    today = datetime.date.today().isoformat()
    when = today
    if os.path.exists(fd("investment_history.json")):
        snaps = json.load(open(fd("investment_history.json"), encoding="utf-8")).get("snapshots", [])
        if snaps:
            when = max(s["date"] for s in snaps)

    noticed = []
    if os.path.exists(fd("alerts.json")):
        noticed = json.load(open(fd("alerts.json"), encoding="utf-8")).get("alerts", [])

    imports = {"imports": []}
    if os.path.exists(fd("imports.json")):
        imports = json.load(open(fd("imports.json"), encoding="utf-8"))
    imports["note"] = ("One record per 'update dashboards', newest last: the files that came in, what "
                       "changed (label / from / to), what was noticed (sev ok / warn / bad + text), "
                       "what was decided without asking (`judged`) and what the owner was asked "
                       "(`asked`). Data → Updates renders it; the import report IS this record. "
                       "Every sentence here reaches the page: write it about the owner's money, "
                       "never about the tool — no 'I', no rule numbers, no file names.")
    if noticed and not any(r.get("date") == when and r.get("migrated") for r in imports["imports"]):
        imports["imports"].append({"date": when, "migrated": "from alerts.json", "files": [],
                                   "changed": [], "noticed": noticed, "judged": [], "asked": []})
    json.dump(imports, open(fd("imports.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("imports.json"), "a", encoding="utf-8").write("\n")
    print(f"→ findata/imports.json ({len(imports['imports'])} record(s)"
          + (f", {len(noticed)} lines carried over from alerts.json" if noticed else "") + ")")

    if not os.path.exists(fd("decisions.json")):
        json.dump({"note": ("What is waiting for the owner to confirm, written by the import: a merchant "
                            "seen for the first time, an e-Transfer typed by default, a transfer whose "
                            "other side is unknown, a file nobody could name. Each item: `added`, "
                            "`kind` (merchant / transfer / file / classification), `what` (one sentence, "
                            "about the money), `default` (what was assumed meanwhile), `source` (which "
                            "statement, which line), `status` open / confirmed, and once confirmed "
                            "`answer` and `resolved`. Data → Updates lists the open ones and the page "
                            "header counts them. Separate from tasks.json: these are produced by an "
                            "import and disappear on a word; tasks are the owner's own."),
                   "decisions": []},
                  open(fd("decisions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(fd("decisions.json"), "a", encoding="utf-8").write("\n")
        print("→ findata/decisions.json (empty)")

    if os.path.exists(fd("alerts.json")):
        os.remove(fd("alerts.json"))
        print("− findata/alerts.json (its lines are in imports.json now)")

    prof["schema"] = 3
    # keep `schema` near the top so it is the first thing a reader sees after the note
    ordered = {}
    for k in ("note", "schema"):
        if k in prof:
            ordered[k] = prof[k]
    for k, v in prof.items():
        ordered.setdefault(k, v)
    json.dump(ordered, open(fd("profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("profile.json"), "a", encoding="utf-8").write("\n")
    print("→ findata/profile.json schema 3")
    print("Now rebuild: python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
