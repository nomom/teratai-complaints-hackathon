"""Owner: B. The case at a glance, in plain English, for the officer's screen (Streamlit today, any frontend later).

    case_summary(record, status) -> {headline, why_here, story, decision, key_row, warnings, tone}

`record` is a stored case (CaseRecord.to_dict()). Everything is derived by code from the decision and its evidence;
nothing here calls the LLM or changes the case. Officers see this first; the full evidence, trace and audit log stay
one click away. Flag codes (NO_MATCH, ...) never reach the screen: each becomes a sentence.
"""
from __future__ import annotations

import datetime as dt


CATEGORY_WORDS = {
    "ATM_NOT_DISPENSED": "ATM cash not dispensed", "DUPLICATE_CHARGE": "Duplicate card charge",
    "FAILED_TRANSFER": "Failed transfer", "UNAUTHORISED_CARD": "Disputed card payment",
    "SCAM_TRANSFER": "Possible scam", "FEE_DISPUTE": "Fee dispute", "SERVICE_QUALITY": "Service complaint",
}
AUTH_WORDS = {"None": "no strong authentication", "3DS-OTP": "a one-time password (3DS-OTP)",
              "Chip+PIN": "chip and PIN", "Contactless": "contactless tap", "App approval": "app approval"}
ASK_WORDS = {"what_happened": "what went wrong", "transaction_type": "the type of transaction", "date": "the date",
             "amount": "the amount", "merchant_or_recipient": "the merchant or recipient", "card_last4": "the card used"}
FLAG_WORDS = {
    "NO_MATCH": "Couldn't identify which transaction the customer means",
    "AMBIGUOUS_MATCH": "Two transactions fit equally well: confirm which one the customer means",
    "CHECK_FAILED": "The drafted reply failed the self-check: fix it before sending",
    "DRAFT_REJECTED": "The agent's reply failed the self-check twice, so a standard reply is in the box: "
                      "review it before sending (the rejected drafts are under \"How the agent decided\")",
    "DETAILS_STILL_MISSING": "Still too vague after 2 follow-up questions",
    "VAGUE_FRAUD_REPORT": "Possible fraud reported without details: contact the customer",
}


def case_summary(record: dict, status: str | None = None) -> dict:
    status = status or record.get("status", "")
    d, ex = record["decision"], record.get("extraction", {})
    ev = d.get("evidence", {})
    off_topic = ex.get("intent") == "OUT_OF_SCOPE"
    kind = "Not a banking complaint" if off_topic else CATEGORY_WORDS.get(record["category"], record["category"])
    due = _when(record.get("sla_due", ""), with_year=False)
    return {
        "headline": f"{record['complaint']['complaint_id']} · {d['priority']} · {kind}" + (f" · acknowledge by {due}" if due else ""),
        "why_here": _why_here(record, status),
        "story": _story(record, off_topic),
        "decision": _decision(record, off_topic),
        "key_row": _row(ev.get("txn")),
        "warnings": [f"Reply check: {p}" for p in record.get("check_problems", [])],
        "tone": {"PENDING_APPROVAL": "warning", "FRAUD_QUEUE": "error", "AWAITING_CUSTOMER": "info"}.get(status, "success"),
    }


def _why_here(record: dict, status: str) -> list[str]:
    """Why this case is where it is. For a queue: every reason it needs a person, in words."""
    d, ex = record["decision"], record.get("extraction", {})
    flags, ev = d.get("flags", []), d.get("evidence", {})
    limit = float(ev.get("policy", {}).get("AUTO_REFUND_LIMIT_MYR", 500))
    if status in ("PENDING_APPROVAL", "FRAUD_QUEUE"):
        out = []
        if status == "FRAUD_QUEUE" and record["category"] == "SCAM_TRANSFER":
            out.append("Possible scam: the customer sent the money themselves, so the fraud team tries a recall")
        elif status == "FRAUD_QUEUE" and ev.get("txn"):
            auth = AUTH_WORDS.get(ev["txn"].get("auth_method", ""), ev["txn"].get("auth_method", ""))
            out.append(f"The disputed payment was approved with {auth}: it needs a fraud investigation")
        if d.get("outcome") == "DECLINE" and "NO_MATCH" not in flags:
            out.append("Declines always need an officer's approval")
        if d.get("refund_amount_myr", 0) > limit:
            out.append(f"Refund of {_rm(d['refund_amount_myr'])} is above the {_rm(limit)} auto-approval limit")
        for f in flags:
            if f == "CROSSCHECK_UNRESOLVED":
                x = ex.get("crosscheck", {})
                out.append(f"Unsure what kind of complaint this is: {CATEGORY_WORDS.get(x.get('llm'), x.get('llm'))} "
                           f"or {CATEGORY_WORDS.get(x.get('rules'), x.get('rules'))}. Confirm before approving")
            elif f in FLAG_WORDS:
                out.append(FLAG_WORDS[f])
        if not d.get("outcome"):
            out.append("Our follow-up question failed the self-check: approve or fix it before it goes out")
        return out or ["Waiting for a person to review"]
    return [{
        "AWAITING_CUSTOMER": "Waiting for the customer's reply to our follow-up question",
        "RESOLVED": "Resolved automatically" + (f": refund within the {_rm(limit)} limit"
                                                if d.get("outcome") == "REFUND" else ""),
        "ANSWERED": "Answered automatically: not a banking complaint",
        "APPROVED": "Approved by an officer and sent",
        "REJECTED": "Rejected by an officer: the drafted reply was not sent",
    }.get(status, status)]


