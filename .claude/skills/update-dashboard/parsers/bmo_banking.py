"""BMO Everyday Banking statements — Primary Chequing and Savings Amplifier, one layout, and
sometimes more than one account in one PDF.

The PDF's digit font has no text map, so pypdf hands the digits and punctuation back as glyph
codes: "/5/2c/4/3/8/2e/0/2" is 5,438.02 and "May /0/5/2c /2/0/2/6" is May 05, 2026. `decode`
turns that back into text before anything else looks at it. What it then looks like:

    For the period ending August 05, 2026
    Savings Amplifier Account # 0006 3874-471            <- an account section starts here
    Jul 04 Opening balance 0.11
    Jul 21 Online Transfer, TF 0006#3874-471 2,000.00 2,000.11     <- movement, then balance
    Jul 31 Interest Earned 0.30 2,000.41
    Aug 05 Closing totals 0.00 2,000.30                   <- deducted total, added total

Every row prints its balance, so the sign of a movement is the balance's own difference.
Reconciled per account: the chain closes on the printed closing balance, and the deducted and
added totals match the summary.
"""
import datetime
import re

from ._pdf import AMOUNT, ParseError, date_in_period, holder_after, long_date, money, month_no, result, text_lines

NAME = "bmo_banking"
RULE = "balance chain closes; deducted and added match the printed totals"
GLYPH = re.compile(r"/([0-9a-f]{2})|/(\d)")
PUNCT = {"2c", "2e", "2d", "28", "29", "3a", "3b", "2f", "26", "27", "23", "24", "2a", "2b", "3d", "40", "25"}
DATE = re.compile(r"^([A-Z][a-z]{2}) (\d{2}) (.*)$")
ROW = re.compile(r"^(.*?)\s+(" + AMOUNT + r")\s+(" + AMOUNT + r")\s*$")
SECTION = re.compile(r"^(.+?) Account # (\d{4}) (\d{4}-\d{3})\s*(.*)$")


def decode(s):
    def one(m):
        if m.group(1) is not None and m.group(1) in PUNCT:
            return chr(int(m.group(1), 16))
        if m.group(1) is not None:
            # "/12" is the digit 1 followed by the digit 2, not a glyph code.
            return m.group(1)[0] + m.group(1)[1] if m.group(1).isdigit() else m.group(0)
        return m.group(2)
    return GLYPH.sub(one, s)


def parse(path):
    lines = [decode(l) for l in text_lines(path)]
    text = "\n".join(lines)
    pm = re.search(r"For the period ending ([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not pm:
        raise ParseError("no 'For the period ending' line; not a BMO Everyday Banking statement")
    end = long_date(pm.group(1))

    # Account sections: each starts with '<name> Account # <transit> <number>' inside the
    # activity part, and runs to its 'Closing totals' row.
    try:
        act = next(i for i, l in enumerate(lines) if l.startswith("Here's what happened"))
    except StopIteration:
        raise ParseError("no 'Here's what happened in your account' table")
    sections, cur = [], None
    for l in lines[act:]:
        sm = SECTION.match(l)
        if sm and not sm.group(4):
            cur = {"name": sm.group(1).strip(), "account": sm.group(3)[-3:], "lines": []}
            sections.append(cur)
        elif cur is not None:
            cur["lines"].append(l)
    if not sections:
        raise ParseError("no account section found")

    holder = holder_after(lines, lambda l: l.strip() == "Everyday Banking")
    out = []
    for sec in sections:
        opening = closing = None
        start = None
        rows = []
        t_out = t_in = None
        for l in sec["lines"]:
            # pypdf sometimes splits a month name ("M ar 16"); close the gap before matching.
            l = re.sub(r"^([A-Z]) ?([a-z]) ?([a-z]) (\d{2}) ", r"\1\2\3 \4 ", l)
            dm = DATE.match(l)
            if not dm:
                continue
            date = date_in_period(month_no(dm.group(1)), int(dm.group(2)), end.replace(day=1), end)
            rest = dm.group(3)
            if rest.startswith("Opening balance"):
                opening = money(rest.split()[-1]); start = date; continue
            if rest.startswith("Closing totals"):
                rm = ROW.match(rest)
                if rm:
                    t_out, t_in = money(rm.group(2)), money(rm.group(3))
                break
            rm = ROW.match(rest)
            if not rm:
                raise ParseError(f"{sec['name']}: row without amount and balance: {l!r}")
            rows.append({"date": date, "description": rm.group(1).strip(),
                         "amount": abs(money(rm.group(2))), "balance": money(rm.group(3))})
        if opening is None:
            raise ParseError(f"{sec['name']}: no opening balance row")
        bal = opening
        for r in rows:
            d = round(r["balance"] - bal, 2)
            if abs(abs(d) - r["amount"]) > 0.005:
                raise ParseError(f"{sec['name']}: balance moves by {d:,.2f} but the row says {r['amount']:,.2f}: {r['description']!r}")
            r["amount"] = d
            bal = r["balance"]
        closing = bal
        # The summary block prints the same account with opening, deducted, added, closing.
        sm = re.search(r"-" + re.escape(sec["account"]) + r"\b\s+(" + AMOUNT + r")\s+(" + AMOUNT + r")\s+(" + AMOUNT + r")\s+(" + AMOUNT + r")\s*$",
                       "\n".join(l for l in lines[:act] if "-" + sec["account"] in l), re.M)
        s_open = s_close = None
        if sm:
            s_open, s_out, s_in, s_close = (money(sm.group(i)) for i in (1, 2, 3, 4))
            t_out = t_out if t_out is not None else s_out
            t_in = t_in if t_in is not None else s_in
        dec = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
        add = round(sum(r["amount"] for r in rows if r["amount"] > 0), 2)
        ok = ((t_out is None or abs(dec - t_out) < 0.005) and (t_in is None or abs(add - t_in) < 0.005)
              and (s_close is None or abs(closing - s_close) < 0.005))
        detail = (f"{sec['name']} #{sec['account']}: {len(rows)} rows; opening {opening:,.2f} → closing {closing:,.2f}"
                  f" (summary {s_close}); deducted {dec:,.2f} (statement {t_out}); added {add:,.2f} (statement {t_in})")
        out.append(result(NAME, path, sec["account"],
                          datetime.date.fromisoformat(start) if start else end.replace(day=1), end, rows,
                          {"deducted": t_out, "added": t_in, "summaryClosing": s_close},
                          RULE, ok, detail, opening, closing,
                          sec["name"], holder, "Chequing" if "chequing" in sec["name"].lower() else "Savings"))
    if len(out) == 1:
        return out[0]
    # More than one account in the file: one result per account, the file's verdict is all of them.
    return {"parser": NAME, "file": path, "accounts": out,
            "reconcile": {"rule": RULE, "ok": all(o["reconcile"]["ok"] for o in out),
                          "detail": " | ".join(o["reconcile"]["detail"] for o in out)}}
