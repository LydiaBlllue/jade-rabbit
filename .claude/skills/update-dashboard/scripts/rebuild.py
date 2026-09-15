#!/usr/bin/env python3
"""Build both dashboards from findata/. Every data constant in the HTML comes from here.

WHY THIS EXISTS. The dashboards bake their data in as constants. Until 2026-09-09 about twenty of
those constants had no source but the page itself — the classified chequing rows, the net-worth
history, the open tasks, the filing grid, the planning assumptions, the investment theses — so a
public copy had to be scrubbed of one person's life, and the setup skill had to "hand over" a page
that still carried the previous owner's holdings. Now the page is a template and this is the only
build step: nothing in dashboards/ is typed by hand, and a template with every constant emptied
(`--template`) contains nobody.

Every derivation was checked against the live page before being encoded here — the acceptance
test for the change was that a rebuild from the new files rendered every page byte for byte.

    rebuild.py [root]                 # check only: what would change, and what is already in sync
    rebuild.py [root] --write         # apply, to both dashboards
    rebuild.py [root] --template DIR  # write the dashboards to DIR with every constant emptied
"""
import sys, os, re, json, csv, collections
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flows import totals as flow_totals   # the plan's sums, read from its flows -- one place
import layout                              # where each findata file lives (schema 6)

MAIN_NAMES = ("ly_finance_dashboard.html", "finance_dashboard.html")   # an owner's copy, or the template's
INV_NAME = "investment_dashboard.html"
FUND_TYPES = ("bond_fund", "equity_fund")

# The two cuts of net worth, one row per value of one axis (FINANCE.md §8a). The label is what
# the page says, the colour is design (DESIGN.md palette), and both are keyed by the axis value
# so a row keeps its colour whatever else is present.
ROLE_ROWS = (("grow", "Invested", "#2a78d6"), ("set-aside", "Earmarked", "#eda100"),
             ("buffer", "Cash", "#1baf7a"), ("none", "Other assets", "#4a3aa7"))
REACH_ROWS = (("today", "Reach today", "#1baf7a"), ("costs", "Reach, but it costs", "#eda100"),
              ("spoken", "Spoken for", "#eb6834"), ("locked", "Locked in property", "#c98500"),
              ("abroad", "Across a border", "#4a3aa7"))


# The shape of findata/ this script builds from. profile.json carries the same number; when
# they differ the workspace needs tools/migrate_<from>to<to>.py before anything is rebuilt.
# 2 = page constants moved into findata (2026-09-09); 3 = alerts.json replaced by imports.json
# and decisions.json (2026-09-10); 4 = every account row carries the five axes side / role /
# reach / value / against, and feeds keeps only the flow words (2026-09-10, FINANCE.md §8a);
# 5 = the monthly plan is flows (income / committed / saving / allowance) and plan.json's
# imputedRent is a committed flow that starts after FIRE (2026-09-10, FINANCE.md §8b); 6 =
# findata/ is three folders, register / ledgers / history, one per layer (2026-09-10, layout.py).
SCHEMA = 9


