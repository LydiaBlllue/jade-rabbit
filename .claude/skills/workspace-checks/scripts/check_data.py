#!/usr/bin/env python3
"""Check findata/ for the mistakes that make the numbers wrong.

The UI linter protects how things look. This one protects whether they are true,
which matters more: a miscategorised $111 charge moved the FIRE target by $33,000.
Every check here comes from something that actually went wrong.

Usage:  python3 check_data.py [workspace-root]
Exit:   0 clean or notes only, 1 if any ERROR
"""
import csv, json, os, re, sys, collections, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "update-dashboard", "scripts"))
from flows import totals as flow_totals, KINDS as FLOW_KINDS   # the plan's sums, read once, there
import layout                                                   # where each findata file lives

CATEGORIES = {"Grocery","Subscription","Dining","Shopping","Transport","Entertainment","Other"}
# SOURCES and LEDGERS are read from findata/accounts.json, not written out here. A table
# copied into a script drifts exactly like one copied into a document: accounts.json
# gained spendTag / stmtTag / ledger on 2026-09-08 so there is one place to change.
def _registry(root):
    with open(layout.path(root, "accounts.json"), encoding="utf-8") as fh:
        accs = json.load(fh)["accounts"]
    src = {a["spendTag"] for a in accs if a.get("spendTag")}
    led = [(a["ledger"], " ".join(x for x in (a["inst"], a["name"], a.get("id")) if x and x != "\u2014"))
           for a in accs if a.get("ledger")]
    return src, sorted(led)
NOISE      = {"SP","SQ","WL","TST","PADDLE.NET","LS"}


# ===== categories =====
# The five questions these checks answer. Added 2026-09-08 after the owner pointed out that the
# script had stopped being a linter: a broken balance chain and a stale README link were coming
# out through the same channel, with the same mark, at the same severity. The category rides on
# each FINDING rather than on the rule, because one rule legitimately produces more than one kind
# of problem -- D14 reports both "this registry contradicts itself" (rules) and "the page is
# stale" (build), and calling those the same thing is what the split is meant to stop.
CATS = [("reconcile", "does the money add up on its own terms"),
        ("rules",     "is a rule in FINANCE.md being broken"),
        ("build",     "is the artefact current with findata/"),
        ("hygiene",   "is the data itself clean"),
        ("conform",   "does it still follow DESIGN.md")]
CAT_ORDER = [c[0] for c in CATS]
CAT_LABEL = {c[0]: c[1] for c in CATS}


def render(title, F, verbose=False):
    """Group by category, most consequential first. Money that does not add up outranks a
    documentation link that has rotted, and the output has to say so without being read closely."""
    print(f"\n=== {title} ===")
    bad = 0
    if not F:
        print("  \u2713 nothing to check here")
        return 0
    for cat in CAT_ORDER:
        rows = [f for f in F if f[3] == cat]
        if not rows:
            continue
        errs = [r for r in rows if r[0] == "ERROR"]
        warns = [r for r in rows if r[0] == "WARN"]
        bad += len(errs)
        mark = "\u2717" if errs else ("\u26a0" if warns else "\u2713")
        tally = (f"{len(errs)} problem" + ("s" if len(errs) != 1 else "")) if errs \
                else (f"{len(warns)} to look at" if warns else f"{len(rows)} checks")
        print(f"  {cat:<10} {mark} {tally}")
        for sev, rule, msg, _ in errs + warns:
            m2 = "\u2717" if sev == "ERROR" else "\u26a0"
            print(f"     {m2} [{rule}] {msg}")
        if verbose:
            for _, rule, msg, _c in [r for r in rows if r[0] == "NOTE"]:
                print(f"     \u00b7 [{rule}] {msg}")
    return bad

def const_field(src, const, field):
    """One field out of `const NAME = {...}` on a single line, matched by NAME rather than by the
    order the fields happen to be written in. Positional regexes broke the moment FOREIGN gained
    currency / symbol / label (2026-09-09), which is the sort of edit a checker should survive."""
    blk = re.search(r"const " + const + r" = \{[^\n]*", src)
    if not blk:
        return None
    # The key may be bare (`asof:`) in a hand-written literal or quoted (`"asof":`) once
    # rebuild.py writes the constant as JSON; both are the same field.
    m = re.search(r'"?\b' + field + r'"?\s*:\s*"?([\d.\-]+)"?', blk.group(0))
    return m.group(1) if m else None


def brand(note):
    t = re.sub(r'\s*\[[^\]]+\]\s*$', '', note).replace("*"," ").replace(","," ").upper().split()
    return t[1] if len(t) > 1 and t[0].rstrip("-") in NOISE else (t[0] if t else note.upper())

def merchant_key(note):
    """Finer than brand(): keeps the service apart, drops the order ids and city."""
    n = re.sub(r'\s*\[[^\]]+\]\s*$', '', note)
    n = re.sub(r'\s*\([^)]*\)', '', n)
    n = re.sub(r'\*[A-Z0-9]{5,}', '', n)
    n = re.sub(r'\b\d{3}-\d{3}-\d{4}\b|\*+\d+|#\d+', '', n)
    n = re.sub(r'\s+(ON|QC|BC|CA|NY|WA)\b.*$', '', n)
    return re.sub(r'\s{2,}', ' ', n).strip(' ,-').upper()

def load(root, name):
    p = layout.path(root, name)
    return p if os.path.exists(p) else None

