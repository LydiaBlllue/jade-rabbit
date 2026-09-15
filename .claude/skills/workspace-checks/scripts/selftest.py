#!/usr/bin/env python3
"""Break things on purpose, and check the linters notice.

WHY. The linters are the bottom layer of this workspace: everything above them is prose someone
has to read and follow, and they are the only part that is enforced. Nothing was watching THEM.
On 2026-09-08 that cost two bugs in one afternoon, both silent:

  · check_design' S4 rule walked a hardcoded "skills/" folder to resolve bare filenames. The
    skills moved to .claude/skills/ and the rule started failing every path it was meant to check.
  · hook.py found the workspace by counting "..", so one extra directory level made ROOT point at
    .claude/. It linted a folder with no data in it, reported three ledgers "missing", exited 0,
    and went on saying everything passed.

The second is the one that matters: a checker that has stopped checking and still says OK is worse
than no checker. So each case below plants a specific fault in a COPY of the workspace and asserts
that a specific rule fires. The copy matters -- the manual version of this ran against live files
with backups, one mistake away from being the fault it was testing for.

    selftest.py [root]
"""
import sys, os, re, csv, json, shutil, tempfile, subprocess, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "update-dashboard", "scripts"))
import layout  # where each findata file lives (schema 6)

HERE = os.path.dirname(os.path.abspath(__file__))


def stage(root, dst):
    """A minimal but complete copy. archive/ is reproduced as empty files: D14 reads the NAMES
    to check tags, and the real folder is megabytes of statement PDFs and screenshots."""
    # docs/ comes too: README links to docs/pipeline.svg and friends, and S4 checks that every
    # path README hands the reader resolves. Leaving it out gave every staged copy three phantom
    # S4 errors, which nobody saw because the baseline guard was broken (2026-09-09).
    # templates/ too: T1 rebuilds the pages from it and compares.
    # tools/ too: README hands the reader `tools/sync.py`, and S4 resolves every such path.
    # .private/ too, when it exists: an owner's README may name its deny list and S4 resolves it.
    for d in ("findata", "dashboards", "docs", "templates", "tools", ".private"):
        if os.path.isdir(os.path.join(root, d)):
            shutil.copytree(os.path.join(root, d), os.path.join(dst, d))
    # .claude/ has to come too: S4 resolves the script paths README points at, and without it
    # every baseline run failed on paths that are perfectly fine in the real workspace.
    shutil.copytree(os.path.join(root, ".claude"), os.path.join(dst, ".claude"))
    # OWNER.md is optional (a workspace may not have written one yet); README names it.
    # .gitignore too: S4 exempts the files an owner writes and the tool deliberately does not ship
    # (setup-answers.json), and it learns which those are from there (2026-09-13).
    for f in ("CLAUDE.md", "DESIGN.md", "FINANCE.md", "README.md", "OWNER.md", ".gitignore"):
        if os.path.exists(os.path.join(root, f)):
            shutil.copy2(os.path.join(root, f), dst)
    # README names these folders in prose and S4 checks that every path it hands the reader
    # resolves, so the copy has to have them or the baseline fails on paths that are fine.
    shutil.copytree(os.path.join(root, "inbox"), os.path.join(dst, "inbox"))
    os.makedirs(os.path.join(dst, "archive"))
    for f in os.listdir(os.path.join(root, "archive")):
        open(os.path.join(dst, "archive", f), "w").close()


def run(script, args, cwd):
    p = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                       cwd=cwd, capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


def fired(out, rule):
    return any(re.match(r"\s*[✗⚠]\s*\[" + rule + r"\]", l) for l in out.splitlines())


def rules_seen(out):
    return set(re.findall(r"[✗⚠·]\s*\[([A-Z]\d+)\]", out))


# --- the faults, each one a mistake that has really happened or really could -------------
def m_readme_path(r):
    edit(r, "README.md", lambda s: s.replace("check_data.py", "check_data_MOVED.py"))
def m_design_pages(r):
    edit(r, "DESIGN.md", lambda s: s.replace("| Records | Updates · Accounts · Statements · Tasks |",
                                             "| Records | Insights · Statements · Tasks |"))
def m_nav_orphan(r):
    edit(r, main_dash(r),
         lambda s: s.replace('<section data-pg="acct" hidden>', '<section data-pg="acctX" hidden>'))
def m_spending_row(r):
    p = layout.path(r, "spending.csv")
    lines = open(p, encoding="utf-8").read().splitlines(True)
    open(p, "w", encoding="utf-8").writelines(lines[:-1])
def m_funds_drift(r):
    edit_json(r, layout.rel("funds.json"), lambda d: d["plan"].__setitem__("everyday", 9999))
def m_fund_overclaim(r):
    edit_json(r, layout.rel("funds.json"),
              lambda d: d["funds"][0]["opening"].__setitem__("amount", 999999))
def m_acct_drift(r):
    edit_json(r, layout.rel("accounts.json"), lambda d: d["accounts"][0].__setitem__("balance", 1.0))
def m_bad_cover(r):
    edit_json(r, layout.rel("accounts.json"),
              lambda d: d["documents"][0].__setitem__("covers", ["nope"]))
def m_submitted_orphan(r):
    edit_json(r, layout.rel("accounts.json"),
              lambda d: d["documents"][1].__setitem__("key", "Renamed 999"))
def m_sources_literal(r):
    edit(r, main_dash(r),
         lambda s: s.replace("const SOURCES = ACCT.documents", "const SOURCES = [] || ACCT.documents"))
