#!/usr/bin/env python3
"""Check the LY Finance dashboards against the rules in DESIGN.md.

Only the mechanical rules live here. Anything needing judgement (is this page
worth its own entry? does this grouping match how the owner thinks?) stays with the
human -- a linter that guesses at taste just trains you to ignore it.

Usage:  python3 check_design.py <file.html> [more.html ...]
Exit:   0 clean or notes only, 1 if any ERROR
"""
import re, sys, os, json

# ---------------------------------------------------------------- helpers
def luminance(hex_):
    c = [int(hex_[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]

def contrast(a, b):
    x, y = luminance(a), luminance(b)
    return round((max(x, y) + .05) / (min(x, y) + .05), 2)

def style_block(src):
    m = re.search(r'<style>(.*?)</style>', src, re.S)
    return m.group(1) if m else ""

def css_var(css, name, default=None):
    m = re.search(re.escape(name) + r'\s*:\s*(#[0-9a-fA-F]{6}|[^;\n]+)', css)
    return m.group(1).strip() if m else default

def js_strings(src):
    """String literals that can reach the screen. Skips the giant data constants."""
    body = re.sub(r'^const (SPENDING|CHEQUING|INVEST|DATA|WSINC|WSDEP|SUBMITTED) = .*?;$',
                  '', src, flags=re.M | re.S)
    out = []
    for m in re.finditer(r'"((?:[^"\\\n]|\\.){8,})"|\'((?:[^\'\\\n]|\\.){8,})\'|`((?:[^`\\]|\\.){8,}?)`', body):
        s = m.group(1) or m.group(2) or m.group(3)
        line = body[:m.start()].count("\n") + 1
        out.append((line, s))
    return out

# ---------------------------------------------------------------- rules
def _exists_somewhere(root, filename):
    """Is this bare filename anywhere in the workspace? Prose mentions it without a path."""
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in {"archive", "node_modules", ".git", "share"}]
        if filename in files or filename in dirs:
            return True
    return False



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

def check(path):
    src = open(path, encoding="utf-8").read()
    css = style_block(src)
    # Everything this file checks is form: pixel heights, contrast, line width, media queries,
    # self-containment, and whether DESIGN.md still describes the navigation it claims to. That
    # is one category, and unlike its sibling this script really is a linter.
    F = []          # (severity, rule, message, category)
    def err(r, m):  F.append(("ERROR", r, m, "conform"))
    def warn(r, m): F.append(("WARN", r, m, "conform"))
    def note(r, m): F.append(("NOTE", r, m, "conform"))

    # -- §4 desktop-only layout -------------------------------------------
    body = re.search(r'\bbody\s*\{([^}]*)\}', css)
    bodycss = body.group(1) if body else ""
    if "min-width:1120px" not in bodycss.replace(" ", ""):
        err("L1", "body is missing min-width:1120px (DESIGN.md §4, desktop only)")
    mw = re.search(r'max-width:\s*(\d+)px', bodycss)
    if not mw:
        err("L1", "body is missing a max-width (§4 expects 1760px)")
    elif int(mw.group(1)) < 1600:
        warn("L1", f"body max-width is {mw.group(1)}px; §4 widened it to 1760px for the 32\" screen")
    for m in re.finditer(r'@media([^{]*)\{', css):
        q = m.group(1)
        if "width" not in q:
            continue    # prefers-reduced-motion and friends are fine; only width queries were dropped
        warn("L2", f"@media ({q.strip()}) at style line {css[:m.start()].count(chr(10))+1} — "
                   "the narrow-screen view was dropped (§4)")
    if "col-hide-sm" in src:
        warn("L3", "col-hide-sm is a leftover narrow-screen class; §4 removed responsive column hiding")

    # -- §4 charts must scale with width, not be pinned by height ----------
    fixed_h = {}
    for m in re.finditer(r'([^{}]+)\{([^}]*height\s*:\s*(\d+)px[^}]*)\}', css):
        for sel in m.group(1).split(","):
            fixed_h[sel.strip()] = m.group(3)
    for m in re.finditer(r'<svg\b([^>]*)>', src):
        attrs = m.group(1)
        if "viewBox" not in attrs:
            continue
        line = src[:m.start()].count("\n") + 1
        sid = (re.search(r'id="([^"]+)"', attrs) or [None, "?"])[1]
        if re.search(r'style="[^"]*height\s*:\s*\d+px', attrs):
            err("C1", f"line {line}: <svg id={sid}> has an inline pixel height. "
                      "viewBox + meet + fixed height scales to the height and centres, so a wider "
                      "window only adds blank gutters (§4). Use width:100%; height:auto.")
        for cls in re.findall(r'class="([^"]+)"', attrs):
            for c in cls.split():
                if "." + c in fixed_h:
                    err("C1", f"line {line}: <svg id={sid}> uses .{c}, which sets "
                              f"height:{fixed_h['.'+c]}px. Same trap — use height:auto.")

    # -- §5d text is capped so long prose stays readable -------------------
    caps = {".meta": 720, ".say": 820, ".note-box": 900, ".pgsub": 620}
    for sel, want in caps.items():
        rule = re.search(re.escape(sel) + r'\s*\{([^}]*)\}', css)
        if rule and "max-width" not in rule.group(1):
            warn("T1", f"{sel} has no max-width; §5d caps it at {want}px so lines stay 60–90 characters")
    # The two dashboards name their long-prose row differently; check whichever one is present
    # rather than hard-coding the main dashboard's markup.
    prose = [(r'\.alert-row\s*>\s*span:last-child', ".alert-row > span:last-child"),
             (r'\.rule\s+\.det', ".rule .det")]
    for pat, label in prose:
        if re.search(pat.replace("\\s*>", "") .replace("\\s+", " ").replace("\\.", "."), src.replace('"', "'")) or re.search(pat, css):
            if not re.search(pat + r'\s*\{[^}]*max-width', css):
                err("T2", f"long prose rows ({label}) are uncapped. This was the worst offender in "
                          "the 2026-09-06 review: 242 characters on one 1252px line, 2.7× the "
                          "comfortable limit (§5d).")

    # -- §5d muted grey has to stay legible at 10.5–11.5px -----------------
    muted, surf, page = css_var(css, "--muted"), css_var(css, "--surface"), css_var(css, "--page")
    for bg, label in ((surf, "--surface"), (page, "--page")):
        if muted and bg and muted.startswith("#") and bg.startswith("#"):
            c = contrast(muted, bg)
            if c < 4.5:
                err("K1", f"--muted {muted} on {label} {bg} is {c}:1, below AA 4.5. "
                          "It carries the 10.5–11.5px .lab/.cap text (§5d).")
            else:
                note("K1", f"--muted on {label}: {c}:1 ✓")

    # -- §4 a page is a NAV entry plus a section, and nothing else ---------
    keys = set(re.findall(r'\{k:"([a-z]+)"', src))
    secs = set(re.findall(r'<section data-pg="([a-z]+)"', src))
    for k in sorted(keys - secs):
        err("S1", f'NAV has "{k}" but there is no <section data-pg="{k}">')
    for k in sorted(secs - keys):
        err("S1", f'<section data-pg="{k}"> exists but nothing in NAV points to it')

    # -- §4 the documents that describe this file have to still be true ----
    # Docs rot fastest right after a refactor, and a stale spec is worse than none: the next
    # session trusts it. S4 covers DESIGN.md (the page table, the two body widths, --headh)
    # and README.md (the entry points it advertises, and every path it hands you). Both are
    # checked from the main dashboard -- it is the one they tabulate, and the investment
    # dashboard is read off disk from here.
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)), ".."))
    b_min = re.search(r'min-width:\s*(\d+)px', bodycss)
    nav = re.search(r'const NAV = \[(.*?)\n\];', src, re.S)
    if nav:
        real = {}
        for sec, items in re.findall(r'\{sec:"([^"]*)",\s*items:\[(.*?)\]\}', nav.group(1), re.S):
            real[sec or "—"] = re.findall(r'n:"([^"]+)"', items)
        n_pages = len(re.findall(r'\{k:"', nav.group(1)))
        n_secs = len([k for k in real if k != "—"])   # Home sits above the section list
        top = real.get("—", []) + [k for k in real if k != "—"]   # sidebar as a reader sees it

        design = os.path.join(root, "DESIGN.md")
        if os.path.exists(design):
            spec = open(design, encoding="utf-8").read()
            # The count lives in a marker, not in the sentence beside it: S4 used to read it out
            # of the sentence beside it, so rewording -- or translating -- that line turned this
            # check off without a word. 2026-09-09.
            m = re.search(r'<!--\s*LINT:PAGES\s+pages=(\d+)\s+sections=(\d+)\s*-->', spec)
            if not m:
                warn("S4", "DESIGN.md has no <!-- LINT:PAGES pages=N sections=M --> marker, so its "
                           "page table is no longer checked against NAV")
            elif int(m.group(1)) != n_pages or int(m.group(2)) != n_secs:
                err("S4", f"DESIGN.md §4 says {m.group(1)} pages in {m.group(2)} sections; "
                          f"NAV actually has {n_pages} pages in {n_secs} named sections")
            for sec, names in real.items():
                if sec == "—":
                    continue
                row = re.search(r'\|\s*' + re.escape(sec) + r'\s*\|([^|]*)\|', spec)
                if not row:
                    err("S4", f'DESIGN.md §4 has no row for the "{sec}" section')
                else:
                    listed = [x.strip() for x in row.group(1).split("·")]
                    if listed != names:
                        err("S4", f'DESIGN.md §4 lists {sec} as "{" · ".join(listed)}" '
                                  f'but NAV has "{" · ".join(names)}"')
            d_w = re.search(r'min-width:\s*(\d+)px;\s*max-width:\s*(\d+)px', spec)
            if d_w and b_min and mw and (d_w.group(1), d_w.group(2)) != (b_min.group(1), mw.group(1)):
                err("S4", f"DESIGN.md §4 says body is {d_w.group(1)}–{d_w.group(2)}px; "
                          f"this file has {b_min.group(1)}–{mw.group(1)}px")
            d_h, f_h = re.search(r'--headh:\s*(\d+)px', spec), css_var(css, "--headh")
            if d_h and f_h and d_h.group(1) + "px" != f_h:
                err("S4", f"DESIGN.md §5a says --headh:{d_h.group(1)}px; this file has {f_h}. "
                          "The two divider lines only align because both blocks read that variable.")

        # README.md is the front door; README.zh.md is the same door in Chinese (2026-09-11) and
        # is held to the same markers, paths and images, so a translation cannot go stale unseen.
        for rname in ("README.md", "README.zh.md"):
            readme = os.path.join(root, rname)
            if not os.path.exists(readme):
                continue
            rd = open(readme, encoding="utf-8").read()

            # -- S6 "N planted faults" is derived, never typed ---------------
            # 2026-09-09: README said 22 in English and 22 in Chinese, release.py said 22 in one
            # place and 24 in another, and the table actually held 26. A number that describes the
            # code belongs to the code; the marker is language-free so a translation cannot hide it.
            # -- S7 the "N constants" claim, and the names beside it -------------
            # Same disease as S6: CLAUDE.md said 15, the public CLAUDE.md said 16, rebuild.py
            # derived 17. The list of names drifts the same way, so both are read from the script.
            rb = os.path.join(root, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py")
            for doc in ("CLAUDE.md", "README.md"):
                dp = os.path.join(root, doc)
                if not (os.path.exists(rb) and os.path.exists(dp)):
                    continue
                names = set(re.findall(r'out\["(\w+)"\]', open(rb, encoding="utf-8").read()))
                dt = open(dp, encoding="utf-8").read()
                cm = re.search(r'<!--\s*LINT:CONSTS\s+n=(\d+)\s*-->', dt)
                if cm and int(cm.group(1)) != len(names):
                    err("S7", f"{doc} says rebuild.py derives {cm.group(1)} constants; it derives "
                              f"{len(names)}")
                if cm:
                    missing = sorted(n for n in names if n not in dt)
                    if missing:
                        err("S7", f"{doc} lists the constants rebuild.py derives but omits "
                                  + ", ".join(missing))

            st = os.path.join(root, ".claude", "skills", "workspace-checks", "scripts", "selftest.py")
            if os.path.exists(st):
                real = len(re.findall(r'^\s*\("[A-Z]\d+",\s*"',
                                      open(st, encoding="utf-8").read(), re.M))
                # CLAUDE.md advertises the same numbers and was not covered when S6 was written:
                # it still said 21 and 24 an hour after the table reached 26 (2026-09-09).
                # A separate variable: `rd` is what S4 resolves paths out of further down, and
                # folding CLAUDE.md into it made every backticked word in that file a README path.
                extra = os.path.join(root, "CLAUDE.md")
                adv = rd + ("\n" + open(extra, encoding="utf-8").read() if os.path.exists(extra) else "")
                fm = re.search(r'<!--\s*LINT:FAULTS\s+n=(\d+)\s*-->', adv)
                if not fm:
                    warn("S6", f"{rname} has no <!-- LINT:FAULTS n=N --> marker; the number of "
                               "planted faults it advertises is unchecked")
                elif int(fm.group(1)) != real:
                    err("S6", f"{rname} says selftest plants {fm.group(1)} faults; the table has {real}")
                else:
                    for m in re.finditer(r'(\d+)\s*(?:specific\s+)?(?:planted\s+)?faults?|种下\s*(\d+)\s*个故障', adv):
                        n = m.group(1) or m.group(2)
                        if n and int(n) != real:
                            err("S6", f"{rname} says {n} faults somewhere in prose; the table has {real}")
            # `inv=N` is optional since 2026-09-10: the investment dashboard was merged into the
            # main page, and a README that still advertises one is checked only if the file exists.
            nav_m = re.search(r'<!--\s*LINT:NAV\s+main=(\d+)/(\d+)(?:\s+inv=(\d+))?'
                              r'\s+minwidth=(\d+)\s*-->', rd)
            if not nav_m:
                warn("S4", f"{rname} has no <!-- LINT:NAV main=P/S inv=P minwidth=W --> marker. The "
                           "numbers it advertises are unchecked -- and this check used to read "
                           "them out of Chinese prose, so a translation would have silenced it.")
            else:
                if (int(nav_m.group(1)), int(nav_m.group(2))) != (n_pages, n_secs):
                    err("S4", f"{rname} says the main dashboard is {nav_m.group(1)} pages / "
                              f"{nav_m.group(2)} sections; NAV has {n_pages} / {n_secs}")
                if b_min and nav_m.group(4) != b_min.group(1):
                    err("S4", f"{rname} tells the reader the window has to be at least "
                              f"{nav_m.group(4)}px; body min-width is {b_min.group(1)}px")
                # The sidebars a reader is actually shown: the "·" lines following the marker.
                bullets = [l for l in rd[nav_m.end():].split("\n## ", 1)[0].splitlines()
                           if "·" in l]
                inv = os.path.join(root, "dashboards", "investment_dashboard.html")
                inames = []
                if os.path.exists(inv):
                    inav = re.search(r'const INAV = \[(.*?)\n\];',
                                     open(inv, encoding="utf-8").read(), re.S)
                    if inav:
                        inames = re.findall(r'n:"([^"]+)"', inav.group(1))
                        if nav_m.group(3) is not None and int(nav_m.group(3)) != len(inames):
                            err("S4", f"{rname} says the investment dashboard is "
                                      f"{nav_m.group(3)} pages; INAV has {len(inames)}")
                for got, wanted, what in ((bullets[0] if bullets else None, top, "sidebar"),
                                          (bullets[1] if len(bullets) > 1 else None, inames,
                                           "investment dashboard")):
                    if got is None or not wanted:
                        continue
                    listed = [x.strip() for x in got.split("·")]
                    if listed != wanted:
                        err("S4", f'README lists the {what} as "{" · ".join(listed)}" '
                                  f'but the file has "{" · ".join(wanted)}"')
            # Every path README hands you has to resolve. A front door that points at a file
            # which moved is worse than one that says nothing -- 2026-09-06 it shipped with
            # `friend_ledger.csv` instead of `findata/friend_ledger.csv`.
            for tok in re.findall(r'`([^`\n]+)`', re.sub(r'```.*?```', '', rd, flags=re.S)):
                if " " in tok or "<" in tok:
                    continue                       # a filename pattern, not a path
                if "/" not in tok and not re.search(r'\.(md|html|csv|json|py)$', tok):
                    continue                       # `data`, `-2` and friends are just words
                if tok.startswith(("~", "/", "http")):
                    continue                       # not a path inside the workspace, so resolving
                                                   # it against root is meaningless (2026-09-09:
                                                   # the README naming the release output outside
                                                   # the repo was reported as a broken link)
                if os.path.exists(os.path.join(root, tok)):
                    continue
                # A bare filename is a prose mention ("check_data.py owns the numbers"), so it counts
                # as resolved if it still exists anywhere in the tree. A token with a slash
                # in it is a path the reader is meant to follow, and has to be exact.
                # 2026-09-08: this used to walk a hardcoded "skills/" folder, which stopped
                # existing the day the skills moved to .claude/skills/ -- so the checker that
                # guards against stale paths broke on a stale path of its own. Walk the tree.
                if "/" not in tok and _exists_somewhere(root, tok):
                    continue
                err("S4", f"{rname} points at `{tok}`, which does not exist")

            # Images too: the hero and the pipeline diagram are handed to the reader by an <img>
            # or a ![](), neither of which is backticked, so the sweep above never saw them.
            # A README whose first impression is a broken-image icon is exactly what S4 is for.
            for img in set(re.findall(r'<img[^>]+src="([^"]+)"', rd)
                           + re.findall(r'!\[[^\]]*\]\(([^)]+)\)', rd)):
                if img.startswith(("http://", "https://", "data:")):
                    continue
                if not os.path.exists(os.path.join(root, img.split("#")[0])):
                    err("S4", f"{rname} shows the image `{img}`, which does not exist")

    # -- S4 / S6 for the documents the model reads --------------------------------------
    # The three SKILL.md files are the instructions Claude follows on every import and setup, and
    # nothing checked them: on 2026-09-13 the import skill still told the run to check
    # `dashboards/ly_finance_dashboard.html` three days after the page was renamed, and the checks
    # skill said the selftest plants "fifteen" faults when the table held 42. A path in a skill has
    # to resolve the way a README path does -- exactly against the workspace, against the skill's
    # own folder, or, for a bare name or a folder mentioned in passing, anywhere in the tree. The
    # scripts and pages a fenced command runs are held to the same rule, because those are the
    # lines the model copies. A skill's "N faults" is read from the selftest table like README's.
    skills = os.path.join(root, ".claude", "skills")
    st = os.path.join(skills, "workspace-checks", "scripts", "selftest.py")
    real = len(re.findall(r'^\s*\("[A-Z]\d+",\s*"', open(st, encoding="utf-8").read(), re.M)) \
        if os.path.exists(st) else None
    for sk in (sorted(os.listdir(skills)) if os.path.isdir(skills) else []):
        sp = os.path.join(skills, sk, "SKILL.md")
        if not os.path.exists(sp):
            continue
        doc = f".claude/skills/{sk}/SKILL.md"
        text = open(sp, encoding="utf-8").read()
        fences = "\n".join(re.findall(r'```.*?```', text, flags=re.S))
        prose = re.sub(r'```.*?```', '', text, flags=re.S)
        toks = set(re.findall(r'`([^`\n]+)`', prose))
        # in a command, only the scripts and pages it names: a .json it writes may not exist yet
        toks |= set(re.findall(r'(?<![\w/$])((?:[\w.-]+/)*[\w.-]+\.(?:py|html))\b', fences))
        ignored = [l.strip().lstrip("!") for l in open(os.path.join(root, ".gitignore"), encoding="utf-8")
                   if l.strip() and not l.startswith("#")] if os.path.exists(os.path.join(root, ".gitignore")) else []
        for tok in sorted(toks):
            if any(c in tok for c in " <*{$[]") or tok.startswith(("~", "/", "http", "..")):
                continue                       # a pattern, a placeholder, or outside the workspace
            if "/" not in tok and not re.search(r'\.(md|html|csv|json|py)$', tok):
                continue                       # `type`, `--verify` and friends are just words
            if re.fullmatch(r'[\w.-]+/', tok):
                continue                       # `decisions/`: a folder named, not a path to follow
            cand = tok.rstrip("/")
            if any(g.rstrip("/") == cand or os.path.basename(g.rstrip("/")) == os.path.basename(cand)
                   for g in ignored):
                continue                       # written by an owner, deliberately not shipped
            # An owner's copy may still carry the `ly_` name (CLAUDE.md, first paragraph); the
            # tool's skills name the page as the template does.
            alias = os.path.join(root, "dashboards", "ly_" + os.path.basename(cand)) \
                if cand.startswith("dashboards/") else ""
            if (os.path.exists(os.path.join(root, cand)) or os.path.exists(os.path.join(skills, sk, cand))
                    or (alias and os.path.exists(alias))
                    or _exists_somewhere(root, os.path.basename(cand))):
                continue
            err("S4", f"{doc} points at `{tok}`, which does not exist")
        if real is not None:
            fm = re.search(r'<!--\s*LINT:FAULTS\s+n=(\d+)\s*-->', text)
            if fm and int(fm.group(1)) != real:
                err("S6", f"{doc} says selftest plants {fm.group(1)} faults; the table has {real}")
            for m in re.finditer(r'(\d+)\s*(?:specific\s+)?(?:planted\s+)?faults?', prose):
                if int(m.group(1)) != real:
                    err("S6", f"{doc} says {m.group(1)} faults somewhere in prose; the table has {real}")

    # -- S5 the sidebar wordmark must still have both halves ----------------
    # DESIGN.md §5a: the top of the sidebar is a mark plus the brand text. On 2026-09-09 an
    # edit gave the <span> the same id as its parent <button>, so setting textContent on the
    # id wiped the button's children -- the mark vanished on load and every checker still
    # passed, because none of them looked for it.
    # Only the main dashboard carries a wordmark; DESIGN.md §5a gives the investment one a
    # link back instead, so `const NAV` is what says which file this is.
    if re.search(r'^const NAV = \[', src, re.M):
        brand = re.search(r'<button class="brand"[^>]*>(.*?)</button>', src, re.S)
        if not brand:
            err("S5", "the sidebar has no .brand button (DESIGN.md §5a)")
        else:
            inner = brand.group(1)
            if "<svg" not in inner:
                err("S5", "the sidebar wordmark has no mark in it (DESIGN.md §5a)")
            ids = re.findall(r'id="([^"]+)"', brand.group(0))
            if len(ids) != len(set(ids)):
                err("S5", f"duplicate id inside the wordmark: {ids}. Writing textContent to a "
                          "shared id wipes the mark.")

    # -- §5a the two header rules must land on the same line ---------------
    if ".pghead" in css:
        # the wordmark block is .brand on the main dashboard and .side .head on the investment one
        wm = re.search(r'\.(?:side\s+\.head|side\s+\.brand|brand)\s*\{([^}]*)\}', css)
        head = re.search(r'\.pghead\s*\{([^}]*)\}', css)
        both = (wm and "var(--headh)" in wm.group(1)) and (head and "var(--headh)" in head.group(1))
        if not both:
            warn("S2", "the sidebar wordmark and .pghead should both take their height from "
                       "var(--headh); otherwise their divider lines drift apart per page (§5a)")

    # -- §5d auto-fit with a fixed max silently drops a column -------------
    for m in re.finditer(r'repeat\(auto-fit,\s*minmax\(\s*\d+px\s*,\s*(\d+)px\s*\)\)', css):
        err("S3", f"grid auto-fit with a fixed {m.group(1)}px max sizes tracks at that max, so it "
                  "fits fewer cards than the row can hold and wraps the rest. §5d switched the "
                  "stat rows to flex with flex:1 1 190px; max-width.")

    # -- §4 self-contained, no network --------------------------------------
    for m in re.finditer(r'<(?:script|link)\b[^>]*(?:src|href)="(https?:)?//[^"]+"', src):
        err("X1", f"external resource {m.group(0)[:70]}… — dashboards must be self-contained (§4)")

    # -- §5b the page talks about the owner's money, never about itself (S8) -------------
    # 2026-09-10, the owner: "the UI language has too much AI in it." The tells: the page saying
    # "I", explaining how it knows ("worked out from your data"), rule numbers, file names and
    # checker vocabulary on screen. Scanned on the page CODE -- the template when there is one --
    # because the prose in tasks.json or rules.json is the owner's own and is theirs to write.
    is_main = bool(re.search(r'^const NAV = \[', src, re.M))
    tpl = os.path.join(root, "templates", "dashboards",
                       "finance_dashboard.html" if is_main else os.path.basename(path))
    code = open(tpl, encoding="utf-8").read() if os.path.exists(tpl) \
        else re.sub(r'^const [A-Z_]+ = .*;$', '', src, flags=re.M)
    code = re.sub(r'^\s*//.*$', '', code, flags=re.M)            # comments are for the maintainer
    code = re.sub(r'<style>.*?</style>', lambda m: "\n" * m.group(0).count("\n"), code, flags=re.S)
    # `I` followed by a dot is a JavaScript object (INVEST is `I` in the code), not a pronoun.
    VOICE = [(r"\bI\b(?![.\w])|\bI[\u2019']", "the page speaks in the first person"),
             (r'\b[Rr]ule \d', "a rule number"),
             (r'\b\w+\.(?:json|csv)\b|\bfindata\b', "a file name"),
             (r'\b(?:lint(?:er)?|checker|constant|denominator)\b', "tool vocabulary"),
             (r'\b(?:worked out from|not written by hand|derived from|re-?derives?)\b',
              "an explanation of how the page knows")]
    texts = [(l, s) for l, s in js_strings(code)
             if not re.search(r'\n\s*(?://|const |let |function |\}\))', s)]   # a literal that swallowed code
    html = re.sub(r'<script>.*?</script>', lambda m: "\n" * m.group(0).count("\n"), code, flags=re.S)
    texts += [(html[:m.start()].count("\n") + 1, m.group(1).strip())
              for m in re.finditer(r'>([^<>]{3,})<', html)]
    where = "template" if os.path.exists(tpl) else "page"
    for line, s in texts:
        for pat, why in VOICE:
            m = re.search(pat, s)
            if m:
                err("S8", f'{where} line {line}: "{s[:80]}" — {why} ({m.group(0)!r}). The page talks '
                          "about your money, never about itself (DESIGN.md §5b).")
                break

    # -- §5b one fact per line, no "·" chains -------------------------------
    for line, s in js_strings(src):
        if re.search(r'<[a-z/]', s) or "class=" in s:
            continue        # markup template, not a sentence shown to the reader
        if s.count("·") >= 2 and len(s) > 45:
            note("W1", f'line {line}: "{s[:88]}" — {s.count("·")} "·" in one string. '
                       "Fine for a list of account names, wrong for a chain of facts (§5b).")
    for m in re.finditer(r'(hoverable|showTip)\s*\([^;]{0,400}?·', src, re.S):
        warn("W2", f"line {src[:m.start()].count(chr(10))+1}: a tooltip built with "
                   f"{m.group(1)}() contains '·'. §5 puts one fact per line with <br>.")
    return F

# ---------------------------------------------------------------- output
def main(argv):
    v = "-v" in argv or "--verbose" in argv
    argv = [a for a in argv if not a.startswith("-")]
    if not argv:
        print(__doc__); return 2
    worst = 0
    for path in argv:
        if not os.path.exists(path):
            print(f"missing: {path}"); worst = 2; continue
        if render(f"design — {os.path.basename(path)}", check(path), v):
            worst = max(worst, 1)
    return worst

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