def same(a, b):
    """Deep equality that compares numbers by value, so 0 and 0.0 are not a difference."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def trailing_digits(s):
    m = re.search(r'(\d+)\D*$', s or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------- source data
def load(root):
    fd = lambda n: layout.path(root, n)
    # A workspace someone has just set up has balances but no history yet, and it never has the
    # ledger files named after somebody else's banks. Missing CSVs read as empty rather than
    # crashing; missing JSON is a real problem, because those carry the structure — except the
    # few that a workspace legitimately lacks, which get an empty default below.
    def rd(n):
        p = fd(n)
        return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []
    def jd(n, default=None):
        p = fd(n)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
        if default is None:
            raise SystemExit(f"{layout.rel(n)} is missing — the setup skill writes it")
        return default
    accounts = jd("accounts.json")
    d = {"spending": rd("spending.csv"), "acts": rd("ws_activities.csv"),
         "hold": rd("holdings_latest.csv"),
         "banks": jd("banks.json"), "foreign": jd("foreign.json"), "profile": jd("profile.json"),
         "rules": jd("rules.json"), "accounts": accounts, "funds": jd("funds.json"),
         "plan": jd("plan.json"),
         "tasks": jd("tasks.json", {"tasks": []}),
         "filings": jd("filings.json", {"filed": {}}),
         "imports": jd("imports.json", {"imports": []}),
         "decisions": jd("decisions.json", {"decisions": []}),
         "nw_hist": jd("networth_history.json", {"snapshots": []}),
         # The ledgers this workspace actually has, keyed by account key.
         "ledgers": {a["key"]: rd(a["ledger"]) for a in accounts["accounts"] if a.get("ledger")},
         # A workspace with no investments has no foreign-currency holdings to convert, so it has
         # no exchange rate — and should not be made to invent one. 1.0 converts nothing.
         "fx": jd("fx.json", {"usd_cad": 1.0, "asof": None, "quality": "none"}),
         "hist": jd("investment_history.json", {"snapshots": []}),
         "merchants": jd("merchants.json")}
    d["rate"] = d["fx"]["usd_cad"]
    have = int(d["profile"].get("schema", 2))
    if have < SCHEMA:
        raise SystemExit(f"findata/ is schema {have} and this tool builds schema {SCHEMA} — run "
                         f"tools/migrate_{have}to{have+1}.py on the workspace first, then rebuild")
    if have > SCHEMA:
        raise SystemExit(f"findata/ is schema {have}, newer than this tool ({SCHEMA}) — sync a newer tool")
    return d


def cashflow_rows(d, accs, rate, half, wsinc):
    """The monthly cash-flow rows, from the typed ledgers (schema 9; they used to be copied into
    cashflow.json by the import, and nothing checked the copy). One row per month from the first
    ledger row to the newest: what payroll delivered, what came in typed Rent / Gift / Other /
    Repayment, what moved to the broker and back (a Transfer whose label names the broker), how
    many of the outgoing ones were exactly half the monthly investing amount, and the broker's
    own income for the month. Only ledgers whose `feeds` include "Cash flow" count."""
    broker = (next((a["inst"] for a in accs if a.get("role") == "grow" and a.get("value") == "export"), "") or "").lower()
    rows = collections.defaultdict(lambda: {"payroll": 0.0, "wsOut": 0.0, "wsIn": 0.0, "rent": 0.0, "gift": 0.0,
                                            "other": 0.0, "repaid": 0.0, "inv": 0.0, "nRule": 0})
    for a in accs:
        if not a.get("ledger") or "Cash flow" not in (a.get("feeds") or ""):
            continue
        for r in d["ledgers"].get(a["key"], []):
            t, amt, lab = r.get("type") or "", float(r["amount"] or 0), (r.get("label") or "").lower()
            m = rows[r["date"][:7]]
            if t == "Payroll" and amt > 0: m["payroll"] += amt
            elif t == "Rent" and amt > 0: m["rent"] += amt
            elif t == "Gift" and amt > 0: m["gift"] += amt
            elif t == "Other" and amt > 0: m["other"] += amt
            elif t == "Repayment" and amt > 0: m["repaid"] += amt
            elif t == "Transfer" and broker and broker in lab:
                if amt < 0:
                    m["wsOut"] += -amt
                    if abs(-amt - half) < 0.01: m["nRule"] += 1
                else:
                    m["wsIn"] += amt
    for w in wsinc:
        rows[w["ym"]]["inv"] += w["div"] + w["int"] + w["lend"] + w["tax"]
    return [dict(ym=ym, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()})
            for ym, m in sorted(rows.items())]


def account_sets(d):
    """Which broker account is what. The classification is NOT in the code and NOT in the
    holdings export -- it is the `role` axis of accounts.json (schema 4). Dry powder is not an
    axis: rules.json names the symbols, and they are counted inside every `grow` account."""
    port, earm = set(), set()
    for a in d["accounts"]["accounts"]:
        if a.get("src") != "holdings_latest.csv":
            continue
        if a.get("role") == "grow": port.add(a["id"])
        if a.get("role") == "set-aside": earm.add(a["id"])
    return port, earm, set(port)


def holdings_by_account(d):
    mv, bv = collections.defaultdict(float), collections.defaultdict(float)
    sym = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in d["hold"]:
        n, v, cur = r.get("Account Number"), r.get("Market Value"), r.get("Market Value Currency")
        if not n or not v:
            continue
        cad = float(v) * (d["rate"] if cur == "USD" else 1)
        mv[n] += cad
        sym[n][r.get("Symbol")] += cad
        if r.get("Book Value (CAD)"):
            bv[n] += float(r["Book Value (CAD)"])
    return mv, bv, sym


def clean(obj):
    """Strip the editor-facing keys (`note`, `zh_*`) from a findata object before it reaches a page."""
    return {k: v for k, v in obj.items() if k != "note" and not k.startswith("zh_")}


# ---------------------------------------------------------------- derivations
def derive(d):
    out, rate = {}, d["rate"]
    accs = d["accounts"]["accounts"]
    port, earm, dry = account_sets(d)
    mv, bv, sym = holdings_by_account(d)
    fj, bank, plan, prof = d["foreign"], d["banks"], d["plan"], d["profile"]
    by_id = {a["id"]: a for a in accs}
    label_of = lambda acct_id: (by_id.get(acct_id) or {}).get("label") or (by_id.get(acct_id) or {}).get("name") or acct_id

    # --- SPENDING: a straight copy of the ledger, with the statement tag split off the note
    ACCT_OF = {a["spendTag"]: a["stmtLabel"] for a in accs if a.get("spendTag") and a.get("stmtLabel")}
    spend = []
    for r in d["spending"]:
        m = re.search(r'\s*\[([A-Za-z]+\d+)/\d{8}\]\s*$', r["note"])
        spend.append({"date": r["date"], "amount": round(float(r["amount"]), 2),
                      "currency": r["currency"], "category": r["category"],
                      "note": r["note"][:m.start()].strip() if m else r["note"].strip(),
                      "acct": ACCT_OF.get(m.group(1)) if m else None})
    spend.sort(key=lambda e: e["date"])          # stable: same-day rows keep ledger order
    out["SPENDING"] = spend

    # --- CHEQUING: the classified rows of every ledger. The classification is the `type`
    # column of the ledger itself (a row without one is not shown); `label` overrides the bank's
    # description for display. Until 2026-09-09 this list was typed into the page.
    chq = []
    for a in accs:
        if not a.get("ledger"):
            continue
        src = a["inst"] + " " + trailing_digits(a.get("id"))
        for r in d["ledgers"].get(a["key"], []):
            if r.get("type"):
                chq.append({"date": r["date"], "desc": r.get("label") or r["description"],
                            "type": r["type"], "amount": float(r["amount"]), "src": src})
    chq.sort(key=lambda r: r["date"])
    out["CHEQUING"] = chq

    # --- SUB_KEYS: the subscription brands, from merchants.json.
    def brand_token(match):
        t = re.sub(r'^(SP|SQ|WL|TST|LS)[\s*\-]+', '', match.strip(), flags=re.I)
        return re.split(r'[^A-Za-z0-9]+', t)[0].lower()
    subs = collections.OrderedDict()
    for m in d["merchants"]["merchants"]:
        if m.get("category") != "Subscription":
            continue
        key = brand_token(m["match"])
        name = m.get("brand") or key.title()
        e = subs.setdefault(name, {"k": [], "name": name})
        if key not in e["k"]:
            e["k"].append(key)
    out["SUB_KEYS"] = list(subs.values())

    today = datetime.date.today().isoformat()
    out["TODAY"] = today
    out["PROFILE"] = clean(prof)
    out["RULES"] = clean(d["rules"])
    out["IMPORT_DAY"] = prof.get("importDay", 26)
    # The institution that holds the portfolio. Its name was written into a dozen strings on
    # both pages; now every one of them reads this.
    broker = next((a["inst"] for a in accs if a.get("role") == "grow" and a.get("value") == "export"), None) or "your broker"
    out["BROKER"] = broker
    out["BORN"] = prof.get("born")
    out["ACCT"] = d["accounts"]
    out["FUNDS"] = d["funds"]

    # --- the owner's plan: the figure the FIRE target is built on, the months excluded from
    # every comparison, and the projection / late-life care assumptions
    out["PLAN_BASE_DEFAULT"] = plan["planBase"]
    # The fixed part of the planning figure: every committed flow still paid after FIRE, paid
    # today or not (an owner who does not pay rent yet has one that starts at FIRE). Added to the
    # measured everyday median on the Baseline page so the two can be compared.
    out["COMMITTED_KEEP"] = flow_totals(d["funds"]["plan"])["committedKeep"]
    out["MONTH_SKIP"] = plan.get("skipMonths", {})
    ret = plan.get("retirement", {})
    out["SCENARIOS"] = ret.get("scenarios", [])
    out["HORIZON"] = ret.get("horizon", 25)
    out["ANCHOR_Y"] = ret.get("anchorYear", int(today[:4]))
    out["LIFE_TO"] = ret.get("lifeTo", 95)
    out["COAST_R"] = ret.get("coastR", 0.05)
    out["HOME_CARE"] = ret.get("homeCare", {})
    out["LTC_TIERS"] = ret.get("ltcTiers", [])

    out["NW_HISTORY"] = [{k: v for k, v in h.items() if k in ("ym", "v", "cadOnly")}
                         for h in d["nw_hist"]["snapshots"]]
    # The portfolio, one value per month (newest snapshot in each), for the FIRE trajectory's
    # "actual" line. FIRE is measured on the portfolio, not on net worth.
    ph = {}
    for h in d["hist"]["snapshots"]:
        ph[h["date"][:7]] = round(h["cadInv"] + (h.get("foreign") or 0))
    out["PORT_HISTORY"] = [{"ym": k, "v": v} for k, v in sorted(ph.items())]
    out["TASKS"] = d["tasks"]["tasks"]
    out["GAPS"] = d["accounts"].get("missing", [])
    out["SUBMITTED"] = d["filings"]["filed"]

    # --- WSINC: dividends, interest, stock lending and withholding tax, USD converted
    inc = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in d["acts"]:
        ym = r["effective_date"][:7]
        a = float(r["net_cash_amount"] or 0) * (rate if r["currency"] == "USD" else 1)
        t, desc = r["activity_type"], r["description"].lower()
        if t == "Dividend": inc[ym]["div"] += a
        elif t == "Interest": inc[ym]["lend" if "lending" in desc else "int"] += a
        elif t == "Tax": inc[ym]["tax"] += a
    out["WSINC"] = [{"ym": k, "div": round(v["div"], 2), "int": round(v["int"], 2),
                     "lend": round(v["lend"], 2), "tax": round(v["tax"], 2)}
                    for k, v in sorted(inc.items())]

    # --- WSDEP: only EFT landing in the broker's chequing doorway account. Money paid straight
    # into a registered account is a contribution, not the pay-yourself-first cadence.
    half = round(flow_totals(d["funds"]["plan"])["invest"] / 2, 2)
    dep = collections.defaultdict(lambda: {"amt": 0.0, "nRule": 0})
    for r in d["acts"]:
        if (r["activity_type"] == "MoneyMovement" and r["activity_sub_type"] == "EFT"
                and r["account_type"] == "Chequing" and r["currency"] == "CAD"):
            a = float(r["net_cash_amount"] or 0)
            if a > 0:
                ym = r["effective_date"][:7]
                dep[ym]["amt"] += a
                if abs(a - half) < 0.01: dep[ym]["nRule"] += 1
    cur_ym = max((r["effective_date"][:7] for r in d["acts"]), default="")
    out["WSDEP"] = [{"ym": k, "amt": round(v["amt"], 2), "nRule": v["nRule"]}
                    for k, v in sorted(dep.items()) if k < cur_ym or v["amt"]]

    # --- STMT_END / LEDGER_THRU / DOC_LATEST: how far each source reaches, read off the files
    def newest(rows, col, tag):
        ds = set()
        for r in rows:
            for m in re.finditer(tag + r'/(\d{8})', r.get(col) or ""):
                ds.add(m.group(1))
        return max(ds) if ds else None
    iso = lambda s: s and f"{s[:4]}-{s[4:6]}-{s[6:]}"
    stmt, thru = {}, {}
    for a in accs:
        if a.get("ledger") and a.get("stmtTag"):
            thru[a["key"]] = iso(newest(d["ledgers"].get(a["key"], []), "statement", a["stmtTag"]))
        if not a.get("stmtLabel"):
            continue
        if a.get("ledger") and a.get("stmtTag"):
            stmt[a["stmtLabel"]] = thru[a["key"]]
        elif a.get("spendTag"):
            stmt[a["stmtLabel"]] = iso(newest(d["spending"], "note", a["spendTag"]))
    out["STMT_END"] = stmt
    out["LEDGER_THRU"] = thru
    by_key = {a["key"]: a for a in accs}
    acts_latest = max((r["effective_date"] for r in d["acts"]), default=None)
    bank_asof = {x["account"]: x.get("asof") for x in bank["assets"] + bank["debts"]}
    latest = {}
    for doc in d["accounts"]["documents"]:
        into = doc.get("into")
        acc = by_key.get((doc.get("covers") or [None])[0])
        if into == "holdings_latest.csv" and acc:
            v = acc.get("asof")
        elif into == "ws_activities.csv":
            v = acts_latest
        elif into == "foreign.json":
            v = fj.get("asof")
        elif acc and acc["key"] in thru:
            v = thru[acc["key"]]
        elif acc and acc.get("spendTag"):
            v = iso(newest(d["spending"], "note", acc["spendTag"]))
        elif into == "banks.json" and acc:
            v = bank_asof.get(acc.get("name"))
        else:
            v = None
        latest[doc["key"]] = v
    out["DOC_LATEST"] = latest

    # --- the net-worth family, read off the register's axes (schema 4, FINANCE.md §8a).
    # Every total reads exactly one axis: net worth reads `side`, the by-purpose card reads
    # `role`, the reach table reads `reach` and nets a liability against the asset it names, and
    # dry powder is rules.json's symbols inside `grow`. Until 2026-09-10 net worth was five feed
    # words added up here, so a home had nowhere to go and a mortgage made net worth negative.
    rate_f = fj.get("cadPerUnit", 0)
    fgn_cur = fj.get("currency")
    fgn_cad = round(fj["total"] * rate_f)
    fgn_fund_rows = [a for a in fj["accounts"] if a["type"] in FUND_TYPES]
    fgn_funds = round(sum(a["value"] for a in fgn_fund_rows) * rate_f)
    bank_bal = {x["account"]: x["balance"] for x in bank["assets"] if x.get("balance") is not None}
    bank_bal.update({x["account"]: -x["balance"] for x in bank["debts"]})
    fgn_inst = collections.defaultdict(float)
    for x in fj["accounts"]:
        fgn_inst[x["inst"]] += x["value"]

    def cad_of(a):
        """One item in CAD, from its source. The register's own balance is a copy D14 verifies;
        only a `stated` item (a home, a loan with no statement) is read from the register."""
        src = a.get("src")
        if src == "holdings_latest.csv": v, cur = mv.get(a["id"], 0.0), "CAD"
        elif src == "banks.json": v, cur = bank_bal.get(a["name"], 0.0), a.get("cur", "CAD")
        elif src == "foreign.json": v, cur = fgn_inst.get(a["inst"], 0.0), fgn_cur
        else: v, cur = (a.get("balance") or 0.0), a.get("cur", "CAD")
        if cur == "USD": v *= rate
        elif cur and cur != "CAD" and cur == fgn_cur: v *= rate_f
        # An asset keeps its sign (an overdrawn chequing account is a negative asset, and it
        # was one before the axes); a liability is the amount owed, whichever way the file wrote it.
        return abs(v) if a.get("side") == "liability" else v

    items = [(a, cad_of(a)) for a in accs
             if not (a.get("src") in (None, "none") and a.get("balance") is None)]
    assets = [(a, v) for a, v in items if a.get("side") != "liability"]
    liabs = [(a, v) for a, v in items if a.get("side") == "liability"]
    by_key = {a["key"]: a for a in accs}

    # DESIGN.md §4: BOTH cuts have to add up to the same net worth. Round once per ROW of each
    # cut (a role total, a reach total), never per item -- twenty items rounded one by one drift
    # several dollars from the true sum -- and settle the one dollar the two cuts can disagree by
    # on the largest reach row. The foreign side is one figure on the page (FOREIGN_CAD = total ×
    # rate, rounded once) and in the history, so the abroad items share that figure between roles.
    ca = [(a, v) for a, v in assets if a.get("reach") != "abroad"]
    ab = [(a, v) for a, v in assets if a.get("reach") == "abroad"]
    def by(rows, axis, order):
        tot = collections.OrderedDict((k, 0.0) for k in order)
        for a, v in rows:
            tot[a.get(axis)] += v
        return tot
    role_ca = {k: round(v) for k, v in by(ca, "role", [r for r, _, _ in ROLE_ROWS]).items()}
    reach_ca = {k: round(v) for k, v in by(ca, "reach", [r for r, _, _ in REACH_ROWS]).items()}
    if reach_ca:
        big = max(reach_ca, key=lambda k: reach_ca[k])
        reach_ca[big] += sum(role_ca.values()) - sum(reach_ca.values())
    role_ab = {k: round(v) for k, v in by(ab, "role", [r for r, _, _ in ROLE_ROWS]).items() if v}
    if role_ab:
        if "grow" in role_ab:
            role_ab["grow"] = fgn_funds
        rest = [r for r in role_ab if r != "grow"]
        if rest:
            role_ab[rest[-1]] += fgn_cad - sum(role_ab.values())
        else:
            role_ab["grow"] = fgn_cad
    by_role = collections.OrderedDict((r, role_ca[r] + role_ab.get(r, 0)) for r, _, _ in ROLE_ROWS)
    by_reach = collections.OrderedDict((r, reach_ca[r]) for r, _, _ in REACH_ROWS)
    by_reach["abroad"] = sum(role_ab.values())
    roles_present = {a.get("role") for a, _ in assets}
    reach_present = {a.get("reach") for a, _ in assets}

    # Debts: one rounding of the total, and the secured part rounded per reach row it is netted
    # into, so the reach table's "less what you owe" is exactly what is not already netted.
    R_debt = round(sum(v for _, v in liabs))
    sec_by_reach = collections.defaultdict(float)
    for a, v in liabs:
        on = by_key.get(a.get("against") or "")
        if on is not None and on.get("side") != "liability":
            sec_by_reach[on.get("reach")] += v
    secured = 0
    for r_, v in sec_by_reach.items():
        v = round(v)
        secured += v
        by_reach[r_] -= v                          # equity, not gross, on the reach table

    R_inv, R_earm, R_cash, R_other = role_ca["grow"], by_role["set-aside"], role_ca["buffer"], role_ca["none"]
    invested = sum(v for a, v in ca if a.get("role") == "grow")
    net_worth = sum(role_ca.values()) - R_debt        # the Canadian side; the page adds FOREIGN_CAD
    dry_syms = set()
    for b in d["rules"].get("buckets", []):
        if b.get("target"):
            dry_syms |= set(b.get("symbols", []))
    dry_cad = round(sum(v for k in dry for s_, v in sym[k].items() if s_ in dry_syms))
    tickers = {r["Symbol"] for r in d["hold"]
               if r.get("Symbol") and r.get("Security Type") != "CURRENCY"
               and r.get("Account Number") in port}

    out["NW_DEBT"] = R_debt
    # The line under "Less what you owe": the owner's words if plan.json carries them, else the
    # debts by name. It used to read "MasterCard and Visa, both inside the grace period" for
    # everyone, mortgage holders included (2026-09-10, found by a test owner with a mortgage).
    debts = [a["name"] for a, _ in liabs]
    dn = (", ".join(debts[:-1]) + " and " + debts[-1]) if len(debts) > 1 else (debts[0] if debts else "")
    out["DEBT_NOTE"] = plan.get("descriptions", {}).get("debt") or ((dn + " — the balances owed today") if dn else "Nothing owed")
    fgn_label = fj.get("label") or "Foreign"

    # One line under each row. The owner's own words if plan.json carries them (keyed by the
    # label), otherwise a description built from the register — never a sentence about somebody
    # else's accounts.
    desc = plan.get("descriptions", {})
    def named(axis, val):
        by = collections.OrderedDict()
        for a, _ in assets:
            if a.get(axis) == val:
                by.setdefault(a["inst"], []).append(a["name"])
        return "; ".join(", ".join(v) + " at " + k for k, v in by.items())
    def part(axis, val, tail):
        who = named(axis, val)
        return (who + " — " + tail) if who else tail[:1].upper() + tail[1:]
    generic_parts = {
        "Invested": part("role", "grow", "the part whose whole job is to grow"),
        "Earmarked": part("role", "set-aside", "already has a purpose, so it stays outside the portfolio"),
        "Cash": part("role", "buffer", "the day-to-day buffer"),
        "Other assets": part("role", "none", "owned, but not money that grows or gets spent"),
    }
    generic_reach = {
        "Reach today": "Investment and cash accounts with no age gate and no penalty",
        "Reach, but it costs": "Registered retirement savings: withdrawable, but taxed as income that year",
        "Spoken for": "Earmarked for a purpose. Reachable, but spending it means giving up what it was for",
        "Locked in property": "What the property is worth less what is still owed on it. Reachable only by selling",
        "Across a border": "Held abroad. Reachable, but through conversion and transfer limits, which take time",
    }
    out["NWPARTS"] = [{"k": lab, "v": by_role[r], "c": c, "d": desc.get("nwparts", {}).get(lab, generic_parts[lab])}
                      for r, lab, c in ROLE_ROWS if r in roles_present]
    out["REACH"] = [{"k": lab, "v": by_reach[r], "c": c, "d": desc.get("reach", {}).get(lab, generic_reach[lab])}
                    for r, lab, c in REACH_ROWS if r in reach_present]
    got_parts = sum(r["v"] for r in out["NWPARTS"]) - R_debt
    got_reach = sum(r["v"] for r in out["REACH"]) - (R_debt - secured)
    if not (got_parts == got_reach == net_worth + fgn_cad):
        raise SystemExit(f"net worth by purpose sums to {got_parts:,}, by reach to {got_reach:,}, "
                         f"but net worth is {net_worth + fgn_cad:,} — the two cuts must agree (DESIGN.md §4)")
    # incomeYtd was a hand-typed number the old "patch the numbers" mode never touched: the net
    # investment income of the current year, which WSINC already holds month by month.
    out["BOOKV"] = {"mv": R_inv + fgn_funds,
                    "bv": round(sum(bv[k] for k in port)
                                + sum((a["value"] - a.get("gain", 0)) for a in fgn_fund_rows) * rate_f),
                    "incomeYtd": round(sum(r["div"] + r["int"] + r["lend"] + r["tax"]
                                           for r in out["WSINC"] if r["ym"].startswith(today[:4])))}

    hold_asof = max((a.get("asof") or "" for a in accs if a.get("src") == "holdings_latest.csv"), default=None) or None
    pay = next((a for a in accs if "Income" in (a.get("feeds") or "")), None)
    out["INVEST"] = {
        "netWorth": net_worth,
        "assets": R_inv + R_earm + R_cash,
        "debts": R_debt,
        # Nothing invested yet is 0%, not a crash.
        "dryPct": round(dry_cad / invested * 1000) / 10 if invested else 0,
        "dryCad": dry_cad,
        "investable": R_inv, "earmarked": R_earm, "other": R_other,
        # Liabilities that sit on an asset are netted on the reach table, not listed under it.
        "debtsSecured": secured,
        "holdings": len(tickers) + len(fgn_fund_rows),
        "asof": hold_asof, "fxAsof": d["fx"].get("asof"), "fx": rate,
        "banksAsof": (pay or {}).get("asof"),
        "cashflow": cashflow_rows(d, accs, rate, half, out["WSINC"]),
        "portfolio": R_inv + fgn_funds, "foreignFunds": fgn_funds,
        # Who pays money back (a friend, a family member): the register's document that carries
        # `counterparty` (schema 9), never a name in the page code.
        "counterparty": next(({"name": doc["counterparty"]} for doc in d["accounts"].get("documents", [])
                              if doc.get("counterparty")), None),
    }
    out["FOREIGN"] = {"asof": fj["asof"], "currency": fj.get("currency"), "symbol": fj.get("symbol", ""),
                      "label": fgn_label, "total": round(fj["total"], 2), "cadPerUnit": rate_f,
                      # A fund row shows its code beside the name, the way the broker app does.
                      "rows": [dict([("inst", a["inst"]),
                                     ("n", (a.get("label") or a["name"]) + (" · " + a["code"] if a.get("code") else "")),
                                     ("v", round(a["value"], 2))]
                                    + ([("cash", 1)] if a["type"] not in FUND_TYPES else []))
                               for a in fj["accounts"]]}

    # --- what each update left behind: the record, and the queue of things to confirm.
    # The page shows these on Data → Updates and counts the open queue in its header line;
    # the story of an update lives in the record and nowhere else on the page.
    out["IMPORTS"] = sorted(
        [{"date": r["date"], "files": r.get("files", []), "changed": r.get("changed", []),
          "noticed": r.get("noticed", []), "judged": r.get("judged", []), "asked": r.get("asked", [])}
         for r in d["imports"]["imports"]], key=lambda r: r["date"], reverse=True)
    out["DECISIONS"] = [{k: v for k, v in x.items()} for x in d["decisions"]["decisions"]]

    # --- the investment dashboard's own constants
    positions, tick = [], collections.OrderedDict()
    for r in d["hold"]:
        n = r.get("Account Number")
        if not n or not r.get("Symbol"):
            continue
        usd = r.get("Market Value Currency") == "USD"
        p = {"account": label_of(n), "sym": r["Symbol"], "name": r.get("Name"),
             "qty": float(r["Quantity"]),
             "mv": round(float(r["Market Value"]) * (rate if usd else 1), 2),
             "bv": round(float(r.get("Book Value (CAD)") or 0), 2)}
        if usd: p["usd"] = 1
        if r.get("Security Type") == "CURRENCY": p["cash"] = 1
        positions.append(p)
        if not p.get("cash"):
            t = tick.setdefault(p["sym"], {"sym": p["sym"], "name": p["name"], "mv": 0.0, "bv": 0.0, "accounts": []})
            t["mv"] = round(t["mv"] + p["mv"], 2); t["bv"] = round(t["bv"] + p["bv"], 2)
            if p["account"] not in t["accounts"]:
                t["accounts"].append(p["account"])
    ticks = sorted(tick.values(), key=lambda t: -t["mv"])
    for t in ticks:
        t["pl"] = round(t["mv"] - t["bv"], 2)
    out["DATA"] = {"fx": rate, "asof": hold_asof, "today": today, "broker": broker,
                   "positions": positions, "tickers": ticks}
    out["FX"] = {"rate": rate, "asof": d["fx"].get("asof"), "quality": d["fx"].get("quality")}
    out["HIST"] = [{"date": h["date"], "cadInv": h["cadInv"], "dry": h["dry"], "dryPct": h["dryPct"],
                    "tickers": h["tickers"], "fgn": h.get("foreign")} for h in d["hist"]["snapshots"]]
    out["FGN"] = {"asof": max((a.get("asof") or "" for a in fgn_fund_rows), default=fj["asof"]) or fj["asof"],
                  "symbol": fj.get("symbol", ""), "label": fgn_label, "cadPerUnit": rate_f,
                  "cash": fj.get("summary", {}).get("cash", 0),
                  "funds": [{"sym": a.get("code") or a["name"], "name": a.get("label") or a["name"],
                             "inst": a.get("inst", ""), "amount": a["value"], "gain": a.get("gain", 0)}
                            for a in fgn_fund_rows]}
    return out


# Which file each constant lives in. Everything not listed is the main dashboard's.
# Since 2026-09-10 the investing pages live in the main dashboard, so every constant is the main
# page's. The "inv" path below is kept for a workspace whose template still has a second file.
INV_ONLY = set()
BOTH = {"PROFILE", "RULES", "IMPORT_DAY"}


def wanted(out, which):
    if which == "inv":
        return {k: v for k, v in out.items() if k in INV_ONLY or k in BOTH}
    return {k: v for k, v in out.items() if k not in INV_ONLY}


# ---------------------------------------------------------------- splicing
def span(src, name):
    """Byte range of the literal after `const NAME = `, string- and escape-aware."""
    m = re.search(r'^const ' + name + r'\s*=\s*', src, re.M)
    if not m:
        raise KeyError(name)
    i = m.end()
    if src[i] not in "[{":
        j = src.index(";", i)
        return i, j
    depth, instr, esc, q = 0, False, False, ""
    for j in range(i, len(src)):
        c = src[j]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == q: instr = False
            continue
        if c in "\"'": instr, q = True, c
        elif c in "[{": depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return i, j + 1
    raise ValueError(name)


def apply_one(src, name, want):
    """Replace the literal after `const NAME =` with `want` as JSON. Returns (src, message|None).
    A current literal that is not JSON (a JavaScript object with bare keys, or comments inside)
    counts as different: the first rebuild after the shape change rewrites it."""
    a, b = span(src, name)
    cur = src[a:b]
    try:
        if same(json.loads(cur), want):
            return src, None
        n_old = len(json.loads(cur)) if isinstance(want, (list, dict)) else 1
    except (ValueError, TypeError):
        n_old = None
    n_new = len(want) if isinstance(want, (list, dict)) else 1
    note = f"{name}: replaced" + (f" ({n_old} → {n_new})" if n_old is not None and n_old != n_new else "")
    return src[:a] + json.dumps(want, ensure_ascii=False) + src[b:], note


def finish(which, src, main_fn):
    """The non-constant touches a build makes. Today: the investment page's link back to the main
    dashboard names that file — an owner's copy may still be called ly_finance_dashboard.html while
    the template says finance_dashboard.html. check_data's T1 applies this too, so a built page is
    still exactly template + findata + finish()."""
    if which == "inv":
        src = re.sub(r'(<a class="back" href=")[^"]*(" id="back">)', lambda m: m.group(1) + main_fn + m.group(2), src, count=1)
    return src


def empty_like(v):
    if isinstance(v, bool): return False
    if isinstance(v, dict): return {}
    if isinstance(v, list): return []
    if isinstance(v, (int, float)): return 0
    if isinstance(v, str): return ""
    return None


def emptied(src, names):
    """The template form: every owned constant emptied, and any comment on the same line as a
    scalar removed — a comment beside the imputed-rent scalar was one owner's reasoning about her rent."""
    for name in names:
        try:
            a, b = span(src, name)
        except KeyError:
            continue
        src = src[:a] + json.dumps(empty_like(names[name])) + src[b:]
        m = re.search(r'^const ' + name + r'\s*=\s*[^;\n]*;([ \t]*//[^\n]*)', src, re.M)
        if m:
            src = src[:m.start(1)] + src[m.end(1):]
    return src


