#!/usr/bin/env python3
"""fixtures.py — synthetic statements, in the text shapes the parsers know, from a workspace's
own ledgers.

    python3 tools/fixtures.py <workspace> <outdir>        # writes the PDFs, prints a manifest

A parser is only worth trusting if something exercises it, and the real statements can never
enter the repository. So the demo owner's ledgers are rendered back into statements — one PDF
per statement tag, laid out line for line the way pypdf reads the real ones — and the parsers
have to read them and reconcile. The manifest says, per file, which parser, how many rows and
what the closing figure is, so the selftest can hold the parser to it. Real PDFs regress only
inside an owner's workspace (selftest runs the parsers over archive/ there).

Every layout here is the text a real statement of that kind produces, minus the boilerplate:
a fixture that drifted from the real shape would prove nothing, so change one only against a
fresh extraction of the real thing.
"""
import csv
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdfgen import write_pdf  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                ".claude", "skills", "update-dashboard", "scripts"))
import layout  # noqa: E402

MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LONG = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December")


def d(s):
    return datetime.date.fromisoformat(s)


def money(v, dollar=False):
    s = f"{abs(v):,.2f}"
    if v < 0:
        return ("- $" if dollar else "- ") + s
    return ("$" if dollar else "") + s


def long_date(dt):
    return f"{LONG[dt.month - 1]} {dt.day}, {dt.year}"


# ---------------------------------------------------------------- the four layouts
def rbc_banking(acct_digits, start, end, opening, rows, owner):
    dep = sum(r["amount"] for r in rows if r["amount"] > 0)
    wd = -sum(r["amount"] for r in rows if r["amount"] < 0)
    closing = round(opening + dep - wd, 2)
    head = ["1 of 1", "Royal Bank of Canada", "Your RBC personal banking", "account statement",
            f"From {long_date(start)} to {long_date(end)}",
            f"Your account number: 03652-50{acct_digits}", owner.upper(),
            "Summary of your account for this period",
            f"Your opening balance on {long_date(start)} {money(opening, True)}",
            f"Total deposits into your account + {money(dep)}",
            f"Total withdrawals from your account - {money(wd)}",
            f"Your closing balance on {long_date(end)} = {money(closing, True)}",
            "Details of your account activity",
            "Date Description Withdrawals ($) Deposits ($) Balance ($)",
            f"Opening Balance {money(opening)}"]
    body, last_day = [], None
    for i, r in enumerate(rows):
        day = r["date"]
        prefix = f"{d(day).day} {MON[d(day).month - 1]} " if day != last_day else ""
        last_day = day
        # The real statement prints a balance on the last row of each day only.
        last_of_day = i + 1 == len(rows) or rows[i + 1]["date"] != day
        line = f"{prefix}{r['description']} {money(abs(r['amount']))}"
        if last_of_day:
            line += f" {money(r['balance'])}"
        body.append(line)
    tail = [f"Closing Balance {money(closing, True)}",
            "Please check this Account Statement without delay and advise us of any error or omission within 45 days."]
    return [head + body + tail]


def bmo_banking(name, acct_digits, start, end, opening, rows, owner):
    out = -sum(r["amount"] for r in rows if r["amount"] < 0)
    inn = sum(r["amount"] for r in rows if r["amount"] > 0)
    closing = round(opening + inn - out, 2)
    number = f"0006 3874-{acct_digits[-3:]}"
    head = ["Page 1 of 1", "Everyday Banking", owner.upper(), "Your Everyday Banking statement",
            f"For the period ending {LONG[end.month - 1]} {end.day:02d}, {end.year}",
            "Summary of your account", "Total Total Closing", "Opening amounts amounts balance ($) on",
            f"Account balance ($) deducted ($) added ($) {MON[end.month - 1]} {end.day:02d}, {end.year}",
            f"{name} Account", f"# {number} {money(opening)} {money(out)} {money(inn)} {money(closing)}",
            "Here's what happened in your account", "Amounts deducted Amounts added",
            "Date Description from your account ($) to your account ($) Balance ($)",
            f"{name} Account # {number}", "Owner:", owner.upper(),
            f"{MON[start.month - 1]} {start.day:02d} Opening balance {money(opening)}"]
    body = [f"{MON[d(r['date']).month - 1]} {d(r['date']).day:02d} {r['description']} "
            f"{money(abs(r['amount']))} {money(r['balance'])}" for r in rows]
    tail = [f"{MON[end.month - 1]} {end.day:02d} Closing totals {money(out)} {money(inn)}",
            "Please report any errors, omissions or irregularities in writing within 30 days of the statement date."]
    return [head + body + tail]


