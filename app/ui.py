"""Owner: C. Officer dashboard: submit a complaint, work the approval and fraud queues, see why each case was decided.

    streamlit run app/ui.py          (needs the worker running: python -m app.worker)
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import store  # noqa: E402
from app.worker import submit, submit_reply  # noqa: E402

st.set_page_config(page_title="Teratai complaints", layout="wide")
# Transactions run April-September 2026, so live complaints default to a received time just after that.
DEFAULT_RECEIVED = "2026-09-30 18:00"
CHANNELS = ["App chat", "Email", "Call centre note", "Branch form", "Social media DM"]

page = st.sidebar.radio("Page", ["Submit complaint", "Approval queue", "Fraud queue", "Awaiting customer", "All cases"])
st.sidebar.write(store.counts())


def money(v):
    return "-" if v is None else f"RM{v:.2f}"


def show_case(case, actions=False):
    rec = case["record"]
    d = rec["decision"]
    cols = st.columns(6)
    for col, (k, v) in zip(cols, [("Category", case["category"]), ("Transaction", case["matched_txn_id"] or "-"),
                                  ("Outcome", case["outcome"] or "-"), ("Refund", money(case["refund_amount_myr"])),
                                  ("Priority", case["priority"]), ("Route", case["route"] or "-")]):
        col.metric(k, v)
    if not case["outcome"]:
        st.info("No decision yet: the agent is waiting for the customer's details.")
    ex = rec["extraction"]
    st.caption(f"Status **{case['status']}** · intent {ex.get('intent', 'COMPLAINT')}"
               f"{' (' + ex['confidence'] + ' confidence)' if ex.get('confidence') else ''}"
               f" · reply in {case['reply_language']} · SLA acknowledge by {case['sla_due']}"
               f" · flags {json.loads(case['flags']) or 'none'} · extraction by {ex.get('source', 'rules')}")
    st.markdown("**Complaint:** " + case["text"])
    st.markdown("**Why:**\n" + "\n".join(f"- {r}" for r in d["reasons"]))
    if rec["check_problems"]:
        st.error("Self-check FLAGGED: " + "; ".join(rec["check_problems"]))
    else:
        st.success("Self-check VERIFIED: every ID and amount in the reply is in the evidence")
    if actions:
        text = st.text_area("Reply (edit before approving if needed)", case["reply_text"], height=200,
                            key=f"r-{case['complaint_id']}")
        officer = st.text_input("Officer", "officer1", key=f"o-{case['complaint_id']}")
        a, b = st.columns(2)
        if a.button("Approve and send", key=f"a-{case['complaint_id']}"):
            try:
                store.approve(case["complaint_id"], officer, text if text != case["reply_text"] else None)
                st.rerun()
            except store.ReplyCheckFailed as e:
                st.error("Not sent: the reply failed the self-check.\n\n" + "\n".join(f"- {p}" for p in e.problems))
        if b.button("Reject", key=f"x-{case['complaint_id']}"):
            store.reject(case["complaint_id"], officer)
            st.rerun()
    else:
        st.text_area("Reply", case["reply_text"], height=180, disabled=True, key=f"r-{case['complaint_id']}")
    if case["status"] == "AWAITING_CUSTOMER":
        customer_reply_box(case)
    with st.expander("Evidence"):
        st.json(d["evidence"])
    with st.expander("Trace (each step, timing, LLM usage)"):
        st.json({"trace": rec["trace"], "llm_usage": rec["llm_usage"], "extraction": rec["extraction"]})
    with st.expander("Audit log"):
        st.table(case["audit"])


def customer_reply_box(case):
    """Plays the customer's side: answer the follow-up question, and the worker reprocesses the case."""
    cid = case["complaint_id"]
    answer = st.text_area("Customer's answer to the follow-up question", key=f"c-{cid}")
    if st.button("Send customer reply", key=f"s-{cid}") and answer.strip():
        before = case["record"]["complaint"].get("follow_ups", 0)
        submit_reply(cid, answer)
        with st.spinner("Waiting for the worker..."):
            for _ in range(60):
                time.sleep(0.5)
                now = store.get_case(cid)
                if now and now["record"]["complaint"].get("follow_ups", 0) > before:
                    break
            else:
                st.warning("Not processed yet. Is `python -m app.worker` running?")
        st.rerun()


if page == "Submit complaint":
    st.header("New complaint")
    with st.form("new"):
        customer_id = st.text_input("Customer ID", "CUS-00150")
        channel = st.selectbox("Channel", CHANNELS)
        received_at = st.text_input("Received at (YYYY-MM-DD HH:MM)", DEFAULT_RECEIVED)
        text = st.text_area("Complaint text", height=150)
        sent = st.form_submit_button("Submit")
    if sent and text.strip():
        cid = submit({"customer_id": customer_id, "channel": channel, "received_at": received_at, "text": text})
        st.info(f"{cid} dropped into the inbox; waiting for the worker...")
        for _ in range(30):
            case = store.get_case(cid)
            if case:
                show_case(case)
                break
            time.sleep(0.5)
        else:
            st.warning("Not processed yet. Is `python -m app.worker` running?")

elif page == "Awaiting customer":
    rows = store.list_cases("AWAITING_CUSTOMER")
    st.header(f"Awaiting customer ({len(rows)})")
    st.caption("Open cases with no decision yet: we asked these customers for more details. "
               "Their reply continues the case automatically.")
    for row in rows:
        with st.expander(f"{row['complaint_id']} · {row['customer_id']} · {row['text'][:80]}"):
            show_case(store.get_case(row["complaint_id"]))

elif page in ("Approval queue", "Fraud queue"):
    status = "PENDING_APPROVAL" if page == "Approval queue" else "FRAUD_QUEUE"
    rows = store.list_cases(status)
    st.header(f"{page} ({len(rows)})")
    for row in rows:
        with st.expander(f"{row['complaint_id']} · {row['priority']} · {row['category']} · "
                         f"{row['outcome'] or 'follow-up question'} {money(row['refund_amount_myr'])}"):
            show_case(store.get_case(row["complaint_id"]), actions=True)

else:
    rows = store.list_cases()
    st.header(f"All cases ({len(rows)})")
    st.dataframe([{k: r[k] for k in ("complaint_id", "status", "category", "outcome", "refund_amount_myr", "priority",
                                     "route", "check_ok", "updated_at")} for r in rows], width="stretch")
    pick = st.text_input("Open case")
    if pick:
        case = store.get_case(pick.strip())
        show_case(case) if case else st.warning("Not found")
