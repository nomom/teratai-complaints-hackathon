"""Owner: A. Apply complaint_policy.csv in code: outcome, refund to the sen, priority, route.

The LLM never decides money. Every rule here should cite the evidence it used in `reasons`.
"""
from __future__ import annotations

import datetime as dt

from . import tools
from .matching import Match, _has_twin
from .schemas import Decision

FRAUD_CATEGORIES = {"UNAUTHORISED_CARD", "SCAM_TRANSFER"}


def decide(complaint: dict, category: str, match: Match) -> Decision:
    t = match.txn
    reasons, flags = list(match.reasons), list(match.flags)
    evidence = {"txn": tools.txn_summary(t), "candidates": match.candidates}
    outcome, refund = "INFO_ONLY", 0.0

    if category == "SERVICE_QUALITY":
        outcome = "INFO_ONLY"
    elif t is None:
        # Never guess money. Fraud categories still go to the fraud team.
        outcome = "INVESTIGATE" if category in FRAUD_CATEGORIES else "DECLINE"
        reasons.append("No transaction found: sent to a human")
    elif category == "DUPLICATE_CHARGE":
        recv = tools.received(complaint)
        pool = tools.find_debits(complaint["customer_id"], t["time"] - dt.timedelta(hours=1), recv, {t["channel"]})
        twin = _has_twin(t, pool)
        evidence["twin"] = tools.txn_summary(twin)
        reversed_ = [x["txn_id"] for x in (t, twin) if x and tools.get_reversal(x["txn_id"])]
        if twin and not reversed_:
            outcome, refund = "REFUND", t["amount"]
            reasons.append(f"Identical charge {twin['txn_id']} {int((t['time'] - twin['time']).total_seconds())}s earlier, neither reversed")
        else:
            outcome = "DECLINE"
            reasons.append("Already reversed" if reversed_ else "No identical charge within the duplicate window")
    elif category == "FAILED_TRANSFER":
        rev = tools.get_reversal(t["txn_id"])
        evidence["reversal"] = tools.txn_summary(rev)
        if t["status"] == "Failed" and not rev:
            outcome, refund = "REFUND", t["amount"]
            reasons.append("Status Failed and no reversal credit")
        else:
            outcome = "DECLINE"
            reasons.append(f"Reversed by {rev['txn_id']} on {rev['txn_time']}" if rev else "Transfer completed")
    elif category == "ATM_NOT_DISPENSED":
        j = tools.get_atm_journal(t["txn_id"])
        evidence["atm_journal"] = j
        if j and float(j["dispensed_myr"]) < float(j["requested_myr"]):
            outcome, refund = "REFUND", float(j["requested_myr"]) - float(j["dispensed_myr"])
            reasons.append(f"Journal: requested RM{j['requested_myr']}, dispensed RM{j['dispensed_myr']}")
        else:
            outcome = "DECLINE"
            reasons.append("Journal shows the full amount dispensed")
    elif category == "UNAUTHORISED_CARD":
        if t["auth_method"] == "None":
            outcome, refund = "REFUND", t["amount"]
            reasons.append("Card not present with no strong authentication")
        else:
            outcome = "INVESTIGATE"      # 3DS-OTP / Chip+PIN (and anything unexpected: safer than refunding)
            reasons.append(f"Approved with {t['auth_method']}: fraud team investigates")
    elif category == "SCAM_TRANSFER":
        outcome = "INVESTIGATE"
        reasons.append("Authorised push-payment scam: fraud team attempts a recall")
    elif category == "FEE_DISPUTE":
        due, why = fee_due(complaint["customer_id"], t)
        evidence["fee_due"] = due
        over = round(t["amount"] - due, 2)
        reasons.append(why)
        if over > 0:
            outcome, refund = "REFUND", over
        else:
            outcome = "DECLINE"

    refund = round(refund, 2)
    prio = priority(complaint, category)
    evidence["customer_age"] = tools.age_on(complaint["customer_id"], tools.received(complaint).date())
    return Decision(matched_txn_id=t["txn_id"] if t else "", outcome=outcome, refund_amount_myr=refund,
                    priority=prio, route=route(outcome, refund, flags), candidates=[c[1] for c in match.candidates],
                    evidence=evidence, reasons=reasons, flags=flags)


def fee_due(customer_id, t):
    """The fee that should have been charged, from fee_schedule.csv. TODO(A): verify against training labels."""
    acct = tools.get_account(t["account_id"])
    product = acct["product"] if acct else ""
    desc = t["description"]
    charged_on = t["time"].date()
    for f in tools.get_fee_schedule():
        if not desc.startswith(f["fee_name"]):
            continue
        if f["fee_code"].startswith("MSC") and f["product"] != product:
            continue
        if f["fee_code"] == "DEBIT_ANNUAL":
            age = tools.age_on(customer_id, charged_on)
            if age >= int(tools.param("DEBIT_FEE_WAIVER_AGE")):
                return 0.0, f"Debit card fee waived: customer was {age} on {charged_on}"
            return float(f["amount_myr"]), f"Debit card fee RM{f['amount_myr']} applies (age {age})"
        if f["fee_code"].startswith("CC_ANNUAL"):
            if f["product"] != product:
                continue
            opened = dt.date.fromisoformat(acct["open_date"])
            try:
                anniversary = opened.replace(year=opened.year + 1)
            except ValueError:                       # opened 29 Feb
                anniversary = opened.replace(year=opened.year + 1, day=28)
            if charged_on < anniversary:
                return 0.0, f"Card opened {opened}: annual fee waived in the first year"
            return float(f["amount_myr"]), f"{product} annual fee RM{f['amount_myr']} due"
        return float(f["amount_myr"]), f"{f['fee_name']} for {product}: RM{f['amount_myr']}"
    return t["amount"], f"No fee schedule row for '{desc}' on {product}: treated as correctly charged"


def priority(complaint: dict, category: str) -> str:
    base = tools.policy(category)["base_priority"]
    age = tools.age_on(complaint["customer_id"], tools.received(complaint).date())
    if age >= int(tools.param("VULNERABLE_AGE")):
        return {"P3": "P2", "P2": "P1"}.get(base, base)
    return base


def route(outcome: str, refund: float, flags=()) -> str:
    if outcome == "INVESTIGATE":
        return "FRAUD_TEAM"
    if outcome == "DECLINE" or refund > float(tools.param("AUTO_REFUND_LIMIT_MYR")):
        return "HUMAN_APPROVAL"
    if flags:                     # guardrail: anything flagged never goes out on its own
        return "HUMAN_APPROVAL"
    return "AUTO_RESOLVE"
