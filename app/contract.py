"""Owner: C. The organisers' API contract (docs/api.md): a stored case as GET /cases/{id} must return it.

Only the contract fields, nothing else: the contract endpoints need no login, so evidence, customer details and the
audit log stay behind GET /cases/{id}/record (staff login).

The decision fields are always the agent's own (from the stored record): an officer's edit or approval never changes
them; what the officer did is in `human_action`.
"""
from app import store

# Case status in the store -> (case_state, sent). docs/api.md, "Case states (human in the loop)".
STATE = {
    "RESOLVED": ("auto_resolved", True),
    "ANSWERED": ("auto_resolved", True),          # off-topic message answered automatically
    "AWAITING_CUSTOMER": ("auto_resolved", True),  # our follow-up question went out; the case reopens on their reply
    "SENT": ("auto_resolved", True),               # the old name for RESOLVED
    "PENDING_APPROVAL": ("awaiting_approval", False),
    "FRAUD_QUEUE": ("with_fraud_team", False),     # sent becomes true once the fraud team sends the holding reply
    "APPROVED": ("approved", True),
    "REJECTED": ("rejected", False),
}


def case_view(case: dict) -> dict:
    """GET /cases/{id} for a decided case."""
    rec = case["record"]
    d = rec["decision"]
    state, sent = STATE.get(case["status"], ("awaiting_approval", False))
    if case["status"] == "FRAUD_QUEUE":
        sent = store.holding_reply_sent(case)        # docs/api.md: with_fraud_team, at most a holding reply, sent either
    return {
        "complaint_id": case["complaint_id"],
        "status": "done",
        "category": rec["category"],
        "matched_txn_id": d["matched_txn_id"] or "",
        "outcome": d["outcome"] or "INFO_ONLY",       # a case awaiting the customer has no decision yet
        "refund_amount_myr": f"{float(d['refund_amount_myr']):.2f}",
        "priority": d["priority"],
        "reply_language": rec["reply_language"],
        "route": d["route"] or "AUTO_RESOLVE",
        "reply_text": rec["reply_text"],              # the agent's draft, never the officer's edit
        "self_check": "flagged" if rec.get("check_problems") else "passed",
        "case_state": state,
        "sent": sent,
        "human_action": store.human_action(case),
    }
