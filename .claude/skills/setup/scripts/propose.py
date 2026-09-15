#!/usr/bin/env python3
"""propose.py — draft the setup answers from the first files the owner dropped.

    python3 .claude/skills/setup/scripts/propose.py .              # read inbox/, show the draft
    python3 .claude/skills/setup/scripts/propose.py . --write      # ... and write it
    python3 .claude/skills/setup/scripts/propose.py . --json       # the draft as JSON, on stdout

The setup used to be about thirty questions typed into an answers file by hand, in a shape only
the scaffold knew — the first real clone (2026-09-11) hit eight bugs in that path. But the first
month's files already hold most of the answers: a statement says which bank, which account, what
kind, what it closed at and on which day; a holdings export lists every account at the broker.
This reads them and drafts `findata/register/setup-answers.json` in the scaffold's shape, with

  - `_proposed`: where every drafted value came from (statement, export, default), so the owner
    confirms a table instead of typing it; and
  - `_open`: the questions the files cannot answer (who you are, how often you are paid, what an
    account is for when the default would be wrong, anything held abroad). The scaffold refuses
    to run while any is left — a draft is not an answer.

Files are identified by their CONTENT, never their name: every PDF is offered to every parser and
the one that reads it wins; a CSV is recognised by its columns. Nothing is written without
--write, and even then only the answers file: findata/ itself is still written by the scaffold,
after the owner has confirmed.
"""
import argparse
import collections
import csv
import datetime
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SKILLS, "update-dashboard"))
sys.path.insert(0, os.path.join(SKILLS, "update-dashboard", "scripts"))
import layout  # noqa: E402
import scaffold  # noqa: E402  default_axes and the kinds the tool understands
from parsers import NAMES, ParseError, ParserUnavailable, parse  # noqa: E402

IGNORE = {"README.txt", ".gitkeep", ".DS_Store"}
IMAGES = (".png", ".jpg", ".jpeg", ".heic", ".webp")
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
# A parser's name says whose layout it reads; that is the institution the statement came from.
INST_OF_PARSER = {"rbc": "RBC", "bmo": "BMO"}
# Broker exports are recognised by their column set. These two are the column sets the tool's
# broker reads (rebuild.py reads holdings_latest.csv and ws_activities.csv in exactly this shape).
EXPORTS = {
    "holdings": {"inst": "Wealthsimple", "cols": {"Account Name", "Account Type", "Account Number",
                                                  "Symbol", "Market Value", "Market Value Currency"},
                 "into": "holdings_latest.csv", "reconcile": "positions replace the previous snapshot"},
    "activities": {"inst": "Wealthsimple", "cols": {"account_id", "account_type", "activity_type",
                                                    "net_cash_amount", "effective_date"},
                   "into": "ws_activities.csv", "reconcile": "also refresh fx.json from the 'FX Rate:' rows"},
}
# Generic words, not anyone's employer: a credit whose description carries one is pay.
PAY = re.compile(r"\b(PAY|PAYROLL|PYRL|SALARY|WAGES)\b")
DEBIT_PURCHASE = re.compile(r"INTERAC PURCHASE|CONTACTLESS INTERAC|POINT OF SALE|DEBIT PURCHASE|POS PURCHASE", re.I)
CARD_CREDIT = re.compile(r"PAYMENT|TRSF FROM|CASHBACK|REMISES", re.I)
BIG = 300


def pattern_of(name):
    """The bank's own filename with its date taken out: 'Chequing Statement-2306 2026-08-25.pdf'
    -> 'Chequing Statement-2306 <date>.pdf', 'August 5, 2026-2.pdf' -> '<Month D, YYYY>-2.pdf'.
    That pattern is how preflight will recognise next month's file."""
    stem, ext = os.path.splitext(name)
    s = re.sub(MONTH + r" \d{1,2}, \d{4}", "<Month D, YYYY>", stem)
    s = re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", s)
    s = re.sub(r"(?<!\d)20\d{6}(?!\d)", "<date>", s)
    return s + ext


