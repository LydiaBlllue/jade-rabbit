#!/usr/bin/env python3
"""migrate_4to5.py — move a workspace from findata schema 4 to 5.

    python3 tools/migrate_4to5.py <workspace>

What changed in 5 (2026-09-10, FINANCE.md §8b):
  - `funds.json` `plan` holds `flows`: one row per thing that happens to the paycheque each
    month — `income`, `committed` (rent, a mortgage, a loan: paid before anything is chosen),
    `saving` (the transfer to the broker) and `allowance` (the guilt-free line). The scalars
    `takeHome`, `invest` and `everyday` are sums of them now and are removed from the file; the
    page, rebuild.py and check_data.py read the sums from the flows.
  - `plan.json` `imputedRent` becomes a committed flow with `starts: "fire"`: rent the owner will
    pay after FIRE but does not pay today. It stays out of this month's split and inside the
    planning figure, which is exactly what the scalar did — as a row anyone can read.
  - `profile.json` becomes `"schema": 5`.

A workspace that pays rent or a loan today gets NO committed flow from this script: nothing in
schema 4 said so (take-home was written net of it). Add the row by hand — name, amount, `until`
if it ends, `afterFire` — and raise the income flow by the same amount. D21 then looks for the
payment in the ledger.

Safe to run twice: a workspace already at 5 is left alone.
"""
import json
import os
import sys


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    ws = os.path.abspath(argv[1])
    fd = lambda n: os.path.join(ws, "findata", n)
    if not os.path.exists(fd("profile.json")):
        print(f"no findata/profile.json under {ws}"); return 2
    prof = json.load(open(fd("profile.json"), encoding="utf-8"))
    have = int(prof.get("schema", 2))
    if have >= 5:
        print(f"findata/ is already schema {have}; nothing to do"); return 0
    if have != 4:
        print(f"findata/ is schema {have}; this script only moves 4 → 5 "
              f"(run migrate_{have}to{have + 1}.py first)"); return 2

    fj = json.load(open(fd("funds.json"), encoding="utf-8"))
    plan = fj["plan"]
    pj = json.load(open(fd("plan.json"), encoding="utf-8"))
    flows = []
    flows.append({"key": "pay", "kind": "income", "name": "Take-home pay",
                  "amount": plan.get("takeHome", 0),
                  "note": plan.get("takeHomeNote", "What actually lands in your account each month.")})
    imputed = pj.get("imputedRent", 0) or 0
    if imputed:
        flows.append({"key": "rent-after-fire", "kind": "committed", "name": "Rent",
                      "amount": imputed, "starts": "fire", "afterFire": "keep",
                      "note": "Not paid today. Part of the planning figure from the day FIRE begins."})
    flows.append({"key": "invest", "kind": "saving", "name": "Invest", "amount": plan.get("invest", 0),
                  "to": "broker", "note": "Off the top, before anything else — pay-yourself-first."})
    flows.append({"key": "everyday", "kind": "allowance", "name": "Everyday allowance",
                  "amount": plan.get("everyday", 0),
                  "note": "The guilt-free line. No categories and no caps below it."})

    newplan = {}
    for k, v in plan.items():
        if k in ("takeHome", "takeHomeNote", "invest", "everyday"):
            continue
        newplan[k] = v
        if k == "start":
            newplan["flows"] = flows
    if "flows" not in newplan:
        newplan = {"flows": flows, **newplan}
    for k in ("zh_takeHome", "zh_everyday"):
        if k in newplan:
            newplan["zh_flows_" + k[3:]] = newplan.pop(k)
    fj["plan"] = newplan
    json.dump(fj, open(fd("funds.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("funds.json"), "a", encoding="utf-8").write("\n")
    for f in flows:
        print(f"  {f['kind']:<10} {f['name']:<20} {f['amount']:>8}" + ("   (after FIRE)" if f.get("starts") else ""))
    print(f"→ findata/funds.json: plan.flows with {len(flows)} rows; takeHome / invest / everyday removed")

    if "imputedRent" in pj:
        pj.pop("imputedRent")
        if isinstance(pj.get("note"), str):
            pj["note"] = pj["note"].replace("; `imputedRent` is rent you will pay but do not yet", "")
        json.dump(pj, open(fd("plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(fd("plan.json"), "a", encoding="utf-8").write("\n")
        print(f"→ findata/plan.json: imputedRent {imputed} moved into the flows")

    prof["schema"] = 5
    json.dump(prof, open(fd("profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(fd("profile.json"), "a", encoding="utf-8").write("\n")
    print("→ findata/profile.json: schema 5")
    print("now: rebuild.py --write, then the checkers; add today's rent or loan payments as committed flows if you have any")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
