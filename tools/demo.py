#!/usr/bin/env python3
"""A whole year of made-up money for the public build.

The tool is only worth showing with data in it, and the real data is the one thing that
cannot be shown. So this file invents a person -- Emma Roy, 31, a project coordinator in
Ottawa, single, renting, paid twice a month -- and writes every findata/ file the tool reads,
internally consistent: every balance chain closes, every card statement adds up, the funds
fit inside the account they are claimed against, the dry-powder band is met, and the number
of holdings is inside the target. check_data.py is the proof; it runs on the output.

Nothing here is copied from a real account. Amounts are typical for a Canadian woman in her
early thirties on a median salary, deliberately unremarkable.

    build(out_dir) -> ctx        writes <out_dir>/findata/* and returns what the release
                                 build needs to splice into the two dashboards
"""
import csv, json, os, random, datetime as dt, math

NOTE_IMPORTS = "One record per 'update dashboards', newest last: the files that came in, what changed (label / from / to), what was noticed (sev ok / warn / bad + text), what was decided without asking (`judged`) and what the owner was asked (`asked`). Data → Updates renders it; the import report IS this record. Every sentence here reaches the page: write it about the owner's money, never about the tool — no 'I', no rule numbers, no file names."
NOTE_DEC = "What is waiting for the owner to confirm, written by the import: a merchant seen for the first time, an e-Transfer typed by default, a transfer whose other side is unknown, a file nobody could name. Each item: `added`, `kind` (merchant / transfer / file / classification), `what` (one sentence, about the money), `default` (what was assumed meanwhile), `source` (which statement, which line), `status` open / confirmed, and once confirmed `answer` and `resolved`. Data → Updates lists the open ones and the page header counts them. Separate from tasks.json: these are produced by an import and disappear on a word; tasks are the owner's own."

from collections import defaultdict, OrderedDict
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 ".claude", "skills", "workspace-checks", "scripts"))
from check_data import merchant_key  # one normalisation, owned by the checker
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 ".claude", "skills", "setup", "scripts"))
from scaffold import default_axes, flow_feeds  # the five axes, owned by setup
import layout  # where each findata file lives (schema 6)

TODAY = "2026-09-08"
FX = 1.3712                      # USD/CAD used everywhere below
SEED = 20260908

P = dict(first="Emma", last="Roy", name="Emma Roy", initials="ER", upper="EMMA ROY",
         city="Ottawa", friend="Sam", friend_upper="SAM DOE",
         pay=1800.00, rent=1250.00, invest=800, everyday=1300, big=300, take_home=2350)

ID = dict(bmo_chq="4471", bmo_sav="9032", bmo_mc="5518", rbc_chq="7740", rbc_esav="7758", rbc_visa="3306",
          tfsa="HQ7TF4A21CAD", rrsp="HQ7RR9B33CAD", fhsa="HQ7FH2C17CAD", nr="HQ7NR6D48CAD",
          hys="HQ7HY3E05CAD", crypto="HQ7CR8F62CAD", chq="WK7CQ1G90CAD")

# ------------------------------------------------------------------ small date helpers
def D(y, m, d): return dt.date(y, m, d)
def iso(d): return d.isoformat()
def ym(d): return d.strftime("%Y-%m")
def month_end(y, m): return D(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)
def stmt_after(d, day):
    """First `day`-of-month on or after d: the statement a transaction lands on."""
    if d.day <= day: return D(d.year, d.month, day)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return D(y, m, day)
def tag(d, day): return stmt_after(d, day).strftime("%Y%m%d")
def months(a, b):
    y, m = a
    while (y, m) <= b:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
def r2(x): return float(f"{x:.2f}")

# ------------------------------------------------------------------ spending
SUBS_FIXED = [   # merchant, amount, day, category — the charges that come back every month
 ("SPOTIFY SPOTIFY.COM", 11.29, 4, "Subscription"),
 ("NETFLIX.COM NETFLIX.COM", 18.99, 12, "Subscription"),
 ("APPLE.COM/BILL TORONTO ON", 3.99, 16, "Subscription"),
 ("KOODO MOBILE", 45.20, 10, "Subscription"),
 ("GOODLIFE FITNESS TORONTO ON", 32.99, 1, "Subscription"),
 ("AMAZON PRIME MEMBER AMAZON.CA", 10.99, 22, "Subscription"),
 ("OC TRANSPO MONTHLY PASS OTTAWA ON", 135.00, 26, "Transport"),
]
VAR = [          # merchant, category, times a month, low, high, may go on the MasterCard
 ("LOBLAWS 1234 OTTAWA ON", "Grocery", 2, 45, 110, False),
 ("FARM BOY #17 OTTAWA ON", "Grocery", 3, 18, 55, True),
 ("COSTCO WHOLESALE W1211 OTTAWA ON", "Grocery", 1, 95, 175, True),
 ("METRO 456 OTTAWA ON", "Grocery", 1, 25, 65, True),
 ("TIM HORTONS #2231 OTTAWA ON", "Dining", 3, 3.5, 9, False),
 ("UBER CANADA/UBEREATS TORONTO ON", "Dining", 2, 22, 48, True),
 ("SUBWAY 40112 OTTAWA ON", "Dining", 1, 11, 16, True),
 ("THAI EXPRESS OTTAWA ON", "Dining", 1, 13, 19, True),
 ("STARBUCKS 1100 OTTAWA ON", "Dining", 1, 5, 8, False),
 ("AMAZON.CA AMAZON.CA", "Shopping", 1, 15, 80, False),
 ("AMZN MKTP CA", "Shopping", 1, 12, 60, True),
 ("SHOPPERS DRUG MART 0781 OTTAWA ON", "Shopping", 2, 8, 45, True),
 ("DOLLARAMA #1052 OTTAWA ON", "Shopping", 1, 4, 18, False),
 ("WINNERS 3215 OTTAWA ON", "Shopping", 0.5, 25, 90, True),
 ("CANADIAN TIRE #030 OTTAWA ON", "Shopping", 0.4, 15, 80, True),
 ("UBER CANADA/UBERTRIP TORONTO ON", "Transport", 1, 12, 28, True),
 ("CINEPLEX 7620 OTTAWA ON", "Entertainment", 0.5, 14, 30, True),
 ("STEAM PURCHASE SEATTLE WA", "Entertainment", 0.3, 10, 40, False),
 ("CANADA POST OTTAWA ON", "Other", 0.3, 5, 20, False),
]
ONE_OFF = [      # date, merchant, amount, category, card
 ("2026-06-14", "BEST BUY #957 OTTAWA ON", 429.99, "Shopping", "V"),     # the one big buy
 ("2026-04-25", "IKEA OTTAWA ON", 186.40, "Shopping", "M"),
 ("2026-07-18", "TICKETMASTER CANADA TORONTO ON", 92.50, "Entertainment", "V"),
]
VISA_DAY, MC_DAY, RBC_DAY, BMO_DAY = 19, 20, 25, 5
VISA_LAST, MC_LAST = "20260819", "20260820"        # newest statements on hand
MC_FROM = D(2026, 4, 21)                            # the MasterCard arrived in April
SPEND_FROM, SPEND_TO = D(2025, 12, 20), D(2026, 8, 20)