def m_finance_figure(r):
    # Anchored on the key column, so it plants the same fault in a FINANCE.md written in any
    # language (2026-09-09: it used to match the Chinese label instead of the key).
    edit(r, "FINANCE.md",
         lambda s: re.sub(r"(^\| net_worth \|[^|]*\|)[^|]*\|", r"\1 $1 |", s, count=1, flags=re.M))
def m_finance_restate(r):
    # Plant the restatement right under the figures table, inside section 1 -- D15 scans only
    # that section. Anchored on the table's last row, not on a sentence of prose, so the same
    # fault can be planted in any FINANCE.md that carries the table (2026-09-09: the public
    # build's FINANCE.md has different prose and this used to assert "mutation did nothing").
    def f(s):
        m = re.search(r"^\| gap \|\s*([^|]+?)\s*\|", s, re.M)      # the label this file uses
        label = m.group(1) if m else "gap"
        return s.replace("<!-- LINT:FIGURES:END -->",
                         "<!-- LINT:FIGURES:END -->\n\n" + label + " $1,234,567.", 1)
    edit(r, "FINANCE.md", f)
# The 2026-09-09 markers. Each of these used to be a Chinese phrase inside prose, so a reword or
# a translation switched the check off without a word. A missing marker must WARN, not pass.
def m_pages_marker_wrong(r):
    edit(r, "DESIGN.md",
         lambda s: re.sub(r"(LINT:PAGES pages=)(\d+)", lambda m: m.group(1) + "99", s, count=1))
def m_pages_marker_gone(r):
    edit(r, "DESIGN.md", lambda s: s.replace("LINT:PAGES", "LINT-PAGES-was-here", 1))
def m_nav_marker_wrong(r):
    edit(r, "README.md",
         lambda s: re.sub(r"(LINT:NAV main=)(\d+)", lambda m: m.group(1) + "99", s, count=1))
def m_nav_marker_gone(r):
    edit(r, "README.md", lambda s: s.replace("LINT:NAV", "LINT-NAV-was-here", 1))
def m_readme_sidebar(r):
    # the "·" list under the marker is what a reader is shown; it has to match the real sidebar
    edit(r, "README.md",
         lambda s: s.replace("Home · Spending", "Home · Spendingg", 1))
def m_figures_end_gone(r):
    edit(r, "FINANCE.md", lambda s: s.replace("<!-- LINT:FIGURES:END -->", "", 1))

