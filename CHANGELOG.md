# Changelog

## 1.0 — unreleased

The tool is the repository; every workspace, the author's included, is an instance of it.

- **The product is 玉蟾 · Jade Toad** (2026-09-14). It was Jade Rabbit. The owner wanted a name from
  Chinese myth that is a woman's, an animal's and a goal's at once, and the toad is all three: in the
  earliest telling (《淮南子》) Heng'e reaches the moon and becomes its toad, and 蟾宫折桂 — plucking
  the cassia in the toad palace — is the idiom for reaching a hard goal, which is what a FIRE number
  is. The mark is the Majiayao frog motif (c. 2500 BCE: round head, one spine, four bent limbs,
  three toes) inside a full moon; `docs/logo.svg` is the source, the sidebar coin and `docs/hero.png`
  are drawn from it, and the wordmark is still the one `PRODUCT` constant the page reads, never typed.
  The repository is named `jade-toad` and public since 2026-09-15; the old address redirects.
- `templates/dashboards/` holds the page code with every constant empty. `rebuild.py` builds
  `dashboards/` from the template and `findata/`, and lint **T1** fails if a page is edited in
  place or a template carries data. About twenty constants that used to live only in the HTML —
  the classified chequing rows, the net-worth history, the tasks, the filing grid, the planning
  assumptions, the investment theses and checkpoints — are findata files now.
- `tools/sync.py` pushes the tool into a workspace and touches nothing that is the owner's;
  `tools/demo.py` generates the demo owner's whole `findata/`. The scrub-and-scan release line is
  gone: there is nothing to scrub.
- `OWNER.md`, loaded by `CLAUDE.md`, is where one person's banks, traps and decisions live. The
  three governing documents say nothing about anyone.
- The `setup` skill writes a whole workspace from an interview; the investment page checks one
  thing (`rules.json` buckets against their target bands) and shows the rest as the owner's notes.
- **The page talks about your money, never about itself** (2026-09-10). The owner: "the UI
  language has too much AI in it." Copy that said "I", explained how a number was made, or put
  rule numbers and file names on screen was rewritten; DESIGN.md §5b carries the seven rules and
  lint S8 holds the page code to them.
- `alerts.json` is retired (findata schema 3; `tools/migrate_2to3.py` moves a workspace). Each
  update now appends one record to `imports.json` — the files, what changed, what was noticed,
  what was decided without asking, what the owner was asked — and every item still waiting for
  the owner sits in `decisions.json`. A new **Data → Updates** page renders both; the Portfolio
  page computes its rule status today instead of showing the sentences of one import for months;
  and one sentence under the net worth in the page header says how far the numbers reach, what is
  still missing and how many items are waiting. `profile.json` carries `schema`, and `sync.py`
  refuses to copy a tool that builds a newer shape than the workspace has.
- **Setup starts from the files** (2026-09-12). The first real clone showed the interview was
  about thirty answers typed by hand into a shape only the scaffold knew. Now the owner drops last
  month's files first and `setup/scripts/propose.py` drafts the answers from them: every PDF is
  offered to every parser, the broker exports are recognised by their columns, and the draft
  carries the accounts (bank, product, kind, number, balance, closing day), the monthly files
  (filename pattern, parser, where each lands) and a first plan (take-home from payroll, the
  investing amount from what reached the broker, an allowance from the cards) — with where each
  value came from, and the questions the files cannot answer. On the author's own August files it
  found 15 of 20 accounts and all 9 monthly files; the scaffold refuses a draft while a question
  is open, and the same files become the first import. The parsers now also report the product,
  the holder and the kind printed on a statement. Two scaffold fixes the run exposed: a refused
  setup no longer clears the demo ledgers first, and accounts abroad get a screenshot document so
  preflight can name the screenshots. The selftest drafts a setup from the synthetic statements.
- **The cash-flow rows are derived, and the Cash flow page is gone** (findata schema 9, 2026-09-10).
  `cashflow.json` was the one copy in the workspace nothing re-derived: the monthly income rows
  the Income page reads are sums of the typed ledgers, and are computed at build now
  (`cashflow_rows` in rebuild.py) — a retyped e-Transfer changes the page on the next rebuild
  instead of waiting for someone to rewrite the table. The counterparty (someone repaying a loan)
  is `counterparty` on their ledger's row in the register's `documents[]`, where D10 reads it.
  The Cash flow page itself went at the owner's word — nothing on it was worth a page; the
  pay-yourself-first check lives on Home and Monthly plan, judged on the broker's record. D22
  warns on a cash-flow ledger row with no type, since an untyped row now counts in nothing.
- **A fund's contribution is a flow** (findata schema 8, 2026-09-10). The `monthly` a fund used to
  carry was the one line of the plan not written as a flow; it is a `saving` row with `to: <fund
  key>` now, the page and D13 read it there, and D13 fails a fund that still carries `monthly`.
