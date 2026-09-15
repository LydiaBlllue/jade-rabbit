# DESIGN.md — the dashboard design rules

> Compiled from everything the owner said during the 2026-08-11 Spending Dashboard redesign.
> **Every dashboard design and revision after that has to follow this file**; where an old habit
> conflicts with it, this file wins. New or changed rules go in here once the owner has confirmed them.

## 1. Brand and language

- Title: **Jade Toad · `<owner>`**, where the owner comes from `findata/register/profile.json` — it is the
  first thing anyone changes to make this theirs, and it is never typed into the markup.
  Here it is the product name, **Jade Toad**, with the owner's name in small type beneath it.
- Interface language: **English throughout** — labels, buttons, hints, empty states.
- Seven fixed spending categories, in English: Grocery / Subscription / Dining / Shopping /
  Transport / Entertainment / Other. The category name *is* the definition; never mix languages
  in it.
- The one exception is gone (the owner, 2026-08-20): **the Investment Dashboard is in English too**,
  same as the main one, and the visual rules apply to it equally.

## 2. Visual style (settled against the KJ Rainey look)

- **White cards on a pale ground**: page `#f9f9f7`, cards `#fcfcfb` with a 10px radius and a
  hairline border.
- **Small grey uppercase labels**: every card title is 10.5px, letter-spaced, uppercase, grey —
  `SPENT`, `MONTHLY BASELINE`, that register.
- **Big numbers**: a statistic is 26px or more, bold, tabular numerals.
- Typeface: the system sans (system-ui / Segoe UI). No serifs, nothing decorative.
- **Light theme only**: no dark-mode adaptation; the page stays on a white ground whatever the
  system is set to.
- Month switching uses **pill selectors**, the selected one black on white.

## 3. Colour

- The category palette is a dataviz-validated 7-slot set — colour-blind safe, checked in light
  mode: Grocery `#2a78d6` blue / Dining `#eb6834` orange / Subscription `#1baf7a` teal /
  Shopping `#eda100` yellow / Transport `#e87ba4` pink / Entertainment `#008300` green /
  Other `#4a3aa7` purple.
- **Colour follows the category, permanently. It is never reassigned by rank or by size.**
- Anything semantic — up or down, good or bad — must carry **colour *and* a symbol or arrow**.
  Colour alone is not allowed to be the signal.

## 4. Page structure

- One self-contained HTML file, no external dependencies.
- **Desktop only** (the owner, 2026-09-06, overturning the earlier "mobile-friendly at 375px" rule):
  `body` is `min-width:1120px; max-width:1760px` — widened from 1280 on 2026-09-06 because
  the owner works on a **32-inch screen**. **What widens is the charts and the wide tables, not
  everything**:
  - Stat cards (`grid-stats` / `stats`) use `repeat(auto-fit,minmax(190px,340px))` with
    `justify-content:start`. A single big number should not be stretched into a 500px-wide card;
    white space on the right is better.
  - `.meta` label/value rows cap at 720px — put the two ends far enough apart and it stops
    reading as one line. `.say` 820px, `.note-box` 900px, `.pgsub` 620px, sliders 560px.
  - Charts and wide tables have no cap. The wider the window the clearer they get, and that is
    the entire point of widening.
  - ⚠ **A chart must be `width:100%; height:auto`. Never give it a fixed pixel height.**
    `viewBox` + `preserveAspectRatio="xMidYMid meet"` + a fixed height means the drawing is
    scaled to its height and centred: a wider window only adds white space on both sides and the
    picture does not grow at all. Found by measuring on the owner's 32-inch screen, 2026-09-06.
    Deleting `height:190px|280px` from `.trend-svg` / `.year-svg` and three inline
    `style="height:…"` took the trend chart from an actual 940×190 to 1434×290. Do the same for
    every new chart.
  - The old rule was `min-width:1120px; max-width:1280px` with a `@media (max-width:720px)`
    block; the narrow-screen adaptation is gone. Design new things at desktop width and stop
    making compromises for a phone.
