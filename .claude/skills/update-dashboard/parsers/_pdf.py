"""What every statement parser shares: the text of a PDF, money, dates, and the sign puzzle.

The sign puzzle is the real work. A bank statement's text comes out of the PDF as lines with
the amounts at the end and the column headings gone — "Online Banking transfer - 5723 100.07"
is a deposit and "Misc Payment RBC CREDIT CARD 77.77" is a withdrawal, and nothing in the line
says which. What does say is the running balance the statement prints every few rows: between
two printed balances the signed amounts must add up to the difference, and with a handful of
rows there is exactly one way to sign them. `assign_signs` solves that; when two ways fit (rare,
and only when two rows carry the same amount) the description decides.
"""
import datetime
import re

from . import ParserUnavailable, ParseError

MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
AMOUNT = r"-?\s?\$?\d{1,3}(?:,\d{3})*\.\d{2}|-?\s?\$?\d+\.\d{2}"


def text_lines(path):
    """Every non-blank line of the PDF, in page order."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ParserUnavailable("pypdf is not installed (pip3 install --user pypdf); read the statement by hand")
    r = PdfReader(path)
    out = []
    for p in r.pages:
        # A non-breaking space (0xa0) between an amount and "CR" is a space to everything below.
        out += [l.replace("\xa0", " ").strip() for l in (p.extract_text() or "").splitlines() if l.strip()]
    return out


def money(s):
    """'$1,234.56' / '- 4.00' / '4.49 CR' / '-$690.41' -> float; CR and a leading minus are negative."""
    t = s.strip()
    neg = t.startswith("-") or t.endswith("CR")
    t = re.sub(r"[^\d.]", "", t)
    if not t:
        raise ParseError(f"not an amount: {s!r}")
    v = float(t)
    return -v if neg else v


def month_no(name):
    m = MONTHS.get(name.strip(". ").lower()[:3])
    if not m:
        raise ParseError(f"not a month: {name!r}")
    return m


def date_in_period(month, day, start, end):
    """A statement prints 'Aug 3' without a year; the year is the one that puts the day inside
    the statement period (a January statement covers December rows)."""
    for y in (end.year, end.year - 1, end.year + 1):
        try:
            d = datetime.date(y, month, day)
        except ValueError:
            continue
        if start - datetime.timedelta(days=3) <= d <= end + datetime.timedelta(days=3):
            return d.isoformat()
    return datetime.date(end.year, month, day).isoformat()


def long_date(s):
    """'July 24, 2026' / 'Aug. 20, 2026' / 'AUG 19, 2026' -> date."""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if not m:
        raise ParseError(f"not a date: {s!r}")
    return datetime.date(int(m.group(3)), month_no(m.group(1)), int(m.group(2)))


DEPOSIT_WORDS = ("received", "deposit", "interest", "from", "refund", "credit", "payroll", "pay/")
WITHDRAW_WORDS = ("purchase", "fee", "to ", "payment", "withdrawal", "transfer to", "bill")


def _lean(desc):
    d = desc.lower()
    if any(w in d for w in DEPOSIT_WORDS) and not any(w in d for w in ("transfer to", "to deposit")):
        return 1
    if any(w in d for w in WITHDRAW_WORDS):
        return -1
    return 0


def assign_signs(rows, opening, closing):
    """rows: [{amount: unsigned float, balance: float|None, description}] in statement order.
    Returns the rows with `amount` signed so every printed balance is met, or raises."""
    out = [dict(r) for r in rows]
    bal = opening
    seg = []          # indexes since the last printed balance

    def solve(idxs, target):
        n = len(idxs)
        if n > 22:
            raise ParseError(f"{n} rows between two printed balances is more than this can sign")
        fits = []
        for mask in range(1 << n):
            s = 0.0
            for k, i in enumerate(idxs):
                s += out[i]["amount"] if mask >> k & 1 else -out[i]["amount"]
            if abs(s - target) < 0.005:
                fits.append(mask)
        if not fits:
            raise ParseError(f"no way to sign {n} row(s) so that the balance moves by {target:,.2f}")
        if len(fits) > 1:
            # Prefer the signing the descriptions lean towards; ties stay an error.
            def score(mask):
                return sum(_lean(out[i]["description"]) * (1 if mask >> k & 1 else -1)
                           for k, i in enumerate(idxs))
            best = max(score(m) for m in fits)
            fits = [m for m in fits if score(m) == best]
            if len(fits) > 1:
                raise ParseError("two rows of the same amount could each be the deposit; read them by eye")
        for k, i in enumerate(idxs):
            if not (fits[0] >> k & 1):
                out[i]["amount"] = -out[i]["amount"]

    for i, r in enumerate(out):
        seg.append(i)
        if r.get("balance") is not None:
            solve(seg, round(r["balance"] - bal, 2))
            bal = r["balance"]
            seg = []
    if seg:
        solve(seg, round(closing - bal, 2))
    # Fill the running balance forward so every row carries one, the way the ledgers do.
    bal = opening
    for r in out:
        bal = round(bal + r["amount"], 2)
        if r.get("balance") is not None and abs(r["balance"] - bal) > 0.005:
            raise ParseError(f"balance chain breaks at {r['description']!r}: {bal:,.2f} vs printed {r['balance']:,.2f}")
        r["balance"] = bal
    if abs(bal - closing) > 0.005:
        raise ParseError(f"rows end at {bal:,.2f} but the statement closes at {closing:,.2f}")
    return out


def result(parser, path, account, start, end, rows, totals, rule, ok, detail, opening=None, closing=None,
           product=None, holder=None, kind=None):
    return {"parser": parser, "file": path, "account": account,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "opening": opening, "closing": closing, "rows": rows, "totals": totals,
            "reconcile": {"rule": rule, "ok": bool(ok), "detail": detail},
            "product": product, "holder": holder, "kind": kind}


# Trademark marks and the like that statements print after product names.
MARKS = re.compile(r"(?:TM|™|®|‡|\*)")


def clean_product(s, inst=None):
    """'Signature® RBC Rewards® Visa‡' -> 'Signature Rewards Visa'. The institution is dropped:
    the register carries it separately."""
    s = MARKS.sub("", s or "")
    if inst:
        s = re.sub(r"\b" + re.escape(inst) + r"\b", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -")
    return s or None


def holder_after(lines, pred):
    """The account holder's name: the first all-capitals line of letters after the line `pred`
    matches. Statements print it in the address block."""
    for i, l in enumerate(lines):
        if pred(l):
            for nxt in lines[i + 1:i + 8]:
                if re.fullmatch(r"[A-Z][A-Z .'-]{2,}", nxt.strip()):
                    return nxt.strip()
            return None
    return None
