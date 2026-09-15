#!/usr/bin/env python3
"""Open the dashboards in a real browser and check what only a browser can see.

check_design.py reads the file as text, so it can prove a chart has no fixed height in the
CSS. It cannot prove the chart then actually grows on a 32" screen, that every page still
draws instead of throwing, or that nothing scrolls sideways at 1120px. Those four things were
checked by hand every time -- about 28 tool calls a run, and the findings were re-derived from
scratch each month because nothing wrote down how the navigation works.

Usage:  python3 check_render.py dashboards/a.html [dashboards/b.html ...] [-v]
Exit:   0 clean or notes only, 1 if any ERROR, 2 if the browser is missing

Needs Playwright + Chromium (installed 2026-09-08):
    pip3 install --user playwright && python3 -m playwright install chromium
"""
import os, sys

WIDTHS = [1120, 1440, 1760]   # DESIGN.md §4: min-width 1120, max-width 1760
TALL   = 900                  # viewport height used for the "does a page fill a screen" check
FILLS  = 600                  # a page shorter than this at 900px tall leaves the screen empty

CATS = [("build",   "is the artefact current with findata/"),
        ("conform", "does it still follow DESIGN.md")]
CAT_ORDER = [c[0] for c in CATS]
CAT_LABEL = {c[0]: c[1] for c in CATS}

# Collected inside the page. Kept here rather than rediscovered every month: the sidebar is a
# list of [data-k] elements that are CLICKED -- the location hash is a compound state string
# (#p=home&ym=...&alw=...), so assigning to it does not navigate and neither does firing
# hashchange. Some [data-k] elements are spending-category chips, not pages; a data-k with no
# matching section[data-pg] is one of those and is skipped, not reported as a broken link.
PROBE = r"""
async () => {
  const errs = [];
  window.addEventListener('error', e => errs.push(String(e.message)));
  const navs = [...document.querySelectorAll('[data-k]')]
      .filter(el => document.querySelector('section[data-pg="' + el.dataset.k + '"]'));
  const pages = [];
  for (const el of navs) {
    el.click();
    await new Promise(r => setTimeout(r, 90));
    const s = document.querySelector('section[data-pg="' + el.dataset.k + '"]');
    const r = s.getBoundingClientRect();
    pages.push({
      k: el.dataset.k,
      shown: getComputedStyle(s).display !== 'none',
      h: Math.round(r.height),
      text: s.innerText.trim().length,
      // Text that only a broken template produces. 2026-09-08 a renamed field left
      // "undefined transfer" on the Insights page and all three text checkers passed.
      // ⚠ PROBE must stay a RAW string: written as a normal one, the \b below became a Python
      // backspace (\x08) and this regex could never match anything, so R5 reported "clean" from
      // the day it was written until 2026-09-09. A check that cannot fail is not a check.
      junk: (s.innerText.match(/\b(undefined|NaN|null|\[object Object\])\b/g) || []).slice(0, 3),
      // The PAINTED width, not the element's box. With a fixed height plus
      // preserveAspectRatio the <svg> element still stretches full width while the drawing
      // inside it is scaled to the height and centred -- so a bounding rect shows no problem
      // and the chart is capped anyway. getScreenCTM().a is the viewBox-unit -> CSS-pixel
      // scale actually in force, so viewBox width x that is what the reader sees.
      charts: [...s.querySelectorAll('svg, canvas')].map(c => {
        if (c.tagName.toLowerCase() === 'svg' && c.viewBox && c.viewBox.baseVal &&
            c.viewBox.baseVal.width && c.getScreenCTM()) {
          return Math.round(c.viewBox.baseVal.width * c.getScreenCTM().a);
        }
        return Math.round(c.getBoundingClientRect().width);
      }).filter(w => w > 200),
      hscroll: document.documentElement.scrollWidth - document.documentElement.clientWidth
    });
  }
  const sections = [...document.querySelectorAll('section[data-pg]')].map(s => s.dataset.pg);
  return { pages, sections, errs };
}
"""


def probe(path):
    """Load the page once per width and return {width: result}. Import is inside the function
    so the missing-browser message is a sentence, not a traceback from the top of the file."""
    from playwright.sync_api import sync_playwright
    out, console = {}, []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for w in WIDTHS:
            pg = b.new_page(viewport={"width": w, "height": TALL})
            pg.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: console.append(str(e)))
            pg.goto("file://" + os.path.abspath(path))
            pg.wait_for_timeout(400)
            out[w] = pg.evaluate(PROBE)
            pg.close()
        b.close()
    return out, console


