"""Owner: C. The four roles, and which cases each may see and act on. One place, so every endpoint applies the same rules.

    officer    complaints officer (first tier): the HUMAN_APPROVAL queue only
    fraud      fraud analyst (first tier): the FRAUD_TEAM queue only
    manager    admin: every case, both queues (second-tier approval comes later)
    customer   a signed-up bank customer: only their own cases, and only what was actually sent to them

See docs/bonus_platform.md for the roles and tmp/ops_platform_todo.md for what is still to build.
"""
OFFICER, FRAUD, MANAGER, CUSTOMER = "officer", "fraud", "manager", "customer"
STAFF_ROLES = (OFFICER, FRAUD, MANAGER)
ALL_ROLES = STAFF_ROLES + (CUSTOMER,)

QUEUE_ROUTE = {OFFICER: "HUMAN_APPROVAL", FRAUD: "FRAUD_TEAM"}      # the one queue each first-tier role works

# Audit actions that are messages the customer really received or sent. A drafted reply waiting for a person is
# not one of them: the customer must never see it before a human approves it.
CUSTOMER_MESSAGES = ("question_sent", "reply_sent", "customer_replied")


def case_filter(account) -> dict:
    """Column filters that limit a case list to what this account may see (arguments for store.list_cases)."""
    if account.role == MANAGER:
        return {}
    if account.role == CUSTOMER:
        return {"customer_id": account.username}
    return {"route": QUEUE_ROUTE[account.role]}


def can_view(account, case: dict) -> bool:
    return all(case.get(k) == v for k, v in case_filter(account).items())


def can_act(account, case: dict) -> bool:
    """Approve or reject: staff only, and only on a case in their own queue."""
    return account.role in STAFF_ROLES and can_view(account, case)


def customer_view(case: dict) -> dict:
    """A case as its customer sees it: their message, its status, and the messages exchanged. No decision internals."""
    out = {k: case.get(k) for k in ("complaint_id", "received_at", "channel", "text", "status", "updated_at")}
    if "audit" in case:
        out["messages"] = [{"ts": a["ts"], "from": "customer" if a["action"] == "customer_replied" else "bank",
                            "text": a["detail"]} for a in case["audit"] if a["action"] in CUSTOMER_MESSAGES]
    return out
