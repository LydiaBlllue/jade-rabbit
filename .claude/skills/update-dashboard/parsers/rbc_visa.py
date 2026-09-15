"""RBC Visa statements (Avion, Cash Back, Signature Rewards — one layout).

What the text looks like once pypdf has read it:

    STATEMENT FROM JUL 21 TO AUG 19, 2026
    EMMA ROY  4510 15** **** 3306
    Payments & credits -$968.18
    Purchases & debits $927.92
    Interest $0.00
    Fees $0.00
    NEW BALANCE $37.51
    JUL 25 JUL 27 WL *STEAM PURCHASE 425-889-9642 WA      <- transaction date, posting date, merchant
    24011346207100002795626                                  <- reference number, its own line
    $20.84                                                   <- the amount, its own line
    AUG 10 AUG 10 AUTOMATIC PAYMENT -THANK YOU -$77.77       <- or all on one line, no reference

A purchase is positive on the statement and money out of the owner's pocket, so it is written
NEGATIVE the ledger's way; a payment or credit (-$) is positive. Reconciled against the two
totals the statement prints: purchases & debits + fees + interest on one side, payments &
credits on the other.
"""
import re

from ._pdf import AMOUNT, ParseError, clean_product, date_in_period, long_date, money, month_no, result, text_lines

NAME = "rbc_visa"
RULE = "parsed purchases = Purchases & debits + Fees + Interest; parsed credits = Payments & credits"
TXN = re.compile(r"^([A-Z]{3}) (\d{2}) ([A-Z]{3}) (\d{2}) (.*?)(?:\s+(-?\$[\d,]+\.\d{2}))?\s*$")
AMT_LINE = re.compile(r"^(-?\$[\d,]+\.\d{2})$")
REF_LINE = re.compile(r"^\d{15,}$")


def parse(path):
    lines = text_lines(path)
    text = "\n".join(lines)
    # "STATEMENT FROM JUL 21 TO AUG 19, 2026", or with both years when the period crosses one:
    # "STATEMENT FROM DEC 20, 2025 TO JAN 19, 2026".
    m = re.search(r"STATEMENT FROM ([A-Z]{3}) (\d{1,2})(?:, (\d{4}))? TO ([A-Z]{3}) (\d{1,2}), (\d{4})", text)
    if not m:
        raise ParseError("no 'STATEMENT FROM ... TO ...' line; not an RBC Visa statement")
    year = int(m.group(6))
    end = long_date(f"{m.group(4)} {m.group(5)}, {year}")
    sm = month_no(m.group(1))
    sy = int(m.group(3)) if m.group(3) else (year - 1 if sm > end.month else year)
    start = long_date(f"{m.group(1)} {m.group(2)}, {sy}")
    card = re.search(r"\*\*\*\* (\d{4})", text)
    account = card.group(1) if card else None

    def grab(label):
        mm = re.search(r"^" + label + r"\s+(" + AMOUNT + r")\s*$", text, re.M)
        return money(mm.group(1)) if mm else None
    totals = {"purchases": grab(r"Purchases & debits"), "credits": grab(r"Payments & credits"),
              "interest": grab(r"Interest"), "fees": grab(r"Fees"), "new_balance": grab(r"NEW BALANCE"),
              "previous": grab(r"Previous Account Balance")}
    if totals["purchases"] is None or totals["new_balance"] is None:
        raise ParseError("the CALCULATING YOUR BALANCE block was not found")

    rows, open_row = [], None
    for l in lines:
        tm = TXN.match(l)
        if tm:
            if open_row is not None:
                raise ParseError(f"transaction without an amount: {open_row['description']!r}")
            date = date_in_period(month_no(tm.group(1)), int(tm.group(2)), start, end)
            row = {"date": date, "description": tm.group(5).strip(), "amount": None, "balance": None,
                   "posted": date_in_period(month_no(tm.group(3)), int(tm.group(4)), start, end)}
            if tm.group(6):
                row["amount"] = -money(tm.group(6))
                rows.append(row)
            else:
                open_row = row
            continue
        if open_row is not None:
            if REF_LINE.match(l):
                open_row["reference"] = l
                continue
            am = AMT_LINE.match(l)
            if am:
                open_row["amount"] = -money(am.group(1))
                rows.append(open_row)
                open_row = None
                continue
            # A merchant name that wrapped onto a second line.
            open_row["description"] = (open_row["description"] + " " + l).strip()
    if open_row is not None:
        raise ParseError(f"transaction without an amount: {open_row['description']!r}")
    debits = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
    credits = round(sum(r["amount"] for r in rows if r["amount"] > 0), 2)
    want_d = round((totals["purchases"] or 0) + (totals["fees"] or 0) + (totals["interest"] or 0), 2)
    want_c = round(-(totals["credits"] or 0), 2)
    ok = abs(debits - want_d) < 0.005 and abs(credits - want_c) < 0.005
    detail = (f"{len(rows)} rows; purchases {debits:,.2f} vs statement {want_d:,.2f}; "
              f"credits {credits:,.2f} vs statement {want_c:,.2f}; new balance {totals['new_balance']:,.2f}")
    pm = next((m for m in (re.match(r"^(?!STATEMENT)(.*\bVisa\b.*)$", l) for l in lines[:15]) if m), None)
    hm = re.search(r"^([A-Z][A-Z .'-]+?)\s+\d{4} \d{2}\*\* \*\*\*\* \d{4}", text, re.M)
    return result(NAME, path, account, start, end, rows, totals, RULE, ok, detail,
                  totals["previous"], totals["new_balance"],
                  clean_product(pm.group(1), 'RBC') if pm else None,
                  hm.group(1).strip() if hm else None, "Credit card")