def date_in_name(name):
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", name)
    if not m:
        return None
    g = [x for x in m.groups() if x]
    return f"{g[0]}-{g[1]}-{g[2]}"


def money(v):
    if v is None:
        return "—"
    return ("-" if v < 0 else "") + f"${abs(v):,.2f}"


def read_statement(path):
    """Offer the PDF to every parser; the first that reads it wins. (result, None) or (None, why)."""
    last = None
    for name in NAMES:
        try:
            return parse(path, name), None
        except ParseError as e:
            last = str(e)
    return None, last or "no parser reads this layout"


def sniff_csv(path):
    with open(path, encoding="utf-8-sig") as fh:
        header = set(next(csv.reader(fh), []))
    for kind, spec in EXPORTS.items():
        if spec["cols"] <= header:
            return kind
    return None


def propose(root, inbox):
    files = sorted(f for f in os.listdir(inbox) if f not in IGNORE and not f.startswith("."))
    seen = []                       # what each file was read as, for the report
    stmts = {}                      # (inst, digits) -> the newest statement of that account
    first = {}                      # (inst, digits) -> the earliest month seen
    holdings = activities = None
    images, unknown, by_hand = [], [], []
    for f in files:
        p = os.path.join(inbox, f)
        low = f.lower()
        if low.endswith(".pdf"):
            try:
                res, why = read_statement(p)
            except ParserUnavailable:
                by_hand.append(f)
                seen.append((f, "a PDF", "pypdf is not installed — it will be read by hand"))
                continue
            if not res:
                unknown.append(f)
                seen.append((f, "a PDF no parser reads", why))
                continue
            for part in (res.get("accounts") or [res]):
                inst = INST_OF_PARSER.get(part["parser"].split("_")[0], part["parser"])
                k = (inst, part["account"])
                part = dict(part, _file=f, _inst=inst)
                if k not in stmts or part["period"]["to"] > stmts[k]["period"]["to"]:
                    stmts[k] = part
                first[k] = min(first.get(k, part["period"]["to"][:7]), part["period"]["to"][:7])
                seen.append((f, f"{part['parser']}", f"{inst} {part.get('product') or part['kind']} …{part['account']}, "
                             f"to {part['period']['to']}, {'reconciled' if part['reconcile']['ok'] else 'DOES NOT reconcile'}"))
        elif low.endswith(".csv"):
            kind = sniff_csv(p)
            if kind == "holdings":
                holdings = (f, list(csv.DictReader(open(p, encoding="utf-8-sig"))))
                seen.append((f, "broker holdings export", f"{len({r['Account Number'] for r in holdings[1] if r.get('Account Number')})} accounts"))
            elif kind == "activities":
                activities = (f, list(csv.DictReader(open(p, encoding="utf-8-sig"))))
                seen.append((f, "broker activities export", f"{len(activities[1])} rows"))
            else:
                unknown.append(f)
                seen.append((f, "a CSV", "columns match no export the tool reads"))
        elif low.endswith(IMAGES):
            images.append(f)
            seen.append((f, "a screenshot", "read with you — balances abroad, usually"))
        else:
            unknown.append(f)
            seen.append((f, "unknown", "not a statement, export or screenshot"))

    accounts, proposed, questions = [], {}, []
    def src(field, how):
        proposed[field] = how

    # --- the exchange rate first: the holdings export's USD positions need it
    fx, fx_note = None, None
    if activities:
        by_day = collections.defaultdict(list)
        for r in activities[1]:
            m = re.search(r"FX Rate: ([\d.]+)", r.get("description", ""))
            if m:
                by_day[r["effective_date"]].append(float(m.group(1)))
        if by_day:
            day = max(by_day)
            fx = round(statistics.median(by_day[day]), 4)
            fx_note = f"median of {len(by_day[day])} 'FX Rate:' rows on {day}"
    # --- accounts from the statements
    holders = collections.Counter()
    payroll_key, pay_amounts = None, []
    # Within a bank: chequing, then savings, then cards — the order an owner thinks of them in.
    KORDER = {"Chequing": 0, "Savings": 1, "Credit card": 2}
    for (inst, digits), s in sorted(stmts.items(), key=lambda kv: (kv[0][0], KORDER.get(kv[1].get("kind"), 3), kv[0][1])):
        kind = s.get("kind") or "Chequing"
        name = s.get("product") or f"{kind} {digits}"
        card = kind in scaffold.DEBT_KINDS
        rows = s["rows"]
        pays = [r["amount"] for r in rows if r["amount"] > 0 and PAY.search(r["description"].upper())]
        debit = any(DEBIT_PURCHASE.search(r["description"]) for r in rows)
        ledger = None if card or kind != "Chequing" else re.sub(r"\W+", "_", f"{inst}_{kind}_{digits}").lower() + ".csv"
        if s.get("holder"):
            holders[s["holder"]] += 1
        acc = {"inst": inst, "name": name, "kind": kind, "id": "…" + digits, "cur": "CAD",
               "balance": -s["closing"] if card and s["closing"] is not None else s["closing"],
               "asof": s["period"]["to"], "feeds": "Spending" if card else ("Cash flow" if ledger else "")}
        if ledger:
            acc["ledger"] = ledger
            if debit:
                acc["feeds"] += ", Spending"
        acc["doc"] = {"file": pattern_of(s["_file"]), "closes": int(s["period"]["to"][8:]),
                      "from": first[(inst, digits)], "parser": s["parser"],
                      "into": "spending.csv" if card else (ledger or "banks.json"),
                      "reconcile": s["reconcile"]["rule"] if (card or ledger) else "balance and as-of only"}
        acc.update({k: v for k, v in scaffold.default_axes({**acc, "src": "banks.json"}).items() if k in ("role", "reach")})
        if pays and len(pays) >= len(pay_amounts):
            payroll_key, pay_amounts = len(accounts), pays
        accounts.append(acc)
        src(f"accounts.{name}", f"statement {s['_file']} ({s['parser']}, {'reconciled' if s['reconcile']['ok'] else 'NOT reconciled'})")
    if payroll_key is not None:
        a = accounts[payroll_key]
        a["feeds"] = "Income, " + (a["feeds"] or "Cash flow")

    # --- accounts from the broker's exports
    broker_names = []
    if holdings:
        f, rows = holdings
        tot, meta = collections.OrderedDict(), {}
        for r in rows:
            n = r.get("Account Number")
            if not n:
                continue
            mv = float(r.get("Market Value") or 0) * ((fx or 1.0) if r.get("Market Value Currency") == "USD" else 1.0)
            tot[n] = tot.get(n, 0.0) + mv
            meta.setdefault(n, (r.get("Account Name", "").strip(), r.get("Account Type", "").strip()))
        used = {a["name"] for a in accounts}
        for n, v in tot.items():
            nick, typ = meta[n]
            kind = typ if typ in scaffold.INVEST_KINDS else "Investment"
            name = nick if nick and nick.isascii() else (typ or "Investment")
            if name in used:
                name = f"{name} {n[-4:]}"
            used.add(name)
            acc = {"inst": EXPORTS["holdings"]["inst"], "name": name, "kind": kind, "id": n, "cur": "CAD",
                   "balance": round(v, 2), "asof": date_in_name(f), "feeds": ""}
            if nick and nick != name:
                acc["seenAs"] = nick            # the owner's own nickname, shown so they recognise it
            ax = scaffold.default_axes({**acc, "src": "holdings_latest.csv"})
            acc.update({k: ax[k] for k in ("role", "reach")})
            if "saving" in (nick or "").lower() and acc["role"] == "grow":
                acc["role"], acc["reach"] = "set-aside", "spoken"
                src(f"accounts.{name}.role", "its name says savings — set aside, outside the portfolio (confirm)")
            accounts.append(acc)
            broker_names.append(name)
            src(f"accounts.{name}", f"holdings export {f}")
        month = (date_in_name(f) or datetime.date.today().isoformat())[:7]
        accounts[len(accounts) - len(tot)]["doc"] = {
            "key": "Holdings", "file": pattern_of(f), "closes_label": "any time", "from": month,
            "into": EXPORTS["holdings"]["into"], "reconcile": EXPORTS["holdings"]["reconcile"],
            "alsoCovers": broker_names[1:]}
    cash_asked = []
    if activities:
        f, rows = activities
        known = {a["id"] for a in accounts}
        extra = collections.OrderedDict()
        for r in rows:
            if r.get("account_id") and r["account_id"] not in known:
                extra.setdefault(r["account_id"], r.get("account_type", "").strip())
        month = (date_in_name(f) or datetime.date.today().isoformat())[:7]
        host = None
        for n, typ in extra.items():
            kind = "Chequing" if "chequ" in typ.lower() else "Savings"
            name = typ or kind
            acc = {"inst": EXPORTS["activities"]["inst"], "name": name, "kind": kind, "id": n,
                   "cur": "USD" if n.endswith("USD") or "usd" in typ.lower() else "CAD",
                   "balance": None, "asof": date_in_name(f), "feeds": ""}
            ax = scaffold.default_axes({**acc, "src": "banks.json"})
            acc.update({k: ax[k] for k in ("role", "reach")})
            accounts.append(acc)
            cash_asked.append(name)
            src(f"accounts.{name}", f"activities export {f} (it names the account but carries no balance)")
            host = host or acc
        host = host or next((a for a in accounts if a["inst"] == EXPORTS["activities"]["inst"] and "doc" not in a), None)
        if host is not None:
            others = [a["name"] for a in accounts if a["inst"] == EXPORTS["activities"]["inst"] and a is not host]
            host["doc"] = {"key": "Activities", "file": pattern_of(f), "closes_label": "any time", "from": month,
                           "into": EXPORTS["activities"]["into"], "reconcile": EXPORTS["activities"]["reconcile"],
                           "alsoCovers": others}

    # --- the plan
    plan = {"bigThreshold": BIG}
    src("plan.bigThreshold", "default: a single purchase of $300 or more is a big buy")
    if pay_amounts:
        per = collections.Counter(round(x, 2) for x in pay_amounts).most_common(1)[0][0]
        plan["takeHome"] = round(per * 2)
        plan["takeHomeNote"] = f"Payroll of {money(per)}, twice a month."
        src("plan.takeHome", f"{len(pay_amounts)} payroll deposit(s) of {money(per)} on {accounts[payroll_key]['inst']} {accounts[payroll_key]['name']} — assumed twice a month")
        questions.append({"id": "pay", "q": f"Your payroll deposit is {money(per)}. Paid twice a month — take-home {money(per * 2)} a month?",
                          "suggest": plan["takeHome"]})
    else:
        questions.append({"id": "pay", "q": "No payroll deposit in these statements. What is your take-home pay a month?"})
    if activities:
        dep = collections.defaultdict(list)
        for r in activities[1]:
            if (r.get("activity_type") == "MoneyMovement" and r.get("activity_sub_type") == "EFT"
                    and "chequ" in (r.get("account_type") or "").lower() and r.get("currency") == "CAD"):
                a = float(r.get("net_cash_amount") or 0)
                if a > 0:
                    dep[r["effective_date"][:7]].append(a)
        newest = max((r["effective_date"][:7] for r in activities[1]), default="")
        done = [m for m in sorted(dep) if m < newest] or sorted(dep)
        if done:
            m = done[-1]
            plan["invest"] = round(sum(dep[m]))
            src("plan.invest", f"{len(dep[m])} transfer(s) reached the broker in {m}: " + ", ".join(money(x) for x in dep[m]))
            questions.append({"id": "invest", "q": f"In {m}, {' + '.join(money(x) for x in dep[m])} reached your broker. "
                                                  f"Is {money(plan['invest'])} a month your standing investment?", "suggest": plan["invest"]})
    if "invest" not in plan:
        questions.append({"id": "invest", "q": "How much do you move to your broker each month?"})
    spend = 0.0
    for (inst, digits), s in stmts.items():
        if (s.get("kind") or "") in scaffold.DEBT_KINDS:
            spend += sum(-r["amount"] for r in s["rows"] if r["amount"] < 0 and -r["amount"] < BIG
                         and not CARD_CREDIT.search(r["description"]))
    if spend:
        plan["everyday"] = int(round(spend / 50.0) * 50)
        src("plan.everyday", f"{money(spend)} of card purchases under {money(BIG)} on the newest statements, rounded")
        questions.append({"id": "everyday", "q": f"Your cards show {money(spend)} of everyday spending this month. "
                                                 f"Set the guilt-free allowance at {money(plan['everyday'])}?",
                          "suggest": plan["everyday"]})
    else:
        questions.append({"id": "everyday", "q": "What everyday allowance a month — the guilt-free line, no categories under it?"})
    questions.append({"id": "committed", "q": "Anything paid every month before you choose anything — rent, a mortgage, a loan? "
                                              "And rent you do not pay now but will after FIRE?"})
    questions.append({"id": "planBase", "q": "Your planning spend for the FIRE target, a month, rent after FIRE included?",
                      "suggest": plan.get("everyday")})
    plan["planBase"] = plan.get("everyday")
    questions.append({"id": "funds", "q": "Anything you are saving towards — a trip, big purchases? A name, a goal, a date. (None is fine.)"})

    # --- the investing rule
    grow_ids = {a["id"] for a in accounts if a.get("role") == "grow"}
    tickers = sorted({r["Symbol"] for r in (holdings[1] if holdings else [])
                      if r.get("Symbol") and r.get("Security Type") != "CURRENCY" and r.get("Account Number") in grow_ids})
    rules = {"buckets": [{"key": "rest", "name": "Holdings", "catchAll": True}], "maxHoldings": len(tickers) or 10}
    if tickers:
        src("rules", f"{len(tickers)} holdings in the invested accounts; one bucket, no target range, by default")
        questions.append({"id": "buckets", "q": f"You hold {len(tickers)}: {', '.join(tickers)}. Group them into buckets, and does one "
                                                f"have a target range? And how many holdings do you want at most?"})

    # --- the rest, which no file carries
    holder = holders.most_common(1)[0][0] if holders else None
    questions.insert(0, {"id": "owner", "q": (f"Your statements say {holder}. " if holder else "") +
                                             "What name should show under Jade Toad?",
                         "suggest": holder.title() if holder else None})
    questions.insert(1, {"id": "born", "q": "Roughly what year were you born? (Only the retirement-age arithmetic uses it.)"})
    questions.insert(2, {"id": "accounts", "q": f"Is the accounts table right? Change a name, a kind, what an account is for, "
                                                f"or which ones keep a line-by-line ledger."})
    questions.insert(3, {"id": "missing", "q": "Any account these files do not show — savings with no statement this month, "
                                               "a loan, a home, an account abroad?"})
    if cash_asked:
        questions.insert(4, {"id": "cash", "q": f"What balance does the app show for {', '.join(cash_asked)}? The exports name "
                                                f"{'them' if len(cash_asked) > 1 else 'it'} but carry no balance."})
    others = [r for s in stmts.values() for r in s["rows"]
              if r["amount"] > 0 and "e-transfer" in r["description"].lower()
              and not (holder and holder.replace(" ", "") in r["description"].upper().replace(" ", ""))]
    if others:
        questions.append({"id": "counterparty", "q": "e-Transfers came in from someone else ("
                          + ", ".join(f"{money(r['amount'])} on {r['date']}" for r in others[:4])
                          + "). Is anyone paying you back a loan? Their payments are never counted as income."})
    questions.append({"id": "foreign", "q": (f"You dropped {len(images)} screenshot(s). " if images else "") +
                                            "Anything held in another currency? The bank, the balance, the currency and today's rate."})
    if unknown or by_hand:
        questions.append({"id": "files", "q": "These files were not recognised: " + ", ".join(unknown + by_hand) +
                                              ". What are they?"})

    answers = {"owner": None, "born": None, "currency": "CAD", "importDay": 26,
               "accounts": accounts, "plan": plan, "funds": [], "rules": rules,
               "foreign": None, "fx": fx or 1.0,
               "_proposed": proposed, "_open": questions,
               "_files": [{"file": f, "read_as": w, "detail": d} for f, w, d in seen]}
    src("importDay", "default: the 26th")
    if fx:
        src("fx", fx_note)
    return answers