- **One dashboard, one left sidebar** (2026-09-10). The investment dashboard, a second file
  with its own sidebar and a link back, was merged into the **Investing** group: Overview
  (the old Portfolio page plus the four stat cards, the bucket picture and the rate behind the
  numbers), Holdings, Rules, Checkpoints, and the foreign-currency page. Three seams went with
  it: two sidebars with different brands, a Portfolio page and an Overview page showing the
  same numbers, and two templates to keep in step. Everything derived for those pages lives
  inside one `IV` object so nothing there collides with the rest of the page.
  - **Records is a secondary group**: closed at the foot of the sidebar, opened by clicking its
    heading or by landing on one of its pages; while closed, its heading carries the strongest
    dot inside. **Data sources was renamed Statements** — what you drop in is a statement, and
    "data source" is the pipeline's word for it.
  - **The foreign-currency entry is named by the data** (`foreign.json` `label`) and hidden in a
    workspace with no accounts abroad; the docs and the checks know it as Foreign.
  - The old top tabs, the `@media(max-width:520px)` block and the `col-hide-sm` hidden columns
    are all deleted (2026-09-06); the Accounts column of the Holdings table is always visible.
- **Navigation is the left sidebar** (the owner picked B from two mock-ups on 2026-09-06; the
  mock-ups are not shipped with the tool).
  Text tabs across the top are abolished: tabs wrap as pages are added, and at 375px they had
  already wrapped onto two lines.
  - Structure: `.shell` = `aside.side` (190px, `position:sticky`) + `main.main`. The sidebar is
    rendered from the `NAV` constant in 4 sections — **Spending / Investing / Plan / Data** —
    with Home pinned above them under no section heading.
  - **A new page is one entry in `NAV` plus one `<section data-pg="key" hidden>`**, and nothing
    else. `setPage()` is driven entirely by `NAV`; no more hand-written `id` branches.
  - Every page has a `#pgTitle` and a one-line `#pgSub`. **If the page title already says it,
    delete the `.lab` on the card** — do not say it twice.
  - **Dots**: `pageFlags()` works out which pages have something on them (Tasks has an open
    item / Freshness has a source past 30 days / Portfolio breaks the dry-powder or holdings
    rule) and hangs a 6px dot on the right of the sidebar entry — amber `#c98500` = look at
    this, red `#d03b3b` = a rule is broken. This is the sidebar's core advantage over top tabs;
    remember to wire new rules into it.
  - Month pills appear only on `PILL_PAGES` (home / tx / budget).
  - The foot of the sidebar carries the tool version (`v1.0`) in muted 10.5px. MAJOR.MINOR:
    polish moves the minor, a change of shape moves the major.
