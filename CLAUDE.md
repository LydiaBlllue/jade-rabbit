# Jade Toad — how this workspace works

A personal-finance workspace run by Claude Code. You maintain one thing here: the **dashboard**
(`dashboards/finance_dashboard.html` — an older workspace may still call it
`ly_finance_dashboard.html`). It is **built**, never edited: the page code lives in
`templates/dashboards/`, every number in it comes from `findata/`, and `rebuild.py` is the only
thing that writes to `dashboards/`. (Until 2026-09-10 the investing pages were a second file,
`investment_dashboard.html`; they are the Investing group of the one page now.)

**Read `FINANCE.md` before touching a number, `DESIGN.md` before touching the page, and
`OWNER.md` before assuming anything about whose workspace this is.** The first two are the
specification; the third is the owner's — their accounts, their banks, their decisions and the
mistakes that taught them. Anything agreed out loud has to land in one of the three or it does not
survive the next session.

Three kinds of writing, three lifetimes: **the spec** (these documents — what is true today, no
history), **dated records** (the tool's are `CHANGELOG.md`; an owner's are the files in their
`decisions/` folder, which the sync never touches — read when the question is *why*), and
**data** (`findata/`). `OWNER.md` stays short by keeping only the first kind: a replaced decision
moves, dated, into `decisions/` with a one-line pointer left behind.

⚠ **This file states no current figures.** Every live number is in the `LINT:FIGURES` table in
`FINANCE.md`, and check_data's D15 verifies that table against the dashboard. Writing a figure in
a second place is how one of them goes stale.

## The data