def sync_figures(root, out):
    """FINANCE.md states every current figure once, in a keyed table that D15 checks against the
    page. The table is a build product like the dashboards: its values follow findata/, its keys
    and labels are the owner's (a translated label survives)."""
    fin = os.path.join(root, "FINANCE.md")
    if not os.path.exists(fin):
        return None
    inv, pb = out["INVEST"], out["PLAN_BASE_DEFAULT"]
    fj, plan = out["FOREIGN"], out["FUNDS"]["plan"]
    nw = inv["netWorth"] + round(fj["total"] * fj["cadPerUnit"])
    port = inv["portfolio"]
    tgt = pb * 300
    val = {"plan_base": f"${pb:,} /mo", "fire_target": f"${tgt:,}", "net_worth": f"${nw:,}",
           "portfolio": f"${port:,}",
           "progress": f"{round(port / tgt * 100, 1) if tgt else 0}%", "gap": f"${tgt - port:,}",
           "invest_monthly": f"${flow_totals(plan)['invest']:,}", "everyday": f"${flow_totals(plan)['allowance']:,}",
           "big_threshold": f"${plan['bigThreshold']:,}", "dry_powder": f"{inv['dryPct']}%"}
    topup = next((f for f in out["FUNDS"]["funds"] if f.get("role") == "topup"), None)
    if topup and topup.get("goal"):
        val["travel_goal"] = f"${topup['goal']:,}"
    text, hits = open(fin, encoding="utf-8").read(), []
    for key, v in val.items():
        pat = re.compile(r'^(\| *' + key + r' *\|[^|]*\| *)([^|]*?)( *\|)', re.M)
        if pat.search(text):
            new_text = pat.sub(lambda m: m.group(1) + v + m.group(3), text, count=1)
            if new_text != text:
                hits.append(key); text = new_text
    if not topup:
        text = re.sub(r'^\| *travel_goal *\|.*\n', "", text, flags=re.M)
    open(fin, "w", encoding="utf-8").write(text)
    return hits


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 and not argv[1].startswith("--") else os.getcwd()
    write = "--write" in argv
    template = argv[argv.index("--template") + 1] if "--template" in argv else None
    out = derive(load(root))

    files = []
    tdir = os.path.join(root, "templates", "dashboards")
    for n in MAIN_NAMES:
        if os.path.exists(os.path.join(root, "dashboards", n)):
            files.append(("main", n)); break
    else:
        # No main dashboard yet (a fresh sync, the demo build): it is created from the template.
        if os.path.exists(os.path.join(tdir, "finance_dashboard.html")):
            files.append(("main", "finance_dashboard.html"))
    if os.path.exists(os.path.join(tdir, INV_NAME)):
        files.append(("inv", INV_NAME))
    elif os.path.exists(os.path.join(root, "dashboards", INV_NAME)):
        # A built page whose template is gone (the investment dashboard, merged into the main page
        # on 2026-09-10). dashboards/ is a build product, and this is the one script that writes
        # it, so it is also the one that removes what no longer builds.
        if write:
            os.remove(os.path.join(root, "dashboards", INV_NAME))
            print(f"  − dashboards/{INV_NAME}: removed, its pages are in the main dashboard now")
        else:
            print(f"  · dashboards/{INV_NAME} has no template any more; --write removes it")
    if not files:
        raise SystemExit("no dashboard found under dashboards/ and no template under templates/dashboards/")
    os.makedirs(os.path.join(root, "dashboards"), exist_ok=True)

    print(f"=== rebuild — {len(out)} constants derived from findata/ ===")
    total_changes = 0
    for which, fn in files:
        path = os.path.join(root, "dashboards", fn)
        src = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        want = wanted(out, which)
        # The template is the source when the workspace has one: dashboards/ is then a build
        # product of templates/dashboards/ + findata/, and editing page code means editing the
        # template. The messages below still describe the change against the current page.
        tname = "finance_dashboard.html" if which == "main" else fn
        tpath = os.path.join(root, "templates", "dashboards", tname)
        tsrc = open(tpath, encoding="utf-8").read() if os.path.exists(tpath) else None
        changes, insync, skipped = [], [], []
        for name, val in want.items():
            # The template is filled on its own: a constant the template carries and the built
            # page does not yet (BROKER, the first time) must still reach the build. The first
            # version skipped the template whenever the page raised, so a new constant rendered
            # as its empty form on every page that used it (2026-09-09).
            if tsrc is not None:
                try:
                    tsrc, _ = apply_one(tsrc, name, val)
                except KeyError:
                    skipped.append(f"{name}: no `const {name} =` in templates/dashboards/{tname}")
            try:
                src2, msg = apply_one(src, name, val)
            except KeyError:
                if tsrc is None:
                    # Not silent: a constant this script believes it maintains, that the page does
                    # not expose under that exact name, is a sync doing nothing at all.
                    skipped.append(f"{name}: no `const {name} =` in {fn}")
                else:
                    changes.append(f"{name}: new on this page")
                continue
            if msg:
                changes.append(msg); src = src2
            else:
                insync.append(name)
        if tsrc is not None:
            # Page code changed in the template, or a constant the page did not carry: the
            # built file follows the template even when every constant already agreed.
            if tsrc != src and not changes:
                changes.append("page code follows templates/dashboards/" + tname)
            src = tsrc
        if src:
            src = finish(which, src, next((n for w, n in files if w == "main"), "finance_dashboard.html"))
        if which == "main" and src:
            # A field nobody reads and nobody maintains is not harmless: INVEST once carried a
            # FIRE target for a month after the target moved, invisible on the page and ready to
            # be believed by the next rebuild.
            ia, ib = span(src, "INVEST")
            orphan = [k for k in json.loads(src[ia:ib]) if k not in want["INVEST"] and f"INVEST.{k}" not in src]
            if orphan:
                skipped.append("INVEST has fields nobody reads and rebuild does not maintain: " + ", ".join(orphan))
        print(f"\n  {fn}" + ("  (from templates/dashboards/" + tname + ")" if tsrc is not None else ""))
        if insync:
            print(f"    ✓ in sync ({len(insync)}): " + ", ".join(sorted(insync)))
        for m in changes: print(f"    → {m}")
        for m in skipped: print(f"    ⚠ {m}")
        total_changes += len(changes)
        if template:
            os.makedirs(template, exist_ok=True)
            tname = "finance_dashboard.html" if which == "main" else fn
            open(os.path.join(template, tname), "w", encoding="utf-8").write(emptied(src, want))
            print(f"    template → {os.path.join(template, tname)}")
        elif write and changes:
            open(path, "w", encoding="utf-8").write(src)
            print(f"    written. Run the checkers.")
    if write:
        hits = sync_figures(root, out)
        if hits:
            print(f"\n  FINANCE.md: figures updated — " + ", ".join(hits))
    if not write and not template and total_changes:
        print(f"\n  {total_changes} change(s) NOT written. Re-run with --write to apply.")
    elif not total_changes and not template:
        print("\n  nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