def _story(record: dict, off_topic: bool) -> str:
    """What happened, in one or two sentences, from the evidence."""
    d, ex, cat = record["decision"], record.get("extraction", {}), record["category"]
    ev = d.get("evidence", {})
    t = ev.get("txn")
    if off_topic:
        return "The message isn't about the customer's accounts or transactions."
    if not d.get("outcome"):
        asks = [ASK_WORDS.get(m, m) for m in ex.get("missing_info", [])] or ["more details"]
        return "Too general to act on. We asked the customer for " + _join(asks) + "."
    if cat == "SERVICE_QUALITY":
        return "A service complaint with no money involved."
    if not t:
        n = len(d.get("candidates", []))
        return (f"No transaction could be matched to the message ({n} possible {'one' if n == 1 else 'ones'} in the "
                f"window, none supported by the customer's details).")
    amt, when, who = _rm(t["amount_myr"]), _when(t["txn_time"]), t.get("merchant_or_counterparty", "")
    if cat == "ATM_NOT_DISPENSED":
        j = ev.get("atm_journal") or {}
        where = j.get("atm_location") or who
        if j and float(j["dispensed_myr"]) < float(j["requested_myr"]):
            return f"The ATM at {where} gave {_rm(j['dispensed_myr'])} of {_rm(j['requested_myr'])} on {when}."
        return f"The ATM at {where}: the journal shows the full {amt} was dispensed on {when}."
    if cat == "DUPLICATE_CHARGE":
        twin = ev.get("twin")
        if not twin:
            return f"One charge of {amt} at {who} on {when}; no identical second charge was found."
        gap = _gap(twin["txn_time"], t["txn_time"])
        story = f"Two identical charges of {amt} at {who} on {when}, {gap} apart."
        return story + (" One has already been reversed." if d["outcome"] == "DECLINE" else " Neither was reversed.")
    if cat == "FAILED_TRANSFER":
        rev = ev.get("reversal")
        state = (f"already reversed on {_when(rev['txn_time'])}" if rev else
                 "failed and was not reversed" if t.get("status") == "Failed" else "completed")
        return f"{t.get('channel', 'Transfer')} of {amt} to {who} on {when}: {state}."
    if cat == "UNAUTHORISED_CARD":
        auth = AUTH_WORDS.get(t.get("auth_method", ""), t.get("auth_method", ""))
        card = f" (card ending {t['card_last4']})" if t.get("card_last4") else ""
        return f"The customer disputes {amt} at {who} on {when}{card}, approved with {auth}."
    if cat == "SCAM_TRANSFER":
        return f"The customer says they were tricked into sending {amt} to {who} on {when} by {t.get('channel', 'transfer')}."
    if cat == "FEE_DISPUTE":
        product = ev.get("account", {}).get("product", "the account")
        due = ev.get("fee_due")
        should = f"; the fee schedule says {_rm(due)} for {product}" if due is not None else ""
        return f"{t.get('description') or 'A fee'} of {amt} on {when}{should}."
    return f"Transaction of {amt} at {who} on {when}."


def _decision(record: dict, off_topic: bool) -> str:
    d = record["decision"]
    outcome, refund = d.get("outcome"), d.get("refund_amount_myr", 0.0)
    if off_topic:
        return "Answered politely; nothing to decide."
    if not outcome:
        return "No decision yet: waiting for the customer's details."
    return {
        "REFUND": f"Refund {_rm(refund)}.",
        "DECLINE": "Decline: no refund.",
        "INVESTIGATE": "Fraud team investigates; no refund yet.",
        "INFO_ONLY": "Apologise and pass to the team concerned; no money involved.",
    }.get(outcome, outcome)


def _row(t: dict | None) -> str:
    """The one transaction that proves the decision, on one line."""
    if not t:
        return ""
    auth = t.get("auth_method", "")
    parts = [t["txn_id"], _when(t["txn_time"], with_time=True), t.get("channel", ""), _rm(t["amount_myr"]),
             t.get("merchant_or_counterparty", ""), f"card {t['card_last4']}" if t.get("card_last4") else "",
             auth if auth not in ("", "N/A") else "", t.get("status", "")]
    return " · ".join(p for p in parts if p)


def _rm(v) -> str:
    return f"RM{float(v):,.2f}"


def _when(stamp: str, with_time: bool = False, with_year: bool = True) -> str:
    try:
        t = dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or ""
    out = f"{t.day} {t:%b}" + (f" {t.year}" if with_year else "")
    return out + (f", {t:%H:%M}" if with_time or not with_year else "")


def _gap(first: str, second: str) -> str:
    secs = int((dt.datetime.fromisoformat(second) - dt.datetime.fromisoformat(first)).total_seconds())
    return f"{secs // 60} min {secs % 60} s" if secs >= 60 else f"{secs} s"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