def rbc_visa(last4, start, end, previous, rows, owner):
    purchases = round(sum(r["amount"] for r in rows), 2)
    credits = previous
    new = round(previous + purchases - credits, 2)
    up = lambda dt: f"{MON[dt.month - 1].upper()} {dt.day:02d}"
    period = (f"STATEMENT FROM {up(start)}, {start.year} TO {up(end)}, {end.year}" if start.year != end.year
              else f"STATEMENT FROM {up(start)} TO {up(end)}, {end.year}")
    head = [owner.upper(), "Cash Back RBC Visa", f"{owner.upper()}  4510 15** **** {last4}", period,
            f"PREVIOUS ACCOUNT BALANCE {money(previous, True)} IMPORTANT INFORMATION",
            "CALCULATING YOUR BALANCE", f"Previous Account Balance {money(previous, True)}",
            f"Payments & credits -{money(credits, True)}", f"Purchases & debits {money(purchases, True)}",
            "Cash advances $0.00", "Interest $0.00", "Fees $0.00",
            f"Total Account Balance {money(new, True)}", f"NEW BALANCE {money(new, True)}",
            "TRANSACTION", "DATE", "POSTING", "DATE ACTIVITY DESCRIPTION AMOUNT ($)"]
    body = []
    if previous:
        pay = start + datetime.timedelta(days=5)
        body.append(f"{up(pay)} {up(pay)} PAYMENT - THANK YOU / PAIEMENT - MERCI -{money(previous, True)}")
    for i, r in enumerate(rows):
        dt = d(r["date"]); post = dt + datetime.timedelta(days=1)
        body += [f"{up(dt)} {up(post)} {r['description']}", f"7408342{dt.strftime('%y%j')}{i:011d}",
                 money(r["amount"], True)]
    tail = [f"TOTAL ACCOUNT BALANCE {money(new, True)}", "INTEREST RATE CHART"]
    return [head + body + tail]


def bmo_mastercard(last4, start, end, previous, rows, owner):
    purchases = round(sum(r["amount"] for r in rows), 2)
    credits = previous
    new = round(previous + purchases - credits, 2)
    ds = lambda dt: f"{MON[dt.month - 1]}. {dt.day}"
    head = ["BMO CashBack Mastercard", "Summary of your account",
            f"Previous total balance, {ds(start - datetime.timedelta(days=1))}, {start.year} {money(previous, True)}",
            f"Payments and credits -{money(credits)}", f"Purchases and other charges +{money(purchases)}",
            "New installments 0.00", "Cash advances1 0.00", "Total interest charges 0.00", "Fees 0.00",
            f"Total balance {money(new, True)}", owner, f"Card number XXXX XXXX XXXX {last4}",
            f"Statement date {ds(end)}, {end.year}", f"Statement period {ds(start)}, {start.year} - {ds(end)}, {end.year}",
            "Transactions since your last statement", "TRANS", "DATE", "POSTING", "DATE DESCRIPTION AMOUNT ($)",
            f"Card number: XXXX XXXX XXXX {last4}    {owner.upper()}"]
    body = []
    if previous:
        pay = start + datetime.timedelta(days=6)
        body.append(f"{ds(pay)} {ds(pay)} TRSF FROM/DE ACCT/CPT    0006-XXXX-471 {money(previous)} CR")
    for r in rows:
        dt = d(r["date"]); post = dt + datetime.timedelta(days=1)
        body.append(f"{ds(dt)} {ds(post)} {r['description']:<25} OTTAWA       ON {money(r['amount'])}")
    tail = [f"Subtotal for {owner.upper()} {money(purchases)}",
            f"Total for card number XXXX XXXX XXXX {last4} {money(new, True)}"]
    return [head + body + tail]