<!-- LINT:PAGES pages=19 sections=5 -->
- **LY Finance Dashboard is the main dashboard**: 19 pages under 5 sidebar sections (the
  2026-09-06 rebuild, replacing 6 top tabs). **Lint rule S4 checks this table against the `NAV`
  constant, so changing the navigation means changing this table too** — S4 also checks the page
  count, the sidebar list and the minimum width stated in `README.md`, and that every path the
  README hands you resolves, because the README is the front door and pointing at the wrong
  place is worse than saying nothing:
  | Section | Pages |
  |---|---|
  | — | Home (net worth, two cuts of it, At a glance) |
  | Spending | This month · Year · Subscriptions · Monthly plan |
  | Income | Overview · Investment income |
  | Investing | Overview · Holdings · Rules · Checkpoints · Foreign |
  | Plan | FIRE · Coast & care · Baseline |
  | Records | Updates · Accounts · Statements · Tasks |
  The Insights page was absorbed on 2026-09-10: what stood out about the year is a card on the
  Spending overview, how the plan is holding is a card on Monthly plan, and the one check that
  wants a decision (a subscription seen once) sits on Updates under "Worth a second look".
  **The Accounts page** (the owner asked for it 2026-09-07) is one row per place money sits, grouped
  by institution, with the institution row giving that institution's net position (credit cards
  negative, currencies listed separately and never added together); **a CAD total on the last
  row** (the owner, 2026-09-08) — the one place on the page where currencies are added, so its
  tooltip must state the rate and its date, how many balance-less accounts were left out, and it
  must reconcile against the net worth in the page header (mark the row ⚠ when it does not).
  Below it, a `gaps` card lists what is missing, why, and how to fix it. The source is
  `findata/register/accounts.json` — **a register, not a second set of books**: balances are copied from
  banks.json / holdings_latest.csv / foreign.json and lint D14 re-derives them. The reason it exists:
  the workspace could answer "which files are due this month" (Data sources) but not "where is my
  money", and the account list had to be assembled by hand from four data files every time —
  which is exactly how an account goes missing.
  **The Updates page** (2026-09-10) is where an update leaves its trace. Three stat cards (last
  update, waiting for you, updates on file), then **To confirm** — every item the import could not
  settle on its own, from `findata/history/decisions.json`, each with what was assumed meanwhile and which
  statement it came from — and then one card per update from `findata/history/imports.json`: what changed
  (label, from, to), what was noticed, what was decided without asking, what you were asked. It
  replaced the "Rule status" list on the Portfolio page, which had been showing the sentences of
  one import as the state of things for months. **The story of an update lives here and nowhere
  else; every other page shows a status computed today.**
  The old Overview split into Home + Budget + Subscriptions, the old Investments into Portfolio +
  Cash flow + Foreign, the old FIRE into FIRE + Coast + Baseline, and the old Insights/Tasks into
  four pages. Investing → Overview is the investment-discipline summary; the detail is the rest
  of the Investing group. **The headline number of the Investing group is Portfolio, "money
  that is actually invested"** (the owner, 2026-08-20): Wealthsimple's non-earmarked accounts plus
  the foreign funds; not FHSA, not High-yield savings (those get their own Earmarked card), and no
  bank balance or Chinese demand deposit. The page keeps that as its only denominator (the old
  Investable capital was folded into it); the dry-powder denominator is its Canadian part, and
  the foreign-currency assets are listed separately under the structure chart. Full definitions are in
  CLAUDE.md. **The FIRE tab** (the owner asked for it as its own page, 2026-08-13) holds everything
  FIRE: the progress stat cards (progress % / net worth / gap / target), the progress bar, and
  the adjusted monthly baseline — the baseline moved out of Overview and FIRE progress moved out
  of Investments, and neither is repeated anywhere else. The FIRE page carries the **Coast and
  drawdown card** (the owner, 2026-09-06): two sliders (age you stop contributing / age you start
  drawing, stored in localStorage `ly_coast`), a three-colour line (blue = still contributing,
  green = compounding on its own, amber = drawing down), an **age** x-axis (the owner was born in
  2000, `BORN=2000`) drawn to 95; the headline conclusion is a full sentence saying at what age
  it reaches the target with no further contribution, and a `metaList` underneath gives the
  portfolio value at drawdown, the annual withdrawal, what share of the portfolio that is, and
  how long it lasts. It also carries the **Trajectory to FIRE chart** (the owner, 2026-08-13): net
  worth under $2,500/month of contributions at 3% / 5% / 7% real, drawn to the target's dashed
  line, each curve stopping and marking the point where it arrives, the legend giving
  "X.X years · month year". The chart has a money y-axis on nice steps; **the x-axis is calendar
  years anchored permanently at 2026** so it does not drift across a new year (the owner,
  2026-08-13); the real net-worth snapshots (`NW_HISTORY`) are drawn as a black line with dots
  that show their value on hover, the three projections continue from the current month, and the
  first legend row is Actual.
- **Spending is read two ways, in this order** (2026-09-10): **This month** first — one month
  opened up: four stat cards (spent, biggest category, above typical, everyday against the
  allowance), the category list on the left and the line-by-line of the chosen category on the
  right, driven by the month pills — because that is the page looked at every week; **Year**
  second — the year pills, the yearly stat cards, the year by category, the monthly stacked
  chart and "What stands out" — looked at now and then. Neither page carries a plan verdict
  beyond the everyday line; Monthly plan does.