`inbox/` is where statements are dropped. `findata/` is the only source of truth, and it is
three folders, one per layer of the information model below, split by **who writes the file**:
`register/` (the owner's declarations), `ledgers/` (the facts the import writes) and
`history/` (what each update leaves behind). Every script resolves a bare filename through
`layout.py` in the update-dashboard scripts, so the register names files without folders.
Every place money sits and every file that arrives is registered in
**`findata/register/accounts.json`**, which everything else is derived from:

- `accounts[]` — one row per place money sits. **`key` is the primary key**, not the account
  number, because some accounts have no number to join on. **Five axes place it** — `side`,
  `role`, `reach`, `value` and, on a liability, `against` — and every total the page shows reads
  exactly one of them (below, and FINANCE.md §8a). `feeds` says only what a ledger is used for
  on the page ("Income" for the ledger payroll lands in, "Spending", "Cash flow", "Repayments"
  for a counterparty's ledger); `ledger` names its CSV; `label` is what the Investing pages call
  it.
- `documents[]` — one row per file dropped each month, with the filename pattern, the closing
  day, `into` (which findata file it lands in), `reconcile` (what has to balance before it is
  allowed in), `covers` (which accounts) and `tags` (how it is named in `archive/`). A
  counterparty's ledger (someone repaying a loan) is a document like any other, with
  `counterparty` naming the person; D10 reads it there.
- **A file is not an account**: one holdings export covers several accounts, and an investment
  account has no monthly statement at all.
- ⚠ It is **a register, not a second set of books**. Its `balance` and `asof` are copies of
  `banks.json` / `holdings_latest.csv` / `foreign.json`, and **D14 re-derives every one from its
  source**. To change a balance, change the source file.

The rest of `findata/`, and what each carries:

| file | what it is |
|---|---|
| `spending.csv` | every purchase, tagged with the statement it came from |
| each account's ledger CSV | date, description, amount, balance, statement, **`type`**, `label` — the balance chain must close (D1), and `type` is the classification the page shows |
| `holdings_latest.csv`, `ws_activities.csv` | the broker's exports |
| `banks.json` | one balance and one as-of date per bank account |
| `profile.json` | the owner (shown under the Jade Toad wordmark and in the tab), the year of birth, the import day |
| `funds.json` | the monthly plan as **flows** — `income`, `committed` (rent, a mortgage, a loan), `saving` (to the broker, or to a fund by `to`), `allowance`, each with an amount and, where it applies, `until`, `afterFire`, `pays`, `starts` — and the named funds (`role: topup` / `big`), which carry no number of their own |
| `plan.json` | planning spend, months excluded from comparisons, the retirement assumptions, the owner's one-line descriptions of the net-worth parts |
| `rules.json` | the investing buckets and their target bands, the owner's theses (`notes`) and `checkpoints` |
| `merchants.json` | merchant → category |
| `fx.json` | a dated exchange rate — absent means "no foreign-currency holdings" |
| `foreign.json` | foreign-currency accounts; an empty list is the supported way to say there are none |
| `imports.json`, `decisions.json` | one record per update — the files, what changed, what was noticed, what was decided without asking, what the owner was asked; and the queue of items still waiting for the owner to confirm, each with the default applied meanwhile |
| `investment_history.json`, `networth_history.json` | one snapshot per import / one net-worth point per month |
| `tasks.json`, `filings.json` | open tasks; which month each document was filed (checked against `archive/` by T2) |

⚠ `findata/` must not be renamed `data`: iCloud for Windows excludes any folder called `data`
from syncing.

## How information is stored and reached

Everything in this folder sits in one of five layers. The layer decides who may write it, which
checker guards it, and whether the page may read it:

| layer | answers | only writer | how it changes |
|---|---|---|---|
| **evidence** — `inbox/` → `archive/` | where is the original | the import (rename and move) | append only |
| **facts** — `findata/ledgers/`: the ledgers, `spending.csv`, the broker exports, `banks.json`, `fx.json`, `foreign.json` | what actually happened to the money | the import's parse step | a ledger is append only and every row carries its statement tag; a snapshot (`holdings_latest.csv`, `banks.json`, `fx.json`, `foreign.json`) is replaced whole and dated by `asof`, its previous state living in `archive/` and in `history/` |
| **history** — `findata/history/`: `imports.json`, `decisions.json`, `filings.json`, the two `*_history.json` | what the world looked like at each update | the import's last step | one record per update, never rewritten — except a `decisions.json` item, which is closed in place (`answer`, `resolved`) when the owner answers |
| **declarations** — `findata/register/`: `accounts.json`, `funds.json`, `plan.json`, `rules.json`, `merchants.json`, `profile.json`, `tasks.json` | how the owner chooses to see the money | the owner, through `setup` or out loud | edited, with a dated reason beside the value |
| **derived** — `dashboards/`, the figures table in `FINANCE.md` | what the page shows | `rebuild.py` | overwritten whole, idempotent |

The rules that follow, each with the checker that holds it:

- **One fact lives in one layer.** A copy is allowed only if a checker re-derives it from its
  source every time: the balances in `accounts.json` (D14), a fund's `backing` (D13), the
  figures table (D15), the built page (T1).
- **No back-edges.** Derived output is never an input. What the page lets you change — planning
  spend, the toggles — lives in the browser's localStorage and never flows back into `findata/`.
- **Access is by key, never by position.** `accounts.json` `key` is the join; the statement tag
  at the end of a ledger row points at the archive file; `filings.json` and `archive/` name each
  other (T2). Files may move, keys may not.
- **The page reads nothing at runtime.** Constants are baked in at build time. That is why the
  file is self-contained, and why every change to the data needs a rebuild.
- **Time is handled per layer**: facts by statement tag, history by update date, declarations by
  `asof` and the reason next to the value; derived has no time but "now".

When something new has to be stored, first ask which layer it belongs to. The answer settles who
writes it, which check guards it and whether the page may read it. Something that fits no single
layer is usually two things stuck together — `feeds` was: a net-worth part, a location, a
strategy word and a fund label in one tag.

### The register's axes

**Both halves are live: balance items since findata schema 4, flows since schema 5 (both
2026-09-10; `tools/migrate_3to4.py` and `tools/migrate_4to5.py` move a workspace).**

Net worth used to be five words in `feeds` added up in `rebuild.py`, so every new kind of thing
— a home, a mortgage, a pension — needed a new word and a new line of code, and an owner with a
mortgage got a net worth with the loan in it and the house nowhere. Each account row is now a
**balance item with five orthogonal axes**, and each derived total reads exactly one of them:

- `side` — asset / liability → net worth = Σ assets − Σ liabilities
- `role` — grow / set-aside / buffer / none → Portfolio is `grow`; net worth by purpose is one
  slice per role
- `reach` — today / costs / spoken / locked / abroad → the reach table
- `value` — export / statement / stated (with `asof`) → what D14 can re-derive, and what it can
  only date
- `against` — a liability names the asset it sits on → the reach table shows equity, not gross

The defaults come from the kind (`scaffold.py` `default_axes`, which the migration and the demo
share), so a fresh row and a migrated one agree; the owner overrides any axis in the register.
D19 rejects an illegal pair (a liability with a role, an asset with an `against`, a `value` that
contradicts the source file) and fails a `rules.json` that still carries the old `exclude`
list — the Investing pages read the set-aside role from the register (schema 7). D20
insists a `stated` balance carries an `asof` and warns past a year. Selftest plants both.

Each line of the monthly plan is a **flow** with `kind` (income / committed / saving /
allowance), `amount` and, where it applies, `until`, `afterFire` (keep / drop), `pays` (the
liability it repays) and `starts: "fire"` (rent an owner will pay but does not yet) — FINANCE.md
§8b. The sums every consumer reads come from one module, `flows.py` in the update-dashboard
scripts: the page derives take-home, invest and the allowance from `FUNDS.plan.flows` at load,
`rebuild.py` reads the pay-yourself-first amount and `COMMITTED_KEEP` (the fixed part of the
planning figure) from it, and D13 / D15 read the same sums. D21 matches every committed flow
paid today against the ledgers, the way `WSDEP` matches the investing transfers, and warns when
no payment of that size moved in the two whole months before the newest ledger date. Selftest
plants a committed flow the ledger never shows.

## The monthly import

**Saying "update dashboards" means invoking the `update-dashboard` skill**
(`.claude/skills/update-dashboard/SKILL.md`). The order, the parsing trap in each source and the
report template are all in that file. **Do not work from memory.**

- **The import is one local run: `scripts/update.py . --write`** (2026-09-14). It does every step
  below for every file a parser can read, and prints a summary — never the rows. What reaches you
  is what a program cannot decide: a file it could not name or could not read, a row it could not
  type, a merchant seen for the first time, an e-Transfer with no name on the other side. Those
  are your job; the statements themselves are not, and you do not open one a parser has read.
  The selftest strips the newest statement of every document out of a copy of the demo, runs
  the script on the synthetic statement, and expects the demo's own rows back.
- **Step 0 is always `preflight.py`** (the run does it first). It names every file in `inbox/` from `accounts.json`,
  finds byte-identical duplicates, and says how old everything already on hand is. It also
  fingerprints `inbox/` **and** `findata/` by content hash, because two different things move
  under a long run: a file *arrives* in inbox, or a file you already *read* changes behind you.
  The second cannot be grepped for — the file is right, the write is right, and the only thing
  out of date is the copy in your head. So: **`--verify` before every write, `--reseed` after
  every write of your own.**
- **Anything preflight cannot name stops the run.** Ask; never infer an account from a filename.
- **Parsers read the statements; a person reads only what a parser refuses.** Every bank
  document in the register names one (`documents[].parser`), the modules live in
  `.claude/skills/update-dashboard/parsers/`, and `scripts/parse.py <file> --doc <key>` runs it:
  rows signed the ledger's way, dated with the right year, with a running balance, reconciled
  the way the document's `reconcile` says. The parser takes the account from the statement's
  own text, never from the filename. They need `pypdf` (`pip3 install --user pypdf`); without it
  the import reads by hand, as it always could. A parser that reconciles is trusted over a
  reading by eye. The proof: `tools/fixtures.py` renders the demo owner's ledgers back into
  statements in the exact text shape the real ones have, and the selftest holds every parser to
  them (plus one tampered total that has to be refused); in an owner's workspace the selftest
  also runs the parsers over every real statement in `archive/`. The setup reads the same way:
  `setup/scripts/propose.py` drafts the register from the first files dropped, and asks only
  what they cannot say.
- The import day is `profile.json` `importDay`; it appears once per dashboard as `IMPORT_DAY`,
  and every label derives from it.

## Nothing in a dashboard is typed by hand

<!-- LINT:CONSTS n=44 -->
`rebuild.py` builds the dashboard from `templates/dashboards/` and `findata/`, deriving
**44 constants**: ACCT, ANCHOR_Y, BOOKV, BORN, BROKER, CHEQUING, COAST_R, COMMITTED_KEEP, DATA, DEBT_NOTE, DECISIONS, DOC_LATEST, FGN, FOREIGN, FUNDS, FX, GAPS, HIST, HOME_CARE, HORIZON, IMPORTS, IMPORT_DAY, INVEST, LEDGER_THRU, LIFE_TO, LTC_TIERS, MONTH_SKIP, NWPARTS, NW_DEBT, NW_HISTORY, PLAN_BASE_DEFAULT, PORT_HISTORY, PROFILE, REACH, RULES, SCENARIOS, SPENDING, STMT_END, SUBMITTED, SUB_KEYS, TASKS, TODAY, WSDEP, WSINC. It compares without writing by default; `--write`
applies, and it is idempotent. `--template DIR` writes the page with every constant emptied,
which is what the template *is*: page code and nobody's numbers.

Two checkers hold that line. **T1**: every one of those constants is empty in the template, and
`dashboards/` is exactly what the template and `findata/` build — a page edited in place fails.
**T2**: `filings.json` and `archive/` agree about what has ever been filed. So the things an
import has to *write* are all in `findata/`: the `type` column of each ledger, `filings.json`,
the two history files, `imports.json` and `decisions.json`, and the owner's reasons in `plan.json`,
`tasks.json` and `accounts.json`.

**No account number, institution name or person's name appears in the page code.** The broker
is `BROKER` (the institution of the accounts that feed Portfolio), the counterparty is the
register's (the document that carries `counterparty`), the band and the cap are `rules.json`'s, the descriptions under the net-worth
parts are `plan.json`'s. Adding an account is one edit to the register.

## Numbers in documents go in markers

Contracts that let the prose be reworded or translated without silencing a checker:

- `DESIGN.md`: `<!-- LINT:PAGES pages=N sections=M -->`
- `README.md` and `README.zh.md` (each checked): `<!-- LINT:NAV main=P/S minwidth=W -->`, the sidebar list read from the `·`
  lines that follow it; `<!-- LINT:FAULTS n=N -->` for the selftest (S6 reads the real number
  out of `selftest.py`)
- this file: `<!-- LINT:CONSTS n=N -->` (S7 reads the real number and the names out of
  `rebuild.py`)
- `FINANCE.md`: the figures table is keyed — column 1 is a stable id, column 2 the label in
  whatever language the file is written in, and `<!-- LINT:FIGURES:END -->` ends it. D15 looks
  values up by key and takes the words for its restatement scan from the label column.

## The checkers

A `PostToolUse` hook runs the matching checker after any edit to `dashboards/` or `findata/`.
**Silent when clean.**

```bash
python3 .claude/skills/workspace-checks/scripts/check_data.py .
python3 .claude/skills/workspace-checks/scripts/check_design.py dashboards/finance_dashboard.html
python3 .claude/skills/workspace-checks/scripts/check_render.py dashboards/finance_dashboard.html
python3 .claude/skills/workspace-checks/scripts/selftest.py .
```

- `check_data.py` — whether the numbers are real. Its output is grouped by what actually failed:
  `reconcile` (balance chains, cross-file totals), `rules` (a repayment is never income, a
  subscription is a repeat charge, a fund claim never exceeds its account), `build` (is the page
  current with the data, and is it what the template builds), `hygiene` (missing tags, duplicate
  rows, a stale rate, filings without a file). **The category is attached to each finding, not to
  the rule** — "the register contradicts itself" and "the page is stale" are not the same
  severity. `-v` shows what passed.
- `check_design.py` — DESIGN.md's mechanical rules, including S4, which checks that the page
  counts, lists, paths and images DESIGN.md and README.md state about themselves are still true.
- `check_render.py` — headless Chromium at 1120 / 1440 / 1760px: every page draws, nothing scrolls
  sideways, a chart's **painted** width really grows with the window, and no `undefined` reaches
  the screen. Needs
  `pip3 install --user playwright && python3 -m playwright install chromium`. Not on the hook;
  run it after changing a template.
- `selftest.py` — the checker of the checkers. It plants specific faults in a copy of the
  workspace and asserts the matching rule fires for each; the count is in README's `LINT:FAULTS`.

**Pass the dashboard by name, never `dashboards/*.html`** — an owner's workspace may keep other
HTML files there (mock-ups, decision records) that were never meant to follow the spec.

## Two things that have already gone wrong

**A merchant name is not a sentence.** A charge from `LIGHTHOUSE PUBLICATION` was filed as a
Subscription because of the word "PUBLICATION" in it. It was a shop, and the charge was a
notebook. Merchant strings are abbreviated and truncated; they cannot be read for meaning. So:
look the merchant up in `merchants.json` first and reuse a hit — only a miss is a judgement, and
every miss goes in the report for the owner to confirm. And **Subscription means the charge
repeats**: a brand seen once is never a subscription, whatever the name suggests and whatever it
cost.

**A checker that has stopped checking is worse than no checker.** One of these linters once
located the workspace by counting `..` from its own path. When the scripts moved one level
deeper, it linted a directory with no data in it, reported three ledgers "missing", **exited 0,
and went on saying it had passed.** That is why `selftest.py` exists, why it plants faults instead
of asserting a clean run, and why finding the workspace is done by looking for `findata/` and
`dashboards/` rather than by counting parents. When you change a checker, run the selftest.

## Style

- Structured output, specific numbers, and say plainly when a rule is broken. No vague
  encouragement.
- Explain a technical term in one plain sentence the first time it appears.
- One disclaimer per reply, never repeated.
- Do not read anything outside this folder unprompted.
- The owner's language, banks and decisions are in `OWNER.md`, loaded below.

@OWNER.md
