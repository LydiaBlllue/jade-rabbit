---
name: update-dashboard
description: Run the monthly data import for this workspace — one local command (update.py) reads inbox/, parses the bank and broker statements, updates findata/, rebuilds the dashboard, archives the originals and appends the update record; you read its summary and settle only what a program cannot. Use whenever the owner says "update dashboards" (or 更新仪表盘), drops new statements in inbox/, or asks what changed this month; also on their import day (profile.json `importDay`). Carries the order the steps have to happen in and the mistakes each one has already caused — a "-2" suffix that is a second account at one bank and a duplicate at another, a merchant guessed into the wrong category, a half-covered month dragging the baseline down, and nine statements that finished syncing after the inbox had already been read.
---

# Update the dashboard

This skill is the ORDER. `CLAUDE.md` holds the definitions — what counts as income, what is in
the Portfolio, which months are comparable — and it stays there because those are needed whenever
the dashboard is touched, not only at import time. Read both.

Every warning below is here because it already went wrong once. None of them are hypothetical.

---

## The run: one command, then the leftovers

```bash
python3 .claude/skills/update-dashboard/scripts/update.py .            # what would happen
python3 .claude/skills/update-dashboard/scripts/update.py . --write    # do it
```

Since 2026-09-14 the steps below are what `update.py` does, in that order, for every file a
parser can read: it names the files (Step 0), parses and reconciles each statement (1), files the
purchases by merchant (2), writes the ledgers, `spending.csv`, `banks.json` and the register's
copies (3), rebuilds the page (4), runs the checkers (5), archives the originals (6) and appends
the update record and the queue of decisions (7). It prints a summary and nothing else — not the
rows. **Read the summary, not the statements.** What it hands back is the whole of your job:

- **A file it stopped on.** A name it could not match to the register, or an identical pair that
  classifies as two documents: ask the owner, never guess. (A PDF whose name says nothing — an
  RBC download arrives as `20260819.pdf` — is first offered to every parser, and the one that
  reads it and reconciles names it by the account the statement itself prints; only a file no
  parser can place stops the run.) A statement that does not follow its
  ledger (the opening balance is not the ledger's closing): a statement in between is missing —
  ask for it, do not bridge the gap by hand.
- **A file to read by hand** (`by hand:` lines): a statement that does not reconcile, a layout no
  parser knows (2026-09-15: no new parsers for now — a bank without one is read this way), a
  screenshot of an account held abroad. A statement you read is only **transcribed**, never
  written by you: put its rows and the totals it prints into a JSON list and run the command
  again with `--hand rows.json`. One entry per file —
  `{"file": "<inbox name>", "doc": "<documents[].key>", "account": "<digits the statement
  prints>", "period": {"from", "to"}, "opening", "closing", "rows": [{"date", "description",
  "amount", "balance"}], "totals": {"deducted"/"added" or "purchases"/"credits"}}` — amounts
  signed the ledger's way (money out negative), balances as printed. The script holds the
  transcription to the same reconciliation as a parser: the chain from opening to closing, the
  debits and credits against the printed totals; what does not add up is refused and named,
  and nothing is written. Then it files the rows the way it files everything else. A
  screenshot has no rows: read the balances into `foreign.json` yourself, as before.
- **A row it could not type** (`untyped:` lines): fill the ledger's `type` and `label` for that
  row; D22 points at it until you do.
- **What it asked** (`?` lines): a merchant seen for the first time, filed as Other meanwhile; an
  e-Transfer with no name on the other side. Each is already a row in `decisions.json`. Put them
  to the owner; when they answer, write `answer` and `resolved` on the row and apply it where it
  belongs (`merchants.json`, the ledger's `type` column).
- **The record.** It has appended one to `imports.json` — `files`, `changed`, `noticed`,
  `judged`, `asked` — and the report to the owner is that record read out. Add to it what you
  decided by hand; never write the report in the chat first.

A `--write` run ends with the checkers and reseeds the preflight fingerprint. Exit 1 means it
stopped before writing; 2 means it wrote and a checker found something — fix that before saying
the update is done; 3 means pypdf is missing and every file is read by hand this month.

---

## What the run does, step by step — and what to do when it hands a file back

## Step 0 — Preflight, and do not skip it

```bash
python3 .claude/skills/update-dashboard/scripts/preflight.py .
```

It names every file in `inbox/`, says which `findata/` file each one feeds, finds byte-identical
pairs, and prints how old everything already on hand is.

**Anything it cannot name stops the run.** Ask the owner. Do not infer an account from a filename
that does not match a known pattern — `LIGHTHOUSE PUBLICATION` was read as a subscription because
the name looked like one, and it was a shop selling notebooks.

It fingerprints **both `inbox/` and `findata/`** by content hash. Two different things move
under a long run, and they fail differently:

- **`inbox/`** — a file *arrives*. On 2026-09-06 nine statements finished syncing from iCloud
  after the inbox had been read, and were noticed only once the holdings work was done.
- **`findata/`** — a file you already *read* changes while you are still reasoning about it. On
  2026-09-08 `foreign.json` changed its total and named a bank that had been "unconfirmed",
  in the middle of two hours of work built on the old numbers. Nothing was
  overwritten and no write failed. What expired was the picture the conclusions came from — and
  that cannot be grepped for, because the file is right, the write is right, and only the copy
  in your head is out of date.

**So verify before every write, and reseed after every write of your own:**

```bash
python3 .claude/skills/update-dashboard/scripts/preflight.py . --verify   # before writing
python3 .claude/skills/update-dashboard/scripts/preflight.py . --reseed   # after you write
```

`--verify` costs one line (~30 tokens) when nothing moved. When `findata/` has moved it says so
and stops: re-read those files, and re-check any number already quoted from them. When the change
was yours, `--reseed` makes your own writes the new baseline.

---

## Step 1 — Parse, one source at a time

**Run the parser first; read by hand only what it refuses.** Every bank document in
`accounts.json` names its parser (`documents[].parser`: `rbc_banking`, `rbc_visa`,
`bmo_banking`, `bmo_mastercard` — the modules in this skill's `parsers/`). For each file
preflight named:

```bash
python3 .claude/skills/update-dashboard/scripts/parse.py "<file>" --doc "<documents[].key>" --json
```

Exit 0: the rows are in the JSON, already signed the ledger's way, dated with the right year,
with a running balance, **and they reconcile** the way the document's `reconcile` says — use
them as they are, and go on to Step 2. Exit 1: the file was read but does not reconcile, or is
a layout the parser does not know — the message says which; read that one file by hand, and
say so in the report (`judged`). Exit 3: pypdf is not installed; everything is read by hand
this month, and the report says so. **A parser that reconciles is trusted over a reading by
eye; a reading by eye is never written over a parser that reconciled.** The parser reads the
account from the statement's own text, not from the filename — which is how a `-2` file that
was really the other account gets caught.

Each source has a reconciliation that must pass before its data is allowed into `findata/`.
Which file it lands in and what has to balance are on its entry in `findata/register/accounts.json`
(`documents[].into` and `documents[].reconcile`) — read them there, per document, rather
than from a table here. The table that used to sit in this spot is why: it was written out
by hand, so it never grew a row for one USD savings account and would not have grown one for
the next card either. Lint **D14** fails when a document declares no `into`/`reconcile`, and
when an account nothing delivers is left unexplained.

**The two suffix rules point opposite ways, and getting them backwards is destructive:**

- **At one bank a `-2` is a different ACCOUNT**: its chequing and savings statements arrive as
  `<Month D, YYYY>.pdf` and `<Month D, YYYY>-2.pdf` in the same batch, and deleting the `-2`
  file deletes a ledger. `accounts.json` says which documents share a filename pattern.
- **At another bank a `-2` is a byte-identical DUPLICATE.** Delete it. Preflight decides by
  hashing, never by trusting the name: an identical pair that classifies as two documents means
  one of them never arrived; a pair that classifies as one is a copy.

The owner's own banks, and what each one does, are in `OWNER.md`.

**Two more that have already caused a wrong number:**

- Debit-card purchases on a chequing statement are spending. They stay in that account's ledger
  for the balance chain **and** get a second row in `spending.csv` carrying that account's
  `spendTag`. Writing only one of the two either breaks the chain or loses the expense.
- Before typing any e-Transfer credit as income, check the sender against the counterparty
  ledger (the register document that carries `counterparty` — someone repaying a loan). A repayment counted as income once
  inflated both income and the savings rate by thousands; lint **D10** now checks every match.

---

## Step 2 — Categorise

1. **Look up `merchants.json` first.** A hit is reused, not re-judged.
2. A miss is a **new merchant** — it must appear in the report for the owner to confirm.
3. **Subscription means the charge repeats.** A brand seen once is not a subscription, whatever
   the name suggests and whatever it cost. Note that a large recurring charge is still not a
   "big buy": subscriptions are excluded from the big-buy threshold by design.
4. Merchant strings are truncated and abbreviated. They are not sentences and cannot be read as
   ones.

---

## Step 3 — Write `findata/`, including the copies

`--verify` first. Then ledgers and JSON, then the two files that hold **copies** of numbers
owned elsewhere:

- `accounts.json` — every `balance` / `asof`. Lint **D14** re-derives all of them from
  `banks.json`, `holdings_latest.csv` and `foreign.json` and fails on drift.
- `funds.json` — `backing.balance` for the fund accounts. Lint **D13** does the same.

A new account or a new statement means **one** edit now, not three: add a row to `accounts`, and
a row to `documents` if it produces a file. `SOURCES` is derived from it, and `SUBMITTED` has to
gain the same key.

Then `--reseed`, so the dashboard rebuild in Step 4 is checked against what you just wrote rather
than against what was there this morning.

---

## Step 4 — Rebuild the dashboard

`--verify` again first, then:

```bash
python3 .claude/skills/update-dashboard/scripts/rebuild.py .          # what would change
python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write  # apply
```

It builds **the dashboard from `templates/dashboards/` + `findata/`**, every constant
included — there is nothing in a dashboard that is typed by hand any more, and lint **T1** fails
if a page is edited in place instead of rebuilt. Which constants it owns lives in the script, not
here, so it cannot go stale the way a written checklist does.

One thing about how it works, because it matters when reading its output: it rounds the
**components** once and builds every total from those, because rounding each part and rounding
the sum are not the same thing — the first version put the two net-worth cuts $1 apart, which
DESIGN.md §4 forbids. That invariant is asserted inside the script.

**What the import step therefore has to WRITE into `findata/`, because a program cannot see it:**

| file | what the import writes |
|---|---|
| each ledger's `type` / `label` columns | the classification of every row (Payroll / Transfer / Repayment / Fee …) and a readable label when the bank's description is not one |
| `filings.json` | the month each archived document covers, keyed by `documents[].key` — written in Step 6, checked against `archive/` by lint **T2** |
| `networth_history.json` | one point when the holdings export reaches a new month |
| `investment_history.json` | one snapshot per import |
| `imports.json` | this update's record: the files, what changed, what was noticed, what was decided without asking, what the owner was asked — the report in Step 7 is this record |
| `decisions.json` | every item the owner still has to confirm (a new merchant, a defaulted e-Transfer, an unnamed file) with the default applied meanwhile, and the answers to earlier ones |
| `plan.json` `skipMonths` · `tasks.json` · `accounts.json` `gaps` / `missing` | reasons and decisions the owner gives out loud |

Then `--reseed`.

## Step 5 — Check

```bash
python3 .claude/skills/workspace-checks/scripts/check_design.py \
  dashboards/finance_dashboard.html
python3 .claude/skills/workspace-checks/scripts/check_data.py .
```

The PostToolUse hook runs these after individual edits; run them once over everything at the end
anyway. Pass the page by name rather than globbing `dashboards/*.html`: an owner's workspace may
keep other HTML files there (mock-ups, decision records) that were never meant to follow the spec.

Those two read the files as text. The four things they cannot see — whether a page throws
instead of drawing, sideways scrolling, how wide a chart is really painted, whether a page fills
a screen — are now a third command rather than a manual pass in a browser:

```bash
python3 .claude/skills/workspace-checks/scripts/check_render.py \
  dashboards/finance_dashboard.html
```

It drives headless Chromium (Playwright, installed 2026-09-08), loads each page at 1120 / 1440 /
1760 px, clicks every sidebar entry and measures what was drawn. About 11 seconds, and it replaces
roughly 28 hand-driven browser calls a run.

One thing worth knowing before trusting it: **it measures the chart's painted width, not its
element box.** With a fixed height and `preserveAspectRatio`, the `<svg>` still stretches to full
width while the drawing inside is scaled to the height and centred — the box grows from 794px to
1434px and the picture stays at 638px. The first version of this check compared bounding rects and
called that healthy. It now compares `viewBox width x getScreenCTM().a`.

Open a browser yourself only when you changed how something *looks* and want to see it.

---

## Step 6 — Archive

`archive/YYYYMMDD_<source tag>_<original filename>`, and add ` (redrop)` when the same statement
is dropped again.

The tag for each document is in `findata/register/accounts.json` (`documents[].tags`) — not written out
here, because the copy that used to live in this file lost three foreign-account tags within a day of being
written. Lint **D14** checks the declared tags against what `archive/` actually contains.

Keep the original filename after the tag — it carries the statement date.

---

## Step 7 — Record, then report

The report is not written in the chat first. It is **one record appended to
`findata/history/imports.json`** — `update.py` appends it, with what it filed, changed, noticed, judged
and asked; you add what you settled by hand — and the message to the owner is that record read
out. Five parts, in this order — the same five keys of the record:

1. **`changed`** — net worth, FIRE progress, spending, dry powder: label, from, to.
2. **`asked`** — new merchants and anything else that needs the owner's word. Each one is ALSO a
   row in `findata/history/decisions.json` (`status: open`, the `default` applied meanwhile, the `source`
   statement and line it came from); the page header counts them until the owner answers.
3. **`noticed`** — rules kept or broken (pay-yourself-first, the band, the holding count, the
   allowance, fund claims) and what is still missing (from `GAPS` and the tracker grid), each
   with `sev` ok / warn / bad. This is the story of the update; the Investing page computes
   today's status itself and never shows these sentences.
4. **`judged`** — every default applied and every ambiguity resolved without asking.
5. **`files`** — what came in, named the way the owner knows them ("MasterCard statement to
   Aug 20"), not by filename.

**Every sentence in the record reaches the page.** Write it the way DESIGN.md §5b says: about the
owner's money, never about the tool — no "I", no rule numbers, no file names, no checker names;
a warning ends with what the owner can do. When the owner answers an item, write `answer` and
`resolved` on its row in `decisions.json` and apply the answer where it belongs
(`merchants.json`, the ledger's `type` column).

Then update the register's `documents[]` if what the owner is expected to drop has changed;
the Statements page reads what arrives each month from there.

---

## Where things live

`FINANCE.md` the money logic · `DESIGN.md` how it looks · `CLAUDE.md` definitions, sources,
investment rules · `findata/` the only source of truth · `.claude/skills/workspace-checks/` the
checkers.