- **Monthly plan page** (formerly Budget; the owner rebuilt it 2026-09-07: "the budget system isn't
  very usable. I need guilt-free spending"). The old version was category caps — Total, Dining,
  Shopping, Subscription, turning red when exceeded — which had always contradicted FINANCE.md §3
  ("no category budget caps"), so the page was redone. Source: `findata/register/funds.json`. Four cards:
  - **Free to spend in \<month\>** — the headline, one number: allowance minus this month's
    everyday spending. **No categories at all** (a category cap is a small guilt machine: it
    makes you justify a dinner and never answers whether the month as a whole went well). A track
    bar with an even-pace marker, shown only for the current month.
  - **Where each month goes** — one horizontal stacked bar cutting take-home into the committed
    payments (one segment each: rent, a mortgage, a loan — `funds.json` `plan.flows`, kind
    `committed`, in the neutral `--muted`) / Invest / Everyday / Big buys / Travel / Unallocated,
    with a `metaList` beneath it, one line per part. Take-home, Invest and Everyday are sums of
    the flows, derived on the page at load; Unallocated is what nothing names and stays where the
    paycheque landed — it is not routed to the funds.
    Invest, Everyday and Big buys **can be edited in the page** (`.bud-edit[data-pk]`, stored on
    `ST` as `alw` / `invm` / `bigm`, carried in the URL hash and localStorage). If the parts add
    to more than take-home, a `noteBox` says so.
  - **Your two funds** — Travel (goal bar and deadline) and Big buys (no goal; opening amount,
    contributed to date, drawn down, and the largest single purchase it covers today).
  - **These do not use the category palette**: Invest blue `#2a78d6` / Everyday orange
    `--c-dining` / Big buys yellow `--c-shopping` / Travel purple `--c-other` / Unallocated
    `--pill` — the same non-category semantic colours Home uses for NWPARTS.
  - ⚠ **Every word that reaches the page is English** (§1). Fields in `funds.json` that get
    rendered are written in English; Chinese reasoning goes in `zh_`-prefixed fields the page
    never reads. The first version rendered a Chinese `why` straight onto a card and had to be
    redone on the spot (2026-09-07).
- **Home carries nothing by-month** (the owner, 2026-09-07: "I don't want this by-month information
  on home, and drop Spending by category"). Home answers *where do I stand now*, not *what did I
  spend this month* — so it is **in neither `PILL_PAGES` nor `YEAR_PAGES`** and the month pills
  do not appear there. The old this-month donut and the 6-month income/spending bars were deleted
  (`renderDonut` / `renderTrend` went with them); everything by-month lives in the Spending and
  Income sections.
  - Home now has three cards: **net worth cut by purpose** (one row per `role` in the register:
    Invested / Earmarked / Cash / Other assets, less debt), **the same money cut by how easily
    you could reach it** (one row per `reach`: Reach today / Reach but it costs / Spoken for /
    Locked in property / Across a border, a liability netted into the row of the asset it sits
    on, less what is owed free and clear), and At a glance. A row appears only when the register
    has an item with that value. **Both cuts must total `NW_GLOBAL`** (rebuild.py refuses to
    build otherwise).
  - The idea came from Irene Zhu's 10-Year Wealth Dashboard (the owner shared it 2026-09-07): **do
    not report one net worth, report the rings inside it.** But it is **not a copy** — hers
    layers by Australian super's "locked until an age" rule, and a Canadian RRSP is not locked,
    it is taxed. So the second card layers by **friction cost**, not by age.
- Overview **has no stat cards** (the owner removed all five — Income, Spent, Net, Daily average,
  Transactions — on 2026-08-14): the monthly total is the number in the middle of the donut,
  daily average and transaction count moved into the Budget page's description line, and the
  count and total for transactions sit in the ledger footer. Still **no Month projection**.
- **"At a glance" card at the top of Overview** (the owner, 2026-08-14): one row per other tab —
  uppercase grey tab name, a ⚠/✓/● status, one line of the thing that matters, and a › arrow;
  the whole row is clickable and jumps to that tab. Every word of it is computed from the data.
- **Compact layout** (the owner asked for "denser information" on 2026-08-14): card padding 12/15px,
  grid gap 10px, big numbers 23px, list rows 3–5.5px apart, less vertical white space on the
  page. Density first, but keep the line height readable.
- Overview charts are symmetrical (the owner, 2026-08-13): **Income donut on the left, Spending
  donut on the right**, same size, same interaction. The 6-month trend is **grouped Income vs
  Spending bars** (Income blue `#2a78d6`, Spending orange `#eb6834`, with a legend and the
  series named in the title); the selected month is fully saturated and labelled with its value,
  the others are faded, and clicking a bar jumps to that month.
- Month by Month is the **whole-period view**: two stacked bar charts, spending (the 7 category
  colours) above income (Payroll / Rent / Gift in a blue family, to separate the income domain;
  the owner asked for income in the monthly and yearly views on 2026-08-13). No two-month comparison.
- The income domain is a single blue family (Payroll `#1c5cab` / Rent `#5598e7` / Gift `#9ec5f4`),
  set against the multi-colour category palette used for spending so the two domains read apart.
  Both legends isolate on click.
- **Insights / Tasks tab** (the owner, 2026-08-13): three cards — ① Insights, every line computed
  live and never hand-written (largest category share, subscription and AI-tool share, delivery
  share of Dining, peak month, contribution status, budget overrun; ⚠/✓/● at three levels);
  ② Data freshness (each source's data-through date and its age, ⚠ past 30 days); ③ Open tasks
  (the `TASKS` constant — the owner adds and closes them out loud, Claude maintains them on rebuild;
  ○ open / ✓ done, with the date added).
- ~~Transactions page~~ **deleted** (the owner, 2026-09-06: "by category already covers what it did").
  The line-by-line for a month now appears only in the right-hand column of **This month**,
  entered through a category. ⚠ Three things went with it: **the chequing line-by-line**
  (transfers, fees, e-Transfers — the Cash flow page has monthly totals, not individual rows),
  **search by merchant**, and **filter by account**. If they come back, the natural home for
  line-by-line chequing is the Cash flow page.

## 5. Interaction

- Affordances are **shown, not explained**. ("click again to show all" and its relatives were
  explicitly rejected.) Clickability is carried by pill states, hover backgrounds, and
  highlighting or dimming; when an "everything" state is needed, add an All pill.
- Charts have hover tooltips by default (dark bubble, white text). **One fact per line inside the
  bubble too** — break with `<br>`, never string them on `·`. (Eight places were fixed on
  2026-09-06.)
- **Definitions go in a "?"** (the owner, 2026-08-20): a 14px grey circled `?` follows a stat card
  label or a section title; hover or focus shows the definition in a bubble (dark, white text,
  same as the chart tooltip), click toggles it, clicking away or Esc closes it. The definition
  states the measure itself — what is counted, what is not, what the denominator is, which rule
  it belongs to — in **one or two sentences, with numbers where numbers help, never a paragraph**
  (the owner, 2026-08-20: too long). It never explains an interaction; §5's "no explanatory text"
  is about interaction hints, not definitions. The bubble reuses one floating element and is
  clamped to the viewport, so it never leaves the screen.
- Legends isolate a single category on click: the selection is highlighted and the rest dim.

## 5a. Space at the top of the page, and the page header

> the owner, 2026-09-06: "the whole thing sits too high up."

- `body` has **38px** of top margin, 24px sides, 72px bottom; the sidebar is
  `position:sticky; top:38px` to match. Content must never touch the top of the window.
- **Every page has a `.pghead`**, with a 1px rule below it and
  `margin-bottom:20px`:
  - Left: an **eyebrow** (the section it belongs to, 10.5px uppercase grey), the **title at
    25px** (up from 19px), and one 13px line of description.
  - Home's four stat cards answer one question per section — **Invested** (with the band status), **FIRE progress** (on the portfolio, with the on-track year), **This month's transfer** (pay-yourself-first, from the broker's record), **Free to spend** (the allowance today). Net worth is not a card; it is the header line. (2026-09-10)
  - Right (main dashboard only): **Net worth**, always present — what a banking app does. The
    anchor number is visible from any page, and its definition is in the `?`.
  - **The two rules have to line up** (the owner, 2026-09-06: "the two dividing lines not lining up
    looks bad"): the sidebar wordmark and `.pghead` share the CSS variable `--headh:92px`, and
    both blocks are a fixed height with a `border-bottom`, so whichever page you are on, with or
    without an eyebrow, both rules land on the same y. Changing one height means changing the
    variable, not one side of it.
  - The top of the sidebar holds only **LY Finance** (21px, clicks back to Home) and a 23px flat
    gold coin (outer `#c8971a`, inner `#f0c649`, `$` stroked `#a87c11`; no gradients or shadows,
    in keeping with the restrained light style). The old `data through <date>` line was deleted:
    it took the **newest** date across all sources at a moment when three of them were past 30
    days, which reported the best case as the general case — the opposite of its purpose. Data
    freshness belongs to the Data sources page and the amber dots in the sidebar.
- **A number in the page header is not repeated in the page.** The main dashboard's FIRE and
  Portfolio pages each had a Net worth card; both are gone, taking those pages from four stat
  cards to three.
- Under the sidebar title, one line of `data through <newest data date>`, the maximum of every
  source's as-of.
- **Under the net worth in the page header sits one sentence** (2026-09-10): the newest date any
  statement reaches, whether a statement is still owed this year, and how many items are waiting
  to be confirmed — "Numbers as of Sep 6. Two statements are still missing, and three items are
  waiting for you." / "Everything is filed and nothing is waiting." Clicking it opens Updates. It
  replaced a pipeline strip ("Built · 3 checks ✓ · 10/12 sources fresh · 3 decisions") the owner
  rejected: it talked about the tool. Checks never appear on the page — a page whose checks fail
  is not built.

## 5b. How copy is written (the owner, 2026-09-06; outranks existing habit)

> the owner's words: "splitting sentences with dots… is exhausting to read." Rewritten to read the
> way a banking app reads.

- ❌ **Never string facts on `·`.** A line of explanatory text that packs four facts into
  `A · B · C · D` is not written here.
  - The rejected example: `Partial month — statements stop mid-Aug (Visa to 2026-08-19 · MC to
    2026-08-20 · BMO chq to 2026-08-05 · RBC chq to 2026-08-25), so this total is a floor…`
- ✅ `·` is allowed only between **parallel nouns** — a list of account names, a list of tiers —
  never between sentences.
- **One fact per line**: several data points are rendered with `metaList()` as label-left /
  value-right rows (`.meta`), not squeezed into a sentence.
- **Definitions go in the `?`** (`qMark()`), not in the body. The body carries the conclusion.
- **Sentences are written as sentences**, with a subject and a full stop:
  `You are 34.3% of the way to $837,048, on track for Jun 2036.` — not
  `34.3% of $837,048 · base case (5%) Jun 2036`.
- **Warnings use `noteBox()`** (pale yellow with a `!`), not small grey text.
- Avoid jargon in labels. Internal terms like `Dry powder` stay, but get a plain sentence or a
  `?` beside them. `net of refunds` → `after refunds`; `CAD side` → `Canadian side`.

**The page talks about your money, never about itself** (the owner, 2026-09-10: "the UI language
has too much AI in it — make it user-oriented"). Lint **S8** scans the page code, not the owner's
own prose in the data:

1. **No first person.** The page never says "I": `Newest I have` → `Last received`;
   `Due, but I never got it` → `Due, not filed yet`.
2. **Conclusions and actions, not provenance.** How a number was made goes in the `?` or on
   Updates, never in a card: `Worked out from your data, not written by hand` was deleted.
3. **No rule numbers, file names, constant names or account IDs on screen.** A rule is called by
   what it means (`set aside`, not `rule 2`); an account by its name in `accounts.json`.
4. **A status is a status; a report is a report.** A rule on the Investing page is one line
   computed today, ✓ or how far off. What an update noticed lives on Updates.
5. **A warning ends with what you can do.** `Not filed yet — the Sep 5 statement is ready to
   download.`
6. **Numbers about your money, not the pipeline.** Never `10 of 12 sources fresh`; instead
   `BMO chequing and savings are older than a month`.
7. **No lecturing.** No `worth knowing`, no `read this as`, no `that is X, not Y`. Your own
   principle may be shown, in one sentence, marked as yours.

The prose fields of `imports.json`, `decisions.json`, `plan.json` and `rules.json` reach the page
too and are written by the import to the same rules (update-dashboard, Step 7).

## 5c. The filing grid (the owner, 2026-09-06 — the paper-planner look)

- The first card on the Data sources page is **Filed each month**: one row per source going down,
  twelve months going across, a mark when it has been filed.
- Three marks, with their meanings in the `metaList` below rather than beside the cells:
  - **Filled black dot** = filed for that month
  - **Hollow amber ring** = due, and never arrived
  - **Small grey dot** = not owed yet — the account did not exist that month (the `from` field),
    or that source's statement has not closed
- **"Due" is judged by each source's own closing day**, not by the calendar month: BMO on the
  5th, Visa the 19th, MC the 20th, RBC the 25th; exports with no statement use the import day
  `IMPORT_DAY` (the 26th, changed 2026-09-08). The current month can only show as missing after
  its closing day has passed — otherwise it cries wolf daily.
- The current month's column has a deeper background (`td.now`), and the year is switched with
  pills whose years are derived from the `SUBMITTED` data rather than written down.
- The right-hand "Months in" column gives the count filed, appending an amber "missing N" only
  when something is missing.

## 5d. Hard constraints from the 2026-09-06 UI review

Set after measuring every page at the owner's request. All of them were real problems found that day:

- **Contrast**: `--muted` went from `#898781` (3.50:1 on a card, below AA) to **`#75736d`
  (4.62:1)**. It carries the 10.5–11.5px `.lab` / `.cap` text, and small type plus low contrast
  is two disadvantages at once. Recompute the contrast whenever a grey is changed.
- **Line width**: long body containers are capped. `.alert-row > span:last-child` is **880px** —
  a single Rule status line on Portfolio had been 242 characters across 1252px, 2.7× the
  comfortable reading limit. `.meta` 720 / `.say` 820 / `.note-box` 900 / `.pgsub` 620.
- **A card must not be drawn outside its content**: when a page holds a single capped `.meta`,
  the card gets `.tight` (780px). The Baseline page had a 1306px card wrapped around 720px of
  content, leaving 586px of white on the right — it looked like it had not finished loading.
- **Stat cards use flex, not grid auto-fit**: `repeat(auto-fit,minmax(190px,340px))` lays tracks
  at 340, so four cards in 1306px fit three and wrap the fourth. Use `display:flex` with
  `flex:1 1 190px; max-width:340px`.
- **Every page has to fill a screen**: six pages held under 520px of content at the review
  (Insights 210, Tasks 217, Baseline 293). the owner's direction was **add content, do not merge
  pages**. What gets added must answer a question the page already raises, not pad it:
  - Baseline → a 12-month bar chart, the three months in the median highlighted, the median as a
    red dashed line (answering "why is the baseline $1,290 when June was $2,534")
  - ~~Budget → a 6-month history table~~ **dropped** (the owner, 2026-09-07). The Monthly plan page
    now has three cards and fills a screen on Free to spend + Where each month goes + Your two
    funds (measured at 1,200px+); it does not need a history table for height.
  - Tasks → open and done split into two cards, plus three stat cards
  - Insights / Subscriptions / Foreign → a row of stat cards each

## 5e. Motion (the owner agreed to it 2026-09-06 — two things only)

- **A 120ms fade and 4px rise on page change**, `ease-out`. Switching hard between 16 pages makes
  the eye hunt for its place; a very short entrance makes the change perceptible without having
  to read the title to confirm it.
- **Pure CSS, no JavaScript**:
  `section[data-pg]:not([hidden]){animation:pageIn .12s ease-out}`. Toggling `hidden` takes the
  element through `display:none → block`, so the animation replays by itself. **This part
  matters**: triggering it by adding a class in JS would replay it on every month switch and
  every slider drag as well.
  - Measured: page change fires it once; **switching months, 0; dragging the Coast slider, 0.**
    That chart redraws on every frame while dragging, and an animation bound to "redraw" would
    be a nightmare.
- **`prefers-reduced-motion: reduce` turns motion off globally.** This is an accessibility floor,
  not an option. Note that lint rule L2 only forbids **width-based** `@media`; this one is not on
  that list.
- **Explicitly not doing**: counting-up numbers (a financial figure that rolls makes you read the
  false values on the way), donuts that spin in (unreadable while spinning), any looping
  animation (a distraction on a page you sit and stare at), and anything over 500ms (by the
  second viewing you are waiting for it).
- **The test**: good motion is **expressing a change**, not **performing an entrance**. The Coast
  curve responding live to the slider is the first kind — it lets you feel the relationship
  between when you stop contributing and where you end up, which a static chart cannot give you.

## 5f. Accumulating years (the owner agreed 2026-09-07, asked: "structurally, what happens once this
has years of data in it?")

State the premise first: **file size is not the constraint.** Measured, a ledger row is about 137
bytes and spending runs about 250 rows a year ≈ 35KB a year; ten years is 500–600KB and the
self-contained HTML still opens instantly. So **do not** split files, shard `findata/`, or move
data out of the HTML because "there is more data" — that solves a problem that does not exist.
What actually breaks is **how much fits on one screen**.

- **① The month axis must be bounded.** Any chart drawn by month, any selector listing months,
  gets an array that is either **filtered by year** (`MONTHS_IN(viewYear)`) or a **tail window**
  (`.slice(-N)`). Iterating `MONTHS` directly is never allowed.
  - The shape is **year as container, month as cursor**: one row of year pills, always twelve
    month pills (the empty ones `disabled`). The filing grid `renderTracker()` has been that
    shape from the start; everywhere else copies it.
  - Measured on a copy with three years of data (2026-09-07): before, the month pills were **24
    of them, two rows, 55px** — ten years would be ten rows. After, a constant **12, one row,
    25px**.
  - ⚠ This rule is not precautionary. `renderYear()` **was not reading the year selector at
    all**: choosing 2026 drew all 24 months and 114 bars, invisible only because there was one
    year of data. **This class of bug all surfaces at once on New Year's Day**, and the rule
    exists so there is not a next one.
  - The same trap: `ymLabel()` appends a short year of its own for a month outside the current
    year (`Jun ’25`), so **do not append the year again**. Use `ymFull()` when you want the full
    "Jun 2026". Eighteen places had this wrong, rendering `Aug ’24 2024` on three years of data.

- **② A rolling statistic must state its window; it may never mean "all of history".** A
  reference value — "typical", a median — takes a **tail window** (currently
  `CAT_WINDOW = 12` closed months) and **states that window in the interface** ("vs the last 5
  closed months"), reporting the real count when there are not enough.
  - Why: ten years on, a median over all of history mixes 2026 prices with 2036 prices. The
    number is still there; its meaning is gone.
  - Putting the window on screen is what stops it **drifting silently** — the same reasoning as
    `covEnd`: a definition has to be visible to be defensible.
  - The two gates compose: `covEnd` first (only months where every card has closed), then the
    last 12 of those.

## 6. Restraint in copy

- **No footer disclaimer**, and no long redundant explanatory sentences (explicitly rejected:
  "hard to read and some of them are redundant").
- Explanatory text appears only where it is needed, within one line, in small grey type.
- **No subtitle under a title** (the owner deleted them 2026-08-14); the source and update date
  appear only in the Data freshness table on Insights/Tasks.

## 7. Principles for presenting data

- **The dashboard shows data from 2026-01-01 onward** (the owner, 2026-08-13); earlier history stays
  in the `findata/` files but does not enter the view.

- Every source is labelled with its own as-of date. Amounts are kept per currency, CAD first,
  and other currencies are never mixed into a total. (That does not have to be stated on the page, but the
  arithmetic has to obey it.)
  **Two exceptions, both explicit conversions carrying their rate**: the header Net worth
  (`NW_GLOBAL`, settled 2026-08-14) and the CAD total at the foot of the Accounts table (settled
  2026-09-08). Adding currencies anywhere else is a bug.
- Refunds and negative amounts are shown as green negatives.
- Restraint in labelling chart values: totals on top of bars, amounts in the legend — never a
  number stacked on every data point.