def check(path):
    F = []
    def err(r, m, c="build"):  F.append(("ERROR", r, m, c))
    def warn(r, m, c="conform"): F.append(("WARN", r, m, c))
    def note(r, m, c="conform"): F.append(("NOTE", r, m, c))

    res, console = probe(path)

    # -- R1 every nav entry draws its section, and nothing throws on the way ----
    for w, r in res.items():
        for p in r["pages"]:
            if not p["shown"]:
                err("R1", f"{w}px: clicking '{p['k']}' leaves its section hidden")
            elif p["h"] < 40:
                err("R1", f"{w}px: page '{p['k']}' renders {p['h']}px tall — it is throwing "
                          f"or its data is empty")
        for e in r["errs"]:
            err("R1", f"{w}px: uncaught error — {e[:120]}")
    # -- R5 a page must never show the words a broken template leaves behind ---
    seen = set()
    for r in res.values():
        for p in r["pages"]:
            for j in p["junk"]:
                if (p["k"], j) not in seen:
                    seen.add((p["k"], j))
                    err("R5", f"page '{p['k']}' shows the word \"{j}\" — a field or variable is missing")
    if not seen:
        note("R5", "no undefined / NaN / null in any rendered page", "build")
    for c in console:
        err("R1", f"console error — {c[:120]}")

    base = res[WIDTHS[0]]
    reached = {p["k"] for p in base["pages"]}
    for pg in base["sections"]:
        if pg not in reached:
            err("R1", f"section '{pg}' exists but no sidebar entry reaches it")
    note("R1", f"{len(reached)} pages reached and drawn, no uncaught errors")

    # -- R2 desktop-only means no sideways scrolling anywhere in the range ------
    for w, r in res.items():
        over = {p["k"]: p["hscroll"] for p in r["pages"] if p["hscroll"] > 0}
        for k, px in over.items():
            err("R2", f"{w}px: page '{k}' scrolls {px}px sideways", "conform")
    if not any(p["hscroll"] > 0 for r in res.values() for p in r["pages"]):
        note("R2", f"no horizontal scroll at {' / '.join(map(str, WIDTHS))}px")

    # -- R3 charts must actually get bigger on a bigger screen -----------------
    # DESIGN.md §4: a fixed pixel height plus preserveAspectRatio means the chart is scaled to
    # its height and centred, so a wider window only adds white space. Found on the owner's 32"
    # screen 2026-09-06; the CSS check alone cannot see it because the cap can come from an
    # inline style, a parent, or the viewBox.
    narrow = {p["k"]: p["charts"] for p in res[WIDTHS[0]]["pages"]}
    wide   = {p["k"]: p["charts"] for p in res[WIDTHS[-1]]["pages"]}
    grew = capped = 0
    for k, ws in wide.items():
        ns = narrow.get(k, [])
        for i, w_px in enumerate(ws):
            if i >= len(ns):
                continue
            if w_px <= ns[i] + 2:
                capped += 1
                err("R3", f"page '{k}': a chart draws {ns[i]}px at {WIDTHS[0]} and {w_px}px at "
                          f"{WIDTHS[-1]} — it is height-capped, so the extra width is white space",
                    "conform")
            else:
                grew += 1
    if grew and not capped:
        note("R3", f"{grew} charts grow with the window "
                   f"({WIDTHS[0]} → {WIDTHS[-1]}px)")

    # -- R4 a page should fill the screen it opens on ---------------------------
    thin = sorted((p["h"], p["k"]) for p in res[1440]["pages"] if p["h"] < FILLS)
    for h, k in thin:
        warn("R4", f"page '{k}' is only {h}px tall at 1440×{TALL} — it does not fill a screen",
             "conform")
    if not thin:
        note("R4", f"every page fills a {TALL}px screen")
    return F


def render(title, F, verbose=False):
    print(f"\n=== {title} ===")
    bad = 0
    if not F:
        print("  ✓ nothing to check here")
        return 0
    for cat in CAT_ORDER:
        rows = [f for f in F if f[3] == cat]
        if not rows:
            continue
        errs  = [r for r in rows if r[0] == "ERROR"]
        warns = [r for r in rows if r[0] == "WARN"]
        bad += len(errs)
        mark = "✗" if errs else ("⚠" if warns else "✓")
        tally = (f"{len(errs)} problem" + ("s" if len(errs) != 1 else "")) if errs \
                else (f"{len(warns)} to look at" if warns else f"{len(rows)} checks")
        print(f"  {cat:<10} {mark} {tally}")
        for sev, rule, msg, _ in errs + warns:
            print(f"     {'✗' if sev == 'ERROR' else '⚠'} [{rule}] {msg}")
        if verbose:
            for _, rule, msg, _c in [r for r in rows if r[0] == "NOTE"]:
                print(f"     · [{rule}] {msg}")
    return bad


def main(argv):
    v = "-v" in argv or "--verbose" in argv
    argv = [a for a in argv if not a.startswith("-")]
    if not argv:
        print(__doc__); return 2
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("check_render needs Playwright, which is not installed:\n"
              "  pip3 install --user playwright && python3 -m playwright install chromium")
        return 2
    worst = 0
    for path in argv:
        if not os.path.exists(path):
            print(f"missing: {path}"); worst = 2; continue
        if render(f"render — {os.path.basename(path)}", check(path), v):
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