def check(root):
    # Each rule has a home category; a call may override it, because several rules produce more
    # than one kind of finding. D14 is the clearest case: "this document covers an account that
    # does not exist" is a rules problem, "ACCT no longer matches accounts.json" is a build one.
    HOME = {"D1":"reconcile", "D7":"reconcile", "D8":"reconcile",
            "D3":"rules", "D5":"rules", "D6":"rules", "D10":"rules", "D13":"rules", "D14":"rules",
            "D11":"build", "D12":"build", "D17":"build", "T1":"build", "T2":"hygiene", "D15":"build", "D16":"conform",
            "D2":"hygiene", "D4":"hygiene", "D9":"hygiene", "D18":"hygiene",
            "D19":"rules", "D20":"hygiene", "D21":"rules", "D22":"hygiene"}
    F = []          # (severity, rule, message, category)
    def err(r, m, cat=None):  F.append(("ERROR", r, m, cat or HOME.get(r, "rules")))
    def warn(r, m, cat=None): F.append(("WARN",  r, m, cat or HOME.get(r, "rules")))
    def note(r, m, cat=None): F.append(("NOTE",  r, m, cat or HOME.get(r, "rules")))
    today = datetime.date.today()
    SOURCES, LEDGERS = _registry(root)

    # -- D1 every ledger's balance column must actually chain -----------------
    closing = {}
    for fn, label in LEDGERS:
        p = load(root, fn)
        if not p:
            warn("D1", f"{fn} is missing"); continue
        rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
        prev, breaks = None, 0
        for r in rows:
            bal, amt = float(r["balance"]), float(r["amount"])
            if prev is not None and abs(prev + amt - bal) > 0.005:
                err("D1", f"{fn} {r['date']} {r['description'][:34]}: "
                          f"{prev:,.2f} + {amt:,.2f} != {bal:,.2f}")
                breaks += 1
            prev = bal
        closing[label] = prev
        if not rows:
            # A ledger with only its header is a workspace that has been set up but not yet
            # imported into. That is a state, not a fault — the first statement fills it.
            note("D1", f"{fn}: no rows yet — nothing imported into this ledger")
        elif not breaks:
            note("D1", f"{fn}: {len(rows)} rows, balance chain closes at {prev:,.2f}")

    # -- spending.csv ---------------------------------------------------------
    p = load(root, "spending.csv")
    sp = list(csv.DictReader(open(p, encoding="utf-8-sig"))) if p else []
    if sp:
        seen = collections.Counter()
        by_brand = collections.defaultdict(list)
        for r in sp:
            # D2 the statement tag is what the dashboard parses the account column from
            m = re.search(r'\[([A-Z0-9]+)/(\d{8})\]\s*$', r["note"])
            if not m:
                err("D2", f"spending.csv {r['date']} {r['note'][:40]}: no [SOURCE/YYYYMMDD] tag")
            elif m.group(1) not in SOURCES:
                err("D2", f"spending.csv {r['date']}: unknown source tag {m.group(1)}")
            # D3 the seven categories are the shared vocabulary; a new one needs the owner
            if r["category"] not in CATEGORIES:
                err("D3", f"spending.csv {r['date']}: category '{r['category']}' is not one of the seven")
            seen[(r["date"], r["amount"], r["note"])] += 1
            by_brand[brand(r["note"])].append(r)
        # D4 the merge is meant to dedupe on date+amount+merchant
        for k, n in seen.items():
            if n > 1:
                err("D4", f"spending.csv has {n} identical rows: {k[0]} {k[1]} {k[2][:40]}")
        # D5 a subscription is a charge that repeats
        for b, rs in sorted(by_brand.items()):
            if len(rs) == 1 and rs[0]["category"] == "Subscription":
                warn("D5", f"{b} is filed as Subscription but appears once ({rs[0]['date']}, "
                           f"${rs[0]['amount']}). A subscription repeats — confirm before it "
                           "hardens into the FIRE baseline.")
        # D6 merchants.json is meant to be the one place a merchant is decided
        mp = load(root, "merchants.json")
        if mp:
            mj = json.load(open(mp, encoding="utf-8"))
            table = {e["match"]: e for e in mj.get("merchants", [])}
            by_merch = collections.defaultdict(list)
            for r in sp: by_merch[merchant_key(r["note"])].append(r)
            for mk, rs in sorted(by_merch.items()):
                cats = {r["category"] for r in rs}
                if len(cats) > 1:
                    err("D6", f'"{mk}" is filed under {sorted(cats)} in different rows — '
                              "one merchant, one category")
                if mk and mk not in table and len(rs) >= 2:
                    warn("D6", f'"{mk}" appears {len(rs)} times but is not in merchants.json — '
                               "every merchant should be decided once, there")
            for e in mj.get("merchants", []):
                if e.get("confirmed_by"):
                    hits = [r for r in sp if e["match"].split()[0] in r["note"].upper()]
                    bad = {r["category"] for r in hits} - {e["category"]}
                    if bad:
                        err("D6", f"{e['match']} is confirmed as {e['category']} by "
                                  f"{e['confirmed_by']} but rows use {sorted(bad)}")

    # -- D7 banks.json should agree with the ledger it has ---------------------
    bp = load(root, "banks.json")
    if bp:
        bj = json.load(open(bp, encoding="utf-8"))
        # banks.json names an account the way the register does; the ledger label is the same
        # inst + name + id the D1 loop used. Was a map of three of one owner's accounts.
        with open(layout.path(root, "accounts.json"), encoding="utf-8") as fh:
            _accs = json.load(fh)["accounts"]
        pair = {a["name"]: " ".join(x for x in (a["inst"], a["name"], a.get("id")) if x and x != "\u2014")
                for a in _accs if a.get("ledger")}
        for a in bj.get("assets", []):
            lab = pair.get(a.get("account"))
            # A ledger with no rows yet (a fresh setup) closes at nothing; D7 has nothing to compare.
            if lab and closing.get(lab) is not None and a.get("balance") is not None:
                if abs(a["balance"] - closing[lab]) > 0.005:
                    err("D7", f"banks.json {a['inst']} {a['account']} = {a['balance']:,.2f} but "
                              f"the ledger closes at {closing[lab]:,.2f}")

    # -- D8 the foreign-currency total has to be the sum of its accounts ------------------
    cp = load(root, "foreign.json")
    if cp:
        fj = json.load(open(cp, encoding="utf-8"))
        sym = fj.get("symbol", "")
        tot = sum(a["value"] for a in fj.get("accounts", []))
        if abs(tot - fj.get("total", 0)) > 0.01:
            err("D8", f"foreign.json total {fj.get('total')} != sum of accounts {tot:.2f}")
        for a in fj.get("accounts", []):
            if a.get("inst") in (None, "待确认"):
                warn("D8", f"foreign.json: {a['name'][:30]} has no confirmed institution "
                           f"({sym}{a['value']:,.0f})")

    # -- D9 a carried-forward rate quietly rots ------------------------------
    fp = load(root, "fx.json")
    if fp:
        fj = json.load(open(fp, encoding="utf-8"))
        age = (today - datetime.date(*map(int, fj["asof"].split("-")))).days
        # A rate carried forward for a day or two is not stale; it is simply the newest one
        # anybody has. The complaint is that it has been carried for a WHILE (rule 9's
        # 30 days), which is also why a workspace set up today should not be scolded.
        if fj.get("quality") == "carried-forward" and age > 30:
            err("D9", f"fx.json is carried-forward from {fj['asof']} ({age}d). The Wealthsimple "
                      "activities export carries the broker's own rate — take it from there.")
        elif age > 45:
            warn("D9", f"fx.json is {age} days old ({fj['asof']}, {fj.get('quality')})")
        else:
            note("D9", f"fx.json {fj['usd_cad']} @ {fj['asof']} ({fj.get('quality')}), {age}d old")

    # -- D10 money back from a counterparty is a repayment, never income ---------
    # The register's document that carries `counterparty` names the person and, through `into`,
    # the ledger of what they owe (a friend, a family member) -- schema 9; it used to sit in
    # cashflow.json. An e-Transfer on a bank ledger that matches a row of that ledger, by month
    # and amount, must be typed Repayment -- typed anything else it would be counted as income.
    with open(layout.path(root, "accounts.json"), encoding="utf-8") as fh:
        _docs = json.load(fh).get("documents", [])
    cp = next(({"name": x["counterparty"], "ledger": x.get("into")} for x in _docs if x.get("counterparty")), None)
    lp = load(root, cp["ledger"]) if cp and cp.get("ledger") else None
    if load(root, "cashflow.json"):
        err("D18", "findata/ledgers/cashflow.json is retired: the rows are derived from the ledgers at build "
                   "and the counterparty is the register's. Run tools/migrate.py on this workspace", "hygiene")
    if cp and lp:
        back = [(r["date"], float(r["amount"])) for r in csv.DictReader(open(lp, encoding="utf-8-sig"))
                if (r.get("currency") or "CAD") == "CAD"]
        for fn, label in LEDGERS:
            lpath = load(root, fn)
            if not lpath:
                continue
            for r in csv.DictReader(open(lpath, encoding="utf-8-sig")):
                for d, amt in back:
                    if abs(float(r["amount"]) - amt) < .01 and r["date"][:7] == d[:7] \
                       and "e-TransferReceived" in r["description"].replace(" ", ""):
                        if r.get("type") == "Repayment":
                            note("D10", f"{fn} {r['date']} ${amt:,.0f} = {cp['name']}'s ledger {d}, typed Repayment ✓")
                        else:
                            err("D10", f"{fn} {r['date']} ${amt:,.0f} matches {cp['name']}'s ledger {d} but is "
                                       f"typed {r.get('type') or 'nothing'!r}, not Repayment — it would count as income")

    # -- D11 the dashboard's baked-in numbers have to match findata ----------
    # The main dashboard: an owner's copy may still carry the old `ly_` name; the template and any
    # fresh workspace use `finance_dashboard.html`. A hardcoded name here made every page check
    # silently skip on the demo repository (2026-09-09, caught by the selftest).
    dash = next((os.path.join(root, "dashboards", n) for n in ("ly_finance_dashboard.html", "finance_dashboard.html")
                 if os.path.exists(os.path.join(root, "dashboards", n))),
                os.path.join(root, "dashboards", "finance_dashboard.html"))
    hp = load(root, "investment_history.json")
    if os.path.exists(dash) and hp:
        src = open(dash, encoding="utf-8").read()
        inv = json.loads(re.search(r'^const INVEST = (\{.*\});$', src, re.M).group(1))
        # No snapshots yet means no import has happened; there is nothing to disagree with.
        snaps = json.load(open(hp, encoding="utf-8"))["snapshots"]
        snap = snaps[-1] if snaps else None
        if snap and abs(inv["investable"] - snap["cadInv"]) > 1:
            err("D11", f"dashboard INVEST.investable {inv['investable']:,} != "
                       f"investment_history latest cadInv {snap['cadInv']:,}")
        if snap and abs(inv["dryPct"] - snap["dryPct"]) > 0.05:
            err("D11", f"dashboard dryPct {inv['dryPct']} != history {snap['dryPct']}")
        nw = re.findall(r'\{ym:"(\d{4}-\d{2})",\s*v:(\d+)\}', src)
        if nw:
            ym, v = nw[-1]
            f_tot = const_field(src, "FOREIGN", "total")
            f_rate = const_field(src, "FOREIGN", "cadPerUnit")
            expect = inv["netWorth"] + (round(float(f_tot) * float(f_rate)) if f_tot and f_rate else 0)
            if abs(int(v) - expect) > 2:
                err("D11", f"NW_HISTORY latest ({ym}) is {int(v):,} but netWorth + foreign is {expect:,}")

    # 2026-09-08: found by selftest.py, which planted a drifted foreign.json and watched every rule
    # stay quiet. D8 checks foreign.json against ITSELF and D14 checks accounts.json against it, but
    # nothing compared the dashboard's own FOREIGN constant to the file -- so foreign's contribution to
    # net worth could go stale silently. rebuild.py would fix it; nothing would report it.
    cp3 = load(root, "foreign.json")
    if os.path.exists(dash) and cp3:
        src = open(dash, encoding="utf-8").read()
        cj3 = json.load(open(cp3, encoding="utf-8"))
        d_asof = const_field(src, "FOREIGN", "asof")
        d_total = const_field(src, "FOREIGN", "total")
        m6 = d_asof and d_total
        if not m6:
            err("D11", "the dashboard has no FOREIGN constant to check")
        else:
            if d_asof != cj3["asof"]:
                err("D11", f"dashboard FOREIGN.asof {d_asof} != foreign.json {cj3['asof']}")
            if abs(float(d_total) - cj3["total"]) > 0.01:
                err("D11", f"dashboard FOREIGN.total {d_total} != foreign.json "
                           f"{cj3['total']} — the foreign share of net worth is stale")

    # -- D17 both dashboards agree with profile.json about whose workspace this is ------
    # 2026-09-09: the brand rename reached the main page and not the investment page, which went on
    # saying "LY Finance" in its title and in the link back. rebuild.py had a sync step for it, but
    # that step sat after an early return that fires whenever the main page needs no change -- so it
    # ran only by accident. Nothing compared the two files, so nothing said a word.
    inv_dash = os.path.join(root, "dashboards", "investment_dashboard.html")
    # RULES is the same contract as PROFILE: a file in findata/ that the page copies. Since
    # 2026-09-10 the strategy panel is in the main dashboard; inv_dash is checked only while an
    # older workspace still has the second file on disk.
    for const, srcfile, pages in (("PROFILE", "profile.json", (dash, inv_dash)),
                                  ("RULES", "rules.json", (dash, inv_dash))):
      pp = load(root, srcfile)
      if pp:
        prof = json.load(open(pp, encoding="utf-8"))
        want = {k: v for k, v in prof.items() if k != "note" and not k.startswith("zh_")}
        for f in pages:
            if not os.path.exists(f):
                continue
            fsrc = open(f, encoding="utf-8").read()
            m = re.search(r'^const ' + const + r' = (\{.*?\});', fsrc, re.M)
            if not m:
                err("D17", f"{os.path.basename(f)} has no {const} constant — it is typed in "
                           f"somewhere instead of being read from {srcfile}")
                continue
            got = json.loads(m.group(1))
            if got != want:
                diff = [k for k in set(got) | set(want) if got.get(k) != want.get(k)]
                err("D17", f"{os.path.basename(f)} {const} disagrees with {srcfile} on "
                           + ", ".join(sorted(diff)) + " — run rebuild.py --write")

    # -- T1 the dashboards are a build of templates/dashboards/ + findata/, and nothing else -----
    # 2026-09-09: the page used to carry about twenty constants nobody derived, which is why a
    # public copy had to be scrubbed and a new owner inherited the previous one's holdings. Now
    # the template holds no data at all, and the built page is exactly template + findata --
    # both of which this checks, so a constant typed straight into dashboards/ is caught.
    tdir = os.path.join(root, "templates", "dashboards")
    rbp = os.path.join(root, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py")
    if os.path.isdir(tdir) and os.path.exists(rbp):
        import importlib.util
        spec = importlib.util.spec_from_file_location("rebuild", rbp)
        rb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rb)
        try:
            derived = rb.derive(rb.load(root))
        except SystemExit as e:
            err("T1", f"rebuild.py cannot derive the constants: {e}")
            derived = None
        for which, tname, built in (("main", "finance_dashboard.html", dash),
                                    ("inv", "investment_dashboard.html", inv_dash)):
            tp = os.path.join(tdir, tname)
            if not derived or not os.path.exists(tp) or not os.path.exists(built):
                continue
            tsrc = open(tp, encoding="utf-8").read()
            bsrc = open(built, encoding="utf-8").read()
            want = rb.wanted(derived, which)
            for name, val in want.items():
                try:
                    a, b = rb.span(tsrc, name)
                except KeyError:
                    continue
                try:
                    cur = json.loads(tsrc[a:b])
                except ValueError:
                    err("T1", f"templates/dashboards/{tname}: `{name}` is not JSON"); continue
                if cur not in ({}, [], 0, "", None, False):
                    err("T1", f"templates/dashboards/{tname}: `{name}` is not empty — "
                              f"somebody's data is in the template")
            # The build date is the one thing allowed to differ: take it from the built page.
            try:
                a, b = rb.span(bsrc, "TODAY")
                want["TODAY"] = json.loads(bsrc[a:b])
            except (KeyError, ValueError):
                pass
            try:
                a, b = rb.span(bsrc, "DATA")
                want["DATA"] = dict(want["DATA"], today=json.loads(bsrc[a:b]).get("today"))
            except (KeyError, ValueError):
                pass
            for name, val in want.items():
                try:
                    tsrc, _ = rb.apply_one(tsrc, name, val)
                except KeyError:
                    pass
            tsrc = rb.finish(which, tsrc, os.path.basename(dash))
            if tsrc != bsrc:
                err("T1", f"dashboards/{os.path.basename(built)} is not what templates/ + findata/ "
                          f"build — something was edited in place. Run rebuild.py --write")

    # -- T2 filings.json and archive/ agree on what has ever been filed ---------------------
    # The filing grid was a constant typed into the page; it is a file the import step writes
    # when it archives a document. A month filed with no archived file behind it is a claim
    # without evidence; a tag in archive/ that never got a month is evidence nobody recorded.
    fil_p, acc_p = load(root, "filings.json"), load(root, "accounts.json")
    if fil_p and acc_p:
        filed = json.load(open(fil_p, encoding="utf-8")).get("filed", {})
        docs2 = json.load(open(acc_p, encoding="utf-8")).get("documents", [])
        tags_of = {d2["key"]: set(d2.get("tags", [])) for d2 in docs2}
        in_use = set()
        arc = os.path.join(root, "archive")
        if os.path.isdir(arc):
            known = {t for ts in tags_of.values() for t in ts}
            for f_ in os.listdir(arc):
                m5 = re.match(r"\d{8}_(.+)$", f_)
                if m5:
                    hit = next((t for t in sorted(known, key=len, reverse=True)
                                if m5.group(1).startswith(t + "_")), None)
                    if hit:
                        in_use.add(hit)
        for key, months in filed.items():
            if key not in tags_of:
                err("T2", f"filings.json files '{key}' but accounts.json has no document with that key")
            elif months and tags_of[key] and os.path.isdir(arc) and not (tags_of[key] & in_use):
                err("T2", f"filings.json says '{key}' was filed {len(months)} time(s) but archive/ "
                          f"holds nothing tagged {sorted(tags_of[key])}")
        for key, ts in tags_of.items():
            if ts & in_use and not filed.get(key):
                warn("T2", f"archive/ holds files tagged {sorted(ts & in_use)} but filings.json has "
                           f"no month for '{key}'")

    # -- D12 every row of spending.csv has to reach the dashboard ------------
    # 2026-09-07: the 2025-12-24 OpenAI charge sat in spending.csv but not in the dashboard --
    # 190 rows against 189 -- and nobody had decided that; it fell out of a rebuild. The right
    # way to drop a month from a statistic is MONTH_SKIP, which is named and shown on the page.
    # Silently losing the row is not the same thing: it also loses it from totals and from the
    # statement reconciliation.
    if os.path.exists(dash):
        src = open(dash, encoding="utf-8").read()
        m = re.search(r'const SPENDING = (\[.*?\]);', src, re.S)
        sp = load(root, "spending.csv")
        if m and sp:
            def key(d, a_, n):
                return (d, round(float(a_), 2), re.sub(r"\s*\[[^\]]+\]\s*$", "", n).strip())
            with open(sp, encoding="utf-8") as fh:
                csv_rows = collections.Counter(key(r["date"], r["amount"], r["note"])
                                               for r in csv.DictReader(fh))
            dash_rows = collections.Counter(key(e["date"], e["amount"], e["note"])
                                            for e in json.loads(m.group(1)))
            for k in csv_rows - dash_rows:
                err("D12", f"spending.csv has {k[0]} ${k[1]:,.2f} {k[2][:38]} but the dashboard does not")
            for k in dash_rows - csv_rows:
                err("D12", f"dashboard has {k[0]} ${k[1]:,.2f} {k[2][:38]} but spending.csv does not")
            if not (csv_rows - dash_rows) and not (dash_rows - csv_rows):
                note("D12", f"spending.csv and the dashboard agree on all {sum(csv_rows.values())} rows")

    # -- D13 funds.json is the plan; the dashboard only carries a copy ------
    # Added 2026-09-07 with the guilt-free rebuild. Three separate things can drift here, and
    # each one silently makes the page lie: the baked-in copy falling behind the file, a Chinese
    # string reaching an English-only page (DESIGN.md §1 -- the first cut of this page rendered
    # the Chinese `why` fields straight onto the cards), and the two fund claims growing past the
    # bank cash they are claimed against, which is the only hard constraint the design has.
    fp = load(root, "funds.json")
    if fp and os.path.exists(dash):
        src = open(dash, encoding="utf-8").read()
        fj = json.load(open(fp, encoding="utf-8"))
        m = re.search(r'^const FUNDS = (\{.*?\});$', src, re.M)
        if not m:
            err("D13", "funds.json exists but the dashboard has no FUNDS constant", "build")
        elif json.loads(m.group(1)) != fj:
            err("D13", "dashboard FUNDS differs from findata/funds.json -- rebuild the page", "build")
        else:
            note("D13", "funds.json and the dashboard FUNDS constant agree")
        han = re.compile(r"[\u4e00-\u9fff]")
        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.startswith("zh_") or k == "asof_note":
                        continue
                    walk(v, path + "." + k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, path + f"[{i}]")
            elif isinstance(node, str) and han.search(node):
                err("D13", f"funds.json{path} is rendered on an English-only page but contains "
                           f"Chinese -- move the reason to a zh_ field", "conform")
        walk(fj, "")
        plan = fj["plan"]
        # Schema 5: the plan is flows. Each row needs a kind the tool knows and an amount; the
        # split (everything but income) has to fit inside income, the funds' monthly included.
        for f_ in plan.get("flows") or []:
            if f_.get("kind") not in FLOW_KINDS:
                err("D13", f"funds.json flow {f_.get('name') or f_.get('key')!r}: kind must be one of "
                           f"{', '.join(FLOW_KINDS)}, not {f_.get('kind')!r}")
            if not isinstance(f_.get("amount"), (int, float)) or f_["amount"] < 0:
                err("D13", f"funds.json flow {f_.get('name') or f_.get('key')!r} has no amount")
        # Schema 8: a fund's standing contribution is a saving flow that names the fund. A `monthly`
        # left on the fund is the same number said twice, and the page no longer reads it.
        fund_keys = {f.get("key") for f in fj["funds"]}
        for f in fj["funds"]:
            if "monthly" in f or "monthlyNote" in f:
                err("D13", f"funds.json fund {f.get('name') or f.get('key')!r} still carries `monthly` -- a standing "
                           "contribution is a saving flow with `to` (schema 8). Run tools/migrate.py")
        for f_ in plan.get("flows") or []:
            to = f_.get("to")
            if f_.get("kind") == "saving" and to not in (None, "broker") and to not in fund_keys:
                err("D13", f"funds.json flow {f_.get('name') or f_.get('key')!r} goes to {to!r}, which is neither "
                           "the broker nor a fund in this file")
        ft = flow_totals(plan)
        split = ft["committed"] + ft["saving"] + ft["allowance"]
        if split > ft["income"]:
            err("D13", f"the monthly split asks for ${split:,} against income of ${ft['income']:,}")
        # 2026-09-07: the funds moved off bank cash onto a named Wealthsimple account, so the claim
        # has to be checked against THAT account. A stale backing.balance is the failure that
        # matters -- the page would keep reporting a goal as funded out of money that is not there.
        hp2 = load(root, "holdings_latest.csv")
        acct = {}
        if hp2:
            fxp = load(root, "fx.json")
            fx = json.load(open(fxp, encoding="utf-8"))["usd_cad"] if fxp else None
            with open(hp2, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    n, mv, cur = r.get("Account Number"), r.get("Market Value"), r.get("Market Value Currency")
                    if not n or not mv:
                        continue
                    v = float(mv)
                    if cur == "USD":
                        if fx is None:
                            continue
                        v *= fx
                    acct[n] = acct.get(n, 0) + v
        claims = collections.defaultdict(float)
        for f in fj["funds"]:
            claims[f["backing"]["account"]] += f["opening"]["amount"]
        for a, c in claims.items():
            stated = next(f["backing"]["balance"] for f in fj["funds"] if f["backing"]["account"] == a)
            real = acct.get(a)
            if real is not None and abs(real - stated) > max(50, real * 0.01):
                err("D13", f"funds.json says {a} holds ${stated:,.0f} but holdings_latest.csv "
                           f"totals ${real:,.0f}", "reconcile")
            if c > stated:
                err("D13", f"the funds claim ${c:,.0f} against {a}, which holds ${stated:,.0f}")
            else:
                note("D13", f"funds claim ${c:,.0f} of ${stated:,.0f} in {a}, "
                            f"${stated - c:,.0f} unclaimed")

    # -- D14 accounts.json is a registry, not a second set of books ---------
    # Added 2026-09-07 with the Accounts page. The registry repeats balances that live in three
    # other files, and a repeated number is a number that drifts. Re-derive every one from its
    # stated source and fail on a mismatch -- a stale row here would quietly show a balance that
    # no longer exists, on the one page whose whole job is saying where the money is.
    ap = load(root, "accounts.json")
    if ap:
        aj = json.load(open(ap, encoding="utf-8"))
        if os.path.exists(dash):
            m2 = re.search(r'^const ACCT = (\{.*?\});$', open(dash, encoding="utf-8").read(), re.M | re.S)
            if not m2:
                err("D14", "accounts.json exists but the dashboard has no ACCT constant", "build")
            elif json.loads(m2.group(1)) != aj:
                err("D14", "dashboard ACCT differs from findata/accounts.json -- rebuild the page", "build")
        # A Chinese proper noun inside an English sentence is fine and already appears elsewhere
        # (a bank's name, a fund house, fund names). A Chinese *sentence* on an English page is not. Judge by
        # density and by CJK punctuation rather than by the presence of any han character at all.
        han = re.compile(r"[\u4e00-\u9fff]")
        # NB: not the em dash. U+2014 is ordinary English punctuation and is used throughout
        # this workspace; including it here flagged two pure-English sentences as Chinese.
        cjk_punct = re.compile(r"[\uff0c\u3002\u3001\uff1a\uff1b\u300c\u300d\uff08\uff09]")
        def chinese_prose(t):
            t = str(t or "")
            if not t:
                return False
            n = len(han.findall(t))
            return bool(cjk_punct.search(t)) or (n and n / len(t) > 0.30)
        for a in aj["accounts"]:
            for k in ("name", "kind", "feeds", "note"):
                if chinese_prose(a.get(k)):
                    err("D14", f"accounts.json {a['inst']} {a['name']}.{k} reads as Chinese prose "
                               f"on an English-only page", "conform")
        for g in aj["gaps"]:
            for k in ("what", "why", "fix"):
                if chinese_prose(g.get(k)):
                    err("D14", f"accounts.json gap '{g['k']}'.{k} reads as Chinese prose", "conform")

        # Resolve each source explicitly. An earlier version matched loosely and every foreign.json
        # row matched the same account, which is worse than not checking at all: it reported
        # confident mismatches for accounts it had never actually looked up.
        bank_bal, hold_bal, fgn_bal = {}, {}, {}
        bp2 = load(root, "banks.json")
        if bp2:
            bj2 = json.load(open(bp2, encoding="utf-8"))
            for x in bj2["assets"]:
                if x.get("balance") is not None:
                    bank_bal[x["account"]] = x["balance"]
            for x in bj2["debts"]:
                bank_bal[x["account"]] = -x["balance"]
        hp3 = load(root, "holdings_latest.csv")
        if hp3:
            fxp2 = load(root, "fx.json")
            fx2 = json.load(open(fxp2, encoding="utf-8"))["usd_cad"] if fxp2 else None
            with open(hp3, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    n, mv, cur = r.get("Account Number"), r.get("Market Value"), r.get("Market Value Currency")
                    if not n or not mv:
                        continue
                    v = float(mv)
                    if cur == "USD":
                        if fx2 is None:
                            continue
                        v *= fx2
                    hold_bal[n] = hold_bal.get(n, 0) + v
        cp2 = load(root, "foreign.json")
        if cp2:
            for x in json.load(open(cp2, encoding="utf-8"))["accounts"]:
                fgn_bal[x["inst"]] = fgn_bal.get(x["inst"], 0) + x["value"]
        FGN_ALIAS = {"Unconfirmed bank": "待确认"}

        checked = 0
        for a in aj["accounts"]:
            src = a.get("src")
            if src in (None, "none") or a["balance"] is None:
                continue
            if src == "banks.json":
                hit = bank_bal.get(a["name"])
            elif src == "holdings_latest.csv":
                hit = hold_bal.get(a["id"])
            elif src == "foreign.json":
                hit = fgn_bal.get(FGN_ALIAS.get(a["inst"], a["inst"]))
            else:
                hit = None
            if hit is None:
                warn("D14", f"accounts.json {a['inst']} {a['name']}: nothing in {src} matches it")
            elif abs(hit - a["balance"]) > max(1, abs(hit) * 0.005):
                err("D14", f"accounts.json {a['inst']} {a['name']} says {a['balance']:,.2f} but "
                           f"{src} has {hit:,.2f}", "reconcile")
            else:
                checked += 1

        # Every gap an account points at has to exist, and every gap has to be either owned by an
        # account or explicitly standalone -- otherwise a gap gets fixed and its banner stays up.
        keys = {g["k"] for g in aj["gaps"]}
        owned = {a["gap"] for a in aj["accounts"] if a.get("gap")}
        for k in owned - keys:
            err("D14", f"an account is flagged with gap '{k}', which is not in the gaps list")
        for g in aj["gaps"]:
            if g["k"] not in owned and not g.get("standalone"):
                err("D14", f"gap '{g['k']}' belongs to no account and is not marked standalone")
        # 2026-09-08: accounts.json also became the registry of the DOCUMENTS the owner drops, which
        # until then lived in a second constant (SOURCES) and a third, dead one (IMPORTS) that
        # nothing rendered and that had already drifted. Three checks keep the join honest.
        docs = aj.get("documents", [])
        akeys = {a.get("key") for a in aj["accounts"]}
        if len(akeys) != len(aj["accounts"]) or None in akeys:
            err("D14", "every account needs a unique `key` — documents join on it")
        dkeys = [d["key"] for d in docs]
        if len(set(dkeys)) != len(dkeys):
            err("D14", "two documents share a key; SUBMITTED is keyed on it")
        # A document may name the parser that reads it (parsers/ in the update-dashboard skill).
        # A name no parser has would send every import of that file to a fallback it never
        # meant, silently.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "update-dashboard"))
            from parsers import NAMES as PARSER_NAMES
        except Exception:
            PARSER_NAMES = None
        for d in docs:
            if d.get("parser") and PARSER_NAMES is not None and d["parser"] not in PARSER_NAMES:
                err("D14", f"document '{d['key']}' names parser {d['parser']!r}; the tool has "
                           f"{', '.join(PARSER_NAMES)}")
            for c in d["covers"]:
                if c not in akeys:
                    err("D14", f"document '{d['key']}' covers '{c}', which is not an account")
            # Step 1 of the update-dashboard skill used to carry a hand-written table of
            # source -> target file -> reconciliation. It never grew a row for the BMO USD
            # account. The skill now reads these two fields instead, so a document without
            # them leaves the parser with no stated check to pass.
            for f in ("into", "reconcile"):
                if not d.get(f):
                    err("D14", f"document '{d['key']}' has no `{f}`; "
                               f"Step 1 reads it there instead of from a table")
        # SUBMITTED is the tracker grid. A key on one side and not the other means either a
        # column of ticks nobody asked for, or a source that can never be marked as filed.
        if os.path.exists(dash):
            src = open(dash, encoding="utf-8").read()
            m3 = re.search(r'^const SUBMITTED = (\{.*?\});$', src, re.M | re.S)
            if m3:
                sub = set(json.loads(m3.group(1)))
                need = {d["key"] for d in docs if not d.get("optional")}
                for k in sub - set(dkeys):
                    err("D14", f"SUBMITTED has '{k}' but no document by that name")
                for k in need - sub:
                    warn("D14", f"document '{k}' has no SUBMITTED row, so it can never be ticked")
            if not re.search(r'^const SOURCES = ACCT\.documents', src, re.M):
                err("D14", "SOURCES must be derived from ACCT.documents, not written out again")
        # Archive tags: the naming convention YYYYMMDD_<tag>_<original>. The list used to be
        # hand-copied into SKILL.md and lost three tags within a day of being written, so it
        # lives on the documents now and is checked against what archive/ actually contains.
        known = {t for dd in docs for t in dd.get("tags", [])}
        if sum(len(dd.get("tags", [])) for dd in docs) != len(known):
            err("D14", "two documents claim the same archive tag")
        arc = os.path.join(root, "archive")
        if os.path.isdir(arc):
            seen, unknown = set(), set()
            for f_ in os.listdir(arc):
                m5 = re.match(r"\d{8}_(.+)$", f_)
                if not m5:
                    continue
                rest = m5.group(1)
                hit = next((t for t in sorted(known, key=len, reverse=True)
                            if rest.startswith(t + "_")), None)
                (seen.add(hit) if hit else unknown.add(rest.split("_")[0]))
            if unknown:
                note("D14", "archive/ has files under no known tag: " + ", ".join(sorted(unknown)), "hygiene")
            if seen:
                note("D14", f"archive tags in use: {len(seen)} of {len(known)} declared", "hygiene")

        loose = sorted(akeys - {c for d in docs for c in d["covers"]})
        if loose:
            note("D14", "no document delivers: " + ", ".join(loose))
        note("D14", f"accounts.json: {len(aj['accounts'])} accounts, {len(docs)} documents, "
                    f"{checked} balances re-derived and matching, {len(aj['gaps'])} open gaps")

    # -- D19 the register's axes (schema 4): one value per axis, no illegal pairs ------------
    # Five axes give more ways to be wrong than one tag did. A liability with a role, an asset
    # with an `against`, a value that contradicts the source file, an `against` naming nothing:
    # each would make one total read one thing and the page say another (FINANCE.md §8a).
    if ap:
        SIDES, ROLES = ("asset", "liability"), ("grow", "set-aside", "buffer", "none")
        REACHES, VALUES = ("today", "costs", "spoken", "locked", "abroad"), ("export", "statement", "stated")
        V_OF_SRC = {"holdings_latest.csv": "export", "banks.json": "statement", "foreign.json": "statement"}
        keys_ = {a.get("key") for a in aj["accounts"]}
        side_of = {a.get("key"): a.get("side") for a in aj["accounts"]}
        n_ax = 0
        for a in aj["accounts"]:
            who = f"accounts.json {a['inst']} {a['name']}"
            if a.get("side") not in SIDES:
                err("D19", f"{who}: side must be asset or liability, not {a.get('side')!r}")
                continue
            if a.get("value") not in VALUES:
                err("D19", f"{who}: value must be export, statement or stated, not {a.get('value')!r}")
            want_v = V_OF_SRC.get(a.get("src"), "stated")
            if a.get("value") in VALUES and a.get("value") != want_v:
                err("D19", f"{who}: value is {a['value']} but its balance comes from "
                           f"{a.get('src') or 'nowhere'}, which makes it {want_v}")
            if a["side"] == "liability":
                for k in ("role", "reach"):
                    if a.get(k) is not None:
                        err("D19", f"{who}: a liability has no {k} — it is subtracted, not placed")
                ag = a.get("against")
                if ag is not None and (ag not in keys_ or side_of.get(ag) != "asset"):
                    err("D19", f"{who}: against names {ag!r}, which is not an asset in the register")
            else:
                if a.get("role") not in ROLES:
                    err("D19", f"{who}: role must be one of {', '.join(ROLES)}, not {a.get('role')!r}")
                if a.get("reach") not in REACHES:
                    err("D19", f"{who}: reach must be one of {', '.join(REACHES)}, not {a.get('reach')!r}")
                if a.get("against") is not None:
                    err("D19", f"{who}: only a liability sits against something")
            n_ax += 1
        # rules.json used to carry an exclude list that said the same thing as role = set-aside.
        # Since schema 7 the Investing pages read the axis, and the list must be gone: a list
        # nothing reads is the copy that goes stale (2026-09-10).
        rp2 = load(root, "rules.json")
        if rp2 and "exclude" in json.load(open(rp2, encoding="utf-8")):
            err("D19", "rules.json still carries exclude.accounts — set-aside is the register's role "
                       "axis and nothing reads the list. Run tools/migrate.py on this workspace")
        if not any(f[0] == "ERROR" and f[1] == "D19" for f in F):
            note("D19", f"accounts.json: {n_ax} rows carry consistent axes")

    # -- D20 a stated value is the owner's word, and a word has a date ----------------------
    # A home's value is the one number in the workspace nothing can re-derive (§8c). It gets a
    # date instead of a source, and a date that is a year old is a number that is a year old.
    if ap:
        today_ = datetime.date.today()
        for a in aj["accounts"]:
            if a.get("value") != "stated" or a.get("balance") is None:
                continue
            who = f"accounts.json {a['inst']} {a['name']}"
            if not a.get("asof"):
                err("D20", f"{who}: a stated balance needs an asof — nothing else can re-derive it")
                continue
            try:
                age = (today_ - datetime.date.fromisoformat(a["asof"])).days
            except ValueError:
                err("D20", f"{who}: asof {a['asof']!r} is not a date")
                continue
            if age > 365:
                warn("D20", f"{who}: stated {age} days ago and counted in net worth — restate it")

    # -- D21 a committed flow is declared, not observed: the ledger has to show it -----------
    # The plan says rent is $1,250 a month; the only proof is a $1,250 leaving a ledger every
    # month. Judged the way pay-yourself-first is judged (WSDEP): on what actually moved, in the
    # two whole months before the newest ledger date, so a payment due on the 1st of a month the
    # ledger only half covers is not "missing" yet.
    fp3 = load(root, "funds.json")
    if fp3 and ap:
        ft3 = flow_totals(json.load(open(fp3, encoding="utf-8")).get("plan", {}))
        rows_all = []
        for a in aj["accounts"]:
            lp = load(root, a["ledger"]) if a.get("ledger") else None
            if lp:
                with open(lp, encoding="utf-8") as fh:
                    rows_all += [(r["date"], float(r["amount"] or 0)) for r in csv.DictReader(fh) if r.get("date")]
        if ft3["committedNow"] and rows_all:
            newest = max(dt for dt, _ in rows_all)
            y, m = int(newest[:4]), int(newest[5:7])
            lo = f"{y - (1 if m <= 2 else 0):04d}-{((m - 3) % 12) + 1:02d}-01"
            hi = newest[:7] + "-01"
            unseen = 0
            for f_ in ft3["committedNow"]:
                amt = float(f_["amount"])
                hits = [dt for dt, v in rows_all if lo <= dt < hi and v < 0 and abs(-v - amt) <= max(1, amt * 0.01)]
                if not hits:
                    unseen += 1
                    warn("D21", f"the plan says {f_.get('name') or f_.get('key')} costs ${amt:,.0f} a month, but no ledger "
                               f"shows a payment of that size between {lo[:7]} and {hi[:7]} — declared, not observed")
            if not unseen:
                note("D21", f"{len(ft3['committedNow'])} committed flow(s) seen in the ledgers")
        elif ft3["committedNow"]:
            note("D21", "committed flows declared; no ledger yet to observe them in")

    # -- D15 FINANCE.md is a governing document with live numbers in it ------
    # Added 2026-09-08. DESIGN.md and README have had S4 watching them since 2026-09-06;
    # FINANCE.md had nothing, and it drifted exactly the way an unwatched document does: the net
    # worth was restated in four places and two of them were still measured against a target that
    # had been abandoned a day earlier. The fix was to state each figure ONCE, in a marked table,
    # and check that table here.
    fm = os.path.join(root, "FINANCE.md")
    if os.path.exists(fm) and os.path.exists(dash):
        txt = open(fm, encoding="utf-8").read()
        src = open(dash, encoding="utf-8").read()
        if "<!-- LINT:FIGURES" not in txt:
            err("D15", "FINANCE.md has no LINT:FIGURES table — its numbers are unchecked again")
        else:
            # The table is KEYED, not labelled: column 1 is a stable id, column 2 is whatever
            # the document calls it in whatever language, column 3 is the value. Until 2026-09-09
            # this parser matched the Chinese labels, so translating FINANCE.md would have made
            # D15 report "no figures table" -- a checker silenced by the very edit it polices.
            body = txt.split("<!-- LINT:FIGURES", 1)[1]
            head, sep, tail = body.partition("<!-- LINT:FIGURES:END -->")
            if not sep:
                err("D15", "FINANCE.md has no <!-- LINT:FIGURES:END --> marker, so D15 cannot "
                           "tell where the table stops and the prose starts")
            rows = {}
            for line in head.splitlines():
                if not line.startswith("|"):
                    continue
                c = [x.strip() for x in line.strip("|").split("|")]
                if len(c) >= 3 and re.fullmatch(r"[a-z][a-z0-9_]*", c[0]):
                    rows[c[0]] = (c[1], c[2])          # key -> (label shown, value)
            n = lambda t: float(re.sub(r"[^\d.]", "", t) or 0)

            inv = json.loads(re.search(r'^const INVEST = (\{.*?\});$', src, re.M | re.S).group(1))
            cm_t = const_field(src, "FOREIGN", "total")
            cm_r = const_field(src, "FOREIGN", "cadPerUnit")
            nw = inv["netWorth"] + (round(float(cm_t) * float(cm_r)) if cm_t and cm_r else 0)
            pb = int(re.search(r'const PLAN_BASE_DEFAULT = (\d+)', src).group(1))
            tgt = pb * 300
            fj2 = json.load(open(load(root, "funds.json"), encoding="utf-8"))
            # The fund is found by the role it plays, not by a name: this looked for the literal
            # key "travel", so a workspace whose funds are called anything else crashed the
            # checker outright (2026-09-09, found by the setup acceptance test).
            trav = next((f for f in fj2["funds"] if f.get("role") == "topup"), None)
            port = inv["portfolio"]
            want = {"plan_base": pb, "fire_target": tgt, "net_worth": nw, "portfolio": port,
                    "progress": round(port / tgt * 100, 1) if tgt else 0, "gap": tgt - port,
                    "invest_monthly": flow_totals(fj2["plan"])["invest"],
                    "everyday": flow_totals(fj2["plan"])["allowance"],
                    "big_threshold": fj2["plan"]["bigThreshold"],
                    "dry_powder": inv["dryPct"]}
            if trav:
                want["travel_goal"] = trav["goal"]
            for k, v in want.items():
                if k not in rows:
                    err("D15", f"FINANCE.md figures table is missing the row '{k}'")
                elif abs(n(rows[k][1]) - v) > 0.05:
                    err("D15", f"FINANCE.md says {rows[k][0]} ({k}) is {rows[k][1]}, "
                               f"but the dashboard says {v:,}")
            # And the disease itself: the same fact restated elsewhere in section 1. The words
            # to look for come from the table's own label column, so this survives translation.
            # The `(?![\d,k])` matters: a care model in the same section talks about "$399k" -- a
            # different quantity written in thousands, and the lookahead has to exclude digits too
            # or the regex just backtracks ("$399k" fails on 399, then happily matches 39).
            sec1 = tail.split("\n## ", 1)[0]
            for k, v in (("net_worth", nw), ("fire_target", tgt), ("gap", tgt - nw),
                         ("progress", round(port / tgt * 100, 1))):
                if k not in rows:
                    continue
                label, shown = rows[k]
                pat = (re.escape(label) + r"\s*\*{0,2}([\d.]+)%") if "%" in shown \
                      else (re.escape(label) + r"[^\n]{0,8}?\$([\d,]+)(?![\d,k])")
                for m4 in re.finditer(pat, sec1):
                    got = float(m4.group(1).replace(",", ""))
                    if abs(got - v) > 0.05:
                        err("D15", f"FINANCE.md restates {label} as {m4.group(1)} outside the "
                                   f"figures table; it should say {v:,} or be marked historical")
            if not any(f[0] == "ERROR" and f[1] == "D15" for f in F):
                note("D15", f"FINANCE.md figures table agrees with the dashboard "
                            f"({len(want)} rows checked)")
    # -- D22 a cash-flow ledger row with no type is a row the page cannot count -------------
    # The monthly income rows are derived from `type` (schema 9); an untyped Payroll row is
    # payroll the Income page never shows, and nothing said so until now.
    for a in aj["accounts"] if ap else []:
        if not a.get("ledger") or "Cash flow" not in (a.get("feeds") or ""):
            continue
        lp22 = load(root, a["ledger"])
        if not lp22:
            continue
        with open(lp22, encoding="utf-8-sig") as fh:
            blank = [r for r in csv.DictReader(fh) if r.get("date") and not (r.get("type") or "").strip()]
        if blank:
            warn("D22", f"{a['ledger']}: {len(blank)} row(s) with no type ({blank[0]['date']} "
                        f"{blank[0]['description'][:30]!r} …) -- untyped, they are in the balance chain but "
                        "in no income or transfer figure")

    # -- D18 what an update leaves behind: the record and the queue ------------------------
    # alerts.json used to hold the sentences one import wrote, and the Portfolio page showed them
    # as "Rule status" for as long as they sat there. Since schema 3 (2026-09-10) an update
    # appends a record to imports.json and puts everything the owner has to confirm in
    # decisions.json; the page computes rule status itself. An item the owner is asked to
    # confirm must say what it is, what was assumed meanwhile and when it appeared, or the owner
    # cannot answer it from the page.
    if load(root, "alerts.json"):
        err("D18", "findata/alerts.json is retired: its sentences belong in imports.json as the story "
                   "of that update. Run tools/migrate_2to3.py on this workspace", "hygiene")
    dq = load(root, "decisions.json")
    if dq:
        for i, dd in enumerate(json.load(open(dq, encoding="utf-8")).get("decisions", []), 1):
            gone = [k for k in ("added", "kind", "what", "default", "status") if not dd.get(k)]
            if gone:
                err("D18", f"decisions.json item {i}: no {', '.join(gone)} -- an item the owner is asked "
                           "to confirm has to say what it is, what was assumed meanwhile and when it "
                           "appeared", "hygiene")
            elif dd["status"] not in ("open", "confirmed"):
                err("D18", f"decisions.json item {i}: status {dd['status']!r} is neither open nor confirmed",
                    "hygiene")
            elif dd["status"] == "confirmed" and not dd.get("answer"):
                err("D18", f"decisions.json item {i}: confirmed, but the answer was not written down",
                    "hygiene")
    ip = load(root, "imports.json")
    if ip:
        recs = json.load(open(ip, encoding="utf-8")).get("imports", [])
        for i, rec in enumerate(recs, 1):
            if not rec.get("date"):
                err("D18", f"imports.json record {i} has no date", "hygiene")
            for n in rec.get("noticed", []):
                if n.get("sev") not in ("ok", "warn", "bad"):
                    err("D18", f"imports.json record {i}: a noticed line with sev {n.get('sev')!r}", "hygiene")
        note("D18", f"imports.json: {len(recs)} update record(s)", "hygiene")

    # -- D16 the Chinese guide narrates; it never restates a figure ----------
    # docs/zh/guide.md exists so a reader arriving in Chinese gets the whole story without
    # having to read three English documents. The moment it quotes an amount there are two
    # copies of that number, and one of them is always the stale one -- the same disease
    # FINANCE.md's figures table was built to end. So the rule is mechanical: no currency
    # amount at all. Anything numeric links back to FINANCE.md.
    zg = os.path.join(root, "docs", "zh", "guide.md")
    if os.path.exists(zg):
        found = re.findall(r"[$¥€£¢]\s?\d[\d,]*(?:\.\d+)?", open(zg, encoding="utf-8").read())
        for b in dict.fromkeys(found):
            err("D16", f"docs/zh/guide.md states the amount {b}. The guide is narrative — every "
                       f"figure lives in FINANCE.md and the guide links to it.", "conform")
        if not found:
            note("D16", "docs/zh/guide.md restates no figure", "conform")
    return F

def main(argv):
    v = "-v" in argv or "--verbose" in argv
    root = next((a for a in argv if not a.startswith("-")), ".")
    return 1 if render("data — is the money true", check(root), v) else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
