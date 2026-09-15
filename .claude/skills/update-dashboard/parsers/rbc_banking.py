"""RBC personal banking and savings statements (Day to Day Banking, High Interest eSavings,
Find & Save). One layout for all three.

What the text looks like once pypdf has read it:

    From July 24, 2026 to August 25, 2026
    Your account number: 03652-5027740
    Your opening balance on July 24, 2026 $766.99
    Total deposits into your account + 1,177.84
    Total withdrawals from your account - 1,948.83
    Your closing balance on August 25, 2026 = - $4.00
    Details of your account activity
    Opening Balance 766.99
    3 Aug Contactless Interac purchase - 7473          <- a description can wrap: the amounts
    ESSO CIRCLE K 156.65 610.34                        <- come on the last line of it
    11 Aug Online Banking transfer - 5723 100.07       <- one amount, no balance printed
    e-Transfer received EMMA ROY CAYmXJKs 1,000.00 1,690.41
    Closing Balance - $4.00

A row's date is printed only on the first row of a day. A line ends in one amount (the movement)
or two (movement and the new balance), and nothing says whether the movement went in or out —
the printed balances decide that (see _pdf.assign_signs). Reconciled three ways: the chain
closes, and the deposits and withdrawals add to the two totals the statement prints.
"""
import re

from ._pdf import (AMOUNT, ParseError, assign_signs, clean_product, date_in_period, holder_after,
                   long_date, money, month_no, result, text_lines)

NAME = "rbc_banking"
RULE = "balance chain closes; deposits and withdrawals match the printed totals"
DATE = re.compile(r"^(\d{1,2}) ([A-Z][a-z]{2})\b\s*(.*)$")
TAIL = re.compile(r"^(.*?)\s+(" + AMOUNT + r")(?:\s+(" + AMOUNT + r"))?\s*$")


def parse(path):
    lines = text_lines(path)
    text = "\n".join(lines)
    m = re.search(r"From ([A-Za-z]+ \d{1,2}, \d{4}) to ([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not m:
        raise ParseError("no 'From <date> to <date>' line; not an RBC banking statement")
    start, end = long_date(m.group(1)), long_date(m.group(2))
    acct = re.search(r"Your account number:\s*([\d-]+)", text)
    account = re.sub(r"\D", "", acct.group(1))[-4:] if acct else None

    def grab(label):
        mm = re.search(label + r"(" + AMOUNT + r")\s*$", text, re.M)
        return money(mm.group(1)) if mm else None
    opening = grab(r"Your opening balance on [A-Za-z]+ \d{1,2}, \d{4}\s*=?\s*")
    closing = grab(r"Your closing balance on [A-Za-z]+ \d{1,2}, \d{4}\s*=?\s*")
    t_dep = grab(r"Total deposits into your account\s*\+?\s*")
    t_wd = grab(r"Total withdrawals from your account\s*-?\s*")
    if opening is None or closing is None:
        raise ParseError("opening or closing balance not found")

    # The activity table: from the 'Opening Balance' row to the 'Closing Balance' row.
    try:
        a = next(i for i, l in enumerate(lines) if l.startswith("Opening Balance"))
        b = next(i for i, l in enumerate(lines) if l.startswith("Closing Balance") and i > a)
    except StopIteration:
        raise ParseError("activity table not found")
    rows, pending, cur = [], "", None
    for l in lines[a + 1:b]:
        dm = DATE.match(l)
        if dm:
            cur = date_in_period(month_no(dm.group(2)), int(dm.group(1)), start, end)
            l = dm.group(3)
        tm = TAIL.match(l)
        if not tm:
            pending = (pending + " " + l).strip()
            continue
        desc = (pending + " " + tm.group(1)).strip()
        pending = ""
        rows.append({"date": cur, "description": desc, "amount": abs(money(tm.group(2))),
                     "balance": money(tm.group(3)) if tm.group(3) else None})
    if pending:
        raise ParseError(f"a description with no amount after it: {pending!r}")
    if any(r["date"] is None for r in rows):
        raise ParseError("a row before the first dated row")
    rows = assign_signs(rows, opening, closing)
    dep = round(sum(r["amount"] for r in rows if r["amount"] > 0), 2)
    wd = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
    ok = (t_dep is None or abs(dep - t_dep) < 0.005) and (t_wd is None or abs(wd - t_wd) < 0.005)
    detail = (f"{len(rows)} rows; opening {opening:,.2f} → closing {closing:,.2f}; deposits {dep:,.2f} "
              f"(statement {t_dep}); withdrawals {wd:,.2f} (statement {t_wd})")
    # "RBC Day to Day BankingTM 03652-5022306" / "Find & SaveTM 03652-5062831" names the product;
    # "Your RBC personal savings account statement" says savings, "personal banking" chequing.
    pm = next((re.match(r"^(.+?)(?:TM|™)\s+\d{5}-\d{5,}", l) for l in lines
               if re.match(r"^(?!Your account number)(.+?)(?:TM|™)\s+\d{5}-\d{5,}", l)), None)
    kind = "Savings" if re.search(r"Your RBC personal savings", text) else "Chequing"
    holder = holder_after(lines, lambda l: l.startswith("Your account number"))
    return result(NAME, path, account, start, end, rows,
                  {"deposits": t_dep, "withdrawals": t_wd}, RULE, ok, detail, opening, closing,
                  clean_product(pm.group(1), "RBC") if pm else None, holder, kind)
