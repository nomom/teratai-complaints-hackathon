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
from app.worker import submit  # noqa: E402

st.set_page_config(page_title="Teratai complaints", layout="wide")
# Transactions run April-September 2026, so live complaints default to a received time just after that.
DEFAULT_RECEIVED = "2026-09-30 18:00"
CHANNELS = ["App chat", "Email", "Call centre note", "Branch form", "Social media DM"]

page = st.sidebar.radio("Page", ["Submit complaint", "Approval queue", "Fraud queue", "All cases"])
st.sidebar.write(store.counts())


def show_case(case, actions=False):
    rec = case["record"]
    d = rec["decision"]
    cols = st.columns(6)
    for col, (k, v) in zip(cols, [("Category", case["category"]), ("Transaction", case["matched_txn_id"] or "-"),
                                  ("Outcome", case["outcome"]), ("Refund", f"RM{case['refund_amount_myr']:.2f}"),
                                  ("Priority", case["priority"]), ("Route", case["route"])]):
        col.metric(k, v)
    st.caption(f"Status **{case['status']}** · reply in {case['reply_language']} · SLA acknowledge by {case['sla_due']}"
               f" · flags {json.loads(case['flags']) or 'none'}")
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
            store.approve(case["complaint_id"], officer, text if text != case["reply_text"] else None)
            st.rerun()
        if b.button("Reject", key=f"x-{case['complaint_id']}"):
            store.reject(case["complaint_id"], officer)
            st.rerun()
    else:
        st.text_area("Reply", case["reply_text"], height=180, disabled=True, key=f"r-{case['complaint_id']}")
    with st.expander("Evidence"):
        st.json(d["evidence"])
    with st.expander("Trace (each step, timing, LLM usage)"):
        st.json({"trace": rec["trace"], "llm_usage": rec["llm_usage"], "extraction": rec["extraction"]})
    with st.expander("Audit log"):
        st.table(case["audit"])


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

elif page in ("Approval queue", "Fraud queue"):
    status = "PENDING_APPROVAL" if page == "Approval queue" else "FRAUD_QUEUE"
    rows = store.list_cases(status)
    st.header(f"{page} ({len(rows)})")
    for row in rows:
        with st.expander(f"{row['complaint_id']} · {row['priority']} · {row['category']} · {row['outcome']} "
                         f"RM{row['refund_amount_myr']:.2f}"):
            show_case(store.get_case(row["complaint_id"]), actions=True)

else:
    rows = store.list_cases()
    st.header(f"All cases ({len(rows)})")
    st.dataframe([{k: r[k] for k in ("complaint_id", "status", "category", "outcome", "refund_amount_myr", "priority",
                                     "route", "check_ok", "updated_at")} for r in rows], use_container_width=True)
    pick = st.text_input("Open case")
    if pick:
        case = store.get_case(pick.strip())
        show_case(case) if case else st.warning("Not found")
