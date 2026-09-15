#!/usr/bin/env python3
"""scaffold.py — turn one answers file into a whole findata/.

The setup skill interviews the new owner and writes `setup-answers.json`; this script turns that
into every file the dashboards read. It writes STRUCTURE, not history: balances as given, ledgers
as headers only. The transactions arrive on the first "update dashboards", from real statements.

    python3 scaffold.py <workspace> --answers setup-answers.json [--write] [--force]

Without --write it says what it would do and touches nothing. It refuses to run over a workspace
whose ledgers already have rows in them unless --force is given: someone running setup a second
time by accident would otherwise erase the months they had already imported.

The acceptance test is the same one the release build uses: after `rebuild.py --write`, all four
checkers pass on what this produced. A scaffold that a checker rejects is a bug here, not there.
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "update-dashboard", "scripts"))
import layout  # noqa: E402  where each findata file lives (schema 6)

LEDGER_COLS = ["date", "description", "amount", "balance", "statement"]
SPENDING_COLS = ["date", "amount", "currency", "category", "note"]

# DESIGN.md §1 and CLAUDE.md: the categories are fixed and English. A new one needs a decision,
# not a typo, so the starter file names them and merchants.json is what maps into them.
CATEGORIES = ["Grocery", "Subscription", "Dining", "Shopping", "Transport", "Entertainment", "Other"]

HOLDINGS_COLS = [
    "Account Name", "Account Type", "Account Classification", "Account Number", "Symbol",
    "Exchange", "MIC", "Name", "Security Type", "Quantity", "Position Direction", "Market Price",
    "Market Price Currency", "Book Value (CAD)", "Book Value Currency (CAD)",
    "Book Value (Market)", "Book Value Currency (Market)", "Market Value",
    "Market Value Currency", "Market Unrealized Returns", "Market Unrealized Returns Currency",
]

RETIREMENT_DEFAULTS = {
    "scenarios": [{"r": 0.03, "c": "#9ec5f4", "n": "3% real"}, {"r": 0.05, "c": "#2a78d6", "n": "5% real"},
                  {"r": 0.07, "c": "#104281", "n": "7% real"}],
    "horizon": 25, "anchorYear": 2026, "lifeTo": 95, "coastR": 0.05,
    "homeCare": {"k": "Light care at home", "v": 4200, "esc": 0.015,
                 "d": "Around 4 hours a day of a PSW at roughly $35/hr — meals, cleaning, some personal care. "
                      "Bought by the hour, so it climbs with wages"},
    "ltcTiers": [
        {"k": "Public · basic", "v": 2100, "esc": 0.003, "d": "Shared room in a public long-term-care home. Province-set co-payment for accommodation only — the care itself is publicly funded. A rate reduction exists if income is low. Long waitlist"},
        {"k": "Public · private", "v": 3000, "esc": 0.003, "d": "Private room in the same public system. Same capped pricing, longer wait"},
        {"k": "Private home", "v": 6500, "esc": 0.015, "d": "Private retirement residence with a care package. No waitlist and no subsidy, and priced like any other private service, so it climbs with wages"}],
}

CASH_KINDS = {"Chequing", "Savings", "Money market"}
DEBT_KINDS = {"Credit card", "Line of credit", "Loan", "Mortgage"}
INVEST_KINDS = {"Investment", "TFSA", "RRSP", "FHSA", "Non-registered", "Crypto", "Brokerage"}

# --- the five axes of a balance item (findata schema 4, FINANCE.md §8a) -------------------------
# Every total the page shows reads exactly one of these, so a home, a mortgage or a pension is an
# ordinary row. `feeds` used to carry the net-worth words too (Portfolio, Earmarked, Bank cash,
# Debts, ...); those are axes now and only the flow words stay in `feeds`.
SIDES = ("asset", "liability")
ROLES = ("grow", "set-aside", "buffer", "none")
REACHES = ("today", "costs", "spoken", "locked", "abroad")
VALUES = ("export", "statement", "stated")
VALUE_OF_SRC = {"holdings_latest.csv": "export", "banks.json": "statement", "foreign.json": "statement"}
FLOW_FEEDS = ("Income", "Spending", "Cash flow", "Repayments")


def flow_feeds(feeds):
    """Only the words that say what a ledger is used for on the page; the net-worth words are axes."""
    keep = [t.strip() for t in (feeds or "").split(",") if t.strip() in FLOW_FEEDS]
    return ", ".join(keep)


def default_axes(acc, foreign_src="foreign.json"):
    """side / role / reach / value for one register row, from its kind, its old feeds words and
    where its balance comes from. The interview or the owner may override any of them; this is
    the default a fresh row gets, and what migrate_3to4 derives for an existing one."""
    kind, src = acc.get("kind"), acc.get("src")
    feeds = acc.get("feeds") or ""
    ax = {"side": "liability" if kind in DEBT_KINDS else "asset",
          "value": VALUE_OF_SRC.get(src, "stated")}
    if ax["side"] == "liability":
        if acc.get("against"):
            ax["against"] = acc["against"]
        return ax
    if "Portfolio" in feeds: role = "grow"
    elif "Earmarked" in feeds: role = "set-aside"
    elif "Bank cash" in feeds: role = "buffer"
    elif kind == "Property": role = "none"
    elif kind == "FHSA": role = "set-aside"
    elif kind in CASH_KINDS: role = "buffer"
    elif kind in INVEST_KINDS: role = "grow"
    else: role = "none"
    if src == foreign_src: reach = "abroad"
    elif kind == "Property": reach = "locked"
    elif kind == "RRSP": reach = "costs"
    elif role == "set-aside": reach = "spoken"
    else: reach = "today"
    ax["role"], ax["reach"] = acc.get("role", role), acc.get("reach", reach)
    return ax


def die(msg):
    print("  ✗ " + msg)
    sys.exit(1)


def load_answers(path):
    with open(path, encoding="utf-8") as fh:
        a = json.load(fh)
    # A draft from propose.py carries the questions it could not answer. A draft is not an
    # answer: the owner confirms, the answers go in, the question comes off the list.
    open_q = a.get("_open") or []
    if open_q:
        die(f"{len(open_q)} setup question(s) still open in the answers file — answer them first:\n    "
            + "\n    ".join(f"· {q.get('q', q)}" for q in open_q))
    for req in ("owner", "accounts"):
        if not a.get(req):
            die(f"setup-answers.json has no {req!r} — the interview did not finish")
    for i, acc in enumerate(a["accounts"]):
        for req in ("inst", "name", "kind"):
            if not acc.get(req):
                die(f"account #{i + 1} has no {req!r}")
    return a


def is_demo(root):
    """The demo owner's workspace, as shipped in the repository: profile.json says `demo: true`
    (tools/demo.py writes it). Its ledgers are full, but they are nobody's — a fresh clone
    saying "set this up" must not be refused (found 2026-09-11 on the first real clone)."""
    p = layout.path(root, "profile.json")
    try:
        return bool(json.load(open(p, encoding="utf-8")).get("demo"))
    except (OSError, ValueError):
        return False


def occupied(root):
    """Ledgers that already carry rows. Overwriting these throws away imported months."""
    d = os.path.join(root, "findata")
    if not os.path.isdir(d) or is_demo(root):
        return []
    out = []
    for dirpath, _, files in os.walk(d):
        for f in sorted(files):
            if not f.endswith(".csv"):
                continue
            with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                if len(fh.readlines()) > 1:
                    out.append(f)
    return out


def ordinal(n):
    if n is None:
        return None
    n = int(n)
    suf = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def tag_of(acc, k):
    """The marker written at the end of every row this account's statement produced, e.g.
    `[TD4021/20260831]`. It is what STMT_END and the reconciliation are keyed on."""
    digits = "".join(ch for ch in (acc.get("id") or "") if ch.isdigit())
    return (acc["inst"] + digits).upper().replace(" ", "") or k.upper()


def acc_key(acc, seen):
    """A stable primary key. `id` cannot serve: an account with no number gets "—" (CLAUDE.md)."""
    base = "".join(ch for ch in (acc["inst"] + "-" + acc["name"]).lower()
                   if ch.isalnum() or ch == "-").strip("-")
    k, n = base, 2
    while k in seen:
        k, n = f"{base}-{n}", n + 1
    seen.add(k)
    return k


def build(a, today):
    """Every findata file, as {relative path: text}. Pure — it writes nothing."""
    cur = a.get("currency", "CAD")
    out = {}

    out[layout.rel("profile.json")] = json.dumps({
        "note": "Who this workspace belongs to. The FIRST thing to change when you make it yours: "
                "the name appears in the browser tab and under the Jade Toad wordmark in the sidebar, and it is read from here so it is never typed into the HTML. Jade Toad itself is the product, not a setting.",
        "schema": 9,
        "owner": a["owner"],
        "born": a.get("born", 1990),
        "importDay": int(a.get("importDay", 26)),
    }, ensure_ascii=False, indent=2) + "\n"

    # --- the register: accounts, and the documents that arrive for them ------------------
    seen, accounts, documents = set(), [], []
    for acc in a["accounts"]:
        k = acc.get("key") or acc_key(acc, seen)
        seen.add(k)
        tag = acc.get("tag") or tag_of(acc, k)
        # An investment account's balance comes from the holdings export and nowhere else: a
        # figure typed at setup would sit in the register while net worth read an empty export,
        # and the Accounts page would accuse itself of double-counting. Keep what they said as
        # `statedBalance` so nothing is lost; `balance` stays unknown until the first import.
        investment = acc["kind"] in INVEST_KINDS
        # A stated item -- a home, a car, a loan with no statement -- has no source file: its
        # balance is the owner's word, dated. `src` "none" says so, and D20 keeps the date fresh.
        stated = acc["kind"] == "Property" or acc.get("src") == "none"
        rec = {
            "inst": acc["inst"], "id": acc.get("id", "—"), "name": acc["name"],
            "kind": acc["kind"], "cur": acc.get("cur", cur),
            "balance": None if investment else acc.get("balance"),
            "asof": None if investment else acc.get("asof", today),
            "src": "none" if stated else acc.get("src", "banks.json" if acc["kind"] in CASH_KINDS | DEBT_KINDS
                                                    else "holdings_latest.csv"),
            "ledger": acc.get("ledger"), "feeds": flow_feeds(acc.get("feeds", "")), "key": k,
        }
        rec.update(default_axes({**acc, "src": rec["src"]}))
        # The tags are what ties a row back to the statement it came from. An account with its own
        # ledger carries stmtTag; one whose charges land in spending.csv carries spendTag.
        if acc.get("ledger"):
            rec["stmtTag"] = tag
            rec["stmtLabel"] = acc["name"]
        if "Spending" in (acc.get("feeds") or ""):
            rec["spendTag"] = tag
        if investment and acc.get("balance") is not None:
            rec["statedBalance"] = acc["balance"]
        if acc.get("limit"):
            rec["limit"] = acc["limit"]
        if acc.get("gap"):
            rec["gap"] = acc["gap"]
        accounts.append(rec)
        doc = acc.get("doc")
        if doc:
            # `ep` is the entry point the table groups by, `closes` is displayed, so it is the
            # ordinal string a reader expects — a document with no closing day shows "—".
            d = {
                "key": doc.get("key") or (acc["name"] + " " +
                                          "".join(ch for ch in (acc.get("id") or "") if ch.isdigit())).strip(),
                "ep": doc.get("ep", acc["inst"]),
                "file": doc.get("file", "<statement>.pdf"),
                "closes": doc.get("closes_label") or ordinal(doc.get("closes")) or "—",
                "feeds": acc.get("feeds", ""),
                # A file is not an account: one export can cover several. `alsoCovers` names the
                # other accounts; `from` is the first month this document is owed, so the filing
                # grid does not mark every month back to January as missing on day one.
                "covers": [k] + [x for x in (doc.get("alsoCovers") or [])],
                "from": doc.get("from", today[:7]),
                # The archive tag: the interview may name one (an owner keeping an existing archive);
                # otherwise inst + digits.
                "tags": doc.get("tags") or [tag],
                # `into` and `reconcile` are how the import step knows what to do with the file
                # without a table of instructions somewhere else. Every document needs both.
                "into": doc.get("into") or acc.get("ledger") or
                        ("holdings_latest.csv" if acc["kind"] in INVEST_KINDS else "banks.json"),
            }
            # Which parser reads the file (parsers/ in the update-dashboard skill). Absent means
            # the statement is read by hand; D14 rejects a name no parser has.
            if doc.get("parser"):
                d["parser"] = doc["parser"]
            d["reconcile"] = doc.get("reconcile") or (
                "opening + in - out = closing" if acc.get("ledger")
                else "positions replace the previous snapshot" if acc["kind"] == "Investment"
                else "the closing balance replaces the previous one")
            if doc.get("optional"):
                d["optional"] = True
            documents.append(d)
    name_to_key = {a["name"]: a["key"] for a in accounts}
    for d in documents:
        d["covers"] = [name_to_key.get(c, c) for c in d["covers"]]
    # Accounts abroad arrive as screenshots of an app, not as statements. One document covers them
    # all, so preflight has something to name a screenshot by (2026-09-12: without it, the first
    # import after setup stopped on two screenshots it could not place).
    abroad = [x for x in accounts if x.get("src") == "foreign.json"]
    if abroad and not any(d.get("into") == "foreign.json" for d in documents):
        lab = (a.get("foreign") or {}).get("label") or "Foreign"
        documents.append({
            "key": f"{lab} balances", "ep": lab, "file": "<screenshot>", "closes": "any time",
            "from": today[:7], "feeds": "Balances abroad, net worth", "covers": [x["key"] for x in abroad],
            "tags": ["".join(ch for ch in lab.upper() if ch.isalnum()) + "_SCREENSHOT"],
            "into": "foreign.json", "reconcile": "account total matches the summary shown in the app"})
    # The cash-flow rows are derived at build (schema 9). A counterparty (someone repaying a loan)
    # is named on the document row of their ledger.
    cpa = a.get("counterparty") or {}
    if cpa.get("name"):
        for d in documents:
            if d.get("into") == cpa.get("ledger"):
                d["counterparty"] = cpa["name"]
        if not any(d.get("into") == cpa.get("ledger") for d in documents):
            # Their ledger is not an account's statement, so the interview cannot hang it on an
            # account; it is a document of its own, optional, filed when it changes.
            documents.append({
                "key": f"{cpa['name']} ledger", "ep": cpa.get("ep", cpa["name"]),
                "file": cpa.get("file", "<ledger export>"), "closes": "when it changes",
                "optional": True, "feeds": "Who an e-Transfer came from", "covers": [],
                "tags": ["".join(ch for ch in cpa["name"].upper() if ch.isalnum()) + "_LEDGER"],
                "into": cpa["ledger"], "reconcile": "counterparty only; never counted as income",
                "counterparty": cpa["name"]})
    out[layout.rel("accounts.json")] = json.dumps({
        "asof_note": "The one register of accounts and of the files dropped each month. `balance` "
                     "and `asof` are COPIES of the source files; change the source, not this. "
                     "`key` is the stable join — an account with no number has id \"—\".",
        "accounts": accounts,
        "gaps": a.get("gaps", []),
        "documents": documents,
        "archive_note": "Processed originals live in archive/, named <date processed>_<original>.",
    }, ensure_ascii=False, indent=2) + "\n"

    # --- balances, split the way the dashboard reads them --------------------------------
    assets = [{"inst": x["inst"], "account": x["name"], "balance": x["balance"] or 0,
               "currency": x["cur"], "asof": x["asof"]}
              for x in accounts if x["kind"] in CASH_KINDS and x["src"] == "banks.json"]
    debts = [{"inst": x["inst"], "account": x["name"], "balance": abs(x["balance"] or 0),
              "currency": x["cur"], "asof": x["asof"], "limit": x.get("limit")}
             for x in accounts if x["kind"] in DEBT_KINDS and x["src"] == "banks.json"]
    out[layout.rel("banks.json")] = json.dumps({
        "asof_note": "One as-of date per account, because they do not all arrive together.",
        "assets": assets, "debts": debts,
        "classification": "Bank cash is the daily buffer: earmarked under rule 2 and outside "
                          "investable capital.",
    }, ensure_ascii=False, indent=2) + "\n"

    # --- the monthly plan ----------------------------------------------------------------
    plan = a.get("plan") or {}
    out[layout.rel("funds.json")] = json.dumps({
        "asof_note": "The guilt-free budget: one allowance, no category caps.",
        "plan": {
            "start": today[:7],
            # Schema 5: the plan is flows (FINANCE.md §8b). Take-home, the fixed payments made
            # before anything is chosen, the transfer to the broker, the guilt-free line. Rent
            # the owner will pay after FIRE but does not pay today starts at FIRE: out of this
            # month's split, inside the planning figure.
            "flows": [
                {"key": "pay", "kind": "income", "name": "Take-home pay",
                 "amount": plan.get("takeHome", 0),
                 "note": plan.get("takeHomeNote", "What actually lands in your account each month.")},
            ] + [
                {"key": c.get("key") or re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-"),
                 "kind": "committed", "name": c["name"], "amount": c["amount"],
                 **({"until": c["until"]} if c.get("until") else {}),
                 **({"afterFire": c["afterFire"]} if c.get("afterFire") else {}),
                 **({"pays": c["pays"]} if c.get("pays") else {}),
                 **({"note": c["note"]} if c.get("note") else {})}
                for c in (plan.get("committed") or [])
            ] + ([
                {"key": "rent-after-fire", "kind": "committed", "name": "Rent",
                 "amount": int(plan.get("imputedRent", 0)), "starts": "fire", "afterFire": "keep",
                 "note": "Not paid today. Part of the planning figure from the day FIRE begins."}
            ] if int(plan.get("imputedRent", 0) or 0) else []) + [
                {"key": "invest", "kind": "saving", "name": "Invest", "amount": plan.get("invest", 0),
                 "to": "broker", "note": "Off the top, before anything else — pay-yourself-first."},
                {"key": "everyday", "kind": "allowance", "name": "Everyday allowance",
                 "amount": plan.get("everyday", 0),
                 "note": "The guilt-free line. No categories and no caps below it."},
            ] + [
                # Schema 8: a fund's standing contribution is a saving flow that names the fund.
                {"key": f"{f['key']}-in", "kind": "saving", "name": f.get("name") or f["key"],
                 "amount": f["monthly"], "to": f["key"],
                 **({"note": f["monthlyNote"]} if f.get("monthlyNote") else {})}
                for f in (a.get("funds") or []) if f.get("monthly")
            ],
            "bigThreshold": plan.get("bigThreshold", 300),
            "leftover": plan.get("leftover", "Whatever the allowance does not use tops up the funds below."),
        },
        "funds": [{k: v for k, v in f.items() if k not in ("monthly", "monthlyNote")} for f in (a.get("funds") or [])],
        "claimsAgainst": {
            "source": "Each fund names the account it is claimed against, and the claims have to "
                      "fit inside that account.",
            "note": "A fund is a label on an account you already have, not an account of its own.",
        },
    }, ensure_ascii=False, indent=2) + "\n"

    # --- the one computed investing rule --------------------------------------------------
    out[layout.rel("rules.json")] = json.dumps({
        "note": "Your investing rules, as data. ONE thing is computed: every bucket that carries "
                "a `target` is checked against that range, and the Rules page reports the drift. "
                "Buckets are matched in order and the one marked catchAll takes whatever is left. "
                "Everything else you believe about your portfolio belongs in prose on the page, "
                "judged by you.",
        **(a.get("rules") or {
            "buckets": [{"key": "rest", "name": "Holdings", "catchAll": True}],
            "maxHoldings": 10,
        }),
        **({"notes": [], "checkpoints": []} if not (a.get("rules") or {}).get("notes") else {}),
    }, ensure_ascii=False, indent=2) + "\n"

    # --- merchant map: the categories are fixed, the merchants are yours ------------------
    out[layout.rel("merchants.json")] = json.dumps({
        "note": "The one source of truth for merchant → category. Look a merchant up BEFORE "
                "judging it; a miss is a new merchant and has to be confirmed with you.",
        "why": "A merchant string is an abbreviation and a truncation. It cannot be read for "
               "meaning: LIGHTHOUSE PUBLICATION sells notebooks.",
        "rules": [
            "Subscription means the charge repeats. A merchant seen once is never a "
            "Subscription — file it as Shopping or Other and flag it for confirmation.",
            "The categories are fixed: " + " / ".join(CATEGORIES) + ". A new one needs a decision.",
        ],
        # A list, the shape rebuild.py and D6 read: {match, category, seen, first, last} per merchant.
        "merchants": [],
    }, ensure_ascii=False, indent=2) + "\n"

    fgn = a.get("foreign") or {}
    fa = fgn.get("accounts", [])
    # The total and the summary are derived from the accounts, never asked for: D8 checks this
    # file against ITSELF, and a hand-entered total that does not sum is the first thing it says.
    ftot = round(sum(x.get("value", 0) for x in fa), 2)
    fcash = round(sum(x.get("value", 0) for x in fa
                      if x.get("type") not in ("bond_fund", "equity_fund")), 2)
    out[layout.rel("foreign.json")] = json.dumps({
        "asof": today,
        "currency": fgn.get("currency"),
        "symbol": fgn.get("symbol", ""),
        "label": fgn.get("label", "Foreign"),
        "cadPerUnit": fgn.get("cadPerUnit", 0),
        "total": ftot,
        "accounts": fa,
        "summary": {"cash": fcash, "invested": round(ftot - fcash, 2),
                    "cash_share_pct": round(fcash / ftot * 100, 1) if ftot else 0},
    }, ensure_ascii=False, indent=2) + "\n"

    out[layout.rel("plan.json")] = json.dumps({
        "note": "Your planning assumptions. `planBase` is the monthly planning spend the FIRE target "
                "is built on (× 12 × 25); "
                "`skipMonths` are months excluded from every comparison, each with the reason the "
                "page shows. `retirement` holds the projection scenarios and the late-life care "
                "model; `descriptions` are your own one-liners under the net-worth parts.",
        "planBase": int(plan.get("planBase") or plan.get("everyday") or 0),
        "skipMonths": {},
        "retirement": a.get("retirement") or RETIREMENT_DEFAULTS,
    }, ensure_ascii=False, indent=2) + "\n"
    out[layout.rel("networth_history.json")] = json.dumps({
        "note": "One net-worth point per month, appended on every 'update dashboards' when the "
                "holdings export reaches a new month.", "snapshots": []}, indent=2) + "\n"
    out[layout.rel("tasks.json")] = json.dumps({
        "note": "Open tasks, shown on Data → Tasks. Added and closed out loud by the owner.",
        "tasks": []}, indent=2) + "\n"
    out[layout.rel("filings.json")] = json.dumps({
        "note": "Which month each document was filed, keyed by accounts.json documents[].key. "
                "Written by the import step when a file is archived; checked against archive/ by T2.",
        # One empty list per document, so the filing grid has a row to tick from day one (a fresh
        # workspace used to raise one D14 warning per document, 2026-09-11).
        "filed": {d["key"]: [] for d in documents}}, ensure_ascii=False, indent=2) + "\n"
    out[layout.rel("imports.json")] = json.dumps({
        "note": "One record per 'update dashboards', newest last: the files that came in, what changed (label / from / to), what was noticed (sev ok / warn / bad + text), what was decided without asking (`judged`) and what the owner was asked (`asked`). Data → Updates renders it; the import report IS this record. Every sentence here reaches the page: write it about the owner's money, never about the tool — no 'I', no rule numbers, no file names.",
        "imports": []}, ensure_ascii=False, indent=2) + "\n"
    out[layout.rel("decisions.json")] = json.dumps({
        "note": "What is waiting for the owner to confirm, written by the import: a merchant seen for the first time, an e-Transfer typed by default, a transfer whose other side is unknown, a file nobody could name. Each item: `added`, `kind` (merchant / transfer / file / classification), `what` (one sentence, about the money), `default` (what was assumed meanwhile), `source` (which statement, which line), `status` open / confirmed, and once confirmed `answer` and `resolved`. Data → Updates lists the open ones and the page header counts them. Separate from tasks.json: these are produced by an import and disappear on a word; tasks are the owner's own.",
        "decisions": []}, ensure_ascii=False, indent=2) + "\n"
    out[layout.rel("investment_history.json")] = json.dumps({
        "note": "One snapshot per 'update dashboards'. The first arrives with your first holdings "
                "export; until then the trend cards have nothing to compare against, which is "
                "correct rather than broken.",
        "snapshots": [],
    }, ensure_ascii=False, indent=2) + "\n"

    if any(x["kind"] == "Investment" for x in accounts):
        out[layout.rel("fx.json")] = json.dumps({
            "usd_cad": a.get("fx", 1.0),
            "asof": today,
            "quality": "setup",
            "source": "Set during setup. Replace it from your broker's activities export, which "
                      "carries a dated rate; the holdings export does not.",
            "why_it_matters": "It converts every foreign-currency position, so it moves net worth.",
            "history": [],
        }, ensure_ascii=False, indent=2) + "\n"
        out[layout.rel("holdings_latest.csv")] = ",".join(HOLDINGS_COLS) + "\n"

    # --- the ledgers, headers only --------------------------------------------------------
    out[layout.rel("spending.csv")] = ",".join(SPENDING_COLS) + "\n"
    for led in sorted({x["ledger"] for x in accounts if x.get("ledger")}):
        out[layout.rel(led)] = ",".join(LEDGER_COLS) + "\n"
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--answers")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")

    args = ap.parse_args(argv[1:])

    root = os.path.abspath(args.root)
    # The refusal comes FIRST, before the answers are even parsed: "is this workspace already
    # somebody's?" is the question the setup skill asks with a throwaway answers path, and it has
    # to get the refusal rather than a JSON error.
    busy = occupied(root)
    if busy and not args.force:
        die("these ledgers already have rows in them: " + ", ".join(busy) +
            ".\n    Setup writes empty ledgers, so running it here would throw away months you "
            "have already imported.\n    If that is really what you want, pass --force.")

    if not args.answers:
        die("--answers is required")
    a = load_answers(args.answers)
    today = a.get("today") or datetime.date.today().isoformat()
    files = build(a, today)
    print(f"=== setup scaffold — {len(files)} files from {len(a['accounts'])} accounts")
    for path in sorted(files):
        print(f"  {'→' if args.write else '·'} {path}")
    if not args.write:
        print("\n  nothing written. Re-run with --write to apply.")
        return 0

    # A demo workspace's ledgers belong to nobody; the new register may not name them at all
    # (the demo's friend ledger stayed behind on the first real clone, 2026-09-11). Cleared only
    # here, after the answers have been read and built without error: a refused setup must leave
    # the workspace exactly as it found it (it did not, 2026-09-12).
    if is_demo(root):
        led = os.path.join(root, "findata", "ledgers")
        stale = sorted(f for f in (os.listdir(led) if os.path.isdir(led) else []) if f.endswith(".csv"))
        for f in stale:
            os.remove(os.path.join(led, f))
        if stale:
            print("  − demo ledgers cleared: " + ", ".join(stale))
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
    print("\n  written. Now run rebuild.py --write, then the four checkers — they are the "
          "acceptance test for this scaffold.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
