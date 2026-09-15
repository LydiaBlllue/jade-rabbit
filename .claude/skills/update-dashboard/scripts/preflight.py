#!/usr/bin/env python3
"""Step 0 of "update the dashboard": say what is in inbox/ before a single file is parsed.

Two jobs, both of them lessons rather than conveniences.

1. NAME every file, and stop on anything it cannot name. Mis-filing a statement is worse than
   missing one: at one bank a "-2" suffix is a different ACCOUNT, while at another it
   "-2" is a byte-identical duplicate. Getting that backwards either invents a ledger or
   destroys one. Where the name alone is ambiguous the script says so instead of choosing.

2. CATCH WHAT MOVES UNDER YOU. Two different failures, one mechanism:

   inbox/   — a file ARRIVES mid-run. On 2026-09-06 nine bank statements finished syncing from
              iCloud after the inbox had been read, and were noticed only once the holdings work
              was finished.
   findata/ — a file you already READ changes while you are still reasoning about it. On
              2026-09-08 foreign.json changed its total and named a bank that had been
              "unconfirmed" while a two-hour piece of work was being built on the old figures.
              Nothing was overwritten and no write failed — the WRITES were fine. What went
              stale was the picture the conclusions were drawn from, and nothing said so.

   That second one cannot be grepped for: the file is correct, the write is correct, and only
   the timestamp of the copy in your head is wrong. So it has to be checked, not remembered.

Usage:
    preflight.py [root]             # step 0 — full report, records a fingerprint
    preflight.py [root] --verify    # before any write — one line if nothing moved
    preflight.py [root] --reseed    # after a write YOU intended — re-point the fingerprint
    preflight.py [root] --session   # SessionStart hook: seed silently, speak only if it matters

The --session mode is why the fingerprint is reliable at all. Step 0 only helps if somebody runs
it, and on 2026-09-08 nobody did: the session read inbox/ once at the start, three account
screenshots arrived at 20:50, and they were found hours later by accident. Wired to SessionStart
it seeds every session without being remembered, and stays silent unless something is waiting.
"""
import sys, os, re, json, csv, hashlib, tempfile
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # where each findata file lives (schema 6)

IGNORE = {".DS_Store", "README.txt", "Icon\r"}
MONTHS = ("January February March April May June July August September October November December").split()

# --- what a filename means -------------------------------------------------
# The naming rules are the banks' own defaults, and the accounts come from findata/accounts.json:
# documents[].file is the pattern each one arrives under, documents[].closes tells same-named
# statements apart (same filename, different close day). Until 2026-09-09 this was a table of
# the owner's account numbers written into the script -- the same drift as a table in a doc.
NOTES = {   # what to do with each target file: tool knowledge, keyed by file, not by account
    "spending.csv": "Categorise via merchants.json; a miss is a new merchant for the report.",
    "chequing.csv": "Payroll and broker transfers are typed on the ledger rows. Check every "
                    "Interac sender against the friend ledger before typing anything as income.",
    "rbc_chequing.csv": "Contactless Interac purchases ALSO go to spending.csv, tagged with this "
                        "account's spendTag. An e-Transfer received from the owner's own name is a "
                        "move between her banks, not income.",
    "bmo_savings.csv": "The '-2' file is a second ACCOUNT, not a duplicate.",
    "holdings_latest.csv": "Replaces the file wholesale. Also refresh accounts.json balances.",
    "ws_activities.csv": "Also update fx.json from the 'FX Rate:' rows, and WSDEP / WSINC.",
    "foreign.json": "Read the balances off the image; each account carries its own as-of.",
}
DOCS = []           # set by main() from accounts.json; classify() reads it

