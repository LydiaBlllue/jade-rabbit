"""layout.py — where each findata file lives (schema 6): three folders, one per layer.

CLAUDE.md's information model has five layers. Two already had folders of their own — the
evidence in inbox/ and archive/, the derived pages in dashboards/ — and the middle three sat
together in one flat findata/. Now each has its folder, named by the layer, and the one rule
that decides where a file goes is who writes it:

    findata/register/   the owner's declarations — accounts, profile, funds, plan, rules,
                        merchants, tasks. Written by setup or out loud; edited with a reason.
    findata/ledgers/    the facts the import writes — every ledger CSV, spending.csv, the
                        broker's exports, banks.json, fx.json, foreign.json.
                        Appended, every row tagged with its statement.
    findata/history/    what each update left behind — imports, decisions, filings, the two
                        history files. One record per update, never edited.

Every script asks this module for a path and names the file bare — `path(root, "funds.json")`
— so the register's `ledger` and `documents[].into` fields stay bare filenames too. A name no
list claims is a ledger: the ledger CSVs are named in accounts.json, not here.

The folder is still called findata/: iCloud for Windows excludes any folder named `data`.
"""
import os

REGISTER = ("accounts.json", "profile.json", "funds.json", "plan.json", "rules.json",
            "merchants.json", "tasks.json", "setup-answers.json")
HISTORY = ("imports.json", "decisions.json", "filings.json", "investment_history.json",
           "networth_history.json")
FOLDERS = ("register", "ledgers", "history")


def layer(name):
    base = os.path.basename(name)
    if base in REGISTER:
        return "register"
    if base in HISTORY:
        return "history"
    return "ledgers"


def rel(name):
    """'funds.json' -> 'findata/register/funds.json'. A name that already carries a folder is
    left alone."""
    if "/" in name:
        return name if name.startswith("findata/") else "findata/" + name
    return f"findata/{layer(name)}/{name}"


def path(root, name):
    """The file's path in a workspace. A workspace not yet moved to schema 6 keeps its files
    flat; until migrate_5to6 runs, the flat file is what exists, so it is what is returned."""
    p = os.path.join(root, *rel(name).split("/"))
    if not os.path.exists(p):
        flat = os.path.join(root, "findata", os.path.basename(name))
        if os.path.exists(flat) and not os.path.isdir(os.path.dirname(p)):
            return flat
    return p


def ensure(root):
    for f in FOLDERS:
        os.makedirs(os.path.join(root, "findata", f), exist_ok=True)


def is_split(root):
    return os.path.isdir(os.path.join(root, "findata", "register"))