def gen_spending(rng):
    rows = []   # dict(date, amount, category, merchant, card, stmt)
    def add(d, merchant, amt, cat, card):
        if card == "V":
            t = tag(d, VISA_DAY)
            if t > VISA_LAST: return
            rows.append(dict(date=d, amount=r2(amt), category=cat, merchant=merchant, acct=f"RBC{ID['rbc_visa']}", stmt=t))
        else:
            t = tag(d, MC_DAY)
            if t > MC_LAST or d < MC_FROM: return
            rows.append(dict(date=d, amount=r2(amt), category=cat, merchant=merchant, acct=f"BMO{ID['bmo_mc']}", stmt=t))
    for y, m in months((2025, 12), (2026, 8)):
        last = month_end(y, m).day
        for merchant, amt, day, cat in SUBS_FIXED:
            d = D(y, m, min(day, last))
            if SPEND_FROM <= d <= SPEND_TO: add(d, merchant, amt, cat, "V")
        for merchant, cat, n, lo, hi, mc_ok in VAR:
            k = int(n) + (1 if rng.random() < n - int(n) else 0)
            for _ in range(k):
                d = D(y, m, rng.randint(1, last))
                if not (SPEND_FROM <= d <= SPEND_TO): continue
                card = "M" if (mc_ok and d >= MC_FROM and rng.random() < 0.55) else "V"
                add(d, merchant, rng.uniform(lo, hi), cat, card)
    for ds, merchant, amt, cat, card in ONE_OFF:
        add(dt.date.fromisoformat(ds), merchant, amt, cat, card)
    rows.sort(key=lambda r: (r["date"], r["merchant"]))
    return rows

