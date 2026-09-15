---
name: setup
description: Turn a fresh clone into this person's own workspace. Reads the first statements the owner dropped into inbox/, drafts their accounts, monthly files and plan from them, asks only what the files cannot say, then generates the whole of findata/ and rebuilds the dashboard. Use when someone says "set this up", "make it mine", "I just cloned this", or when findata/ still holds the demo data.
---

# setup — make this workspace yours

The demo data belongs to a person who does not exist. This replaces it with the new owner's, in
one sitting of about twenty minutes, and proves the result with the same four checkers everything
else here is held to.

**What this does NOT do: invent transactions.** It writes the *structure* — the accounts, the
files that arrive each month, the plan, the rule — and leaves every ledger empty. History arrives
on the first "update dashboards", parsed from real statements. A workspace with no history yet is
a correct state, and every page is built to say so rather than to look broken.

---

## The order: files first, then the questions

**Ask for last month's files before asking anything else.** The statements, the broker's holdings
and activities exports, a screenshot of anything held abroad — dropped into `inbox/` with the
banks' own filenames. The files already answer most of the interview: a statement says which
bank, which account, what kind, what it closed at and on which day; a holdings export lists every
account at the broker. The same files are then the first import, so nothing is dropped twice.

Someone who has no files at hand can still be set up: skip to **The interview** and ask
everything, the way it was done before 2026-09-12.

## Step 1 · Draft from the files

```bash
python3 .claude/skills/setup/scripts/propose.py .            # show the draft
python3 .claude/skills/setup/scripts/propose.py . --write    # save it as findata/register/setup-answers.json
```

It offers every PDF to every parser and keeps the one that reads it (never trusting the filename),
recognises the broker exports by their columns, and drafts the answers file with:

- **the accounts** — bank, product name, kind, number, closing balance and date, and a default
  for what each is for (FHSA and anything named "savings" at the broker: set aside);
- **the monthly files** — the filename pattern (the dropped name with its date taken out), the
  closing day, the parser, where it lands;
- **the plan** — take-home from the payroll deposits, the investing amount from what reached the
  broker last month, an allowance from one month of card spending;
- **`_proposed`** — where every drafted value came from;
- **`_open`** — the questions the files cannot answer.

Show the owner the draft **as the tables it prints**, then work through `_open` in order, a few
at a time. Each answer goes into the file and its question comes off the list. **The scaffold
refuses to run while `_open` has anything in it** — a draft is not an answer.

What the files typically cannot say, and so `_open` asks: the name to show (the statements carry
the legal name, which may not be the one the owner uses), the birth year, whether the table is
right, accounts that sent no file this month, balances the broker's exports do not carry, how
often pay arrives, whether last month's transfers are the standing rule, the allowance, fixed
payments and rent after FIRE, the planning spend, funds, the investing buckets, a counterparty
who repays a loan, and anything held abroad.

## Before you write anything

Check whether this workspace is already somebody's:

```bash
python3 .claude/skills/setup/scripts/scaffold.py . --answers /dev/null 2>&1 | head -3
```

The scaffold refuses to run when any ledger already has rows in it. **If it refuses, stop and
ask.** Someone who says "set this up" while holding six months of imported statements means
something else — probably one account added, which is an edit to `findata/register/accounts.json`, not
this.

---

## The interview

**With a draft from Step 1, this section is the reference for answering `_open`, not a second
round of questions.** Without files, ask in the order below, **a few questions at a time, not all
at once**. Repeat back what you
heard before writing anything. Everything here ends up in `setup-answers.json`; nothing is typed
into HTML.

### 1 · Who this belongs to

- Their name. It is shown under the Jade Toad wordmark in the sidebar and in the browser tab;
  Jade Toad is the product and is not a setting.
- Roughly what year they were born. It is used for the retirement-age arithmetic, nothing else.

### 2 · The accounts

For each one: **institution · what they call it · what kind · last few digits · currency ·
today's balance · what it feeds.** An investment account's balance is kept as `statedBalance`
only — the number the pages use comes from the first holdings export, so **the Investing pages
read $0 until that import**, and you should say so when handing over.