def report(a):
    out = [f"=== setup draft — {len(a['_files'])} file(s) read from inbox/", "", "FILES"]
    for x in a["_files"]:
        out.append(f"  {x['file'][:44]:44}  {x['read_as']:26}  {x['detail']}")
    out += ["", f"ACCOUNTS ({len(a['accounts'])})",
            f"  {'bank':13} {'name':24} {'kind':15} {'number':15} {'balance':>13} {'as of':11} {'for':10} {'reach':7} ledger"]
    for x in a["accounts"]:
        out.append(f"  {x['inst'][:13]:13} {(x['name'] + (' ('+x['seenAs']+')' if x.get('seenAs') else ''))[:24]:24} "
                   f"{x['kind'][:15]:15} {x['id'][:15]:15} {money(x['balance']):>13} {str(x['asof'] or '—'):11} "
                   f"{x.get('role') or '—':10} {x.get('reach') or '—':7} {'yes' if x.get('ledger') else '—'}")
    docs = [(x, x["doc"]) for x in a["accounts"] if x.get("doc")]
    out += ["", f"MONTHLY FILES ({len(docs)})"]
    for x, d in docs:
        out.append(f"  {d.get('file', '')[:44]:44}  closes {str(d.get('closes') or d.get('closes_label')):9} "
                   f"{d.get('parser') or '—':15} → {d['into']}")
    out += ["", "PLAN"]
    for k in ("takeHome", "invest", "everyday", "bigThreshold"):
        if k in a["plan"]:
            out.append(f"  {k:13} {money(a['plan'][k]):>11}   {a['_proposed'].get('plan.' + k, '')}")
    out += ["", f"QUESTIONS ({len(a['_open'])}) — the scaffold will not run until every one is answered"]
    for i, q in enumerate(a["_open"], 1):
        out.append(f"  {i:2}. {q['q']}" + (f"  [suggested: {q['suggest']}]" if q.get("suggest") not in (None, "") else ""))
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--inbox", help="where the first files are (default: <root>/inbox)")
    ap.add_argument("--write", action="store_true", help="write findata/register/setup-answers.json")
    ap.add_argument("--json", action="store_true", help="print the draft as JSON instead of the report")
    args = ap.parse_args(argv[1:])
    root = os.path.abspath(args.root)
    inbox = os.path.abspath(args.inbox or os.path.join(root, "inbox"))
    if not os.path.isdir(inbox):
        print(f"  ✗ no inbox at {inbox}"); return 1
    a = propose(root, inbox)
    if args.json:
        print(json.dumps(a, ensure_ascii=False, indent=1))
    else:
        print(report(a))
    if args.write:
        dst = os.path.join(root, layout.rel("setup-answers.json"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump(a, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        if not args.json:
            print(f"\n  → {os.path.relpath(dst, root)} (a draft: answer the questions, then run scaffold.py)")
    elif not args.json:
        print("\n  nothing written. Re-run with --write to save the draft.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
