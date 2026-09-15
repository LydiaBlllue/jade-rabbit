# FINANCE.md — the money logic

> This file owns **the money logic**: how the target is computed, how each month is divided, what
> counts as income. `CLAUDE.md` owns how the work is done, `DESIGN.md` owns how the dashboard
> looks, and the owner's own decisions — why these numbers, which account does what — are in
> `OWNER.md`. The figures table below is kept current by `rebuild.py` and checked by D15; the
> prose refers to it and never restates a number.

## 1. The goal: FIRE

<!-- LINT:FIGURES — check_data's D15 verifies this table against the dashboard constants and
     findata/. ⚠ Every current figure is written HERE AND NOWHERE ELSE. The prose refers to the
     table; it never restates a number. Before 2026-09-08 net worth appeared four times in this
     file, two of them still measured against a target abandoned the day before, and nobody
     noticed. A historical figure must say which month it belongs to.
     Column 1 is a stable key; column 2 is the label, in whatever language this file is in. -->

| key | Figure | Value | Source |
|---|---|---|---|
| plan_base | Planning spend | $2,550 /mo | `PLAN_BASE_DEFAULT`, set by hand |
| fire_target | FIRE target | $765,000 | planning spend × 12 × 25 |
| net_worth | Net worth | $101,791 | `INVEST.netWorth` + `FOREIGN_CAD`, all currencies |
| portfolio | Invested | $67,135 | `INVEST.portfolio` — the number FIRE is measured on |
| progress | Progress | 8.8% | portfolio ÷ target |
| gap | Gap | $697,865 | target − portfolio |
| invest_monthly | Monthly contribution | $800 | `funds.json` flows: `saving` to the broker |
| everyday | Everyday allowance | $1,300 | `funds.json` flows: `allowance` |
| big_threshold | Big-buy threshold | $300 | `funds.json` plan.bigThreshold |
| travel_goal | Travel goal | $3,000 | `funds.json`, due 2027-02 |
| dry_powder | Dry powder | 43.1% | `INVEST.dryPct`, band 40–45% |
<!-- LINT:FIGURES:END -->

- The target is **planning spend × 12 × 25** (the 4% rule), and progress is measured on the
  **portfolio** — the money that will be drawn down — not on net worth, which also holds
  earmarked accounts, bank cash and money abroad. Planning spend (`plan.json`
  `planBase`) is set by hand; the Baseline page shows the measured median beside it and warns past
  10% of drift, but **never changes the target by itself**.
- Net worth covers every account in every currency: the Canadian side plus foreign-currency
  accounts at the reference rate in `foreign.json`.
- The trajectory chart anchors at `plan.json` `retirement.anchorYear` and projects the three
  scenarios there; the late-life care model (home care, then long-term care tiers) is data in the
  same file.

## 2. Income: in the system

- **Payroll** is what lands in the account whose `feeds` include "Income" (`accounts.json`).
- **Not income**: transfers between your own accounts; a counterparty paying you back (their
  ledger is the register document that carries `counterparty`, and D10 checks that every
  matching e-Transfer is typed Repayment); dividends and interest that stay with the broker.
- Investment income (dividends, interest, stock lending, withholding tax) is shown on its own on
  the Income → Investment income page and is not part of the income figure.

## 3. The budget method: pay-yourself-first

- The `saving` flow to the broker in `funds.json` goes out each month in **two transfers of half that**,
  before anything else is spent.
- Whether the rule held is judged on the EFTs reaching the broker's chequing account in the
  activities export (`WSDEP`), because they run ahead of the bank statement.

## 3b. Guilt-free spending

The monthly waterfall, from `funds.json`:

1. Invest — the `saving` flow to the broker
2. Everyday allowance — the `allowance` flow; below that line there are no categories and no caps
3. A single transaction at or above `plan.bigThreshold` is a big buy: outside the allowance, paid
   from the fund with `role: "big"`
4. Whatever allowance is left goes to the fund with `role: "topup"`, overflowing into the big-buys
   fund once it is full

These four steps are the flows of §8b: `saving` (to the broker, or to a fund it names with
`to`), `allowance`, and the leftover routed by `leftoverGoesTo`. A `committed` flow — rent, a mortgage, a loan — sits above them and is paid before
anything is chosen; `income` is the whole paycheque, before it.

A fund is a **label on an account you already have**, not an account of its own; each names its
`backing`. The hard constraint is that the claims against an account never exceed its balance
(D13), and a fund can be renamed, re-backed or removed as data.

## 4. The rhythm

- **Import day** (`profile.json` `importDay`): statements and the broker export go into
  `inbox/`, then say "update dashboards". A scheduled task can remind you that morning and list
  what has arrived and what is missing.
- Each quarter: go through Investing → Rules and Investing → Checkpoints.

## 5. The tool landscape

This workspace is all of it. No budgeting app, no cloud connector; the data exists only in this
folder.

## 6. Naming

The interface and the documents do not call the dashboard a "barbell" (the strategy itself may
still be called that). Seven fixed English categories: Grocery / Subscription / Dining /
Shopping / Transport / Entertainment / Other.

