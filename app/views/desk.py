"""Owner: C. Complaints officer: the resolution desk. Reply first, one primary action, the evidence one tab away."""
import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views import case_view as cv
from app.views.common import current_user, queue_table, run_action


@st.dialog("Escalate to a manager")
def escalate_dialog(user, cid, reply):
    st.write("The case waits for a manager with your proposed reply. Nothing is sent yet.")
    reason = st.text_area("Why are you escalating?", placeholder="e.g. refund above my limit; customer is vulnerable")
    if st.button("Escalate", type="primary", key=f"esc-go-{cid}", disabled=not reason.strip()):
        run_action(ops.escalate, f"{cid} escalated to a manager.", user, cid, reply, reason)


@st.dialog("Reject the drafted reply")
def reject_dialog(user, cid):
    st.write("The case closes as REJECTED and no reply goes out. The agent's decision stays on record.")
    reason = st.text_area("Reason (required)", placeholder="e.g. wrong transaction matched; customer already refunded")
    if st.button("Reject case", key=f"confirm-danger-{cid}", disabled=not reason.strip()):
        run_action(ops.reject, f"{cid} rejected.", user, cid, reason)


def actions(user, case, reply, problems):
    cid = case["complaint_id"]
    over = ops.headroom(user, case) > 0
    c1, c2, c3, c4 = st.columns([1.4, 1, 1, 1])
    if over:
        if c1.button("Escalate to manager", type="primary", key=f"esc-{cid}", width="stretch",
                     help=f"Refund {ui.money(case['refund_amount_myr'])} is above your limit "
                          f"{ui.money(user['approval_limit_myr'])}."):
            escalate_dialog(user, cid, reply)
        c2.caption(f"Above your {ui.money(user['approval_limit_myr'])} limit: a manager approves this one.")
    else:
        if c1.button("Approve & send", type="primary", key=f"approve-{cid}", width="stretch",
                     disabled=bool(problems), help="Disabled until the reply passes the self-check." if problems else None):
            run_action(ops.approve, f"{cid} approved and the reply was sent.", user, cid, reply)
        if c2.button("Escalate", key=f"esc2-{cid}", width="stretch"):
            escalate_dialog(user, cid, reply)
    if c3.button("Reject", key=f"reject-danger-{cid}", width="stretch"):
        reject_dialog(user, cid)
    if c4.button("Re-run agent", key=f"rerun-{cid}", width="stretch",
                 help="Send the original complaint back through the agent (e.g. after the LLM is switched on)."):
        run_action(ops.rerun, f"{cid} sent back to the agent; it returns to a queue once processed.", user, cid)


def render():
    user = current_user()
    ui.page_header("Resolution desk", "Approval queue: declines, refunds over RM 500 and anything the agent flagged")
    rows = ops.cases(["PENDING_APPROVAL"], user)
    limit = user["approval_limit_myr"]
    st.caption(f"Signed in as {user['name']} · approval limit {ui.money(limit) if limit is not None else 'none'}. "
               "Refunds above it are escalated to a manager.")
    if not rows:
        ui.empty_state("The approval queue is clear", "New cases appear here as the agent routes them to a person.")
        if st.button("Refresh", key="desk-refresh"):
            st.rerun()
        return

    # Queue on top, full width (every column readable on a laptop or tablet), the selected case below
    head, refresh = st.columns([2.4, 1], vertical_alignment="bottom")
    head.markdown(f"**{len(rows)} waiting** · select a row to open it")
    if refresh.button("Refresh", key="desk-refresh", width="stretch", icon=":material/refresh:"):
        st.rerun()
    cid = queue_table(rows, "desk-queue")
    case = store.get_case(cid)
    st.divider()
    if not case or case["status"] != "PENDING_APPROVAL":
        ui.alert("info", f"{cid} has just left the queue.")
        return
    cv.header(case)
    cv.decision_strip(case)
    cv.why(case)
    reply, problems = cv.reply_editor(case, f"desk-{cid}", case["reply_text"])
    actions(user, case, reply, problems)
    cv.agent_vs_staff(case)
    cv.explain(case, f"desk-{cid}")
