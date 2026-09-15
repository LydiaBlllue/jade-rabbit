"""parsers — one module per institution and kind of statement.

The import used to read every PDF by eye, each month from scratch, and the only regression test
was the reconciliation. A parser does the reading: it turns the file into rows plus the
statement's own totals, and reconciles them the way the register's `documents[].reconcile`
says. A parse that reconciles goes straight in; one that does not stops and says why, and the
statement is read by hand — the old path, kept as the fallback, never as the default.

Every parser returns the same shape:

    {"parser": name, "file": path,
     "account": "816",                       # the digits the statement itself carries
     "period": {"from": "2026-07-24", "to": "2026-08-25"},
     "opening": 766.99, "closing": -4.00,     # None for a card statement without them
     "rows": [{"date": "2026-08-03", "description": "...", "amount": -156.65, "balance": 610.34}],
     "totals": {...},                          # what the statement prints about itself
     "reconcile": {"rule": "...", "ok": True, "detail": "..."},
     # What the statement says about the account itself, when it prints it (None otherwise).
     # The setup reads these to draft the register; the import never needs them.
     "product": "Day to Day Banking", "holder": "EMMA ROY", "kind": "Chequing"}

Amounts are signed the ledger's way: money out is negative. Row order is the statement's.

They depend on pypdf for the text (`pip3 install --user pypdf`). Without it every parser raises
ParserUnavailable, and the skill reads the file itself — the tool degrades to what it was, it
does not guess.
"""
import importlib

NAMES = ("rbc_banking", "rbc_visa", "bmo_banking", "bmo_mastercard")


class ParserUnavailable(Exception):
    """pypdf is not installed: nothing here can read a PDF."""


class ParseError(Exception):
    """The file was read but not understood: a layout this parser does not know."""


def parse(path, name):
    if name not in NAMES:
        raise ParseError(f"no parser named {name!r}; the register knows {', '.join(NAMES)}")
    mod = importlib.import_module(__name__ + "." + name)
    return mod.parse(path)
