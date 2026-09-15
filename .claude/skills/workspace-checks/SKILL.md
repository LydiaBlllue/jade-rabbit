---
name: workspace-checks
description: Check the workspace across five questions — does the money reconcile, are the financial rules in FINANCE.md still held, is the dashboard current with findata/, is the data itself clean, and does the page still follow DESIGN.md. Use after ANY edit to a dashboard or to findata/, before reporting a change as done — and whenever the owner asks to review the UI, adds a page or chart, or says a number looks wrong. Findings are grouped by which of those five questions failed, because a balance chain that does not close and a stale README link are not the same kind of problem.
---

# Workspace checks

Every rule here was paid for in a mistake. The point of the skill is that each diagnosis only has
to happen once.

**These are not all lint.** The name was corrected on 2026-09-08 after the owner pointed out that
the script then called lint_findata.py had four jobs and none of them were linting. Findings now carry the question
they answer, and the output is grouped by it:

| Group | The question it answers |
|---|---|
| `reconcile` | Does the money add up on its own terms — balance chains, cross-file totals |
| `rules` | Is a rule in FINANCE.md being broken — a repayment is never income, a claim never exceeds its account |
| `build` | Is the artefact current — baked constants against findata/ |
| `hygiene` | Is the data itself clean — missing tags, duplicate rows, a rate going stale |
| `conform` | Does it still follow DESIGN.md — the one that really is a linter |

The category rides on each **finding**, not on the rule: `D14` reports both "this registry
contradicts itself" (rules) and "the page is stale" (build), and those are not the same problem.

## Run it

```bash
# how it looks — the dashboard against DESIGN.md
python3 .claude/skills/workspace-checks/scripts/check_design.py \
  dashboards/finance_dashboard.html

# whether it is true — findata/ ledgers, categories, rates, cross-file agreement
python3 .claude/skills/workspace-checks/scripts/check_data.py .

# whether it actually draws — headless Chromium at 1120 / 1440 / 1760 px (~11s)
python3 .claude/skills/workspace-checks/scripts/check_render.py \
  dashboards/finance_dashboard.html
```

`check_render` is the only one that needs anything installed:

```bash
pip3 install --user playwright && python3 -m playwright install chromium
```

It is deliberately **not** in the PostToolUse hook — 11 seconds on every edit is too slow. Run it
before calling a dashboard change done.

## Check the checkers

```bash
python3 .claude/skills/workspace-checks/scripts/selftest.py .
```

<!-- LINT:FAULTS n=44 -->
Plants 44 specific faults in a **copy** of the workspace and asserts that a named rule fires
for each. Run it after changing a linter, and after moving anything the linters read.

It exists because on 2026-09-08 two linter bugs shipped in one afternoon and both were silent: S4
walked a hardcoded `skills/` folder that had moved, and `hook.py` located the workspace by counting
`..`, so one extra directory level pointed it at `.claude/` — where it found no ledgers, reported
them missing, exited 0 and went on saying everything passed. **A checker that has stopped checking
and still says OK is worse than no checker.** The first run of selftest immediately found a third
hole nobody had noticed: nothing compared the dashboard's `FOREIGN` constant to `foreign.json`.

It also reports rules that exist but that nothing here breaks — its own blind spots, named rather
than assumed away.

A `PostToolUse` hook in `.claude/settings.json` already runs the matching one after
any Edit/Write under `dashboards/` or `findata/`, and stays silent when everything is
clean. Run them by hand when you want the full picture, or when the hook is off.

Pass the dashboard by name. Do **not** glob `dashboards/*.html`: an owner's workspace may keep
other HTML files there (mock-ups, decision records) that were never meant to follow the spec.

Exit code is 1 if anything is an ERROR, 0 otherwise. Three levels:

- **ERROR** — a rule in DESIGN.md is broken. Fix before saying the work is done.
- **WARN** — almost certainly wrong, but there are legitimate exceptions.
- **NOTE** — needs a human eye. The `·` check in particular cannot tell a list of account names
  (fine) from a chain of facts (not fine), so it reports and lets you judge.