# ---------------------------------------------------------------- from a workspace
def build(ws, outdir):
    fd = lambda n: layout.path(ws, n)
    reg = json.load(open(fd("accounts.json"), encoding="utf-8"))
    owner = json.load(open(fd("profile.json"), encoding="utf-8")).get("owner", "Owner")
    by_key = {a["key"]: a for a in reg["accounts"]}
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for doc in reg.get("documents", []):
        parser = doc.get("parser")
        if not parser:
            continue
        acc = by_key.get((doc.get("covers") or [None])[0])
        if not acc:
            continue
        digits = re.sub(r"\D", "", acc.get("id") or "") or "0000"
        if acc.get("ledger") and acc.get("stmtTag"):
            rows = list(csv.DictReader(open(fd(acc["ledger"]), encoding="utf-8")))
            tags = sorted({r["statement"] for r in rows if r.get("statement")})
            prev_end = None
            for tag in tags:
                sel = [r for r in rows if r["statement"] == tag]
                end = d(f"{tag[-8:-4]}-{tag[-4:-2]}-{tag[-2:]}")
                start = prev_end + datetime.timedelta(days=1) if prev_end else d(sel[0]["date"]) - datetime.timedelta(days=1)
                opening = round(float(sel[0]["balance"]) - float(sel[0]["amount"]), 2)
                srows = [{"date": r["date"], "description": r["description"], "amount": float(r["amount"]),
                          "balance": float(r["balance"])} for r in sel]
                if parser == "rbc_banking":
                    pages = rbc_banking(digits[-4:], start, end, opening, srows, owner)
                elif parser == "bmo_banking":
                    pages = bmo_banking(acc["name"], digits, start, end, opening, srows, owner)
                else:
                    continue
                path = os.path.join(outdir, f"{tag.replace('/', '_')}.pdf")
                write_pdf(path, pages)
                manifest.append({"file": path, "parser": parser, "doc": doc["key"], "rows": len(srows),
                                 "closing": srows[-1]["balance"], "opening": opening})
                prev_end = end
        elif acc.get("spendTag"):
            sp = list(csv.DictReader(open(fd("spending.csv"), encoding="utf-8")))
            tag_re = re.compile(r"\[" + re.escape(acc["spendTag"]) + r"/(\d{8})\]\s*$")
            by_tag = {}
            for r in sp:
                m = tag_re.search(r["note"])
                if m:
                    by_tag.setdefault(m.group(1), []).append(r)
            prev_end, previous = None, 0.0
            for tag in sorted(by_tag):
                sel = by_tag[tag]
                end = d(f"{tag[:4]}-{tag[4:6]}-{tag[6:]}")
                start = prev_end + datetime.timedelta(days=1) if prev_end else end - datetime.timedelta(days=30)
                srows = [{"date": r["date"], "description": tag_re.sub("", r["note"]).strip(),
                          "amount": float(r["amount"])} for r in sel]
                if parser == "rbc_visa":
                    pages = rbc_visa(digits[-4:], start, end, previous, srows, owner)
                elif parser == "bmo_mastercard":
                    pages = bmo_mastercard(digits[-4:], start, end, previous, srows, owner)
                else:
                    continue
                path = os.path.join(outdir, f"{acc['spendTag']}_{tag}.pdf")
                write_pdf(path, pages)
                purchases = round(sum(r["amount"] for r in srows), 2)
                manifest.append({"file": path, "parser": parser, "doc": doc["key"],
                                 "rows": len(srows) + (1 if previous else 0), "closing": purchases,
                                 "opening": previous})
                prev_end, previous = end, purchases
    return manifest


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    m = build(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]))
    print(json.dumps(m, indent=1))
