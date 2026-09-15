"""BMO Mastercard statements (CashBack and the rest — one layout).

What the text looks like once pypdf has read it:

    Statement period Jul. 21, 2026 - Aug. 20, 2026
    Card number XXXX XXXX XXXX 5518
    Payments and credits -515.49
    Purchases and other charges +757.45
    Total interest charges 0.00
    Fees 0.00
    Total balance $541.70
    Transactions since your last statement
    Jul. 21 Jul. 22 FARM BOY                 OTTAWA       ON 4.49 CR     <- CR = money in
    Jul. 21 Jul. 22 FARM BOY                 OTTAWA       ON 92.28
    Aug. 16 Aug. 17 COSTCO WHOLESALE W1105   OTTAWA                    <- a row can wrap:
    ON                                                                  <- province, then
    3.15                                                                <- the amount, alone
    Subtotal for EMMA ROY 656.96

A purchase is written NEGATIVE the ledger's way; a payment or a credit (CR) is positive.
Reconciled against the summary: purchases + interest + fees on one side, payments and credits
on the other.
"""
import re

from ._pdf import AMOUNT, ParseError, clean_product, date_in_period, long_date, money, month_no, result, text_lines

NAME = "bmo_mastercard"
RULE = "parsed purchases = Purchases and other charges + interest + Fees; parsed credits = Payments and credits"
TXN = re.compile(r"^([A-Z][a-z]{2})\. (\d{1,2}) ([A-Z][a-z]{2})\. (\d{1,2}) (.*?)(?:\s+(\d{1,3}(?:,\d{3})*\.\d{2})( CR)?)?\s*$")
AMT_LINE = re.compile(r"^(\d{1,3}(?:,\d{3})*\.\d{2})( CR)?$")


def parse(path):
    lines = text_lines(path)
    text = "\n".join(lines)
    pm = re.search(r"Statement period ([A-Za-z]+\.? \d{1,2}, \d{4}) - ([A-Za-z]+\.? \d{1,2}, \d{4})", text)
    if not pm:
        raise ParseError("no 'Statement period' line; not a BMO Mastercard statement")
    start, end = long_date(pm.group(1)), long_date(pm.group(2))
    card = re.search(r"Card number:? X+ X+ X+ (\d{4})", text)
    account = card.group(1) if card else None

    def grab(label):
        mm = re.search(r"^" + label + r"\s*([+-]?\$?[\d,]+\.\d{2})\s*$", text, re.M)
        return money(mm.group(1).replace("+", "")) if mm else None
    totals = {"purchases": grab(r"Purchases and other charges"), "credits": grab(r"Payments and credits"),
              "interest": grab(r"Total interest charges"), "fees": grab(r"Fees"),
              "total_balance": grab(r"Total balance"), "previous": grab(r"Previous total balance,? [A-Za-z]+\.? \d{1,2}, \d{4}")}
    if totals["purchases"] is None or totals["total_balance"] is None:
        raise ParseError("the summary block was not found")

    try:
        a = next(i for i, l in enumerate(lines) if l.startswith("Transactions since your last statement"))
    except StopIteration:
        raise ParseError("no 'Transactions since your last statement' table")
    rows, open_row = [], None
    for l in lines[a + 1:]:
        if l.startswith("Subtotal for") or l.startswith("Total for card number"):
            break
        tm = TXN.match(l)
        if tm:
            if open_row is not None:
                raise ParseError(f"transaction without an amount: {open_row['description']!r}")
            date = date_in_period(month_no(tm.group(1)), int(tm.group(2)), start, end)
            row = {"date": date, "description": re.sub(r"\s{2,}", " ", tm.group(5)).strip(), "amount": None,
                   "balance": None, "posted": date_in_period(month_no(tm.group(3)), int(tm.group(4)), start, end)}
            if tm.group(6):
                v = money(tm.group(6))
                row["amount"] = v if tm.group(7) else -v
                rows.append(row)
            else:
                open_row = row
            continue
        if open_row is not None:
            am = AMT_LINE.match(l)
            if am:
                v = money(am.group(1))
                open_row["amount"] = v if am.group(2) else -v
                rows.append(open_row)
                open_row = None
            else:
                open_row["description"] = (open_row["description"] + " " + l).strip()
    if open_row is not None:
        raise ParseError(f"transaction without an amount: {open_row['description']!r}")
    debits = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
    credits = round(sum(r["amount"] for r in rows if r["amount"] > 0), 2)
    want_d = round((totals["purchases"] or 0) + (totals["interest"] or 0) + (totals["fees"] or 0), 2)
    want_c = round(-(totals["credits"] or 0), 2)
    ok = abs(debits - want_d) < 0.005 and abs(credits - want_c) < 0.005
    detail = (f"{len(rows)} rows; purchases {debits:,.2f} vs statement {want_d:,.2f}; "
              f"credits {credits:,.2f} vs statement {want_c:,.2f}; total balance {totals['total_balance']:,.2f}")
    pm = next((m for m in (re.match(r"^(BMO .*Mastercard)$", l) for l in lines[:15]) if m), None)
    hm = re.search(r"^Subtotal for ([A-Z][A-Z .'-]+?)\s+[\d,]+\.\d{2}\s*$", text, re.M)
    return result(NAME, path, account, start, end, rows, totals, RULE, ok, detail,
                  totals["previous"], totals["total_balance"],
                  clean_product(pm.group(1), 'BMO') if pm else None,
                  hm.group(1).strip() if hm else None, "Credit card")