## What it cannot see

The script reads the file. It does not open a browser, so it is blind to anything that only exists
once the page renders. After a structural change, check these yourself:

1. **Every page renders and has content.** Walk `PAGES`, call `setPage(k)`, confirm the
   section is visible and not near-empty. A page that throws leaves the rest of the script dead.
2. **No horizontal scroll at 1280, 1920 and 2560.** Desktop-only does not mean one width.
3. **Charts actually got wider, not just their container.** Measure the rendered `<svg>` box.
   Measuring the element and declaring victory is exactly how the fixed-height bug survived a
   round of "verification" — the element was 1434px while the drawing inside stayed 940px.
4. **Pages fill roughly a screen.** DESIGN.md §5d puts the floor near 520px. When a page falls
   short the agreed fix is to add a card that answers a question the page already raised — not to
   merge pages, and not to pad.

## Reporting

Give the counts, then the errors with the file and what to change. Numbers over adjectives:
"`.rule .det` is uncapped, 242 characters on one line" beats "text is too wide".

If a finding is a false positive, say so and fix the check — a linter people learn to ignore is
worse than no linter. If a finding reveals a rule DESIGN.md never actually wrote down, add the
rule to DESIGN.md too, or the next session relearns it.

## Rules currently checked

| ID | Checks | §
|---|---|---|
| L1 | `body` has `min-width:1120px` and a max-width ≥1600px | 4 |
| L2 | no `@media` blocks — the mobile view was dropped | 4 |
| L3 | no `col-hide-sm` leftovers | 4 |
| C1 | no `<svg viewBox>` pinned to a fixed pixel height, inline or via its class | 4 |
| T1 | `.meta` / `.say` / `.note-box` / `.pgsub` carry a max-width | 5d |
| T2 | the file's long-prose row is capped | 5d |
| K1 | `--muted` is ≥4.5:1 on both `--surface` and `--page` | 5d |
| S1 | every NAV key has a section and every section has a NAV key | 4 |
| S2 | the wordmark block and `.pghead` both size from `var(--headh)` | 5a |
| S3 | no `repeat(auto-fit, minmax(_, <fixed>px))` on stat rows | 5d |
| D12 | every row of `spending.csv` reaches the dashboard's `SPENDING` (a month is dropped from a statistic via `MONTH_SKIP`, never by losing the row) | — |
| S4 | the docs still describe this file: DESIGN.md's page table, body widths and `--headh`; README's page counts, sidebar names, min-width, and every path it hands the reader | 4 · 5a |
| X1 | no external script/link — the file must stay self-contained | 4 |
| W1 | string literals chaining several facts with `·` | 5b |
| W2 | tooltips containing `·` instead of `<br>` | 5 |

## findata rules

The UI linter protects how things look. This one protects whether the numbers are true,
which matters more — a merchant filed wrong moved the FIRE target by $33,000.

| ID | Checks |
|---|---|
| D1 | every ledger's `balance` column actually chains from row to row |
| D2 | each spending row carries a `[SOURCE/YYYYMMDD]` tag from a known source |
| D3 | categories stay inside the fixed seven |
| D4 | no duplicate date+amount+merchant rows survived the merge |
| D5 | nothing is filed as Subscription unless that brand appears more than once |
| D6 | one merchant, one category; and repeat merchants are in merchants.json |
| D7 | banks.json agrees with the ledger's closing balance |
| D8 | foreign.json total is the sum of its accounts, and each has an institution |
| D9 | fx.json is not carried-forward — the activities export carries the broker's rate |
| D10 | an e-Transfer matching the counterparty ledger named in cashflow.json is typed Repayment, never income |
| D11 | the dashboard's baked-in INVEST / NW_HISTORY match findata |

Adding a rule means editing the relevant script and this table. Keep it to rules that are
mechanically decidable; taste stays with the owner.