def load_docs(root):
    try:
        aj = json.load(open(layout.path(root, "accounts.json"), encoding="utf-8"))
    except Exception:
        return []
    by_key = {a["key"]: a for a in aj.get("accounts", [])}
    out = []
    for d in aj.get("documents", []):
        pat = d.get("file", "") or ""
        if "<" in pat and ">" in pat:
            pre, suf = pat.split("<", 1)[0], pat.rsplit(">", 1)[1]
        else:
            pre, suf = pat, ""
        m = re.search(r"\d{3,}", pre)
        closes = re.search(r"\d+", d.get("closes", "") or "")
        out.append(dict(doc=d, prefix=pre.strip().lower(), suffix=suf.lower(),
                        digits=m.group(0) if m else None,
                        close_day=int(closes.group(0)) if closes else None,
                        acct=by_key.get((d.get("covers") or [None])[0]) or {}))
    return out

def classify(name):
    n = name.strip()
    low = n.lower()
    def hit(x, extra=""):
        d, a = x["doc"], x["acct"]
        note = ((d.get("reconcile") or "") + " " + NOTES.get(d.get("into"), "") + extra).strip()
        return (f"{d['ep']} {d['key']}", a.get("id") or "all covered accounts", d.get("into"), note)

    if low.endswith((".png", ".jpg", ".jpeg", ".heic", ".webp")):
        shots = [x for x in DOCS if x["doc"].get("into") == "foreign.json"]
        if shots:
            return ("Screenshot: " + " / ".join(x["doc"]["key"] for x in shots), "foreign accounts",
                    "foreign.json", NOTES["foreign.json"])
        return (None, None, None, "A screenshot, but no document in accounts.json expects one.")

    # Some banks ship several accounts under the same "<Month D, YYYY>.pdf" name. The close DAY
    # separates them (documents[].closes); a -2 suffix is the second account in the same batch.
    m = re.match(r"^([A-Z][a-z]+) (\d{1,2}), (\d{4})(-2| \(2\))?\.pdf$", n)
    if m and m.group(1) in MONTHS:
        day, dup = int(m.group(2)), m.group(4)
        cands = [x for x in DOCS if x["prefix"] == "" and x["suffix"].endswith(".pdf")]
        if dup:
            c = [x for x in cands if x["suffix"].startswith("-2")]
            if c:
                return hit(c[0], " *** The '-2' file is a second ACCOUNT, not a duplicate. ***")
        else:
            c = sorted([x for x in cands if not x["suffix"].startswith("-2") and x["close_day"]],
                       key=lambda x: abs(x["close_day"] - day))
            if c and abs(c[0]["close_day"] - day) <= 7:
                return hit(c[0])
        return (None, None, None,
                f"A bank statement dated the {day}th -- no document in accounts.json closes near "
                f"that day. Ask which account it is.")
    for x in DOCS:
        if x["prefix"] and low.startswith(x["prefix"]):
            return hit(x)
    for x in DOCS:
        if x["digits"] and x["digits"] in low:
            return hit(x)
    return (None, None, None, "Filename matches nothing in accounts.json documents[].")


def scan(area):
    out = []
    for dirpath, _, files in os.walk(area):
        for f in sorted(files):
            if f in IGNORE or f.startswith("."):
                continue
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            out.append({"name": os.path.relpath(p, area), "path": p,
                        "size": st.st_size, "mtime": int(st.st_mtime)})
    return out


# Content hash, not mtime. iCloud rewrites mtimes without changing a byte, and a fingerprint that
# cries wolf gets ignored, which is the same as not having one.
def fingerprint(root):
    fp = {}
    for area in ("inbox", "findata"):
        d = os.path.join(root, area)
        if not os.path.isdir(d):
            continue
        for f in scan(d):
            fp[f"{area}/{f['name']}"] = sha(f["path"])
    return fp


def snap_path(root):
    key = hashlib.sha1(os.path.abspath(root).encode()).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"ly_preflight_{key}.json")


