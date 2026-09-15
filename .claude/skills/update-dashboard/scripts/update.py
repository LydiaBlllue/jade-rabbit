#!/usr/bin/env python3
"""update.py — the monthly import as one local run.

    python3 .claude/skills/update-dashboard/scripts/update.py .            # say what would happen
    python3 .claude/skills/update-dashboard/scripts/update.py . --write    # do it
    ... --json                                                              # the summary as JSON
    ... --hand rows.json    # statements read by the model, transcribed: [{file, doc, account,
                            #   period{from,to}, opening, closing, rows[{date, description,
                            #   amount, balance}], totals{...}}]; amounts signed the ledger's way

WHY. Until 2026-09-14 the import was: a script parsed each statement and PRINTED every row, and
the model then categorised the rows, typed them, and wrote the ledgers by hand. So the model read
every transaction every month even when every parser succeeded, and the README's "nothing leaves
your computer" was true of the files and false of their contents. Arithmetic and bookkeeping do
not need a model. This script does Steps 0–7 of the update-dashboard skill for everything a
parser can read, and prints a summary: what was filed, and the short list of things a program
cannot decide. Those — and only those — are what the model reads:

  · a merchant seen for the first time (filed as Other meanwhile, queued in decisions.json);
  · an e-Transfer whose other side it cannot name (typed by default, queued the same way);
  · a ledger row it could not type (left blank; D22 keeps pointing at it);
  · a file no parser reads: a statement that does not reconcile, a layout nobody wrote a parser
    for, a screenshot of an account held abroad. A statement like that is read by the model —
    the one thing it still opens — but only transcribed: the rows and the printed totals come
    back as JSON (`--hand rows.json`), and this script reconciles them and files them the same
    way it files a parser's. A transcription that does not add up is refused, not written.

What it never does: infer an account from a filename (preflight names files, and anything it
cannot name stops the run), write a row that does not reconcile, or type a repayment as income
(the counterparty ledger is checked first, the way D10 checks it afterwards).

Exit 0: done (or, without --write, the plan). 1: stopped before writing — an unnamed file, an
identical pair that classifies as two documents, a statement that does not follow its ledger.
2: written, but a checker found something. 3: pypdf is missing; nothing can be parsed.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CHECKS = os.path.join(os.path.dirname(os.path.dirname(SKILL)), "skills", "workspace-checks", "scripts")
sys.path.insert(0, SKILL)
from parsers import parse as parse_file, ParserUnavailable, ParseError, NAMES as PARSERS  # noqa: E402
sys.path.insert(0, HERE)
import layout  # noqa: E402
import preflight  # noqa: E402
import rebuild  # noqa: E402
sys.path.insert(0, CHECKS)
from check_data import merchant_key  # noqa: E402  the one definition of "the same merchant"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LONG = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December")
LEDGER_COLS = ["date", "description", "amount", "balance", "statement", "type", "label"]
SPEND_COLS = ["date", "amount", "currency", "category", "note"]
NEW_MERCHANT_CATEGORY = "Other"      # merchants.json's rule: a first sighting is never a Subscription


def iso_to_date(s):
    return datetime.date.fromisoformat(s)


def short(d):
    return f"{MONTHS[d.month - 1]} {d.day}"


def stamp(d):
    return d.strftime("%Y%m%d")


def money(v):
    return f"${v:,.0f}"


def digits(s):
    return re.sub(r"\D", "", s or "")


def jload(p, default=None):
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return default


def jsave(p, obj):
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(p, "a", encoding="utf-8").write("\n")


def csv_rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []


# ---------------------------------------------------------------- the workspace as the run sees it
class Workspace:
    def __init__(self, root):
        self.root = root
        fd = lambda n: layout.path(root, n)
        self.fd = fd
        self.reg = jload(fd("accounts.json"))
        if not self.reg:
            raise SystemExit("no findata/register/accounts.json — the setup skill writes it")
        self.accounts = self.reg["accounts"]
        self.by_key = {a["key"]: a for a in self.accounts}
        self.docs = self.reg.get("documents", [])
        self.profile = jload(fd("profile.json"), {})
        self.funds = jload(fd("funds.json"), {"plan": {"flows": []}, "funds": []})
        self.banks = jload(fd("banks.json"), {"assets": [], "debts": []})
        self.merchants = jload(fd("merchants.json"), {"merchants": []})
        self.filings = jload(fd("filings.json"), {"filed": {}})
        self.decisions = jload(fd("decisions.json"), {"decisions": []})
        self.imports = jload(fd("imports.json"), {"imports": []})
        self.today = datetime.date.today()
        self.owner = (self.profile.get("owner") or "").upper()
        self.broker = next((a["inst"] for a in self.accounts if a.get("role") == "grow" and a.get("value") == "export"), "")
        cp_doc = next((d for d in self.docs if d.get("counterparty")), None)
        self.cp = cp_doc["counterparty"] if cp_doc else None
        self.cp_rows = csv_rows(fd(cp_doc["into"])) if cp_doc and cp_doc.get("into") else []
        flows = self.funds.get("plan", {}).get("flows", [])
        self.rent = [f["amount"] for f in flows if f.get("kind") == "committed"]
        self.cards = [a for a in self.accounts if a.get("kind") == "Credit card"]
        # What spending.csv already says about a merchant merchants.json has no row for: the
        # rows were filed under one category, so a new row of the same merchant follows them.
        self.row_cats = collections.defaultdict(set)
        for r in csv_rows(fd("spending.csv")):
            self.row_cats[merchant_key(r["note"])].add(r["category"])
        self.bank_accts = [a for a in self.accounts if a.get("src") == "banks.json"]

    def account_for(self, doc, parsed_digits):
        """The register row a parsed account belongs to: the statement's own digits decide,
        never the filename. The document's `covers` is tried first, then every account at the
        same institution (one BMO PDF can carry two accounts)."""
        cands = [self.by_key[k] for k in doc.get("covers", []) if k in self.by_key]
        cands += [a for a in self.accounts if a.get("inst") == doc.get("ep") and a not in cands]
        if parsed_digits:
            for a in cands:
                if digits(a.get("id")) and digits(a.get("id")).endswith(parsed_digits[-4:]):
                    return a
        return cands[0] if len(cands) == 1 or not parsed_digits else None

    def doc_for_account(self, key):
        return next((d for d in self.docs if key in d.get("covers", []) and d.get("parser")), None)

    def doc_name(self, doc):
        return re.sub(r"\s*\d+$", "", doc["key"])


# ---------------------------------------------------------------- what a ledger row is
def merchant_of_debit(desc):
    """'Contactless Interac purchase - 7740 FARM BOY #17 OTTAWA ON' -> 'FARM BOY #17 OTTAWA ON'."""
    m = re.search(r"interac\s+purchase[\s,\-]*(?:\d{3,}\s*)?(.*)$", desc, re.I)
    return (m.group(1) if m else desc).strip(" ,-")


def type_row(ws, acc, desc, amt, when):
    """(type, label, ask) for one ledger row. `ask` is a decisions.json item when the row was
    typed by default rather than by evidence; None otherwise. Blank type means: a program cannot
    tell, the model will."""
    d = desc.upper()
    dn = re.sub(r"[^A-Z0-9]", "", d)
    own = re.sub(r"[^A-Z0-9]", "", ws.owner)
    broker_n = re.sub(r"[^A-Z0-9]", "", ws.broker.upper())
    cp_first = (ws.cp or "").split()[0].upper() if ws.cp else None

    if "INTERACPURCHASE" in dn or "CONTACTLESS" in dn or "POSPURCHASE" in dn or "DEBITCARDPURCHASE" in dn:
        return "Debit purchase", "Debit purchase — " + merchant_key(merchant_of_debit(desc)).title(), None
    # An e-Transfer says so with its hyphen; "OnlineTransfer" contains the letters ETRANSFER and
    # is a bank's own transfer (the first run typed a card payment as one, 2026-09-14).
    if "INTERAC" in dn or re.search(r"E-TRANSFER", d):
        received = amt > 0
        if own and own in dn:
            return "Transfer", "e-Transfer between your own accounts", None
        if received and ws.cp_rows:
            for r in ws.cp_rows:
                if (r.get("direction") == "in" and abs(float(r.get("amount") or 0) - amt) < 0.01
                        and (r.get("date") or "")[:7] == when[:7]):
                    return "Repayment", f"e-Transfer from {ws.cp} (repayment)", None
        if cp_first and cp_first in dn:
            return ("Repayment", f"e-Transfer from {ws.cp} (repayment)", None) if received \
                else ("Repayment", f"e-Transfer to {ws.cp} (loan)", None)
        if received:
            return "Other", "e-Transfer received", {
                "kind": "transfer", "what": f"A {money(amt)} e-Transfer received on {short(iso_to_date(when))} carries no sender you have named.",
                "default": "Other income"}
        return "Transfer", "e-Transfer sent", {
            "kind": "transfer", "what": f"A {money(-amt)} e-Transfer sent on {short(iso_to_date(when))} went to someone you have not named.",
            "default": "Transfer"}
    if broker_n and (broker_n in dn or "WSINVESTMENT" in dn or "WSIMPLE" in dn):
        return "Transfer", f"Transfer {'to' if amt < 0 else 'from'} {ws.broker}", None
    if amt > 0 and ("PAYROLL" in dn or ("PAY" in dn and "DEPOSIT" in dn)):
        return "Payroll", "Payroll deposit", None
    for card in ws.cards:
        cd = digits(card.get("id"))
        if cd and cd in dn and amt < 0:
            return "CC payment", f"{card['name']} payment", None
    if "AUTOPAY" in dn or (("VISA" in dn or "MASTERCARD" in dn) and "PAYMENT" in dn):
        return "CC payment", "Card payment", None
    if "TRANSFER" in dn:
        for other in ws.bank_accts:
            od = digits(other.get("id"))
            if other is not acc and od and od in dn:
                return "Transfer", f"Transfer {'to' if amt < 0 else 'from'} {other['name'].lower()}", None
    if amt < 0 and ("RENT" in dn or any(abs(-amt - r) < 0.01 for r in ws.rent)):
        return "Rent", "Rent", None
    if "FEE" in dn:
        return "Fee", "", None
    if "INTEREST" in dn:
        return "Interest", "", None
    return "", "", None


# ---------------------------------------------------------------- categorising a purchase
def categorise(ws, merchant, table):
    """(category, how): 'hit' reuses merchants.json, 'brand' reuses the one category every entry
    of the same first word carries, 'new' is a merchant nobody has decided — Other meanwhile."""
    key = merchant_key(merchant)
    if key in table:
        return table[key]["category"], "hit", key
    if len(ws.row_cats.get(key, ())) == 1:
        return next(iter(ws.row_cats[key])), "rows", key
    first = key.split()[0] if key else ""
    kin = {e["category"] for k, e in table.items() if first and k.split()[0] == first}
    if len(kin) == 1:
        return kin.pop(), "brand", key
    return NEW_MERCHANT_CATEGORY, "new", key


# ---------------------------------------------------------------- the plan
class Plan:
    def __init__(self):
        self.ledger = collections.defaultdict(list)     # ledger file -> rows to append
        self.spend = []                                 # spending.csv rows to append
        self.bank = {}                                  # register name -> (balance, asof, is_debt)
        self.filed = collections.defaultdict(set)       # doc key -> months
        self.archive = []                               # (src, dst)
        self.delete = []                                # true duplicates
        self.merchant_seen = collections.Counter()      # key -> count
        self.merchant_dates = {}                        # key -> (first, last)
        self.new_merchants = collections.OrderedDict()  # key -> (category, source)
        self.cat_used = {}                              # key -> the category its rows got
        self.decisions = []
        self.judged = []
        self.by_hand = []
        self.stopped = []
        self.unknown = []
        self.untyped = []
        self.credits = []
        self.files = []                                 # sentences, the way the owner knows them
        self.holdings = None                            # (src path, asof)
        self.activities = None
        self.friend = None
        self.counts = collections.Counter()


def classify_inbox(ws, plan):
    preflight.DOCS = preflight.load_docs(ws.root)
    label_to_doc = {f"{d['ep']} {d['key']}": d for d in ws.docs}
    named = []
    files = preflight.scan(os.path.join(ws.root, "inbox"))
    by_hash = collections.defaultdict(list)
    for f in files:
        by_hash[preflight.sha(f["path"])].append(f)
    for h, group in by_hash.items():
        labels = {preflight.classify(os.path.basename(f["name"]))[0] for f in group}
        if len(group) > 1 and len(labels) == 1:
            for f in group[1:]:
                plan.delete.append(f["path"])
            group = group[:1]
        elif len(group) > 1:
            plan.stopped.append(f"{' == '.join(os.path.basename(f['name']) for f in group)} are identical but classify as "
                                f"different documents ({' / '.join(sorted(str(l) for l in labels))}); one of them never arrived")
            continue
        f = group[0]
        label, _acct, into, note = preflight.classify(os.path.basename(f["name"]))
        if not label:
            doc = name_by_contents(ws, plan, f["path"])
            if doc is None and os.path.basename(f["name"]) in plan.hand:
                key = plan.hand[os.path.basename(f["name"])].get("doc")
                doc = next((d for d in ws.docs if d.get("key") == key), None)
                if doc is None:
                    plan.stopped.append(f"{os.path.basename(f['name'])}: the transcription names document {key!r}, which is not in the register")
                    continue
            if doc is None:
                plan.unknown.append((os.path.basename(f["name"]), note))
                continue
            named.append((f["path"], doc))
            continue
        if label.startswith("Screenshot:"):
            plan.by_hand.append((os.path.basename(f["name"]), "a screenshot of an account held abroad: read the balances off the image into foreign.json"))
            continue
        named.append((f["path"], label_to_doc[label]))
    return named


def name_by_contents(ws, plan, path):
    """A PDF whose name says nothing — an RBC download arrives as `20260819.pdf` — is named by
    the statement itself: every parser is offered the file (the way setup drafts the register),
    and the one that reads it and reconciles says which account. Still never the filename."""
    if not path.lower().endswith(".pdf"):
        return None
    hits = []
    for name in PARSERS:
        try:
            res = parse_file(path, name)
        except ParseError:
            continue
        if not res["reconcile"]["ok"]:
            continue
        parts = res.get("accounts") or [res]
        acct_digits = (parts[0].get("account") or "")[-4:]
        for doc in ws.docs:
            if doc.get("parser") != name or not acct_digits:
                continue
            acc = ws.by_key.get((doc.get("covers") or [None])[0])
            if acc and digits(acc.get("id")).endswith(acct_digits):
                hits.append(doc)
    if len(hits) != 1:
        return None
    plan.judged.append(f"{os.path.basename(path)} carried no account in its name; the statement itself says it is "
                       f"the {ws.doc_name(hits[0])} statement.")
    return hits[0]


def plan_statement(ws, plan, path, doc):
    name = os.path.basename(path)
    res = None
    if doc.get("parser"):
        try:
            res = parse_file(path, doc["parser"])
        except ParserUnavailable:
            raise
        except ParseError as e:
            if name not in plan.hand:
                plan.by_hand.append((name, f"{doc['parser']}: {e}"))
                return
        if res is not None and not res["reconcile"]["ok"] and name not in plan.hand:
            plan.by_hand.append((name, "does not reconcile: " + res["reconcile"]["detail"]))
            return
    if res is None or not res["reconcile"]["ok"]:
        if name not in plan.hand:
            plan.by_hand.append((name, f"no parser reads a {ws.doc_name(doc)} statement; transcribe it and hand the rows back with --hand"))
            return
        res = hand_result(ws, plan, doc, plan.hand[name])
        if res is None:
            return
        plan.judged.append(f"The {ws.doc_name(doc)} statement to {short(iso_to_date(res['period']['to']))} was read by eye and transcribed; "
                           f"the rows add up to what it prints.")
    parts = res.get("accounts") or [res]
    end = iso_to_date(parts[0]["period"]["to"])
    tag = doc["tags"][0]
    dst = os.path.join(ws.root, "archive", f"{stamp(end)}_{tag}_{name}")
    redrop = os.path.exists(dst)
    if redrop:
        base, ext = os.path.splitext(dst)
        dst = f"{base} (redrop){ext}"
    plan.archive.append((path, dst))
    filed_any = False
    for part in parts:
        acc = ws.account_for(doc, part.get("account"))
        if not acc:
            plan.by_hand.append((name, f"the statement says account …{part.get('account')}, which matches no account at {doc.get('ep')}"))
            continue
        pdoc = ws.doc_for_account(acc["key"]) or doc
        into = pdoc.get("into")
        p_end = iso_to_date(part["period"]["to"])
        month = p_end.strftime("%Y-%m")
        if into == "spending.csv":
            n = plan_card(ws, plan, acc, pdoc, part, p_end)
        elif into == "banks.json":
            n = 0
        else:
            n = plan_ledger(ws, plan, acc, pdoc, part, p_end)
            if n is None:
                continue                      # the chain does not follow: nothing from this part
        closing = part.get("closing")
        if closing is not None:
            plan.bank[acc["name"]] = (round(float(closing), 2), p_end.isoformat(), acc.get("side") == "liability")
        plan.filed[pdoc["key"]].add(month)
        filed_any = True
        plan.counts["statements"] += 1
        plan.files.append(f"{ws.doc_name(pdoc)} statement to {short(p_end)}" + (" (again)" if redrop else ""))
    if not filed_any:
        plan.archive.pop()


def hand_result(ws, plan, doc, h):
    """A statement the model transcribed, held to the same reconciliation a parser is: the
    balance chain has to run from the printed opening to the printed closing, and the debits and
    credits have to add up to whatever totals the statement prints. What does not add up is not
    written — it is a transcription error, and the model is told which."""
    try:
        rows = [{"date": r["date"], "description": str(r["description"]).strip(),
                 "amount": round(float(r["amount"]), 2),
                 "balance": (round(float(r["balance"]), 2) if r.get("balance") is not None else None)}
                for r in h["rows"]]
        period = {"from": h["period"]["from"], "to": h["period"]["to"]}
        iso_to_date(period["from"]); iso_to_date(period["to"])
        for r in rows:
            iso_to_date(r["date"])
    except (KeyError, TypeError, ValueError) as e:
        plan.stopped.append(f"{h.get('file')}: the transcription is not in the shape update.py reads ({e})")
        return None
    opening = h.get("opening"); closing = h.get("closing")
    totals = h.get("totals") or {}
    problems = []
    bad_dates = [r["date"] for r in rows if not (period["from"] <= r["date"] <= period["to"])]
    if bad_dates:
        problems.append(f"{len(bad_dates)} row(s) dated outside {period['from']}..{period['to']}")
    if doc.get("into") not in ("spending.csv",) and opening is not None:
        bal = round(float(opening), 2)
        for r in rows:
            if r["balance"] is None:
                r["balance"] = round(bal + r["amount"], 2)
            elif abs(r["balance"] - (bal + r["amount"])) > 0.005:
                problems.append(f"{r['date']} {r['description'][:30]!r}: balance {r['balance']:,.2f} is not {bal:,.2f} {r['amount']:+,.2f}")
                break
            bal = r["balance"]
        if closing is not None and abs(bal - float(closing)) > 0.005 and not problems:
            problems.append(f"the rows end at {bal:,.2f} but the statement closes at {float(closing):,.2f}")
    debits = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
    credits = round(sum(r["amount"] for r in rows if r["amount"] > 0), 2)
    for k, v in ((("deducted", "purchases", "withdrawals"), debits), (("added", "credits", "deposits"), credits)):
        printed = next((totals[x] for x in k if totals.get(x) is not None), None)
        if printed is not None and abs(abs(float(printed)) - v) > 0.005:
            problems.append(f"the rows' {k[0]} come to {v:,.2f} but the statement prints {abs(float(printed)):,.2f}")
    ok = not problems
    detail = "; ".join(problems) if problems else f"{len(rows)} rows transcribed; chain and totals agree"
    if not ok:
        plan.stopped.append(f"{h.get('file')} ({ws.doc_name(doc)}): the transcription does not add up — {detail}")
        return None
    return {"parser": "hand", "file": h.get("file"), "account": str(h.get("account") or "")[-4:] or None,
            "period": period, "opening": opening, "closing": closing, "rows": rows, "totals": totals,
            "reconcile": {"rule": "transcribed by eye; chain and printed totals must agree", "ok": True, "detail": detail}}


def plan_ledger(ws, plan, acc, doc, part, end):
    ledger = acc.get("ledger")
    if not ledger:
        return 0
    existing = csv_rows(ws.fd(ledger))
    tag = f"{acc['stmtTag']}/{stamp(end)}"
    if any(r.get("statement") == tag for r in existing):
        plan.judged.append(f"The {ws.doc_name(doc)} statement to {short(end)} was already in the books; nothing was written twice.")
        return 0
    rows = part["rows"]
    if not rows:
        return 0
    last = existing[-1] if existing else None
    if last is not None:
        opening = round(float(rows[0]["balance"]) - float(rows[0]["amount"]), 2) if rows[0].get("balance") is not None \
            else (round(float(part["opening"]), 2) if part.get("opening") is not None else None)
        if opening is not None and abs(opening - float(last["balance"])) > 0.005:
            plan.stopped.append(f"{ws.doc_name(doc)} statement to {short(end)} opens at {opening:,.2f} but the ledger "
                                f"closes at {float(last['balance']):,.2f} on {last['date']} — a statement in between is missing")
            return None
        if rows[0]["date"] < last["date"]:
            plan.stopped.append(f"{ws.doc_name(doc)} statement to {short(end)} starts {rows[0]['date']}, before the ledger's "
                                f"last row {last['date']}")
            return None
    bal = float(part["opening"]) if part.get("opening") is not None else (float(last["balance"]) if last else 0.0)
    table = {e["match"]: e for e in ws.merchants.get("merchants", [])}
    src = f"{ws.doc_name(doc)} statement to {short(end)}"
    for r in rows:
        amt = round(float(r["amount"]), 2)
        bal = round(float(r["balance"]), 2) if r.get("balance") is not None else round(bal + amt, 2)
        t, label, ask = type_row(ws, acc, r["description"], amt, r["date"])
        if ask:
            ask.update(source=f"{src}, {short(iso_to_date(r['date']))}")
            plan.decisions.append(ask)
        if not t:
            plan.untyped.append((ledger, r["date"], r["description"], amt))
        plan.ledger[ledger].append([r["date"], r["description"], f"{amt:.2f}", f"{bal:.2f}", tag, t, label])
        if t == "Debit purchase" and acc.get("spendTag"):
            merchant = merchant_of_debit(r["description"])
            cat, how, key = categorise(ws, merchant, table)
            note_merchant(plan, key, cat, how, r["date"], src)
            plan.spend.append([r["date"], f"{-amt:.2f}", acc.get("cur", "CAD"), cat,
                               f"{merchant} (debit) [{acc['spendTag']}/{stamp(end)}]"])
    plan.counts["ledger rows"] += len(rows)
    return len(rows)


def plan_card(ws, plan, acc, doc, part, end):
    existing = csv_rows(ws.fd("spending.csv"))
    tagend = f"[{acc['spendTag']}/{stamp(end)}]"
    if any(r["note"].rstrip().endswith(tagend) for r in existing):
        plan.judged.append(f"The {ws.doc_name(doc)} statement to {short(end)} was already in the books; nothing was written twice.")
        return 0
    table = {e["match"]: e for e in ws.merchants.get("merchants", [])}
    src = f"{ws.doc_name(doc)} statement to {short(end)}"
    n = 0
    for r in part["rows"]:
        amt = round(float(r["amount"]), 2)
        desc = r["description"].strip()
        if amt >= 0:
            if re.search(r"PAYMENT|THANK YOU|AUTOPAY|TRSF FROM|TRANSFER FROM", desc, re.I):   # a card payment, not a refund
                continue
            plan.credits.append((src, r["date"], desc, amt))
            continue
        cat, how, key = categorise(ws, desc, table)
        note_merchant(plan, key, cat, how, r["date"], src)
        plan.spend.append([r["date"], f"{-amt:.2f}", acc.get("cur", "CAD"), cat, f"{desc} {tagend}"])
        n += 1
    plan.counts["purchases"] += n
    return n


def note_merchant(plan, key, cat, how, when, src):
    plan.merchant_seen[key] += 1
    plan.cat_used[key] = cat
    f, l = plan.merchant_dates.get(key, (when, when))
    plan.merchant_dates[key] = (min(f, when), max(l, when))
    if how == "new" and key not in plan.new_merchants:
        plan.new_merchants[key] = (cat, src)
        plan.decisions.append({"kind": "merchant", "what": f"{key}, seen for the first time.",
                               "default": cat, "source": f"{src}, {short(iso_to_date(when))}"})
    elif how == "brand" and key not in plan.new_merchants:
        plan.new_merchants[key] = (cat, src)
        plan.judged.append(f"Filed {key} as {cat}, like the other {key.split()[0]} charges.")
    elif how == "rows" and key not in plan.new_merchants:
        plan.new_merchants[key] = (cat, src)
        plan.judged.append(f"Filed {key} as {cat}, as its earlier charges were.")


def plan_export(ws, plan, path, doc):
    name = os.path.basename(path)
    into = doc.get("into")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    asof = m.group(1) if m else datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    dst = os.path.join(ws.root, "archive", f"{asof.replace('-', '')}_{doc['tags'][0]}_{name}")
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = f"{base} (redrop){ext}"
    plan.archive.append((path, dst))
    plan.filed[doc["key"]].add(asof[:7])
    if into == "holdings_latest.csv":
        plan.holdings = (path, asof)
        plan.files.append(f"Holdings report of {short(iso_to_date(asof))}")
    elif into == "ws_activities.csv":
        plan.activities = (path, asof)
        plan.files.append(f"Activities export of {short(iso_to_date(asof))}")
    elif doc.get("counterparty"):
        plan.friend = (path, asof)
        plan.files.append(f"{doc['counterparty']}'s ledger of {short(iso_to_date(asof))}")
    else:
        plan.by_hand.append((name, f"lands in {into}, which nothing here knows how to write; transcribe it and hand the rows back with --hand"))
        plan.archive.pop()


# ---------------------------------------------------------------- writing it
def write_plan(ws, plan):
    fd = ws.fd
    layout.ensure(ws.root)
    for ledger, rows in plan.ledger.items():
        p = fd(ledger)
        new = not os.path.exists(p) or os.path.getsize(p) == 0
        with open(p, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(LEDGER_COLS)
            w.writerows(rows)
    if plan.spend:
        p = fd("spending.csv")
        new = not os.path.exists(p) or os.path.getsize(p) == 0
        with open(p, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(SPEND_COLS)
            w.writerows(sorted(plan.spend, key=lambda r: (r[0], r[4])))
    # merchants.json: hits are counted, misses appended — the one place a category is decided.
    if plan.merchant_seen:
        table = {e["match"]: e for e in ws.merchants.setdefault("merchants", [])}
        for key, n in plan.merchant_seen.items():
            f, l = plan.merchant_dates[key]
            if key in table:
                e = table[key]
                e["seen"] = int(e.get("seen") or 0) + n
                e["first"] = min(e.get("first") or f, f)
                e["last"] = max(e.get("last") or l, l)
            else:
                ws.merchants["merchants"].append({"match": key, "category": plan.cat_used.get(key, NEW_MERCHANT_CATEGORY),
                                                  "seen": n, "first": f, "last": l})
        ws.merchants["merchants"].sort(key=lambda e: e["match"])
        jsave(fd("merchants.json"), ws.merchants)
    # banks.json and the register's copies of it
    for name, (bal, asof, is_debt) in plan.bank.items():
        for side in ("assets", "debts"):
            for x in ws.banks.get(side, []):
                if x.get("account") == name and (not x.get("asof") or x["asof"] <= asof):
                    x["balance"], x["asof"] = bal, asof
        for a in ws.accounts:
            if a.get("src") == "banks.json" and a.get("name") == name and (not a.get("asof") or a["asof"] <= asof):
                a["balance"], a["asof"] = (-bal if is_debt else bal), asof
    if plan.bank:
        jsave(fd("banks.json"), ws.banks)
    if plan.friend:
        shutil.copy2(plan.friend[0], fd(next(d["into"] for d in ws.docs if d.get("counterparty"))))
    if plan.activities:
        merge_activities(ws, plan.activities[0])
    if plan.holdings:
        shutil.copy2(plan.holdings[0], fd("holdings_latest.csv"))
        refresh_holdings_copies(ws, plan.holdings[1])
    if plan.bank or plan.holdings:
        jsave(fd("accounts.json"), ws.reg)
    for key, months in plan.filed.items():
        have = ws.filings.setdefault("filed", {}).setdefault(key, [])
        ws.filings["filed"][key] = sorted(set(have) | months)
    if plan.filed:
        jsave(fd("filings.json"), ws.filings)
    if plan.decisions:
        for d in plan.decisions:
            ws.decisions.setdefault("decisions", []).append(
                {"added": ws.today.isoformat(), "kind": d["kind"], "what": d["what"], "default": d["default"],
                 "source": d.get("source", ""), "status": "open"})
        jsave(fd("decisions.json"), ws.decisions)
    os.makedirs(os.path.join(ws.root, "archive"), exist_ok=True)
    for src, dst in plan.archive:
        shutil.move(src, dst)
    for p in plan.delete:
        os.remove(p)


def merge_activities(ws, src):
    p = ws.fd("ws_activities.csv")
    have = []
    header = None
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd, None)
            have = [r for r in rd if r]
    with open(src, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        new_header = next(rd, None)
        new = [r for r in rd if r]
    if header and new_header and header != new_header:
        raise SystemExit(f"the activities export's columns differ from ws_activities.csv: {new_header[:4]}…")
    seen = {tuple(r) for r in have}
    added = [r for r in new if tuple(r) not in seen]
    rows = sorted(have + added, key=lambda r: (r[0], r[1]))
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header or new_header)
        w.writerows(rows)
    # fx.json from the newest 'FX Rate:' row — the broker's own rate, spread included
    rates = [(r[0], float(m.group(1))) for r in rows for m in [re.search(r"FX Rate:\s*([\d.]+)", r[7] if len(r) > 7 else "")] if m]
    if rates:
        d, rate = max(rates)
        fx = jload(ws.fd("fx.json"), {})
        if fx.get("asof") != d or abs(float(fx.get("usd_cad") or 0) - rate) > 1e-9:
            if fx.get("asof"):
                fx.setdefault("history", []).append({"usd_cad": fx.get("usd_cad"), "asof": fx["asof"]})
            fx.update(usd_cad=rate, asof=d, quality="broker-rate",
                      source=f"Broker activities export {os.path.basename(src)}: the 'FX Rate:' rows on the latest date. It is the broker's rate, spread included.")
            jsave(ws.fd("fx.json"), fx)


def refresh_holdings_copies(ws, asof):
    """The register's balance for every account the holdings export values, and the funds'
    backing — copies D14 and D13 re-derive from the export every run."""
    fx = jload(ws.fd("fx.json"), {}).get("usd_cad")
    bal = collections.defaultdict(float)
    for r in csv_rows(ws.fd("holdings_latest.csv")):
        n, mv, cur = r.get("Account Number"), r.get("Market Value"), r.get("Market Value Currency")
        if not n or not mv:
            continue
        v = float(mv)
        if cur == "USD":
            if fx is None:
                continue
            v *= fx
        bal[n] += v
    for a in ws.accounts:
        if a.get("src") == "holdings_latest.csv" and a.get("id") in bal:
            a["balance"], a["asof"] = round(bal[a["id"]], 2), asof
    changed = False
    for f in ws.funds.get("funds", []):
        b = f.get("backing") or {}
        if b.get("account") in bal:
            b["balance"], b["asof"] = round(bal[b["account"]]), asof
            changed = True
    if changed:
        jsave(ws.fd("funds.json"), ws.funds)


# ---------------------------------------------------------------- what the update leaves behind
def derive(root):
    return rebuild.derive(rebuild.load(root))


def spending_by_month(root):
    out = collections.defaultdict(float)
    for r in csv_rows(layout.path(root, "spending.csv")):
        out[r["date"][:7]] += float(r["amount"])
    return out


def write_history(ws, out):
    inv = out["INVEST"]
    fgn = out.get("FOREIGN") or {}
    hp = ws.fd("investment_history.json")
    hist = jload(hp, {"note": "One snapshot per 'update dashboards'.", "snapshots": []})
    tickers = len({r.get("Symbol") for r in csv_rows(ws.fd("holdings_latest.csv"))
                   if r.get("Symbol") and r.get("Symbol") != "CAD"
                   and r.get("Account Number") in {a["id"] for a in ws.accounts if a.get("role") == "grow"}})
    snap = {"date": inv.get("asof") or ws.today.isoformat(), "cadInv": round(inv["investable"], 2),
            "dry": round(inv["dryCad"], 2), "dryPct": inv["dryPct"], "tickers": tickers,
            "foreign": inv.get("foreignFunds") or None, "fx": inv.get("fx")}
    snaps = hist.setdefault("snapshots", [])
    if snaps and snaps[-1].get("date") == snap["date"]:
        snaps[-1] = snap
    else:
        snaps.append(snap)
    jsave(hp, hist)
    np_ = ws.fd("networth_history.json")
    nw = jload(np_, {"note": "One net-worth point per month.", "snapshots": []})
    total = fgn.get("total") or 0
    per = fgn.get("cadPerUnit") or 0
    v = inv["netWorth"] + (round(total * per) if total and per else 0)
    ym = snap["date"][:7]
    pts = nw.setdefault("snapshots", [])
    if pts and pts[-1].get("ym") == ym:
        pts[-1]["v"] = v
    elif not pts or pts[-1]["ym"] < ym:
        pts.append({"ym": ym, "v": v})
    jsave(np_, nw)


def changed_lines(before, after, sp_before, sp_after):
    out = []
    b, a = before["INVEST"], after["INVEST"]
    if b["netWorth"] != a["netWorth"]:
        out.append({"label": "Net worth", "from": money(b["netWorth"]), "to": money(a["netWorth"])})
    if b["dryPct"] != a["dryPct"]:
        out.append({"label": "Dry powder", "from": f"{b['dryPct']}%", "to": f"{a['dryPct']}%"})
    if b["holdings"] != a["holdings"]:
        out.append({"label": "Holdings", "from": b["holdings"], "to": a["holdings"]})
    for ym in sorted(set(sp_after) | set(sp_before)):
        if round(sp_before.get(ym, 0)) != round(sp_after.get(ym, 0)):
            d = datetime.date(int(ym[:4]), int(ym[5:]), 1)
            out.append({"label": f"Spending in {LONG[d.month - 1]}", "from": money(sp_before.get(ym, 0)), "to": money(sp_after.get(ym, 0))})
    return out


def noticed_lines(ws, out, plan):
    inv, rules = out["INVEST"], jload(ws.fd("rules.json"), {})
    lines = []
    for bkt in rules.get("buckets", []):
        if bkt.get("target") and bkt.get("key") == "dry":
            lo, hi = bkt["target"]
            ok = lo <= inv["dryPct"] <= hi
            lines.append({"sev": "ok" if ok else "warn",
                          "text": f"Dry powder is {inv['dryPct']}%, {'inside' if ok else 'outside'} your {lo}–{hi}% band."
                                  + ("" if ok else " Rebalance when you next add money.")})
    cap = rules.get("maxHoldings")
    if cap:
        ok = inv["holdings"] <= cap
        lines.append({"sev": "ok" if ok else "warn",
                      "text": f"{inv['holdings']} holdings, {'inside' if ok else 'over'} your limit of {cap}."
                              + ("" if ok else " Pick one to let go before the next buy.")})
    dep = out.get("WSDEP") or []
    ym = (ws.today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    last = next((d for d in dep if d["ym"] == ym), None)
    half = round(rebuild.flow_totals(ws.funds["plan"])["invest"] / 2, 2)
    if last:
        mon = LONG[int(ym[5:]) - 1]
        if last["nRule"] >= 2:
            lines.append({"sev": "ok", "text": f"{mon} kept the rule: {last['nRule']} deposits of {money(half)} reached the broker."})
        else:
            lines.append({"sev": "warn", "text": f"{mon} shows {money(last['amt'])} reaching the broker against the {money(half * 2)} you planned. Move the rest when you can."})
    allowance = rebuild.flow_totals(ws.funds["plan"]).get("allowance")
    sp = spending_by_month(ws.root)
    if allowance and sp:
        m = max(sp)
        mon = LONG[int(m[5:]) - 1]
        over = sp[m] > allowance
        lines.append({"sev": "warn" if over else "ok",
                      "text": f"Purchases in {mon} come to {money(sp[m])} against the {money(allowance)} allowance."
                              + (" Some of it may be a big buy; say so and it moves." if over else "")})
    for g in ws.reg.get("gaps", []):
        if g.get("sev") in ("warn", "bad"):
            lines.append({"sev": g["sev"], "text": f"{g.get('what', '')}. {g.get('fix', '')}".strip()})
    for a in ws.accounts:
        if a.get("src") == "banks.json" and a.get("asof") and a.get("kind") != "Savings":
            age = (ws.today - iso_to_date(a["asof"])).days
            if age > 45:
                lines.append({"sev": "warn", "text": f"The {a['inst']} {a['name']} statement is {age} days old. The next one is ready to download."})
    return lines


def record(ws, plan, changed, noticed):
    asked = [d["what"] + f" Filed as {d['default']} meanwhile." for d in plan.decisions]
    for name, why in plan.by_hand:
        asked.append(f"{name} needs a pair of eyes: {why}.")
    for ledger, d, desc, amt in plan.untyped:
        asked.append(f"What the {money(abs(amt))} on {short(iso_to_date(d))} ({desc[:40]}) was.")
    rec = {"date": ws.today.isoformat(), "files": plan.files, "changed": changed, "noticed": noticed,
           "judged": plan.judged, "asked": asked}
    ws.imports.setdefault("imports", []).append(rec)
    jsave(ws.fd("imports.json"), ws.imports)
    return rec


def run(script, args, root):
    p = subprocess.run([sys.executable, script] + args, cwd=root, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


# ---------------------------------------------------------------- main
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--write", action="store_true", help="apply; without it, only say what would happen")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--hand", help="JSON of statements the model read and transcribed (see above)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    ws = Workspace(root)
    plan = Plan()
    plan.hand = {}
    if a.hand:
        try:
            for h in json.load(open(a.hand, encoding="utf-8")):
                plan.hand[os.path.basename(h["file"])] = h
        except (ValueError, KeyError, TypeError, OSError) as e:
            print(f"  ✗ --hand {a.hand}: not a list of transcriptions ({e})"); return 1
    summary = {"date": ws.today.isoformat(), "written": False}

    named = classify_inbox(ws, plan)
    try:
        for path, doc in named:
            if doc.get("parser") or (doc.get("into") or "").endswith(".csv") and doc.get("into") != "friend_ledger.csv" \
                    and doc.get("into") not in ("holdings_latest.csv", "ws_activities.csv") and not doc.get("counterparty") \
                    or doc.get("into") == "banks.json":
                plan_statement(ws, plan, path, doc)
            else:
                plan_export(ws, plan, path, doc)
    except ParserUnavailable as e:
        print(f"  ✗ {e}. Nothing can be parsed: pip3 install --user pypdf, then run again.")
        return 3

    say = print if not a.json else (lambda *x, **k: None)
    say(f"=== update — {len(named)} file(s) named in inbox/, {len(plan.unknown)} unnamed ===\n")
    for src, dst in plan.archive:
        say(f"  {os.path.basename(src)}  →  archive/{os.path.basename(dst)}")
    for k, v in sorted(plan.counts.items()):
        say(f"  {v} {k}")
    if plan.spend:
        say(f"  {len(plan.spend)} purchases → spending.csv; {len(plan.new_merchants)} merchant(s) not seen before")
    for name, why in plan.by_hand:
        say(f"  · by hand: {name} — {why}")
    for ledger, d, desc, amt in plan.untyped:
        say(f"  · untyped: {ledger} {d} {desc[:40]!r} {amt:,.2f}")
    for j in plan.judged:
        say(f"  · {j}")
    for d in plan.decisions:
        say(f"  ? {d['what']} (filed as {d['default']} meanwhile)")
    for src, d, desc, amt in plan.credits:
        say(f"  · credit not filed: {src} {d} {desc[:40]!r} {amt:,.2f}")

    stop = plan.unknown or plan.stopped
    if plan.unknown:
        say("\n  --- STOP: files nobody can name ---")
        for name, note in plan.unknown:
            say(f"  ✗ {name}: {note}")
    if plan.stopped:
        say("\n  --- STOP ---")
        for s in plan.stopped:
            say(f"  ✗ {s}")
    summary.update(files=plan.files, by_hand=plan.by_hand, unknown=plan.unknown, stopped=plan.stopped,
                   untyped=plan.untyped, asked=[d["what"] for d in plan.decisions], judged=plan.judged,
                   credits=plan.credits, counts=dict(plan.counts))
    if stop:
        say("\n  Nothing written. Ask the owner, then run again.")
        if a.json:
            print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 1
    if not (plan.archive or plan.delete):
        say("  nothing to import.")
        if a.json:
            print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if not a.write:
        say("\n  Nothing written. Re-run with --write to apply.")
        if a.json:
            print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0

    before, sp_before = derive(root), spending_by_month(root)
    write_plan(ws, plan)
    after, sp_after = derive(root), spending_by_month(root)
    write_history(ws, after)
    after = derive(root)
    changed = changed_lines(before, after, sp_before, sp_after)
    noticed = noticed_lines(ws, after, plan)
    rec = record(ws, plan, changed, noticed)
    summary.update(written=True, changed=changed, noticed=noticed, record=rec)

    rc, out = run(os.path.join(HERE, "rebuild.py"), [".", "--write"], root)
    say("\n  rebuild: " + (out.strip().splitlines()[-1].strip() if out.strip() else f"exit {rc}"))
    findings = []
    for script, args in (("check_data.py", ["."]), ("check_design.py", [rebuild_page(root)])):
        rc2, out2 = run(os.path.join(CHECKS, script), args, root)
        findings += [l.strip() for l in out2.splitlines() if l.strip().startswith(("✗", "⚠"))]
    summary["findings"] = findings
    run(os.path.join(HERE, "preflight.py"), [".", "--reseed"], root)
    say("")
    for c in changed:
        say(f"  {c['label']}: {c['from']} → {c['to']}")
    for n in noticed:
        say(f"  {'✓' if n['sev'] == 'ok' else '!'} {n['text']}")
    if findings:
        say("\n  the checkers found:")
        for f in findings:
            say("  " + f)
    else:
        say("\n  ✓ checkers clean")
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 2 if any(f.startswith("✗") for f in findings) else 0


def rebuild_page(root):
    for n in ("finance_dashboard.html", "ly_finance_dashboard.html"):
        if os.path.exists(os.path.join(root, "dashboards", n)):
            return os.path.join("dashboards", n)
    return os.path.join("dashboards", "finance_dashboard.html")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