Kinds the tool understands: `Chequing`, `Savings`, `Credit card`, `Investment` (or the
specific `TFSA` / `RRSP` / `FHSA` / `Non-registered` / `Crypto`), `Loan`, `Line of credit`,
`Mortgage`, `Property`.

**Ask what each one is for, not which tag it gets.** Every row carries five axes (FINANCE.md
§8a), and each total on the page reads exactly one of them; the scaffold fills them in from the
kind, so you only have to ask where the default would be wrong:

- `role` — what the money is for: `grow` (invested), `set-aside` (a purpose already — a first
  home, an emergency fund), `buffer` (day-to-day cash), `none` (owned, but neither growing nor
  spent — a home, a car). Default: investment kinds → grow, FHSA → set-aside, cash kinds →
  buffer, Property → none.
- `reach` — how easily it can be touched: `today`, `costs` (RRSP: taxed on the way out),
  `spoken` (set aside), `locked` (property), `abroad` (a foreign account).
- `value` — where the balance comes from, and the scaffold sets it: `export` (a broker file),
  `statement` (a bank statement), `stated` (the owner's word — a home, a car). **A stated item
  needs a date**: ask "what is it worth today, and when did you last look?"
- `against` — a mortgage or a car loan sits on an asset: ask which one. The reach table then
  shows the equity, not the gross.
- `side` is asset or liability, from the kind. A liability has no role and no reach.

`feeds` keeps only the flow words: `Income` (the ledger payroll lands in), `Spending` (a card
whose charges go to spending.csv), `Cash flow`, `Repayments` (a counterparty's ledger).

Ask for **every** account, including the ones they think are boring. "Where is the money" is one
of the two questions this tool exists to answer, and an account nobody listed is invisible.

### 3 · What arrives each month

For each account that produces a statement: **what the file is called** (a pattern, e.g.
`Visa Statement-7712 <date>.pdf` — the bank's default name, which is how it is recognised) and
**which day it closes**. An account with no monthly statement simply has no document. One export
can cover several accounts (a broker's holdings file usually does): put the document on one of
them and list the others in `alsoCovers`, by name.

Then: **which day of the month they will sit down and import** (the default is the 26th).

### 4 · The monthly plan

The plan is **flows** (FINANCE.md §8b): each one is a row in `funds.json`, and every number
the page shows is a sum of them.

- Take-home pay per month — the whole paycheque, **before** rent or a mortgage comes out.
- **What is paid every month before anything is chosen**: rent, a mortgage, a car loan, a
  student loan. For each: the name, the amount, **when it ends** if it does (a loan), whether it
  **continues after FIRE** (rent does; a mortgage payment does not; property tax does), and for
  a loan **which liability it repays** (an account from step 2). These go into the interview
  answers as `plan.committed`. An owner who pays no rent today but will after FIRE gives the
  figure as `imputedRent`; it becomes a flow that starts at FIRE. D21 looks for each committed
  payment in the ledgers afterwards, so a number nobody actually pays is caught.
- How much they invest per month — the transfer to the broker.
- Their everyday allowance — the guilt-free line. **No category caps**; that is the point of it.
- What counts as a big buy (the default is a single purchase of $300 or more).
- Any funds they are saving into: a name, a goal, a date. A fund is a **label on an account they
  already have** — nothing is transferred and no new account is opened. At most one fund can be
  `role: "topup"` (leftover allowance flows into it) and one `role: "big"` (big buys come out of
  it). Having neither is fine. **A standing contribution to a fund is a `saving` flow with
  `to: <fund key>`** — a row of the plan, not a number on the fund.

### 5 · The one investing question

**Ask exactly one thing, and only if they invest:**

> What are your buckets, and which one has a target range?

A bucket is a name plus the tickers in it. Any bucket may carry a `target` like `[70, 80]`, and
**that is the only thing this tool computes about your strategy**: where each banded bucket sits
today and how far it has drifted. Everything else an investor believes — which account a holding
belongs in, why they hold a position, when to add — stays prose on the Rules page, judged by
them, because it is a judgement and not an arithmetic fact.

Offer a default if they hesitate, and say plainly that it is a starting point and not advice:

```json
"buckets": [
  {"key":"eq",   "name":"Stocks",         "symbols":["VEQT"],      "target":[70,80]},
  {"key":"fi",   "name":"Bonds and cash", "symbols":["ZAG","CASH"],"target":[20,30]},
  {"key":"rest", "name":"Everything else","catchAll":true}
]
```

Also ask, once: **is any account set aside** — earmarked for a purpose, so it should sit outside
the portfolio entirely? And **how many holdings do they want to end up with** (`maxHoldings`)?

**Do not ask about their strategy beyond this.** Do not ask about tiers, tax placement, or
triggers. Those exist on the page for whoever wants to write them, and pushing a stranger's
framework onto a new owner is exactly what this file is supposed to prevent.

### 6 · Foreign assets

Do they hold anything in another currency? If not, say so and move on — the module renders itself
away. If they do: the currency, its symbol, the display name they want, and today's rate.

---

## Writing it

Put the answers in `findata/register/setup-answers.json` (the shape is at the bottom of this file; Step 1 writes it for you), show
them the summary, and only then:

```bash
python3 .claude/skills/setup/scripts/scaffold.py . --answers findata/register/setup-answers.json --write
python3 .claude/skills/update-dashboard/scripts/rebuild.py . --write
```

Two steps: the scaffold writes `findata/`, the rebuild builds the dashboard from
`templates/dashboards/` and that data — and keeps FINANCE.md's figures table in step. There is no
previous owner to clear out: the template holds nobody's numbers (lint T1 says so), so the new
owner's first view is their own empty workspace.

## Proving it

**This is not optional, and a ✗ here is a bug in the setup, not in the checkers:**

```bash
python3 .claude/skills/workspace-checks/scripts/check_data.py .
python3 .claude/skills/workspace-checks/scripts/check_design.py \
  dashboards/finance_dashboard.html
python3 .claude/skills/workspace-checks/scripts/check_render.py \
  dashboards/finance_dashboard.html
```

`⚠ page does not fill a screen` is expected while the workspace is empty — there genuinely is
little to show yet. Anything else, fix before handing it over.

## Then tell them what to do next

Three things, in this order:

1. **Say "update dashboards".** The files the draft was made from are still in `inbox/`, and
   the register now names every one of them, so they are the first import — nothing is dropped
   twice. That import is what fills the pages. (Set up without files? Then drop last month's
   statements into `inbox/` with the bank's own filenames first.)
2. **Open the dashboard.** `dashboards/finance_dashboard.html`, in a browser, at least 1120px
   wide.
3. **Start `OWNER.md`.** The three governing documents are the tool's and say nothing about
   anyone; everything that is theirs — which bank does what, the traps their statements have,
   the decisions they make out loud — goes in `OWNER.md`, which `CLAUDE.md` loads (and, once a
   decision is replaced, its dated record goes in `decisions/`). Write the
   first few lines with them now: their banks, their broker, their language.

---

## The answers file

```json
{
  "owner": "Alex Chen",
  "born": 1993,
  "currency": "CAD",
  "importDay": 26,
  "accounts": [
    {"inst":"TD","name":"Everyday Chequing","kind":"Chequing","id":"…4021",
     "balance":4210.55,"asof":"2026-08-31","ledger":"chequing.csv",
     "feeds":"Income, Cash flow, Bank cash",
     "doc":{"file":"Chequing Statement-4021 <date>.pdf","closes":31}},
    {"inst":"Questrade","name":"TFSA","kind":"Investment","id":"…5533",
     "balance":38400,"asof":"2026-09-06","feeds":"Portfolio",
     "doc":{"file":"holdings-<date>.csv"}}
  ],
  "plan": {"takeHome":4200,"invest":900,"everyday":1800,"bigThreshold":300},
  "funds": [],
  "rules": {
    "buckets": [{"key":"rest","name":"Holdings","catchAll":true}],
    "maxHoldings": 8
  },
  "foreign": null
}
```

`key`, `stmtTag`, `spendTag` and the document keys are derived — do not write them by hand. An
account with no number gets `"id": "—"`, which is why `key` and not `id` is the join everywhere.