def m_zh_guide_figure(r):
    # Creates the file when the tree has none, so the same fault can be planted in the private
    # workspace (no guide) and in the public one (guide present).
    p = os.path.join(r, "docs", "zh", "guide.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    old = open(p, encoding="utf-8").read() if os.path.exists(p) else "# guide\n"
    open(p, "w", encoding="utf-8").write(old + "\n\u6bcf\u6708\u6295\u8d44 $2,500\u3002\n")

def m_chain_break(r):
    p = layout.path(r, "chequing.csv")
    lines = open(p, encoding="utf-8").read().splitlines(True)
    c = lines[3].split(","); c[3] = "99999.99"
    lines[3] = ",".join(c)
    open(p, "w", encoding="utf-8").writelines(lines)
def m_foreign_internal(r):
    edit_json(r, layout.rel("foreign.json"), lambda d: d.__setitem__("total", 1.0))
def m_foreign_vs_dash(r):
    # "foreign.json moved but the dashboard did not" -- planted whether or not the workspace has any
    # foreign account. With none (the public build), a row the dashboard has never seen is the
    # same fault; indexing accounts[0] used to crash here (2026-09-09).
    def f(d):
        d["asof"] = "2020-01-01"
        if d["accounts"]:
            d["accounts"][0]["value"] = 1.0
        else:
            d["accounts"].append({"name": "Planted account", "type": "cash", "value": 1.0,
                                  "inst": "Test bank", "asof": "2020-01-01"})
        d["total"] = round(sum(a["value"] for a in d["accounts"]), 2)
    edit_json(r, layout.rel("foreign.json"), f)
def m_brand_half_renamed(r):
    # The real 2026-09-09 fault: profile.json was renamed and only the main dashboard followed;
    # the investment page kept the old brand. Since the two pages became one (2026-09-10) the
    # same disease is the page not following profile.json at all.
    edit_json(r, layout.rel("profile.json"), lambda d: d.__setitem__("owner", "Renamed Owner"))


def m_readme_image_gone(r):
    # The README's hero and pipeline diagram are handed over by <img>/![](), which the backtick
    # sweep never looked at; a broken hero is the first thing a visitor sees (2026-09-09).
    import glob
    for pat in ("docs/hero.png", "docs/pipeline.svg"):
        f = os.path.join(r, pat)
        if os.path.exists(f):
            os.remove(f)
            return
    raise AssertionError("no README image to remove")


# The skill docs are what the model reads before it touches anything, and nothing checked them:
# on 2026-09-13 the import skill still named `dashboards/ly_finance_dashboard.html` three days
# after the rename, and the checks skill said "fifteen" faults when the table held 42.
def m_skill_path(r):
    edit(r, ".claude/skills/update-dashboard/SKILL.md",
         lambda s: s.replace("dashboards/finance_dashboard.html", "dashboards/ly_finance_dashboard.html", 1))

def m_skill_faults(r):
    edit(r, ".claude/skills/workspace-checks/SKILL.md",
         lambda s: re.sub(r'LINT:FAULTS n=\d+', 'LINT:FAULTS n=15', s, count=1))


# Schema 4 (2026-09-10): the register's five axes. Two faults the model makes possible and the
# checker has to catch before anything reads them.
def m_axes_illegal(r):
    # A liability given a role: the by-purpose card would count what is owed as if it were owned.
    edit_json(r, layout.rel("accounts.json"),
              lambda d: next(a for a in d["accounts"] if a.get("side") == "liability").__setitem__("role", "grow"))
def m_stated_no_asof(r):
    # A home typed in with no date: the one number nothing can re-derive, and nobody knows how old.
    def f(d):
        d["accounts"].append({"inst": "Land registry", "id": "\u2014", "name": "Home", "kind": "Property",
                              "cur": "CAD", "balance": 400000, "asof": None, "src": "none",
                              "side": "asset", "role": "none", "reach": "locked", "value": "stated",
                              "ledger": None, "feeds": "", "key": "home"})
    edit_json(r, layout.rel("accounts.json"), f)
def m_committed_missing(r):
    # A car loan declared in the plan that no ledger ever shows: the waterfall would carry a
    # payment that is a story, not a fact.
    def f(d):
        d["plan"]["flows"].append({"key": "car", "kind": "committed", "name": "Car loan",
                                   "amount": 410, "until": "2029-06", "afterFire": "drop"})
    edit_json(r, layout.rel("funds.json"), f)
# The parsers (update-dashboard/parsers). A fixture is one of the demo owner's own statements
# rendered back into the text shape the real one has (tools/fixtures.py); the fault is a
# statement whose printed total disagrees with its rows — the parser has to say so, not
# "reconciled". Runner kind "parse": it generates the fixtures into the staged copy and runs
# parse.py on the tampered one.
def m_parse_tampered(r):
    return "rbc_visa"       # which fixture to tamper; the runner does the rest
def m_rules_drift(r):
    # rules.json is the strategy; the page copies it. The copy going stale means the Rules page
    # is checking the portfolio against a band nobody chose any more.
    edit_json(r, layout.rel("rules.json"), lambda d: d.__setitem__("maxHoldings", 99))


def m_template_dirty(r):
    # Somebody's data typed into the template -- the one place that must hold nobody's.
    edit(r, "templates/dashboards/finance_dashboard.html",
         lambda s: s.replace("const IMPORT_DAY = 0;", "const IMPORT_DAY = 26;", 1))


def m_built_by_hand(r):
    # dashboards/ edited in place instead of rebuilt from the template: the build no longer equals
    # template + findata, which is exactly how a hand-typed constant used to slip in.
    edit(r, main_dash(r),
         lambda s: s.replace("</title>", "</title><!-- edited by hand -->", 1))


def m_filed_ghost(r):
    # A month filed for a document that does not exist: a claim with no evidence behind it.
    edit_json(r, layout.rel("filings.json"), lambda d: d["filed"].__setitem__("Ghost statement", ["2026-01"]))


def edit(r, rel, fn):
    p = os.path.join(r, rel)
    s = open(p, encoding="utf-8").read()
    n = fn(s)
    assert n != s, f"mutation did nothing: {rel}"
    open(p, "w", encoding="utf-8").write(n)


def edit_json(r, rel, fn):
    p = os.path.join(r, rel)
    d = json.load(open(p, encoding="utf-8"))
    fn(d)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# check_render rules were never exercised here, which is why R5 could sit broken from the day it
# was written: its regex lived in a non-raw Python string, so \b became a backspace and it matched
# nothing while reporting "clean" (found 2026-09-09). Two cases now cover it. They cost about 11
# seconds each because they drive a real browser.
def m_cashflow_left_behind(r):
    open(os.path.join(r, "findata", "ledgers", "cashflow.json"), "w", encoding="utf-8").write('{"rows": []}\n')

def m_untyped_row(r):
    p = os.path.join(r, "findata", "ledgers", "chequing.csv")
    lines = open(p, encoding="utf-8").read().splitlines()
    for i, l in enumerate(lines):
        if ",Payroll," in l:
            lines[i] = l.replace(",Payroll,", ",,", 1); break
    else:
        raise AssertionError("no Payroll row to untype")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")

def m_fund_monthly_left_behind(r):
    edit_json(r, "findata/register/funds.json", lambda d: d["funds"][0].__setitem__("monthly", 50))

def m_exclude_left_behind(r):
    edit_json(r, "findata/register/rules.json",
              lambda d: d.__setitem__("exclude", {"accounts": ["FHSA"], "why": "said twice"}))

def m_alerts_left_behind(r):
    open(layout.path(r, "alerts.json"), "w", encoding="utf-8").write('{"alerts": []}\n')

def m_decision_no_default(r):
    # An empty queue (an owner with nothing waiting) gets one item planted without its default;
    # this used to index [0] and crash the whole selftest in such a workspace (2026-09-10).
    def f(d):
        if d["decisions"]:
            d["decisions"][0].pop("default", None)
        else:
            d["decisions"].append({"added": "2026-09-01", "kind": "merchant", "status": "open",
                                   "what": "A merchant seen for the first time.", "source": "a statement, line 1"})
    edit_json(r, layout.rel("decisions.json"), f)

# S8 reads the template when there is one, so the fault is planted there. The old label is the
# real sentence the owner rejected on 2026-09-10.
def m_first_person(r):
    edit(r, "templates/dashboards/finance_dashboard.html",
         lambda s: s.replace('<div class="lab">What arrives each month</div>',
                             '<div class="lab">What you drop in, and when I last got it</div>', 1))

def m_brand_mark_gone(r):
    edit(r, main_dash(r),
         lambda s: re.sub(r'<svg class="coin".*?</svg>', '', s, count=1, flags=re.S))

def m_render_nan(r):
    # Anchored on INVEST.netWorth, which every build has -- the first version broke a foreign
    # fund amount, which the public build does not have, so the mutation did nothing there.
    # DELETE the field rather than nulling it: `null + number` is a number in JavaScript, so
    # nulling it produced no visible damage at all. A missing field is also the real shape of the
    # 2026-09-08 fault this rule exists for -- something was renamed and the reader was left
    # looking at "undefined".
    edit(r, main_dash(r),
         lambda s: re.sub(r'"netWorth":\s*-?[\d.]+,\s*', '', s, count=1))
def m_render_chart_capped(r):
    edit(r, main_dash(r),
         lambda s: s.replace("year-svg{width:100%;height:auto", "year-svg{width:100%;height:190px", 1))


def main_dash(r):
    """The main dashboard's path inside a workspace: an owner's copy may still carry the old
    `ly_` name, the template and any fresh workspace use `finance_dashboard.html`."""
    for n in ("ly_finance_dashboard.html", "finance_dashboard.html"):
        if os.path.exists(os.path.join(r, "dashboards", n)):
            return "dashboards/" + n
    return "dashboards/finance_dashboard.html"


def dash_args(r):
    # One file since 2026-09-10; an older workspace's second file is checked while it exists.
    inv = "dashboards/investment_dashboard.html"
    return [main_dash(r)] + ([inv] if os.path.exists(os.path.join(r, inv)) else [])
CASES = [
    ("S4", "README points at a file that moved",            m_readme_path,     "dash"),
    ("S4", "DESIGN.md page table drifts from NAV",          m_design_pages,    "dash"),
    ("S1", "a NAV entry with no matching section",          m_nav_orphan,      "dash"),
    ("D12", "a spending.csv row missing from the page",     m_spending_row,    "find"),
    ("D13", "funds.json changed but the page did not",      m_funds_drift,     "find"),
    ("D13", "a fund claims more than its account holds",    m_fund_overclaim,  "find"),
    ("D14", "accounts.json changed but the page did not",   m_acct_drift,      "find"),
    ("D19", "a liability given a role",                     m_axes_illegal,    "find"),
    ("D20", "a stated balance with no date",                m_stated_no_asof,  "find"),
    ("D21", "a committed flow the ledger never shows",      m_committed_missing, "find"),
    ("P1",  "a statement whose rows do not add up to its total", m_parse_tampered, "parse"),
    ("D14", "a document covers an account that is gone",    m_bad_cover,       "find"),
    ("D14", "SUBMITTED key with no matching document",      m_submitted_orphan,"find"),
    ("D14", "SOURCES written out instead of derived",       m_sources_literal, "find"),
    ("D15", "FINANCE.md figure disagrees with the page",    m_finance_figure,  "find"),
    ("D15", "a figure restated in prose, as it was before", m_finance_restate, "find"),
    ("D1",  "a broken balance chain",                       m_chain_break,     "find"),
    ("D8",  "foreign.json total no longer sums to its accounts", m_foreign_internal,    "find"),
    ("D11", "foreign.json moved but the dashboard did not",     m_foreign_vs_dash,     "find"),
    ("S4", "DESIGN.md LINT:PAGES count is wrong",           m_pages_marker_wrong, "dash"),
    ("S4", "DESIGN.md LINT:PAGES marker deleted",           m_pages_marker_gone,  "dash"),
    ("S4", "README LINT:NAV count is wrong",                m_nav_marker_wrong,   "dash"),
    ("S4", "README LINT:NAV marker deleted",                m_nav_marker_gone,    "dash"),
    ("S4", "README sidebar list drifts from NAV",           m_readme_sidebar,     "dash"),
    ("D15", "FINANCE.md LINT:FIGURES:END marker deleted",   m_figures_end_gone,   "find"),
    ("D16", "the Chinese guide restates a figure",          m_zh_guide_figure,    "find"),
    ("D17", "profile.json renamed but the page did not follow", m_brand_half_renamed, "find"),
    ("S4", "a README image that no longer exists",          m_readme_image_gone,  "dash"),
    ("S4", "a skill doc points at a page that was renamed", m_skill_path,        "dash"),
    ("S6", "a skill doc advertises the wrong fault count",  m_skill_faults,      "dash"),
    ("D17", "rules.json changed but the investment page did not", m_rules_drift,  "find"),
    ("T1",  "somebody's data typed into the template",          m_template_dirty, "find"),
    ("T1",  "a dashboard edited in place, not rebuilt",         m_built_by_hand,  "find"),
    ("T2",  "a month filed for a document that does not exist", m_filed_ghost,    "find"),
    ("S5", "the sidebar wordmark lost its mark",            m_brand_mark_gone,    "dash"),
    ("D18", "alerts.json left behind after the migration",  m_alerts_left_behind, "find"),
    ("D19", "rules.json still carries the exclude list",    m_exclude_left_behind, "find"),
    ("D13", "a fund still carries a monthly contribution",   m_fund_monthly_left_behind, "find"),
    ("D18", "cashflow.json left behind after the migration", m_cashflow_left_behind, "find"),
    ("D22", "a cash-flow ledger row with no type",            m_untyped_row,         "find"),
    ("D18", "an item to confirm with nothing assumed meanwhile", m_decision_no_default, "find"),
    ("S8",  "the page speaks in the first person",          m_first_person,       "dash"),
    ("R5", "a broken field leaves NaN on the page",         m_render_nan,         "render"),
    ("R3", "a chart pinned to a fixed height",              m_render_chart_capped,"render"),
]


PARSE = os.path.join(os.path.dirname(HERE), "..", "update-dashboard", "scripts", "parse.py")
PROPOSE = os.path.join(os.path.dirname(HERE), "..", "setup", "scripts", "propose.py")


def parse_one(ws, path, parser):
    """Run parse.py on one file: (ok, rows, last line)."""
    r = subprocess.run([sys.executable, os.path.normpath(PARSE), path, "--parser", parser, "--json"],
                       capture_output=True, text=True, cwd=ws)
    try:
        res = json.loads(r.stdout)
    except ValueError:
        return False, 0, (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr).strip() else "no output"
    parts = res.get("accounts") or [res]
    return res["reconcile"]["ok"], sum(len(x["rows"]) for x in parts), res["reconcile"]["detail"]


def fixtures_for(ws):
    """The synthetic statements for a staged copy, or None when the tool's fixture writer is absent."""
    fx = os.path.join(ws, "tools", "fixtures.py")
    if not os.path.exists(fx):
        return None
    out = os.path.join(ws, "_fixtures")
    r = subprocess.run([sys.executable, fx, ws, out], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return []


def parse_fault(ws, parser, rule):
    """Plant the fault: rewrite one fixture of `parser` with its printed purchase total off by
    ten dollars, and report the way a checker would."""
    man = fixtures_for(ws)
    if man is None:
        return None
    pick = next((m for m in man if m["parser"] == parser), None)
    if not pick:
        return f"✗ [{rule}] no {parser} fixture to tamper"
    sys.path.insert(0, os.path.join(ws, "tools"))
    from pypdf import PdfReader
    import pdfgen
    lines = []
    for pg in PdfReader(pick["file"]).pages:
        lines.append([l for l in (pg.extract_text() or "").splitlines() if l.strip()])
    hit = False
    for pg in lines:
        for i, l in enumerate(pg):
            if l.startswith("Purchases & debits $"):
                v = float(l.split("$")[1].replace(",", "")) + 10
                pg[i] = f"Purchases & debits ${v:,.2f}"; hit = True
    if not hit:
        return f"✗ [{rule}] fixture has no total line to tamper"
    pdfgen.write_pdf(pick["file"], lines)
    ok, n, detail = parse_one(ws, pick["file"], parser)
    return f"{'·' if ok else '✗'} [{rule}] {detail}"


def propose_check(ws, man):
    """The setup's first step drafts the register from the first files dropped (propose.py). Given
    the demo owner's statements (the fixtures) and broker exports, the draft has to find every
    account the demo register reads a statement for, with the right kind and closing day, and
    every account the holdings export lists — and it has to leave the questions open, because a
    file cannot say who the owner is."""
    prop = os.path.normpath(PROPOSE)
    if not os.path.exists(prop):
        return []
    inbox = os.path.join(ws, "_propose_inbox")
    os.makedirs(inbox, exist_ok=True)
    for m in man:
        shutil.copy(m["file"], inbox)
    led = os.path.join(ws, "findata", "ledgers")
    for src_, dst in (("holdings_latest.csv", "holdings-report-2026-09-06.csv"),
                      ("ws_activities.csv", "activities-export-2026-09-06.csv")):
        if os.path.exists(os.path.join(led, src_)):
            shutil.copy(os.path.join(led, src_), os.path.join(inbox, dst))
    r = subprocess.run([sys.executable, prop, ws, "--inbox", inbox, "--json"], capture_output=True, text=True)
    try:
        draft = json.loads(r.stdout)
    except ValueError:
        return [f"  ✗ propose: no draft — {(r.stdout or r.stderr).strip().splitlines()[-1:]}"]
    reg = json.load(open(layout.path(ws, "accounts.json"), encoding="utf-8"))
    by_key = {a["key"]: a for a in reg["accounts"]}
    got = [(re.sub(r"\D", "", a["id"] or ""), a["kind"], (a.get("doc") or {}).get("closes"))
           for a in draft["accounts"] if (a.get("doc") or {}).get("parser")]
    miss = []
    rendered = {m["doc"] for m in man}          # only accounts a fixture was drawn for can be found
    for d in reg["documents"]:
        if not d.get("parser") or d["key"] not in rendered:
            continue
        acc = by_key[d["covers"][0]]
        digits = re.sub(r"\D", "", acc["id"] or "")
        day = int(re.sub(r"\D", "", d.get("closes") or "0") or 0)
        if not any(digits.endswith(g) and k == acc["kind"] and c and abs(c - day) <= 3 for g, k, c in got):
            miss.append(f"{d['key']} (…{digits}, {acc['kind']}, closes {day})")
    hp = os.path.join(led, "holdings_latest.csv")
    want_h = len({row["Account Number"] for row in csv.DictReader(open(hp, encoding="utf-8-sig"))
                  if row.get("Account Number")}) if os.path.exists(hp) else 0
    got_h = sum(1 for a in draft["accounts"] if a["id"] and not a["id"].startswith("…") and a.get("balance") is not None
                and a["kind"] in ("TFSA", "RRSP", "FHSA", "Non-registered", "Crypto", "Investment"))
    ids = {q["id"] for q in draft.get("_open", [])}
    out = []
    ok = not miss and got_h == want_h and {"owner", "born"} <= ids
    detail = (f"{len(got)} statement account(s), {got_h} of {want_h} broker account(s), {len(ids)} question(s) left open"
              + (f"; missed {', '.join(miss)}" if miss else "")
              + ("" if {"owner", "born"} <= ids else "; the owner's name or birth year was not asked"))
    out.append(f"  {'✓' if ok else '✗'} setup draft: {detail}")
    return out


def parser_checks(root, base):
    """Every fixture must parse and reconcile with the row count the ledger has; every real
    statement in archive/ that names a parser must parse and reconcile."""
    lines = []
    ws = os.path.join(base, "parsers")
    os.makedirs(ws); stage(root, ws)
    man = fixtures_for(ws)
    if man:
        good = 0
        for m in man:
            ok, n, detail = parse_one(ws, m["file"], m["parser"])
            if ok and n == m["rows"]:
                good += 1
            else:
                lines.append(f"  ✗ fixture {os.path.basename(m['file'])} ({m['parser']}): {detail} — expected {m['rows']} rows")
        lines.append(f"\n  {'✓' if good == len(man) else '✗'} parsers: {good} of {len(man)} synthetic statements read and reconciled")
        lines += propose_check(ws, man)
    arc = os.path.join(root, "archive")
    reg = layout.path(root, "accounts.json")
    if os.path.isdir(arc) and os.path.exists(reg):
        docs = json.load(open(reg, encoding="utf-8")).get("documents", [])
        tag_parser = {t: d["parser"] for d in docs if d.get("parser") for t in d.get("tags", [])}
        real, good = 0, 0
        for f in sorted(os.listdir(arc)):
            m = re.match(r"\d{8}_(.+)$", f)
            # The demo's archive is names only (T2 reads the names); a zero-byte file is a
            # placeholder, not a statement.
            if not m or not f.lower().endswith(".pdf") or os.path.getsize(os.path.join(arc, f)) == 0:
                continue
            tag = next((t for t in sorted(tag_parser, key=len, reverse=True) if m.group(1).startswith(t + "_")), None)
            if not tag:
                continue
            real += 1
            ok, n, detail = parse_one(root, os.path.join(arc, f), tag_parser[tag])
            if ok:
                good += 1
            else:
                lines.append(f"  ✗ archive/{f} ({tag_parser[tag]}): {detail}")
        if real:
            lines.append(f"  {'✓' if good == real else '✗'} parsers: {good} of {real} real statements in archive/ read and reconciled")
    return lines


def update_check(root, base):
    """The import as one local run (update.py, 2026-09-14). Strip the newest statement of every
    parser-read document out of a staged copy, drop the synthetic statement for it into inbox/
    under the bank's own filename, run update.py --write, and expect: the demo's own ledger rows
    and purchases back, banks.json and filings.json as they were, the checkers clean, the rebuild
    idempotent, and a second drop of the same statement to write nothing. This is the proof that
    the script does what the model used to do by hand — and that the model no longer has to
    read a statement a parser can."""
    upd = os.path.normpath(os.path.join(os.path.dirname(HERE), "..", "update-dashboard", "scripts", "update.py"))
    if not os.path.exists(upd):
        return []
    ws = os.path.join(base, "update"); os.makedirs(ws); stage(root, ws)
    man = fixtures_for(ws)
    if not man:
        return []
    fd = lambda n: layout.path(ws, n)
    LONG = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December")
    reg = json.load(open(fd("accounts.json"), encoding="utf-8"))
    by_key = {a["key"]: a for a in reg["accounts"]}
    docs = {d["key"]: d for d in reg["documents"]}
    newest = {}
    for m in man:
        newest[m["doc"]] = max(newest.get(m["doc"], m), m, key=lambda x: os.path.basename(x["file"]))
    banks = json.load(open(fd("banks.json"), encoding="utf-8"))
    filings = json.load(open(fd("filings.json"), encoding="utf-8"))
    want = {"ledger": {}, "spend": list(csv.DictReader(open(fd("spending.csv"), encoding="utf-8"))),
            "banks": json.loads(json.dumps(banks)), "filings": json.loads(json.dumps(filings["filed"]))}
    dropped = {}
    for key, m in newest.items():
        doc = docs[key]; acc = by_key[doc["covers"][0]]
        tag = re.search(r"(\d{8})\.pdf$", m["file"]).group(1)
        end = datetime.date(int(tag[:4]), int(tag[4:6]), int(tag[6:]))
        if acc.get("ledger"):
            rows = list(csv.DictReader(open(fd(acc["ledger"]), encoding="utf-8")))
            want["ledger"][acc["ledger"]] = rows
            keep = [r for r in rows if r["statement"] != f"{acc['stmtTag']}/{tag}"]
            with open(fd(acc["ledger"]), "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(keep)
            for x in banks["assets"]:
                if x["account"] == acc["name"]:
                    x["balance"], x["asof"] = float(keep[-1]["balance"]), keep[-1]["date"]
            for a in reg["accounts"]:
                if a["key"] == acc["key"]:
                    a["balance"], a["asof"] = float(keep[-1]["balance"]), keep[-1]["date"]
        else:
            tagend = f"[{acc['spendTag']}/{tag}]"
            cur = list(csv.DictReader(open(fd("spending.csv"), encoding="utf-8")))
            keep = [r for r in cur if not r["note"].endswith(tagend)]
            with open(fd("spending.csv"), "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "amount", "currency", "category", "note"]); w.writeheader(); w.writerows(keep)
            for x in banks["debts"]:
                if x["account"] == acc["name"]:
                    x["balance"], x["asof"] = 0.0, "2000-01-01"
            for a in reg["accounts"]:
                if a["key"] == acc["key"]:
                    a["balance"], a["asof"] = 0.0, "2000-01-01"
        filings["filed"][key] = [mo for mo in filings["filed"][key] if mo != end.strftime("%Y-%m")]
        name = doc["file"].replace("<Month D, YYYY>", f"{LONG[end.month - 1]} {end.day}, {end.year}").replace("<date>", end.isoformat())
        if m["parser"] == "rbc_visa":
            name = f"{tag}.pdf"      # the way an RBC download really arrives: the statement has to name itself
        shutil.copy(m["file"], os.path.join(ws, "inbox", name))
        dropped[key] = (name, f"{tag}_{doc['tags'][0]}_{name}")
    json.dump(banks, open(fd("banks.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(filings, open(fd("filings.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(reg, open(fd("accounts.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(upd), "rebuild.py"), ".", "--write"], cwd=ws, capture_output=True)

    def go():
        r = subprocess.run([sys.executable, upd, ".", "--write"], cwd=ws, capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout + r.stderr
    rc, out = go()
    bad = []
    if rc != 0:
        bad.append(f"update.py exited {rc}: " + " | ".join(out.strip().splitlines()[-3:]))
    for ledger, rows in want["ledger"].items():
        now = list(csv.DictReader(open(fd(ledger), encoding="utf-8")))
        if len(now) != len(rows):
            bad.append(f"{ledger}: {len(now)} rows, the demo had {len(rows)}")
        for a, b in zip(rows, now):
            if any(a[c] != b[c] for c in ("date", "description", "amount", "balance", "statement", "type")):
                bad.append(f"{ledger} {a['date']} {a['description'][:30]!r}: got {b['amount']} / {b['balance']} / {b['type']!r}, demo {a['amount']} / {a['balance']} / {a['type']!r}")
    key = lambda r: (r["date"], r["amount"], r["note"].rsplit("[", 1)[-1])
    o = {key(r): r for r in want["spend"]}
    n = {key(r): r for r in csv.DictReader(open(fd("spending.csv"), encoding="utf-8"))}
    for k in sorted(set(o) - set(n)):
        bad.append(f"spending.csv lost {k[0]} {k[1]} {k[2]}")
    for k in sorted(set(n) - set(o)):
        bad.append(f"spending.csv gained {k[0]} {k[1]} {k[2]}")
    for k in sorted(set(o) & set(n)):
        if o[k]["category"] != n[k]["category"]:
            bad.append(f"spending.csv {k[0]} {o[k]['note'][:30]!r}: {n[k]['category']}, the demo had {o[k]['category']}")
    nb = json.load(open(fd("banks.json"), encoding="utf-8"))
    for side in ("assets", "debts"):
        for a, b in zip(want["banks"][side], nb[side]):
            if (a["balance"], a["asof"]) != (b["balance"], b["asof"]):
                bad.append(f"banks.json {a['account']}: {b['balance']} @ {b['asof']}, the demo had {a['balance']} @ {a['asof']}")
    nf = json.load(open(fd("filings.json"), encoding="utf-8"))["filed"]
    for k, v in want["filings"].items():
        if nf.get(k) != v:
            bad.append(f"filings.json {k}: {nf.get(k)}, the demo had {v}")
    left = [f for f in os.listdir(os.path.join(ws, "inbox")) if not f.startswith(".")]
    if left:
        bad.append(f"inbox/ still holds {left}")
    for script, args in (("check_data.py", ["."]), ("check_design.py", dash_args(ws))):
        o2 = run(script, args, ws)
        if "✗" in o2:
            bad.append(f"{script} after the run: " + "; ".join(l.strip() for l in o2.splitlines() if l.strip().startswith("✗"))[:300])
    r2 = subprocess.run([sys.executable, os.path.join(os.path.dirname(upd), "rebuild.py"), "."], cwd=ws, capture_output=True, text=True)
    if "nothing to do" not in r2.stdout:
        bad.append("rebuild still had changes after the run")
    # the same statement again: nothing written twice, and the file archived as a redrop
    name, arc_name = next(iter(dropped.values()))
    shutil.copy(os.path.join(ws, "archive", arc_name), os.path.join(ws, "inbox", name))
    n_before = sum(len(csv_rows_of(fd(l))) for l in want["ledger"]) + len(csv_rows_of(fd("spending.csv")))
    rc3, out3 = go()
    n_after = sum(len(csv_rows_of(fd(l))) for l in want["ledger"]) + len(csv_rows_of(fd("spending.csv")))
    if rc3 != 0 or n_after != n_before or not any("(redrop)" in f for f in os.listdir(os.path.join(ws, "archive"))):
        bad.append(f"a second drop of {name}: exit {rc3}, rows {n_before} → {n_after}")
    # a statement no parser reads, transcribed by eye and handed back with --hand: the savings
    # statement again, with its parser taken out of the register, dropped under a name nothing
    # matches. The run has to stop on it, then file it from the transcription — and refuse a
    # transcription whose rows do not add up.
    sav = next((k for k, d in docs.items() if d.get("parser") == "bmo_banking" and d["file"].endswith("-2.pdf")), None)
    if sav and sav in newest:
        m = newest[sav]; acc = by_key[docs[sav]["covers"][0]]
        tag = re.search(r"(\d{8})\.pdf$", m["file"]).group(1)
        rows_all = list(csv.DictReader(open(fd(acc["ledger"]), encoding="utf-8")))
        keep = [r for r in rows_all if r["statement"] != f"{acc['stmtTag']}/{tag}"]
        with open(fd(acc["ledger"]), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_all[0].keys())); w.writeheader(); w.writerows(keep)
        reg2 = json.load(open(fd("accounts.json"), encoding="utf-8"))
        for d in reg2["documents"]:
            if d["key"] == sav:
                d["parser"] = None
        json.dump(reg2, open(fd("accounts.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        shutil.copy(m["file"], os.path.join(ws, "inbox", "scan.pdf"))
        rc4, out4 = go()
        if rc4 != 1 or "scan.pdf" not in out4:
            bad.append(f"a statement with no parser under an unmatched name: expected a stop, got exit {rc4}")
        sys.path.insert(0, os.path.dirname(os.path.dirname(upd)))
        from parsers import parse as parse_file  # the transcription, as the model would make it
        res = parse_file(m["file"], "bmo_banking")
        hand = [{"file": "scan.pdf", "doc": sav, "account": res["account"], "period": res["period"],
                 "opening": res["opening"], "closing": res["closing"], "rows": res["rows"], "totals": res["totals"]}]
        hp = os.path.join(base, "hand.json")
        wrong = json.loads(json.dumps(hand)); wrong[0]["rows"][0]["amount"] = round(wrong[0]["rows"][0]["amount"] + 10, 2)
        json.dump(wrong, open(hp, "w", encoding="utf-8"))
        r5 = subprocess.run([sys.executable, upd, ".", "--write", "--hand", hp], cwd=ws, capture_output=True, text=True, timeout=300)
        if r5.returncode != 1 or "does not add up" not in r5.stdout:
            bad.append(f"a transcription off by $10 was not refused (exit {r5.returncode})")
        json.dump(hand, open(hp, "w", encoding="utf-8"))
        r6 = subprocess.run([sys.executable, upd, ".", "--write", "--hand", hp], cwd=ws, capture_output=True, text=True, timeout=300)
        now = list(csv.DictReader(open(fd(acc["ledger"]), encoding="utf-8")))
        core = ("date", "description", "amount", "balance", "statement", "type")
        if r6.returncode != 0 or len(now) != len(rows_all) or any(a[c] != b[c] for a, b in zip(rows_all, now) for c in core):
            bad.append(f"the transcribed savings statement did not come back as the demo had it (exit {r6.returncode}, {len(now)} of {len(rows_all)} rows)")
    n_led = sum(len(v) for v in want["ledger"].values())
    if bad:
        return ["  ✗ update.py: " + b for b in bad[:8]]
    return [f"  ✓ update.py: {len(newest)} statements round-tripped — {n_led} ledger rows and every purchase back where the "
            f"demo had them, banks and filings as they were, a date-only PDF named by its contents, checkers clean, rebuild idempotent, a second drop wrote nothing, a transcribed statement filed and a wrong one refused"]


def csv_rows_of(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []



def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.getcwd()
    base = tempfile.mkdtemp(prefix="ly_selftest_")
    fails, seen = [], set()
    try:
        # 0. the linters must be clean on an UNMODIFIED copy, or every result below is noise.
        clean = os.path.join(base, "clean")
        os.makedirs(clean); stage(root, clean)
        for s, a in (("check_design.py", dash_args(clean) + ["-v"]), ("check_data.py", [".", "-v"]),
                     ("check_render.py", dash_args(clean) + ["-v"])):
            out = run(s, a, clean)
            seen |= rules_seen(out)
            # Judge by the ✗ marks the checkers actually print. This used to grep for
            # "N error", a phrasing they stopped using when the output was regrouped on
            # 2026-09-08 -- so the guard silently passed everything, including a baseline with
            # three real S4 errors in it. A dead guard on a self-test is the same disease the
            # self-test exists to catch.
            if "✗" in out:
                fails.append(f"baseline: {s} already reports errors on an untouched copy\n{out}")
        print(f"=== selftest — {len(CASES)} planted faults ===")

        for i, (rule, what, mut, which) in enumerate(CASES):
            d = os.path.join(base, f"c{i}")
            os.makedirs(d); stage(root, d)
            if which == "parse":
                out = parse_fault(d, mut(d), rule)
                if out is None:
                    print(f"  · [{rule}] {what} — no tools/fixtures.py here, not exercised")
                    continue
            else:
                mut(d)
                script = {"dash": "check_design.py", "find": "check_data.py",
                          "render": "check_render.py"}[which]
                out = run(script, dash_args(d) if which in ("dash", "render") else ["."], d)
            ok = fired(out, rule)
            print(f"  {'✓' if ok else '✗'} [{rule}] {what}")
            if not ok:
                fails.append(f"[{rule}] {what} — planted the fault, {rule} stayed quiet")

        # the parsers, on statements: the demo owner's, rendered back into PDFs (tools/fixtures.py),
        # and in an owner's workspace every real statement in archive/ that names a parser.
        for line in parser_checks(root, base) + update_check(root, base):
            print(line)
            if line.lstrip().startswith("✗"):
                fails.append(line.strip())

        # the checker's own blind spots: rules that exist but nothing here exercises
        untested = sorted(seen - {c[0] for c in CASES})
        if untested:
            print("\n  untested rules (they exist, nothing here breaks them): "
                  + ", ".join(untested))

        # and the bug that started this: hook.py has to find the workspace by landmark
        sys.path.insert(0, HERE)
        import importlib.util
        sp = importlib.util.spec_from_file_location("h", os.path.join(HERE, "hook.py"))
        h = importlib.util.module_from_spec(sp); sp.loader.exec_module(h)
        ok = os.path.isdir(os.path.join(h.ROOT, "findata"))
        print(f"\n  {'✓' if ok else '✗'} hook.py resolves ROOT to a real workspace ({h.ROOT})")
        if not ok:
            fails.append("hook.py ROOT does not contain findata/ — it would lint the wrong folder")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if fails:
        print(f"  {len(fails)} FAILURE(S):")
        for f in fails:
            print("   ✗ " + f.splitlines()[0])
        return 1
    print("  every planted fault was caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