## 7. Earmarked accounts

An account whose `role` is `set-aside` in the register is set aside for a purpose — a first
home, an emergency fund. It is outside Portfolio and outside the dry-powder denominator, whatever
it holds, and it shows "—" in the percentage column. It is one value of one axis (§8a); the
`exclude.accounts` list `rules.json` used to carry said the same thing twice and is gone since
findata schema 7.

## 8. The model: balance items and flows

> **Both halves are live**: 8a since findata schema 4, 8b since schema 5 (2026-09-10;
> `tools/migrate_3to4.py` and `tools/migrate_4to5.py` move a workspace). Nothing in this section
> is a figure.

### 8a. A balance item

Every place money sits, and every thing owed, is one row with five axes. Each total the page
shows reads exactly one axis, so a home, a mortgage, a car loan or a pension is an ordinary row
and needs no special case.

| axis | values | what reads it |
|---|---|---|
| `side` | asset · liability | net worth = Σ assets − Σ liabilities, every currency |
| `role` | grow · set-aside · buffer · none | Portfolio, the number FIRE is measured on, is `grow`; net worth by purpose is one slice per role; §7's earmarked accounts are `set-aside` |
| `reach` | today · costs · spoken · locked · abroad | the reach table: no gate; taxed on the way out; reachable but spoken for; not liquid; across a border |
| `value` | export · statement · stated | how the balance is known: `export` from a file the broker produced, `statement` from any evidence the owner dropped in — a bank statement, a screenshot of an app, a balance read off it and typed into `banks.json` or `foreign.json` — and `stated` typed by hand with an `asof`, the one value nothing can re-derive |
| `against` | the asset a liability sits on | the reach table shows equity: a home less its mortgage, on the `locked` row |

- A home is `asset · none · locked · stated`. It counts in net worth, not in Portfolio and not in
  dry powder. On the reach table it is "Locked in property", net of what is secured against it;
  on the by-purpose card it is "Other assets".
- A mortgage is `liability` with `against: home`. A credit card is `liability` with no `against`.
- Dry powder is not an axis: `rules.json` names the symbols, counted inside `grow`.
- A fund (§3b) is not an axis either: a label claimed against one `set-aside` item.
- The two cuts of net worth — by purpose, by reach — read the same rows and agree by
  construction. The assert stays, because `against` netting is new and negative equity is a real
  case.

### 8b. A flow

Every monthly line of the plan is one row with five axes. The waterfall is the flows in kind
order.

| axis | values | what reads it |
|---|---|---|
| `kind` | income · committed · saving · allowance | the waterfall, top down; §3's pay-yourself-first is `saving` placed before `allowance` |
| `amount` | per month | the waterfall |
| `starts` | absent, or `fire` | a flow that begins only after FIRE — rent an owner will pay but does not yet — is out of this month's split and inside the planning figure |
| `until` | a date, or open | the FIRE projection drops a flow after its end — a loan paid off |
| `afterFire` | keep · drop | rent keeps, a mortgage payment drops, property tax keeps |
| `pays` | the liability it repays | the principal part is saving, not spending |
| `to` | `broker` (the default) or a fund's key | pay-yourself-first counts only the broker; a fund's standing contribution is the saving flow that names it, and nothing on the fund repeats the number |

- **Unallocated** is income less every other kind. It is a hard constraint: below zero the plan
  does not hold and the page says so in red. It is never "money that flows to the funds".
- **Planning spend** is still set by hand and §1's target is still planning spend × 12 × 25.
  The calibration beside it is the measured everyday median plus every committed flow marked
  `keep`, paid today or starting at FIRE — the fixed costs the cards never show. What used to be
  `plan.json` `imputedRent` is an ordinary committed flow with `starts: "fire"`.
- **Savings rate** is saving plus the principal in `pays`, over income.
- **A committed flow is declared, not observed.** D21 matches each one paid today against the
  ledgers the way the investing transfers are matched against the broker's activities — a
  payment of that size in the two whole months before the newest ledger date — and reports an
  unmatched one.

### 8c. What is deliberately simplified

- **Principal and interest.** Without the loan's own ledger the split is unknown, so a payment
  with `pays` is counted whole as committed and the savings rate says principal is not counted.
  Estimating an amortization table would be guessing; bringing the loan statement in as a ledger
  is the honest fix, and it belongs with the parsers.
- **A `stated` value has no evidence behind it.** It is the only number in the workspace nothing
  can re-derive, so it gets its own staleness rule — a home is not stale at thirty days, a car
  is — and FIRE progress stays on Portfolio, which never contains one.
- **`role` is this tool's own vocabulary.** An owner who does not earmark money uses `grow`,
  `buffer` and `none`, and the by-purpose card simply has fewer slices.

Mapping today's `feeds` onto the axes: Portfolio → asset · grow · today (registered retirement
accounts: costs); Earmarked → asset · set-aside · spoken; Bank cash → asset · buffer · today;
Debts → liability; a foreign-currency account → asset · abroad, role per account.