def sha(p, cap=8 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# --- how old is everything we already have ---------------------------------
def freshness(root):
    fd = lambda n: layout.path(root, n)
    rows, today = [], date.today()
    def add(label, d):
        if not d:
            rows.append((label, "—", None)); return
        age = (today - datetime.strptime(d, "%Y-%m-%d").date()).days
        rows.append((label, d, age))
    try:
        bj = json.load(open(fd("banks.json"), encoding="utf-8"))
        for a in bj["assets"] + bj["debts"]:
            if a.get("asof"):
                add(f"{a['inst']} {a['account']}", a["asof"])
    except Exception:
        pass
    for name, key in (("foreign.json", "asof"), ("fx.json", "asof")):
        try:
            add(name, json.load(open(fd(name), encoding="utf-8"))[key])
        except Exception:
            pass
    for name, col in (("holdings_latest.csv", None), ("ws_activities.csv", "effective_date"),
                      ("spending.csv", "date"), ("chequing.csv", "date"),
                      ("rbc_chequing.csv", "date"), ("bmo_savings.csv", "date")):
        try:
            if col:
                with open(fd(name), encoding="utf-8") as fh:
                    ds = [r[col] for r in csv.DictReader(fh) if r.get(col)]
                add(name + " (latest row)", max(ds) if ds else None)
        except Exception:
            pass
    return rows


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 and not argv[1].startswith("--") else os.getcwd()
    global DOCS
    DOCS = load_docs(root)
    verify = "--verify" in argv
    reseed = "--reseed" in argv
    session = "--session" in argv
    inbox = os.path.join(root, "inbox")
    if not os.path.isdir(inbox):
        print(f"no inbox/ under {root}"); return 2

    files = scan(inbox)
    fp, sp = fingerprint(root), snap_path(root)

    if session:
        # Always seed. Speak only when there is something to act on -- a line of noise at the top
        # of every unrelated session is a line that stops being read.
        json.dump(fp, open(sp, "w", encoding="utf-8"))
        say = []
        if files:
            say.append(f"{len(files)} file(s) waiting in inbox/: "
                       + ", ".join(os.path.basename(f["name"]) for f in files[:6])
                       + ("…" if len(files) > 6 else "")
                       + " — this is an import, use the update-dashboard skill.")
        old = [(l, a) for l, d_, a in freshness(root) if a is not None and a > 30]
        if old:
            worst = max(old, key=lambda x: x[1])
            say.append(f"{len(old)} data source(s) over 30 days old, oldest {worst[0]} at {worst[1]}d.")
        try:
            aj = json.load(open(layout.path(root, "accounts.json"), encoding="utf-8"))
            bad = [g for g in aj.get("gaps", []) if g.get("sev") == "bad"]
            if bad:
                say.append(f"{len(bad)} gap(s) affecting net worth: "
                           + "; ".join(g["what"] for g in bad))
        except Exception:
            pass
        if say:
            print("LY Finance workspace:")
            for x in say:
                print("  · " + x)
        return 0

    if reseed:
        json.dump(fp, open(sp, "w", encoding="utf-8"))
        print(f"  ✓ fingerprint re-pointed at the current inbox/ and findata/ "
              f"({len(fp)} files). Your own writes are now the baseline.")
        return 0

    if verify:
        try:
            before = json.load(open(sp, encoding="utf-8"))
        except Exception:
            print("=== preflight --verify ===")
            print("  ✗ no earlier fingerprint. Run preflight without --verify first.")
            return 2
        added   = sorted(set(fp) - set(before))
        removed = sorted(set(before) - set(fp))
        changed = sorted(k for k in set(fp) & set(before) if fp[k] != before[k])
        if not (added or removed or changed):
            print(f"  ✓ inbox/ and findata/ unchanged since the fingerprint ({len(fp)} files). "
                  f"Safe to write.")
            return 0

        print("=== preflight --verify ===")
        IN, FD = "inbox/", "findata/"
        inb = lambda ks: [k for k in ks if k.startswith(IN)]
        fnd = lambda ks: [k for k in ks if k.startswith(FD)]
        cut = lambda k, pre: k[len(pre):]

        if inb(added) or inb(removed) or inb(changed):
            print("\n  inbox/ moved:")
            for k in inb(added):   print(f"    ✗ arrived: {cut(k, IN)}")
            for k in inb(changed): print(f"    ✗ changed: {cut(k, IN)}")
            for k in inb(removed): print(f"    · gone:    {cut(k, IN)}")
            print("    → iCloud is still syncing. Fold the new files in before writing anything.")

        if fnd(added) or fnd(removed) or fnd(changed):
            print("\n  findata/ moved — SOMETHING YOU ALREADY READ IS NOW DIFFERENT:")
            for k in fnd(changed): print(f"    ✗ changed: {cut(k, FD)}")
            for k in fnd(added):   print(f"    ✗ new:     {cut(k, FD)}")
            for k in fnd(removed): print(f"    · gone:    {cut(k, FD)}")
            print("    → Nothing is lost and no write has failed. The risk is that conclusions")
            print("      already drawn from these files are stale. Re-read them before writing,")
            print("      and re-check any number you have quoted from them.")
            print("    → If YOU made these changes on purpose, run --reseed and carry on.")
        return 1

    print(f"=== preflight — {len(files)} file(s) in inbox/ ===\n")
    unknown, plan = [], []
    for f in files:
        label, acct, feeds, note = classify(os.path.basename(f["name"]))
        (plan if label else unknown).append((f, label, acct, feeds, note))

    if plan:
        w = max(len(os.path.basename(f["name"])) for f, *_ in plan)
        for f, label, acct, feeds, note in plan:
            print(f"  {os.path.basename(f['name']):<{w}}  →  {label}")
            print(f"  {'':<{w}}     feeds {feeds}")
            print(f"  {'':<{w}}     {note}\n")

    # Byte-identical pairs. This is how a bank's "-2" duplicates are confirmed rather than assumed.
    by_size = {}
    for f in files:
        by_size.setdefault(f["size"], []).append(f)
    dups = []
    for group in by_size.values():
        if len(group) < 2:
            continue
        seen = {}
        for f in group:
            seen.setdefault(sha(f["path"]), []).append(f["name"])
        dups += [v for v in seen.values() if len(v) > 1]
    bmo_clash = []
    if dups:
        print("  --- byte-identical files ---")
        for v in dups:
            labels = {classify(os.path.basename(x))[0] for x in v}
            # One bank ships true duplicates; another ships two different accounts under
            # near-identical names. The general rule: an identical pair that classifies as TWO
            # documents means one of them never arrived -- a pair that classifies as one is a copy.
            if len(labels) > 1:
                bmo_clash.append(v)
                print(f"  ✗ {' == '.join(v)}")
                print(f"      These classify as DIFFERENT documents ({' / '.join(sorted(labels))}) "
                      f"but the files are identical.")
                print(f"      One of them did not come through. Ask for it again "
                      f"rather than filing the same PDF twice.")
            else:
                print(f"  · {' == '.join(v)}   → true duplicate, keep one and delete the rest")
        print()

    if unknown:
        print("  --- STOP ---")
        for f, _, _, _, note in unknown:
            print(f"  ✗ {os.path.basename(f['name'])}\n      {note}")
        print("\n  Ask the owner what these are. Do not guess: a guessed merchant became a "
              "subscription on 2026-09-06 and had to be walked back.\n")

    rows = freshness(root)
    if rows:
        print("  --- what findata/ already has ---")
        w = max(len(r[0]) for r in rows)
        for label, d, age in rows:
            flag = " ⚠ over 30 days" if age is not None and age > 30 else ""
            print(f"  {label:<{w}}  {d}  {'' if age is None else str(age) + 'd'}{flag}")
        print()

    json.dump(fp, open(sp, "w", encoding="utf-8"))
    here = os.path.join(*os.path.abspath(__file__).split(os.sep)[-5:])
    n_in = sum(1 for k in fp if k.startswith("inbox/"))
    print(f"  fingerprint saved over {len(fp)} files ({n_in} in inbox/, {len(fp)-n_in} in findata/).")
    print(f"  Before each write:   python3 {here} . --verify")
    print(f"  After a write of your own:  python3 {here} . --reseed")
    return 1 if (unknown or bmo_clash) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
