"""flows.py — the monthly plan as flows (findata schema 5, FINANCE.md §8b).

`funds.json` `plan.flows` is a list of rows, each one thing that happens to the paycheque every
month: what comes in (`income`), what is paid before anything is chosen (`committed` — rent, a
mortgage, a loan), what is moved out to be saved (`saving`), and what is free (`allowance`).
The page, rebuild.py and check_data.py all read the same sums from here, so a flow added to the
file changes every one of them and none of them carries a hand-copied number.

A flow may carry `starts: "fire"` — it begins only after FIRE (rent an owner will pay but does
not yet) — and is then left out of this month's split but kept in the planning figure. A
committed flow may carry `until` (the month a loan ends), `afterFire` (`keep`, the default, or
`drop`: a mortgage payment stops, property tax does not) and `pays` (the liability it repays).
"""

KINDS = ("income", "committed", "saving", "allowance")


def active(f):
    """In this month's split. A flow that starts after FIRE is planning, not cash."""
    return not f.get("starts")


def _num(x):
    return int(x) if float(x) == int(float(x)) else round(float(x), 2)


def totals(plan):
    """Every sum the page and the checkers read, from the flows alone."""
    flows = plan.get("flows") or []
    now = [f for f in flows if active(f)]

    def s(kind, rows=now, pred=lambda f: True):
        return _num(sum(float(f.get("amount") or 0) for f in rows if f.get("kind") == kind and pred(f)))

    return {
        "income": s("income"),
        "committed": s("committed"),
        # What is still paid after FIRE, whether or not it is paid today: the fixed part of the
        # planning figure, added to the measured everyday median for the calibration.
        "committedKeep": s("committed", flows, lambda f: f.get("afterFire", "keep") == "keep"),
        "saving": s("saving"),
        # Pay-yourself-first is judged on what reaches the broker; a saving flow with another
        # destination (a fund, a child's plan) is saving but not that rule.
        "invest": s("saving", now, lambda f: (f.get("to") or "broker") == "broker"),
        "allowance": s("allowance"),
        "committedNow": [f for f in now if f.get("kind") == "committed"],
        "incomeNote": next((f.get("note") or "" for f in flows if f.get("kind") == "income"), ""),
    }