# ------------------------------------------------------------------ ledgers
def gen_ledgers(rng, spend):
    """BMO chequing, RBC chequing and BMO savings, with the card statements they pay off."""
    visa_tot = defaultdict(float); mc_tot = defaultdict(float)
    for r in spend:
        (visa_tot if r["acct"].startswith("RBC") else mc_tot)[r["stmt"]] += r["amount"]
    debit_rbc = []      # extra spending rows written by the RBC ledger
    debit_bmo = []
    ev = []             # (date, description, amount, typed desc, type)
    A = ev.append
    for y, m in months((2025, 12), (2026, 9)):
        last = month_end(y, m).day
        if (y, m) > (2025, 12):
            A((D(y, m, 1), "Pre-AuthorizedPayment,OTTAWA PROP MGMT RENT", -P["rent"], "Rent (pre-authorized)", "Rent"))
            A((D(y, m, 2), "Pre-AuthorizedPayment,WSINVESTMENTSINV/PLA", -P["invest"] / 2, "Transfer to Wealthsimple", "Transfer"))
        A((D(y, m, 15), "DirectDeposit,ADP CANADA PAY/PAY", P["pay"], "Payroll deposit (ADP)", "Payroll"))
        A((D(y, m, 17), "Pre-AuthorizedPayment,WSINVESTMENTSINV/PLA", -P["invest"] / 2, "Transfer to Wealthsimple", "Transfer"))
        vt = visa_tot.get(f"{y}{m:02d}{VISA_DAY}", 0.0)
        topup = math.ceil(vt / 10) * 10 if vt else 650.0
        A((D(y, m, 20), f"INTERAC e-Transfer sent {P['upper']}", -float(topup), "e-Transfer to RBC chequing", "Transfer"))
        mt = mc_tot.get(f"{y}{m:02d}{MC_DAY}", 0.0)
        if mt: A((D(y, m, 22), f"OnlineTransfer,TF0005519880045{ID['bmo_mc']}", -r2(mt), "MasterCard payment", "CC payment"))
        A((D(y, m, last), "DirectDeposit,ADP CANADA PAY/PAY", P["pay"], "Payroll deposit (ADP)", "Payroll"))
        A((D(y, m, last), "PerformancePlanFee", -16.95, "Plan fee", "Fee"))
        if (y, m) >= (2026, 5):
            A((D(y, m, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", -500.0, "Transfer to savings", "Transfer"))
    A((D(2026, 3, 3), f"INTERAC e-Transfer sent {P['friend_upper']}", -1500.0, f"e-Transfer to {P['friend']} (loan)", "Friend"))
    A((D(2026, 7, 13), "INTERACe-TransferReceived", 1500.0, f"e-Transfer from {P['friend']} (repayment)", "Friend"))
    # The $200 nobody named: the open item on Data → Updates, typed Other income meanwhile.
    A((D(2026, 8, 11), "INTERACe-TransferReceived", 200.0, "e-Transfer received", "Other"))
    A((D(2026, 3, 25), "Contactless Interac purchase,SHOPPERS DRUG MART 0781", -24.60, "Debit purchase — Shoppers Drug Mart", "Debit purchase"))
    debit_bmo.append(dict(date=D(2026, 3, 25), amount=24.60, category="Shopping",
                          merchant="SHOPPERS DRUG MART 0781 OTTAWA ON", acct=f"BMO{ID['bmo_chq']}", stmt="20260405", debit=True))
    ev = [e for e in ev if D(2025, 12, 6) <= e[0] <= D(2026, 9, 5)]     # through the Sep 5 statement
    ev.sort(key=lambda e: e[0])
    bal = 2140.55
    bmo = []
    for d, desc, amt, tdesc, typ in ev:
        bal = r2(bal + amt)
        bmo.append(dict(date=d, description=desc, amount=r2(amt), balance=bal,
                        statement=f"BMOCHQ{ID['bmo_chq']}/{tag(d, BMO_DAY)}", tdesc=tdesc, type=typ))
    assert min(r["balance"] for r in bmo) > 0, "BMO chequing went negative"

    # RBC Day to Day: the Visa is paid from here, fed by the e-Transfer from BMO.
    ev = []; A = ev.append
    for y, m in months((2026, 1), (2026, 8)):
        vt = visa_tot.get(f"{y}{m:02d}{VISA_DAY}", 0.0)
        topup = math.ceil(vt / 10) * 10 if vt else 650.0
        A((D(y, m, 20), f"e-Transfer received {P['upper']}", float(topup), "e-Transfer from BMO chequing", "Transfer"))
        if vt: A((D(y, m, 22), f"RBC VISA {ID['rbc_visa']} autopay", -r2(vt), "Visa autopay", "CC payment"))
        A((D(y, m, 25), "Monthly fee", -4.0, "Monthly fee", "Fee"))
        for _ in range(2):
            d = D(y, m, rng.randint(1, 24))
            if rng.random() < 0.5:
                merchant, amt, cat, short = "TIM HORTONS #2231 OTTAWA ON", r2(rng.uniform(4.25, 6.8)), "Dining", "TIM HORTONS #2231"
            else:
                merchant, amt, cat, short = "FARM BOY #17 OTTAWA ON", r2(rng.uniform(8, 22)), "Grocery", "FARM BOY #17"
            A((d, f"Contactless Interac purchase - {ID['rbc_chq']} {short}", -amt, f"Debit purchase — {short.title()}", "Debit purchase"))
            debit_rbc.append(dict(date=d, amount=amt, category=cat, merchant=merchant,
                                  acct=f"RBC{ID['rbc_chq']}", stmt=tag(d, RBC_DAY), debit=True))
    ev.sort(key=lambda e: e[0])
    bal = 412.30
    rbc = []
    for d, desc, amt, tdesc, typ in ev:
        bal = r2(bal + amt)
        rbc.append(dict(date=d, description=desc, amount=r2(amt), balance=bal,
                        statement=f"RBCCHQ{ID['rbc_chq']}/{tag(d, RBC_DAY)}", tdesc=tdesc, type=typ))
    assert min(r["balance"] for r in rbc) > 0, "RBC chequing went negative"

    sav_ev = [(D(2026, 5, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", 500.0, "Transfer from chequing", "Transfer"),
              (D(2026, 5, 31), "InterestEarned", 0.29, "Interest", "Interest"),
              (D(2026, 6, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", 500.0, "Transfer from chequing", "Transfer"),
              (D(2026, 6, 30), "InterestEarned", 0.71, "Interest", "Interest"),
              (D(2026, 7, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", 500.0, "Transfer from chequing", "Transfer"),
              (D(2026, 7, 31), "InterestEarned", 1.10, "Interest", "Interest"),
              (D(2026, 8, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", 500.0, "Transfer from chequing", "Transfer"),
              (D(2026, 8, 31), "InterestEarned", 1.52, "Interest", "Interest"),
              (D(2026, 9, 5), f"OnlineTransfer,TF0006#{ID['bmo_chq']}-{ID['bmo_sav']}", 500.0, "Transfer from chequing", "Transfer")]
    bal = 0.0; sav = []
    for d, desc, amt, tdesc, typ in sav_ev:
        bal = r2(bal + amt)
        sav.append(dict(date=d, description=desc, amount=r2(amt), balance=bal,
                        statement=f"BMOSAV{ID['bmo_sav']}/{tag(d, BMO_DAY)}", tdesc=tdesc, type=typ))
    return bmo, rbc, sav, debit_bmo + debit_rbc, visa_tot, mc_tot

# ------------------------------------------------------------------ holdings
PRICE = {"VEQT": 46.10, "VSC": 24.05, "SGOV": 100.42, "XAW": 44.80, "VCN": 52.30,
         "SHOP": 112.40, "BN": 80.15, "ZAG": 14.20, "BTC": 110388.19}
USD_SYMS = {"SGOV"}
NAME = {"VEQT": "Vanguard All-Equity ETF Portfolio - ETF",
        "VSC": "Vanguard Investments Canada Inc. - Canadian Short-term Corporate Bond Index ETF",
        "SGOV": "iShares Trust - iShares 0-3 Month Treasury Bond ETF",
        "XAW": "iShares Core MSCI All Country World ex Canada Index ETF",
        "VCN": "Vanguard FTSE Canada All Cap Index ETF",
        "SHOP": "Shopify Inc.", "BN": "Brookfield Corp.",
        "ZAG": "BMO Aggregate Bond Index ETF", "BTC": "Bitcoin", "CAD": "CAD"}
SEC = {"SHOP": "EQUITY", "BN": "EQUITY", "BTC": "CRYPTOCURRENCY", "CAD": "CURRENCY"}
ACCTS = [("TFSA", "tfsa"), ("RRSP", "rrsp"), ("FHSA", "fhsa"), ("Non-registered", "nr"),
         ("High-yield savings", "hys"), ("Crypto", "crypto")]
# account, symbol, target CAD market value, book value as a ratio of market value
TARGETS = [
 ("TFSA", "VEQT", 22400, 1/1.18), ("TFSA", "VSC", 8100, 1.01), ("TFSA", "SHOP", 2300, 1/1.25), ("TFSA", "CAD", 310, 1),
 ("RRSP", "VEQT", 6900, 1/1.18), ("RRSP", "SGOV", 4200, 1.005), ("RRSP", "BN", 1150, 1/1.15), ("RRSP", "CAD", 85, 1),
 ("FHSA", "VCN", 9800, 1/1.09), ("FHSA", "VSC", 3900, 1.01),
 ("Non-registered", "SGOV", 12600, 1.005), ("Non-registered", "VSC", 4050, 1.01), ("Non-registered", "XAW", 3100, 1/1.12),
 ("Non-registered", "ZAG", 1400, 1.02), ("Non-registered", "CAD", 190, 1),
 ("High-yield savings", "SGOV", 2900, 1.005), ("High-yield savings", "VSC", 6600, 1.01),
 ("Crypto", "BTC", 350, 1/1.10),
]
PORT_ACCTS = {"Non-registered", "TFSA", "RRSP", "Crypto"}
EARM_ACCTS = {"FHSA", "High-yield savings"}

def gen_holdings():
    key = {a: k for a, k in ACCTS}
    pos = []
    for acct, sym, target, ratio in TARGETS:
        aid = ID[key[acct]]
        if sym == "CAD":
            pos.append(dict(acct=acct, aid=aid, sym=sym, qty=float(target), price=1.0, cur="CAD",
                            mv_mkt=float(target), mv_cad=float(target), bv_cad=float(target), bv_mkt=float(target)))
            continue
        price = PRICE[sym]
        if sym in USD_SYMS:
            qty = round(target / FX / price, 4)
            mv_mkt = r2(qty * price); mv_cad = r2(mv_mkt * FX)
            bv_cad = r2(mv_cad * ratio); bv_mkt = r2(bv_cad / FX); cur = "USD"
        else:
            qty = round(target / price, 8 if sym == "BTC" else 4)
            mv_mkt = r2(qty * price); mv_cad = mv_mkt
            bv_cad = r2(mv_cad * ratio); bv_mkt = bv_cad; cur = "CAD"
        pos.append(dict(acct=acct, aid=aid, sym=sym, qty=qty, price=price, cur=cur,
                        mv_mkt=mv_mkt, mv_cad=mv_cad, bv_cad=bv_cad, bv_mkt=bv_mkt))
    return pos

HOLD_HEADER = ["Account Name", "Account Type", "Account Classification", "Account Number", "Symbol", "Exchange", "MIC",
               "Name", "Security Type", "Quantity", "Position Direction", "Market Price", "Market Price Currency",
               "Book Value (CAD)", "Book Value Currency (CAD)", "Book Value (Market)", "Book Value Currency (Market)",
               "Market Value", "Market Value Currency", "Market Unrealized Returns", "Market Unrealized Returns Currency"]

# ------------------------------------------------------------------ Wealthsimple activities
ACT_HEADER = ["effective_date", "effective_time", "settlement_date", "account_id", "account_type", "activity_type",
              "activity_sub_type", "description", "direction", "symbol", "underlying symbol", "name", "currency",
              "quantity", "unit_price", "commission", "net_cash_amount"]

def gen_activities(rng, pos):
    rows = []
    def act(d, aid, atype, kind, sub, desc, cur, amt, sym="", name="", qty="", price=""):
        rows.append([iso(d), f"{rng.randint(9,16):02d}:{rng.randint(0,59):02d}:{rng.randint(0,59):02d}", "", aid, atype, kind, sub,
                     desc, "", sym, "", name, cur, qty, price, "", f"{amt:.2f}"])
    mv = defaultdict(float)
    for p in pos: mv[(p["acct"], p["sym"])] += p["mv_cad"]
    for y, m in months((2026, 1), (2026, 9)):
        last = month_end(y, m).day
        for day in (2, 17):
            d = D(y, m, day)
            if d > dt.date.fromisoformat(TODAY): continue
            act(d, ID["chq"], "Chequing", "MoneyMovement", "EFT", "Deposit", "CAD", P["invest"] / 2)
        if (y, m) < (2026, 9):
            d = D(y, m, 18)
            act(d, ID["chq"], "Chequing", "MoneyMovement", "TRANSFER", f"Money transfer out of the account (executed at {iso(d)})", "CAD", -P["invest"])
            act(d, ID["tfsa"], "TFSA", "MoneyMovement", "TRANSFER_TF", f"Money transfer into the account (executed at {iso(d)})", "CAD", P["invest"])
            d = D(y, m, 19); q = round(P["invest"] / PRICE["VEQT"], 4)
            act(d, ID["tfsa"], "TFSA", "Trade", "BUY", f"VEQT - {NAME['VEQT']}: Bought {q} shares at ${PRICE['VEQT']} per share (executed at {iso(d)})",
                "CAD", -P["invest"], "VEQT", NAME["VEQT"], q, PRICE["VEQT"])
            act(D(y, m, 1), ID["chq"], "Chequing", "Interest", "-", f"Interest received (executed at {iso(D(y,m,1))})", "CAD", r2(0.4 + rng.random() * 0.3))
            # SGOV pays monthly in USD; 15% is withheld outside the RRSP
            for acct, aid, wh in (("Non-registered", ID["nr"], True), ("RRSP", ID["rrsp"], False), ("High-yield savings", ID["hys"], True)):
                usd = mv[(acct, "SGOV")] / FX * 0.042 / 12
                if usd:
                    d = D(y, m, 3)
                    act(d, aid, acct, "Dividend", "-", f"SGOV - {NAME['SGOV']}: Cash dividend distribution", "USD", r2(usd), "SGOV", NAME["SGOV"])
                    if wh: act(d, aid, acct, "Tax", "NRT", f"Non-resident tax (executed at {iso(d)})", "USD", -r2(usd * 0.15))
            for acct, aid in (("TFSA", ID["tfsa"]), ("Non-registered", ID["nr"]), ("FHSA", ID["fhsa"]), ("High-yield savings", ID["hys"])):
                cad = mv[(acct, "VSC")] * 0.036 / 12
                if cad: act(D(y, m, 8), aid, acct, "Dividend", "-", f"VSC - {NAME['VSC']}: Cash dividend distribution", "CAD", r2(cad), "VSC", NAME["VSC"])
            if m in (1, 4, 7):
                for acct, aid in (("TFSA", ID["tfsa"]), ("RRSP", ID["rrsp"])):
                    act(D(y, m, 12), aid, acct, "Dividend", "-", f"VEQT - {NAME['VEQT']}: Cash dividend distribution", "CAD",
                        r2(mv[(acct, "VEQT")] * 0.019 / 4), "VEQT", NAME["VEQT"])
            act(D(y, m, last), ID["tfsa"], "TFSA", "Interest", "-", "Stock lending monthly interest payment", "CAD", r2(0.02 + rng.random() * 0.05))
    d = D(2026, 6, 25)
    act(d, ID["nr"], "Non-registered", "Dividend", "-", f"XAW - {NAME['XAW']}: Cash dividend distribution", "CAD", r2(mv[("Non-registered", "XAW")] * 0.017 / 2), "XAW", NAME["XAW"])
    for ds, fx in (("2026-06-10", 1.3690), ("2026-07-15", 1.3655), ("2026-09-04", FX)):
        d = dt.date.fromisoformat(ds)
        act(d, ID["crypto"], "Crypto", "Trade", "BUY", f"Purchase of 0.00040000 BTC (executed at {ds}), FX Rate: {fx:.4f}", "CAD", -50.0, "BTC", "Bitcoin", 0.0004, "")
    d = D(2026, 8, 12)
    act(d, ID["tfsa"], "TFSA", "Trade", "BUY", f"SHOP - Shopify Inc.: Bought 20.4626 shares at $112.40 per share (executed at {iso(d)})", "CAD", -2300.0, "SHOP", "Shopify Inc.", 20.4626, 112.40)
    rows.sort(key=lambda r: r[0])
    return rows

# ------------------------------------------------------------------ everything
def build(out):
    """Write the demo owner's whole findata/ (and OWNER.md). The dashboards are then built from
    templates/dashboards/ by rebuild.py, like any other workspace -- this script writes data
    only, never a line of page code."""
    rng = random.Random(SEED)
    layout.ensure(out)
    W = lambda name: open(layout.path(out, name), "w", encoding="utf-8", newline="")
    J = lambda name, obj: open(layout.path(out, name), "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    spend = gen_spending(rng)
    bmo, rbc, sav, debits, visa_tot, mc_tot = gen_ledgers(rng, spend)
    allspend = sorted(spend + debits, key=lambda r: (r["date"], r["merchant"]))

    # spending.csv + merchants.json
    with W("spending.csv") as f:
        w = csv.writer(f); w.writerow(["date", "amount", "currency", "category", "note"])
        for r in allspend:
            note = f"{r['merchant']}{' (debit)' if r.get('debit') else ''} [{r['acct']}/{r['stmt']}]"
            w.writerow([iso(r["date"]), f"{r['amount']:.2f}", "CAD", r["category"], note])
    # Keyed the way check_data's D6 looks a merchant up (order ids and city dropped), so the
    # demo passes the same lookup a real import does. Until 2026-09-10 the raw string was
    # written and D6 reported every merchant in the demo as undecided.
    seen = OrderedDict()
    for r in allspend:
        mk = merchant_key(r["merchant"])
        m = seen.setdefault(mk, dict(match=mk, category=r["category"], seen=0, first=iso(r["date"]), last=iso(r["date"])))
        m["seen"] += 1; m["first"] = min(m["first"], iso(r["date"])); m["last"] = max(m["last"], iso(r["date"]))
    J("merchants.json", OrderedDict([
        ("note", "Merchant -> spending category, the only place a category is decided. Look a new statement's merchants up here first; reuse a hit, judge only a miss, and append the miss."),
        ("why", "A merchant string is an abbreviation, not a sentence: a shop with PUBLICATION in its name sold a notebook, not a subscription."),
        ("rules", ["Subscription means the charge repeats. A brand seen once is never a Subscription; file it as Shopping or Other and mark it to confirm.",
                   "An entry with confirmed_by is not re-judged; changing it needs the owner and a new confirmed_on.",
                   "Every merchant seen for the first time goes on the report for the owner to confirm."]),
        ("merchants", sorted(seen.values(), key=lambda x: x["match"]))]))

    # The ledgers carry their classification: `type` is what the page shows, `label` overrides
    # the bank's description when it is not readable. A repayment is typed for what it is.
    for name, rows in (("chequing.csv", bmo), ("rbc_chequing.csv", rbc), ("bmo_savings.csv", sav)):
        with W(name) as f:
            w = csv.writer(f); w.writerow(["date", "description", "amount", "balance", "statement", "type", "label"])
            for r in rows:
                t = "Repayment" if r["type"] == "Friend" else r["type"]
                w.writerow([iso(r["date"]), r["description"], f"{r['amount']:.2f}", f"{r['balance']:.2f}", r["statement"],
                            t, r["tdesc"] if r["tdesc"] != r["description"] else ""])

    pos = gen_holdings()
    with W("holdings_latest.csv") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL); w.writerow(HOLD_HEADER)
        for p in pos:
            w.writerow([p["acct"], p["acct"], "Trade", p["aid"], p["sym"], "", "", NAME[p["sym"]], SEC.get(p["sym"], "ETF"),
                        f"{p['qty']}", "LONG", f"{p['price']}", p["cur"], f"{p['bv_cad']:.2f}", "CAD", f"{p['bv_mkt']:.2f}", p["cur"],
                        f"{p['mv_mkt']:.2f}", p["cur"], f"{p['mv_mkt'] - p['bv_mkt']:.2f}", p["cur"]])
    acts = gen_activities(rng, pos)
    with W("ws_activities.csv") as f:
        w = csv.writer(f); w.writerow(ACT_HEADER); w.writerows(acts)

    # balances
    by_acct = defaultdict(float)
    for p in pos: by_acct[p["acct"]] += p["mv_cad"]
    bmo_bal, sav_bal, rbc_bal = bmo[-1]["balance"], sav[-1]["balance"], rbc[-1]["balance"]
    esav_bal, wschq_bal = 5000.00, 620.00
    mc_bal, visa_bal = r2(mc_tot[MC_LAST]), r2(visa_tot[VISA_LAST])
    banks = OrderedDict([
        ("asof_note", "Balance and statement date per bank account. Replace the number and move the date on each import."),
        ("assets", [
            dict(inst="BMO", account="Primary Chequing", balance=bmo_bal, currency="CAD", asof="2026-09-05"),
            dict(inst="BMO", account="Savings Amplifier", balance=sav_bal, currency="CAD", asof="2026-09-05",
                 note="Opened 2026-05-05 with $500 a month from chequing. Its statement arrives in the same batch as chequing, with a -2 suffix."),
            dict(inst="RBC", account="High Interest eSavings", balance=esav_bal, currency="CAD", asof="2026-08-25", note="The emergency fund. Balance only, no ledger."),
            dict(inst="RBC", account="Day to Day Banking", balance=rbc_bal, currency="CAD", asof="2026-08-25",
                 flag="Fed by an e-Transfer from BMO on the 20th; the Visa autopay comes out on the 22nd."),
            dict(inst="Wealthsimple", account="Chequing", balance=wschq_bal, currency="CAD", asof="2026-09-08",
                 note=f"Account {ID['chq']}. The doorway account: the two monthly transfers land here first (WSDEP counts only this account's EFTs). Read in the app; the holdings export has no cash accounts."),
        ]),
        ("debts", [
            dict(inst="BMO", account="MasterCard", balance=mc_bal, currency="CAD", asof="2026-08-20", limit=5000),
            dict(inst="RBC", account="Cash Back Visa", balance=visa_bal, currency="CAD", asof="2026-08-19", limit=3000, autopay=True),
        ]),
        ("classification", "Bank cash is earmarked as the day-to-day buffer; it is never dry powder."),
    ])
    J("banks.json", banks)

    cash = r2(bmo_bal + sav_bal + esav_bal + rbc_bal + wschq_bal)
    debt = r2(mc_bal + visa_bal)
    invested = sum(v for k, v in by_acct.items() if k in PORT_ACCTS)
    earm = sum(v for k, v in by_acct.items() if k in EARM_ACCTS)
    R_inv, R_earm, R_cash, R_debt = round(invested), round(earm), round(cash), round(debt)
    net_worth = R_inv + R_earm + R_cash - R_debt
    dry = sum(p["mv_cad"] for p in pos if p["acct"] in PORT_ACCTS and p["sym"] in ("SGOV", "VSC"))
    dry_pct = round(dry / invested * 1000) / 10
    tickers = sorted({p["sym"] for p in pos if p["acct"] in PORT_ACCTS and p["sym"] != "CAD"})
    usd_exp = sum(p["mv_cad"] for p in pos if p["acct"] in PORT_ACCTS and p["cur"] == "USD")
    assert 40 <= dry_pct <= 45, dry_pct
    assert len(tickers) <= 10, tickers
    hys_bal = round(by_acct["High-yield savings"])

    # accounts.json -- the register
    def acc(inst, id_, name, kind, cur, balance, asof, src, ledger, feeds, key, **extra):
        # `feeds` is written the old way (with the net-worth words) and split here: the words
        # become the five axes, and only the flow words stay in feeds — schema 4.
        d = OrderedDict(inst=inst, id=id_, name=name, kind=kind, cur=cur, balance=balance, asof=asof, src=src)
        d.update(default_axes(dict(kind=kind, src=src, feeds=feeds)))
        d.update(ledger=ledger, feeds=flow_feeds(feeds), key=key)
        d.update(extra); return d
    accounts = [
        acc("BMO", f"…{ID['bmo_chq']}", "Primary Chequing", "Chequing", "CAD", bmo_bal, "2026-09-05", "banks.json", "chequing.csv", "Income, Cash flow, Bank cash", "bmo-chq-4471",
            spendTag=f"BMO{ID['bmo_chq']}", stmtTag=f"BMOCHQ{ID['bmo_chq']}", stmtLabel="BMO chq"),
        acc("BMO", f"…{ID['bmo_sav']}", "Savings Amplifier", "Savings", "CAD", sav_bal, "2026-09-05", "banks.json", "bmo_savings.csv", "Cash flow, Bank cash", "bmo-sav-9032", stmtTag=f"BMOSAV{ID['bmo_sav']}"),
        acc("BMO", f"…{ID['bmo_mc']}", "MasterCard", "Credit card", "CAD", -mc_bal, "2026-08-20", "banks.json", None, "Spending, Debts", "bmo-mc-5518", spendTag=f"BMO{ID['bmo_mc']}", stmtLabel="MC"),
        acc("RBC", f"…{ID['rbc_chq']}", "Day to Day Banking", "Chequing", "CAD", rbc_bal, "2026-08-25", "banks.json", "rbc_chequing.csv", "Cash flow, Spending, Bank cash", "rbc-chq-7740",
            spendTag=f"RBC{ID['rbc_chq']}", stmtTag=f"RBCCHQ{ID['rbc_chq']}", stmtLabel="RBC chq"),
        acc("RBC", f"…{ID['rbc_esav']}", "High Interest eSavings", "Savings", "CAD", esav_bal, "2026-08-25", "banks.json", None, "Bank cash", "rbc-esav-7758", gap="esav-ledger"),
        acc("RBC", f"…{ID['rbc_visa']}", "Cash Back Visa", "Credit card", "CAD", -visa_bal, "2026-08-19", "banks.json", None, "Spending, Debts", "rbc-visa-3306", spendTag=f"RBC{ID['rbc_visa']}", stmtLabel="Visa"),
        acc("Wealthsimple", ID["nr"], "Non-registered", "Non-registered", "CAD", r2(by_acct["Non-registered"]), "2026-09-06", "holdings_latest.csv", None, "Portfolio, Dry powder, Net worth", "ws-nr"),
        acc("Wealthsimple", ID["tfsa"], "TFSA", "TFSA", "CAD", r2(by_acct["TFSA"]), "2026-09-06", "holdings_latest.csv", None, "Portfolio, Dry powder, Net worth", "ws-tfsa"),
        acc("Wealthsimple", ID["hys"], "High-yield savings", "Non-registered", "CAD", r2(by_acct["High-yield savings"]), "2026-09-06", "holdings_latest.csv", None, "Earmarked, Funds backing, Net worth", "ws-hys"),
        acc("Wealthsimple", ID["fhsa"], "FHSA", "FHSA", "CAD", r2(by_acct["FHSA"]), "2026-09-06", "holdings_latest.csv", None, "Earmarked, Net worth", "ws-fhsa"),
        acc("Wealthsimple", ID["rrsp"], "RRSP", "RRSP", "CAD", r2(by_acct["RRSP"]), "2026-09-06", "holdings_latest.csv", None, "Portfolio, Dry powder, Net worth", "ws-rrsp"),
        acc("Wealthsimple", ID["crypto"], "Crypto", "Crypto", "CAD", r2(by_acct["Crypto"]), "2026-09-06", "holdings_latest.csv", None, "Portfolio, Net worth", "ws-crypto"),
        acc("Wealthsimple", ID["chq"], "Chequing", "Chequing", "CAD", wschq_bal, "2026-09-08", "banks.json", None, "Pay-yourself-first doorway, Bank cash", "ws-chq"),
    ]
    def doc(key, ep, file, closes, feeds, covers, tags, into, reconcile, **extra):
        d = OrderedDict(key=key, ep=ep, file=file, closes=closes, feeds=feeds, covers=covers, tags=tags, into=into, reconcile=reconcile)
        d.update(extra); return d
    documents = [
        doc(f"Chequing {ID['bmo_chq']}", "BMO", "<Month D, YYYY>.pdf", "5th", "Pay, transfers, cash flow", ["bmo-chq-4471"], ["BMO_CHQ4471"], "chequing.csv", "opening + in - out = closing", parser="bmo_banking"),
        doc(f"Savings {ID['bmo_sav']}", "BMO", "<Month D, YYYY>-2.pdf", "5th", "Balance and savings ledger", ["bmo-sav-9032"], ["BMO_SAV9032"], "bmo_savings.csv", "balance chain closes", parser="bmo_banking", **{"from": "2026-05"}),
        doc(f"MasterCard {ID['bmo_mc']}", "BMO", "<Month D, YYYY>.pdf", "20th", "Spending, plan, baseline", ["bmo-mc-5518"], ["BMO_MC5518"], "spending.csv", "parsed total = Purchases and other charges + interest + Fees", parser="bmo_mastercard", **{"from": "2026-05"}),
        doc(f"Day to Day {ID['rbc_chq']}", "RBC", f"Chequing Statement-{ID['rbc_chq']} <date>.pdf", "25th", "Cash flow, debit spending", ["rbc-chq-7740"], ["RBC_CHQ7740"], "rbc_chequing.csv", "balance chain closes", parser="rbc_banking"),
        doc(f"eSavings {ID['rbc_esav']}", "RBC", f"Savings Statement-{ID['rbc_esav']} <date>.pdf", "25th", "Balance", ["rbc-esav-7758"], ["RBC_eSAV7758"], "banks.json", "balance and as-of only", parser="rbc_banking"),
        doc(f"Cash Back Visa {ID['rbc_visa']}", "RBC", f"Visa Statement-{ID['rbc_visa']} <date>.pdf", "19th", "Spending, plan, baseline", ["rbc-visa-3306"], ["Visa_Statement3306"], "spending.csv", "parsed total = Purchases & debits + Fees", parser="rbc_visa"),
        doc("Holdings", "Wealthsimple", "holdings-report-<date>.csv", "any time", "Portfolio, dry powder, net worth", ["ws-nr", "ws-tfsa", "ws-hys", "ws-fhsa", "ws-rrsp", "ws-crypto"], ["WS_HOLDINGS"], "holdings_latest.csv", "replaced wholesale", **{"from": "2026-06"}),
        doc("Activities", "Wealthsimple", "activities-export-<date>.csv", "any time", "Dividends, trades, deposits, exchange rate", ["ws-nr", "ws-tfsa", "ws-hys", "ws-fhsa", "ws-rrsp", "ws-crypto", "ws-chq"], ["WS"], "ws_activities.csv", "also refresh fx.json from the 'FX Rate:' rows", **{"from": "2026-06"}),
        doc("Friend ledger", "Interac", "friend_ledger.csv", "when it changes", "Who an Interac transfer came from", [], ["FRIEND"], "friend_ledger.csv", "counterparty only; never counted as income", optional=True, counterparty=P["friend"].split()[0]),
    ]
    J("accounts.json", OrderedDict([
        ("asof_note", "The register of every place money sits (`accounts`) and every file dropped each month (`documents`). Balances here are COPIES of banks.json / holdings_latest.csv; check_data D14 re-derives them. Change the source file, not this one."),
        ("accounts", accounts),
        ("gaps", [OrderedDict(k="esav-ledger", sev="warn", what="RBC eSavings has a balance but no ledger",
                              why="The statement is a PDF downloaded for the figure; nothing is reconciled line by line",
                              fix="Decide whether the interest lines are worth a fourth ledger, or keep it balance-only")]),
        ("missing", [OrderedDict(ep="RBC", t=f"Line-by-line for eSavings {ID['rbc_esav']}", d="Balance only — the statement is downloaded for the figure, not parsed")]),
        ("documents", documents),
        ("archive_note", "Processed files are moved to archive/ as YYYYMMDD_<tag>_<original name>; the tag is documents[].tags."),
    ]))

    # funds.json
    hys_label = "Wealthsimple High yield savings (Non-registered)"
    backing = dict(account=ID["hys"], label=hys_label, balance=hys_bal, asof="2026-09-06",
                   holds="SGOV and VSC, not cash — spending it means selling first",
                   note="Rule 2 already treats this account as earmarked, so naming part of it Travel and part of it Big buys changes no other number on the dashboard.")
    J("rules.json", OrderedDict([
        ("note", "Your investing rules, as data. ONE thing is computed: every bucket that carries a `target` is checked against that range, and the Rules page reports the drift. Buckets are matched in order and the one marked catchAll takes whatever is left. `notes` are your own theses, shown with the status you gave them and judged by you; `{mv:SYM}`, `{n:SYM}` and `{split:SYM}` in the text are filled from the holdings. `checkpoints` are dates you promised to look at something again."),
        ("buckets", [
            OrderedDict([("key", "dry"), ("name", "Safe end · dry powder"), ("symbols", ["SGOV", "VSC"]), ("target", [40, 45])]),
            OrderedDict([("key", "core"), ("name", "Core index"), ("symbols", ["VEQT", "XAW", "VCN"])]),
            OrderedDict([("key", "sat"), ("name", "High-conviction satellites"), ("symbols", ["SHOP", "BN"])]),
            OrderedDict([("key", "mid"), ("name", "Middle tier · cleanup candidates"), ("catchAll", True)]),
        ]),
        ("maxHoldings", 10),
        ("notes", [
            OrderedDict(status="ok", name="Account placement", text="Growth names in the TFSA: SHOP {mv:SHOP} is TFSA-only since the August consolidation ✓. BN {mv:BN} sits in the RRSP. The one bond ETF outside the dry-powder pair (ZAG {mv:ZAG}) stays non-registered — small enough not to matter."),
            OrderedDict(status="info", name="SHOP — thesis check each quarter", text="Held for merchant growth and take-rate expansion. Review on Q3 results in late October; GMV growth under +20% is the exit trigger."),
            OrderedDict(status="info", name="BN — 3–5 year structural position", text="{mv:BN} in the RRSP. Checkpoint: investor day and Q3 distributable earnings."),
            OrderedDict(status="ok", name="Options — ≤28 DTE, named catalyst, ≤5 open", text="No option positions in this export ✓."),
        ]),
        ("checkpoints", [
            OrderedDict(title="BN investor day", date="2026-09-24", label="Sep 24", why="Distributable earnings and the buyback pace — the reasons the position exists"),
            OrderedDict(title="SHOP Q3 results", date="2026-10-29", label="Late October", why="GMV growth under +20% is the exit trigger; otherwise hold"),
            OrderedDict(title="RRSP deadline", date="2027-03-01", label="Mar 1, 2027", why="Top up the RRSP before the deadline once the TFSA room is used"),
        ]),
    ]))
    J("funds.json", OrderedDict([
        ("asof_note", "The guilt-free plan: pay-yourself-first, one everyday allowance, two named funds. The dashboard's FUNDS constant is a copy of this file (check_data D13). Fields that render on the page are English."),
        ("plan", OrderedDict(start="2026-08",
            # Schema 5: flows. Take-home is the whole paycheque; rent is a committed flow the
            # ledger shows on the 1st (D21 looks for it), and it stays after FIRE.
            flows=[
                OrderedDict(key="pay", kind="income", name="Take-home pay", amount=int(P["pay"] * 2),
                            note=f"Payroll of ${P['pay']:,.0f} twice a month. Investment income stays with the broker and is not counted."),
                OrderedDict(key="rent", kind="committed", name="Rent", amount=int(P["rent"]), afterFire="keep",
                            note="Pre-authorized on the 1st, from chequing. Still there after FIRE."),
                OrderedDict(key="invest", kind="saving", name="Invest", amount=P["invest"], to="broker",
                            note="Off the top, before anything else — pay-yourself-first."),
                OrderedDict(key="everyday", kind="allowance", name="Everyday allowance", amount=P["everyday"],
                            note="The guilt-free line. No categories and no caps below it."),
                # A fund's standing contribution is a saving flow that names the fund (schema 8).
                OrderedDict(key="bigbuy-in", kind="saving", name="Big buys", amount=P["take_home"] - P["invest"] - P["everyday"], to="bigbuy",
                            note=f"${P['take_home']:,} after rent, less ${P['invest']:,} to the broker and ${P['everyday']:,} of allowance. This is everything the paycheque actually has left."),
            ],
            bigThreshold=P["big"], leftoverGoesTo="travel",
            bigThresholdNote="A single transaction at or over this is a big buy: kept out of the allowance and paid from the Big buys fund. Subscriptions are excluded whatever they cost.",
            leftoverNote="Each closed month adds (allowance - everyday spending) to the funds, and that figure is signed: an over month takes from Big buys first, then Travel.")),
        ("funds", [
            OrderedDict(key="travel", role="topup", name="Travel", color="#4a3aa7", goal=3000, by="2027-03", why="A week away in March 2027",
                        opening=dict(date="2026-08-01", amount=3000, **{"from": hys_label + " " + ID["hys"]},
                                     note="Not a transfer — a label on money already in that account, so the goal is met on day one and the discipline is leaving it alone."),
                        backing=backing),
            OrderedDict(key="bigbuy", role="big", name="Big buys", color="#eda100", goal=None, why="One-off purchases like a monitor. If the fund covers it, buy it — it never touches the month's allowance",
                        opening=dict(date="2026-08-01", amount=1000, **{"from": hys_label + " " + ID["hys"]},
                                     note="Same account, second label. No new account was opened: a chequing account pays nothing, costs a monthly fee, and would add another statement to import every month."),
                        backing=backing),
        ]),
        ("claimsAgainst", dict(source="Each fund names the account it is claimed against, and the claims have to fit inside that account",
                               note="Neither fund is an account of its own. Both are labels on one savings account.")),
    ]))
    assert 3000 + 1000 <= hys_bal

    J("profile.json", OrderedDict([
        ("note", "Who this workspace belongs to. The FIRST thing to change when you make it yours: "
                 "the name appears in the browser tab and under the Jade Toad wordmark in the sidebar, and it is read from here so it is never typed into the HTML. Jade Toad itself is the product, not a setting."),
        ("schema", 9), ("demo", True), ("owner", P["name"]), ("born", 1995), ("importDay", 26)]))
    J("plan.json", OrderedDict([
        ("note", "Your planning assumptions. `planBase` is the monthly planning spend the FIRE target is built on (× 12 × 25); `skipMonths` are months excluded from every comparison, each with the reason the page shows. `retirement` holds the projection scenarios and the late-life care model; `descriptions` are your own one-liners under the net-worth parts (leave them out and the page describes each part from the register)."),
        ("planBase", int(P["rent"] + P["everyday"])),
        ("skipMonths", OrderedDict([("2025-12", "Only the tail of the first Visa statement — 11 days, not a month")])),
        ("retirement", RETIREMENT_DEFAULTS),
    ]))
    J("foreign.json", OrderedDict([("asof", TODAY), ("currency", None), ("symbol", ""), ("label", "Foreign"),
                                   ("cadPerUnit", 0), ("total", 0),
                                   ("source", "No foreign-currency accounts in this build. The file exists because the tool reads it; an empty list is the supported way to say 'none'."),
                                   ("accounts", []), ("summary", dict(cash=0, invested=0, cash_share_pct=0))]))
    J("fx.json", OrderedDict([("usd_cad", FX), ("asof", "2026-09-04"), ("quality", "broker-rate"),
                              ("source", "Broker activities export 2026-09-06: the 'FX Rate:' rows on the latest date. It is the broker's rate, spread included."),
                              ("todo", "Refresh from every activities export."),
                              ("why_it_matters", f"USD exposure inside the Portfolio is ${usd_exp:,.0f} ({usd_exp/invested*100:.1f}% of the CAD side); 1% on the rate is ±${usd_exp*0.01:,.0f}"),
                              ("history", [])]))
    hist = [dict(date="2026-06-15", cadInv=61204.40, dry=24110.20, dryPct=39.4, tickers=9, foreign=None),
            dict(date="2026-08-05", cadInv=64851.70, dry=27302.10, dryPct=42.1, tickers=8, foreign=None, fx=1.3690),
            dict(date="2026-09-06", cadInv=r2(invested), dry=r2(dry), dryPct=dry_pct, tickers=len(tickers), foreign=None, fx=FX)]
    J("investment_history.json", OrderedDict([("note", "One snapshot per 'update dashboards'. Portfolio = the accounts marked Portfolio in accounts.json; dry / dryPct on the CAD side."), ("snapshots", hist)]))
    J("networth_history.json", OrderedDict([("note", "One net-worth point per month, appended on every 'update dashboards' when the holdings export reaches a new month."),
                                            ("snapshots", [dict(ym="2026-06", v=86910), dict(ym="2026-08", v=96420), dict(ym="2026-09", v=net_worth)])]))

    with W("friend_ledger.csv") as f:
        w = csv.writer(f); w.writerow(["date", "time", "direction", "currency", "amount", "channel", "counterparty", "status", "counted", "note", "txn_id"])
        w.writerow(["2026-03-03", "18:42:10", "out", "CAD", "1500.00", "Interac", P["friend"], "accepted", "yes", "loan, to be repaid in the summer", "CA1A2B3C4D5E"])
        w.writerow(["2026-07-13", "09:15:33", "in", "CAD", "1500.00", "Interac", P["friend"], "accepted", "yes", "repayment of the March loan", "CA6F7G8H9J0K"])

    # --------------------------------------------------- what an import writes
    inc = defaultdict(float)
    for r in acts:
        if r[5] in ("Dividend", "Interest", "Tax"):
            inc[r[0][:7]] += float(r[16]) * (FX if r[12] == "USD" else 1)
    # The cash-flow rows are derived at build (schema 9); nothing to write here.
    J("filings.json", OrderedDict([
        ("note", "Which month each document was filed, keyed by accounts.json documents[].key. Written by the import step when a file is archived; checked against archive/ by T2."),
        ("filed", OrderedDict([
            (f"Cash Back Visa {ID['rbc_visa']}", sorted({f"{t[:4]}-{t[4:6]}" for t in visa_tot})),
            (f"MasterCard {ID['bmo_mc']}", sorted({f"{t[:4]}-{t[4:6]}" for t in mc_tot})),
            (f"Chequing {ID['bmo_chq']}", sorted({r["statement"][-8:-4] + "-" + r["statement"][-4:-2] for r in bmo})),
            (f"Savings {ID['bmo_sav']}", sorted({r["statement"][-8:-4] + "-" + r["statement"][-4:-2] for r in sav})),
            (f"Day to Day {ID['rbc_chq']}", sorted({r["statement"][-8:-4] + "-" + r["statement"][-4:-2] for r in rbc})),
            (f"eSavings {ID['rbc_esav']}", [f"2026-{m:02d}" for m in range(1, 9)]),
            ("Holdings", ["2026-06", "2026-07", "2026-08", "2026-09"]), ("Activities", ["2026-06", "2026-07", "2026-08", "2026-09"])]))]))
    # The record of the last update and the queue of what it left for the owner to confirm.
    # Every sentence reaches the page (Data → Updates), so it is written about the money, not
    # about the tool: no "I", no rule numbers, no file names.
    zag = sum(p['mv_cad'] for p in pos if p['sym'] == 'ZAG')
    J("imports.json", OrderedDict([
        ("note", NOTE_IMPORTS),
        ("imports", [OrderedDict([
            ("date", "2026-09-06"),
            ("files", ["Cash Back Visa statement to Aug 19", "MasterCard statement to Aug 20",
                       "Chequing and savings statements to Sep 5", "Holdings report of Sep 6",
                       "Activities export of Sep 6"]),
            ("changed", [{"label": "Dry powder", "from": f"{dry_pct + 1.3:.1f}%", "to": f"{dry_pct}%"},
                         {"label": "Holdings", "from": len(tickers) + 1, "to": len(tickers)},
                         {"label": "Spending in August", "from": "$0", "to": "$1,244"}]),
            ("noticed", [
                dict(sev="ok", text=f"Dry powder is {dry_pct}%, inside your 40–45% band: SGOV and VSC hold ${dry:,.0f} of the ${invested:,.0f} Canadian side."),
                dict(sev="ok", text=f"{len(tickers)} holdings, inside your limit of 10. The middle tier is one bond ETF, ZAG at ${zag:,.0f}."),
                dict(sev="ok", text=f"August kept the rule: two deposits of ${P['invest']/2:,.0f} reached the broker on Aug 2 and Aug 17."),
                dict(sev="ok", text="Every statement due has arrived. The next to close are the MasterCard on Sep 20 and the RBC pair on Sep 25."),
                dict(sev="warn", text=f"The $1,500 e-Transfer from {P['friend']} on Jul 13 is the March loan coming back, so it is not income."),
                dict(sev="warn", text="June went over the everyday allowance even with the $429.99 monitor set aside as a big buy."),
            ]),
            ("judged", ["Filed the $429.99 monitor in June as a big buy rather than everyday spending.",
                        f"Typed the Jul 13 e-Transfer from {P['friend']} as a repayment, matching the friend ledger."]),
            ("asked", ["Whether FARM BOY OTTAWA stays in Grocery, and what the unnamed $200 e-Transfer of Aug 11 was."]),
        ])])]))
    J("decisions.json", OrderedDict([
        ("note", NOTE_DEC),
        ("decisions", [
            dict(added="2026-09-06", kind="merchant", what="FARM BOY OTTAWA has appeared 33 times and is filed as Grocery.",
                 default="Grocery", source="Cash Back Visa, most recently Aug 14", status="open"),
            dict(added="2026-09-06", kind="transfer", what="A $200 e-Transfer received on Aug 11 carries no sender name.",
                 default="Other income", source="Chequing statement to Sep 5", status="open"),
            dict(added="2026-08-12", kind="merchant", what="STEAM PURCHASE SEATTLE, seen for the first time.",
                 default="Shopping", source="Cash Back Visa, Aug 3", status="confirmed",
                 answer="Entertainment", resolved="2026-08-12"),
        ])]))
    J("tasks.json", OrderedDict([
        ("note", "Open tasks, shown on Data → Tasks. Added and closed out loud by the owner; `due` is optional and sorts to the top; `status: done` moves a task to the closed list."),
        ("tasks", [
            dict(added="2026-09-06", tag="Money", text="Decide whether the emergency fund stays in RBC eSavings ($5,000, balance only) or moves to the high-yield account beside the two funds.", status="open"),
            dict(added="2026-09-07", tag="Plan", text="Big buys: the $429.99 monitor in June came out of the fund. Confirm the $250/month top-up still makes sense.", status="open"),
            dict(added="2026-09-07", due="2027-03-01", tag="Money", text="RRSP top-up before the March 1 deadline — decide the amount once the January pay stubs are in.", status="open"),
            dict(added="2026-08-20", tag="Data", text="RBC eSavings has a balance but no ledger — decide whether the PDF is worth parsing line by line.", status="open"),
            dict(added="2026-08-12", tag="Money", text="Consolidate SHOP into the TFSA. <b>Done 2026-08-12</b> — bought 20.46 shares in the TFSA.", status="done")])]))

    open(os.path.join(out, "OWNER.md"), "w", encoding="utf-8").write(f"""# OWNER.md — {P['name']}'s workspace notes

> **This file is one person's** — and this person does not exist. {P['name']}, {P.get('age', 31)}, a project
> coordinator in {P['city']}, is the demo owner whose data ships with the tool so that every page has
> something on it. `CLAUDE.md` loads this file with `@OWNER.md`; the `setup` skill replaces it
> with yours.

- Banks: BMO (chequing, savings, MasterCard) and RBC (chequing, eSavings, Visa). The BMO pair
  arrives as `<Month D, YYYY>.pdf` and `<Month D, YYYY>-2.pdf` — the `-2` is the savings account.
- Broker: Wealthsimple. The two monthly transfers land in the Wealthsimple chequing account first.
- {P['friend']} borrowed $1,500 in March and paid it back in July; the ledger is
  `findata/friend_ledger.csv` and the repayment is never income.
- Reply in English.
""")
    # archive/: an empty placeholder per filed statement, named the way the import names them, so
    # the filing grid has the evidence T2 asks for. (The originals of a made-up person do not exist.)
    arc = os.path.join(out, "archive"); os.makedirs(arc, exist_ok=True)
    filed = json.load(open(layout.path(out, "filings.json"), encoding="utf-8"))["filed"]
    for d in documents:
        for m in filed.get(d["key"], []):
            stamp = m.replace("-", "") + "26"
            orig = d["file"].replace("<Month D, YYYY>", dt.date(int(m[:4]), int(m[5:]), 5).strftime("%B %-d, %Y")).replace("<date>", m + "-26")
            open(os.path.join(arc, f"{stamp}_{d['tags'][0]}_{orig}"), "w").close()
    return dict(P=P, net_worth=net_worth, invested=r2(invested), dry_pct=dry_pct, tickers=tickers, n_acts=len(acts))


# The late-life care model and the projection scenarios a new workspace starts with. These are
# published Canadian figures, not anybody's decision; the owner changes them in plan.json.
RETIREMENT_DEFAULTS = OrderedDict([
    ("scenarios", [dict(r=0.03, c="#9ec5f4", n="3% real"), dict(r=0.05, c="#2a78d6", n="5% real"), dict(r=0.07, c="#104281", n="7% real")]),
    ("horizon", 25), ("anchorYear", 2026), ("lifeTo", 95), ("coastR", 0.05),
    ("homeCare", dict(k="Light care at home", v=4200, esc=0.015,
                      d="Around 4 hours a day of a PSW at roughly $35/hr — meals, cleaning, some personal care. Bought by the hour, so it climbs with wages")),
    ("ltcTiers", [
        dict(k="Public · basic", v=2100, esc=0.003, d="Shared room in a public long-term-care home. Province-set co-payment for accommodation only — the care itself is publicly funded. A rate reduction exists if income is low. Long waitlist"),
        dict(k="Public · private", v=3000, esc=0.003, d="Private room in the same public system. Same capped pricing, longer wait"),
        dict(k="Private home", v=6500, esc=0.015, d="Private retirement residence with a care package. No waitlist and no subsidy, and priced like any other private service, so it climbs with wages")]),
])


# README shows these. They are of the demo owner, so they are generated here; S4 checks every
# image README shows resolves, so a missing shot fails the checks rather than leaving a broken image.
SHOTS = [("home.png", "main", "home"), ("spending.png", "main", "trends"), ("plan.png", "main", "budget"),
         ("sources.png", "main", "src"), ("rules.png", "main", "rules")]


def screenshots(out):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  screenshots: SKIPPED (no playwright) — README will point at missing files"); return
    dst = os.path.join(out, "docs", "screens"); os.makedirs(dst, exist_ok=True)
    paths = {"main": os.path.join(out, "dashboards", "finance_dashboard.html")}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for fn, which, key in SHOTS:
            pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            pg.goto("file://" + os.path.abspath(paths[which])); pg.wait_for_timeout(500)
            pg.eval_on_selector(f'[data-k="{key}"]', "el => el.click()"); pg.wait_for_timeout(400)
            pg.screenshot(path=os.path.join(dst, fn)); pg.close()
        b.close()
    print(f"  screenshots: {len(SHOTS)} written to docs/screens/")


if __name__ == "__main__":
    import sys, subprocess
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    c = build(out)
    print(f"demo owner {c['P']['name']}: net worth ${c['net_worth']:,} · portfolio ${c['invested']:,.0f} · dry {c['dry_pct']}% · {len(c['tickers'])} holdings · {c['n_acts']} activity rows")
    rb = os.path.join(out, ".claude", "skills", "update-dashboard", "scripts", "rebuild.py")
    if os.path.exists(rb) and "--no-build" not in sys.argv:
        subprocess.run([sys.executable, rb, out, "--write"], check=True)
        screenshots(out)