- **Set aside is an axis, not a list** (findata schema 7, 2026-09-10; `tools/migrate.py` moves a
  workspace through every step it is behind). `rules.json` `exclude.accounts` said the same thing
  as `role: set-aside` in the register; the Investing pages now read the axis and D19 fails a
  rules.json that still carries the list. `value: statement` is defined as "from any evidence the
  owner dropped in", screenshots included (FINANCE.md §8a).
- **findata/ is three folders** (schema 6, 2026-09-10; `tools/migrate_5to6.py` moves a workspace).
  One per layer of the information model, split by who writes the file: `register/` (the owner's
  declarations), `ledgers/` (the facts the import writes), `history/` (what each update leaves
  behind). Nothing inside a file changes; the register still names files bare, and every script
  resolves them through `layout.py`. The folder is still `findata/` (iCloud for Windows drops any
  folder named `data`).
- **Spending reads This month, then Year** (2026-09-10, the redesign's IA). The page that opens
  one month up — by category, with the line-by-line of the chosen slice — comes first and gains
  a fourth card, everyday spending against the allowance; the year page (total, by category,
  month by month, what stands out) comes second. The month is what gets looked at every week.
- **The Insights page is absorbed** (2026-09-10, the redesign's IA). Its lines had three different
  readers: what stood out about the year now sits on the Spending overview and follows the year
  being viewed, how the plan is holding (pay-yourself-first, the allowance, the funds) sits on
  Monthly plan, and the one check that wants a decision — a subscription whose merchant appeared
  once — sits on Updates under "Worth a second look". 20 pages.
- **Statements are read by parsers** (2026-09-10). `.claude/skills/update-dashboard/parsers/`
  holds one module per institution and kind — `rbc_banking`, `rbc_visa`, `bmo_banking`,
  `bmo_mastercard` — and `documents[].parser` in the register names which one reads a file.
  `scripts/parse.py` returns rows signed the ledger's way, dated with the right year, with a
  running balance, and reconciled the way the register says; the sign of a bank row is solved
  from the printed balances rather than guessed from the words. Step 1 of the import runs the
  parser first and reads by hand only what it refuses. `tools/pdfgen.py` writes PDFs from the
  standard library and `tools/fixtures.py` renders the demo's ledgers back into statements in
  the real text shapes, so the selftest holds every parser to 32 synthetic statements plus one
  tampered total it must refuse (38 faults); in an owner's workspace it also runs the parsers
  over every real statement in `archive/`. Needs `pypdf`, optional: without it the import reads
  by hand as before. D14 rejects a parser name the tool does not have.
- **The monthly plan is flows** (findata schema 5, 2026-09-10; `tools/migrate_4to5.py` moves a
  workspace). `funds.json` `plan.flows` holds one row per thing that happens to the paycheque —
  `income`, `committed` (rent, a mortgage, a loan, each with `until`, `afterFire`, `pays` where
  they apply), `saving`, `allowance` — and the take-home, invest and allowance figures are sums
  of them, read from one module (`flows.py`) by the page, rebuild.py and the checkers. The
  Monthly plan bar shows the committed payments first; Unallocated no longer claims to feed the
  funds. `plan.json` `imputedRent` is a committed flow that starts at FIRE, and the Baseline
  page's calibration adds every committed flow that continues after FIRE. Lint D21 looks for each
  committed payment in the ledgers and warns when none moved; selftest plants one (37). The
  setup interview asks what is paid before anything is chosen.
- **Every account row carries five axes** (findata schema 4, 2026-09-10; `tools/migrate_3to4.py`
  moves a workspace). `side` / `role` / `reach` / `value` / `against` replace the net-worth words
  that used to sit in `feeds`, and each total on the page reads exactly one axis: net worth reads
  `side`, the by-purpose card `role`, the reach table `reach` (netting a liability into the row of
  the asset it names), dry powder the rules' symbols inside `grow`. A home is an ordinary row —
  `asset · none · locked · stated` — and so is the mortgage on it. The demo's reach table had
  been dropping "Spoken for" and showing "Across a border $0" whenever there was nothing
  abroad; rows are now present exactly when the register has an item with that value. Lint D19
  rejects an illegal pair and D20 insists a stated balance carries a date; selftest plants both.
  The setup interview asks what each account is for instead of which tag it gets.
- **The information model is written down** (2026-09-10). CLAUDE.md names the five layers
  everything in a workspace sits in — evidence, facts, history, declarations, derived — with one
  writer each, and the rules that follow (one fact per layer, verified copies only, no back-edges,
  access by key, the page reads nothing at runtime). FINANCE.md §8 adopts the target shape for
  the register: a balance item with five axes (`side`, `role`, `reach`, `value`, `against`) and a
  flow with five (`kind`, `amount`, `until`, `afterFire`, `pays`), so a home, a mortgage and a
  fixed payment are ordinary rows. Design only — `rebuild.py` still reads `feeds`; the code lands
  with findata schema 4.
- **One dashboard** (2026-09-10). The investment dashboard was merged into the main page as the
  Investing group — Overview, Holdings, Rules, Checkpoints, Foreign — ending two sidebars, two
  templates and a Portfolio page that repeated the Overview. `rebuild.py --write` removes a built
  `investment_dashboard.html` whose template is gone. Data became **Records**, a secondary group
  closed at the foot of the sidebar; Data sources became **Statements**; the foreign-currency page
  is named by `foreign.json` and hidden when there are no accounts abroad; Coast & drawdown is
  Coast & care.
- **The skill docs are checked the way README is** (2026-09-13). The three SKILL.md files are
  what Claude reads before every import and setup, and nothing checked them: update-dashboard
  still named `dashboards/ly_finance_dashboard.html` and "both dashboards" three days after the
  page became one file, workspace-checks said the selftest plants "fifteen" faults when the table
  held 42, and `docs/pipeline.py` still drew a release step that no longer exists. S4 now resolves
  every path a skill hands the reader, in prose and in its fenced commands; S6 reads a skill's
  `LINT:FAULTS` marker and its prose the way it reads README's; `docs/pipeline.py` takes its
  counts from the code. Two planted faults cover the new checks. The first run found two more
  stale lines: an `inbox/README.txt` the import was told to keep updated, which the register's
  `documents[]` replaced, and the retired mock-up files still named as decision records.
- **README says what leaves the computer** (2026-09-13). "Nothing leaves your computer" was true of
  the files and false of their contents: what Claude reads to do its part — the rows a parser
  pulls out, a statement no parser can read, the owner's answers — goes to Anthropic like anything
  said in Claude Code. The three front doors (README, README.zh, the Chinese guide) now say so.
  Doing better than saying so — a local orchestrator that hands the model only a summary and the
  items needing judgement — is the next step, not this one.
- **The import is one local run** (2026-09-14). `update-dashboard/scripts/update.py` does
  Steps 0–7 of the skill for every file a parser can read — names the files, parses and
  reconciles each statement, files the purchases by merchant, writes the ledgers and the
  register's copies, rebuilds, checks, archives, appends the update record and the queue of
  decisions — and prints a summary, never the rows. What reaches the model is what a program
  cannot decide: a file it could not name or read, a row it could not type, a merchant seen for
  the first time, an e-Transfer with no name on the other side. The selftest strips the newest
  statement of every document out of a copy of the demo, runs the script on the synthetic
  statement, and expects the demo's own rows back, the checkers clean, the rebuild idempotent
  and a second drop to write nothing. The front doors now say what leaves the computer and what
  does not: a statement a parser read never does. Found on the way: the Mastercard fixture
  printed the merchant and the city with no space between them when the merchant was long; and
  the first dry run on a real workspace showed RBC downloads arrive as `20260819.pdf`, a name
  the register cannot match — such a PDF is now offered to every parser and named by the
  account the statement prints, the way setup drafts the register.
- **Who it is for, and which banks come next** (2026-09-15). The owner's call: people in a
  similar situation — a paycheque, accounts at the big five banks, one of the three brokers most
  people use. README says so, and names the parser order: RBC and BMO exist; TD, Scotiabank and
  CIBC next; then Questrade and Interactive Brokers beside Wealthsimple. Until a bank has a
  parser its statements are read by hand, and README says that too.
- **A statement read by eye is transcribed, not written** (2026-09-15). The owner's call: no
  new parsers for now; a bank without one is read by the model. So that path goes through the
  same script: the model hands the rows and the printed totals back as JSON (`update.py --hand`),
  the script reconciles them the way it reconciles a parser's — chain from opening to closing,
  debits and credits against the totals — refuses what does not add up, and files what does
  like everything else. The selftest takes the savings statement's parser away, drops it under
  a name nothing matches, expects the stop, then the demo's own rows back from a transcription,
  and a refusal for one that is ten dollars off.
- **The demo is complete on the day it shows** (2026-09-15). The owner's call: a first visitor
  sees a finished page, not "three statements are still missing". The demo's chequing and
  savings ledgers now run to the Sep 5 statement (the one due on its Sep 8 "today"), the
  documents that started in May or June carry `from` so the grid stops owing months before
  they existed, and the broker exports are filed every month since June. The header reads
  "Everything due has arrived" apart from the two open items, which stay: they are the queue
  the page is for. The unnamed $200 e-Transfer the demo asks about is now a real row in the
  ledger, typed Other income meanwhile, as the record says.
