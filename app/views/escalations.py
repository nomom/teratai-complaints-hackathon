"""Owner: C. Manager: second-tier approval. Escalations from both queues, with what the first tier did and why."""
import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views import case_view as cv
from app.views.common import current_user, queue_table, run_action


@st.dialog("Reject")
def reject_dialog(user, cid):
    reason = st.text_area("Reason (required)")
    if st.button("Reject case", key=f"confirm-danger-esc-{cid}", disabled=not reason.strip()):
        run_action(ops.reject, f"{cid} rejected.", user, cid, reason)


@st.dialog("Return to the team")
def return_dialog(user, cid, queue):
    guidance = st.text_area(f"Guidance for the {queue}", placeholder="e.g. confirm the recall with the receiving bank first")
    if st.button("Return case", type="primary", key=f"ret-go-{cid}", disabled=not guidance.strip()):
        run_action(ops.return_escalation, f"{cid} returned to the {queue}.", user, cid, guidance)


def render():
    user = current_user()
    ui.page_header("Escalations", "Second-tier approval: cases above a first-tier limit, or marked sensitive")
    rows = ops.cases([ops.ESCALATED], user)
    if not rows:
        ui.empty_state("Nothing is waiting for you", "Officers and fraud analysts escalate cases here.")
        if st.button("Refresh", key="esc-refresh"):
            st.rerun()
        return
    st.markdown(f"**{len(rows)} waiting for a manager** · select a row to open it")
    cid = queue_table(rows, "esc-queue", extra_cols={
        "From": lambda r: "Fraud queue" if (ops.escalation(r["complaint_id"]) or {}).get("from_status") == "FRAUD_QUEUE"
        else "Approval queue"})
    case = store.get_case(cid)
    st.divider()
    if not case or case["status"] != ops.ESCALATED:
        ui.alert("info", f"{cid} has just left the queue.")
        return
    e = ops.escalation(cid) or {}
    who = ops.get_user(e.get("user_id")) or {"name": e.get("user_id", "—"), "role": "officer"}
    from_fraud = e.get("from_status") == "FRAUD_QUEUE"
    queue = "fraud team" if from_fraud else "approval queue"
    cv.header(case)
    ui.render(ui.card(ui.kv([
        ("Escalated by", ui.esc(f"{who['name']} · {ops.ROLES.get(who['role'], who['role'])}")),
        ("When", ui.esc(e.get("ts", "—"))), ("From", ui.esc(queue.capitalize())),
        ("Their limit", ui.esc(ui.money(who.get("approval_limit_myr")) if who.get("approval_limit_myr") is not None else "none")),
        ("Reason", ui.esc(e.get("reason") or "—"))]), "First tier"))
    cv.decision_strip(case)
    cv.why(case)
    if from_fraud:
        ui.alert("info", "Fraud cases are decided by the fraud team. Return it with your guidance, or reject it.")
        c1, c2 = st.columns(2)
        if c1.button("Return to fraud team", type="primary", key=f"ret-{cid}", width="stretch"):
            return_dialog(user, cid, queue)
        if c2.button("Reject", key=f"rej-danger-{cid}", width="stretch"):
            reject_dialog(user, cid)
    else:
        reply, problems = cv.reply_editor(case, f"esc-{cid}", e.get("reply_text") or case["reply_text"],
                                          label="Reply proposed by the first tier")
        c1, c2, c3 = st.columns([1.4, 1, 1])
        if c1.button("Approve & send", type="primary", key=f"esc-approve-{cid}", width="stretch",
                     disabled=bool(problems)):
            run_action(ops.approve, f"{cid} approved and the reply was sent.", user, cid, reply)
        if c2.button("Return to officer", key=f"ret-{cid}", width="stretch"):
            return_dialog(user, cid, queue)
        if c3.button("Reject", key=f"rej-danger-{cid}", width="stretch"):
            reject_dialog(user, cid)
    cv.agent_vs_staff(case)
    cv.explain(case, f"esc-{cid}")
