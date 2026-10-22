"""Owner: C. Officer dashboard: submit a complaint, work the approval and fraud queues, see why each case was decided.

    streamlit run app/ui.py          (needs the worker running: python -m app.worker)

Each case opens with the summary an officer needs to act (agent/summary.py): why it is in this queue, what happened,
the decision, the one transaction that proves it, and the reply. The full evidence, how the agent decided, and the
audit log are one click away, collapsed.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from agent.summary import case_summary  # noqa: E402
from app import store  # noqa: E402
from app.worker import submit, submit_reply  # noqa: E402

st.set_page_config(page_title="Teratai complaints", layout="wide")
# Transactions run April-September 2026, so live complaints default to a received time just after that.
DEFAULT_RECEIVED = "2026-09-30 18:00"
CHANNELS = ["App chat", "Email", "Call centre note", "Branch form", "Social media DM"]
STATUS_WORDS = {"PENDING_APPROVAL": "Approval queue", "FRAUD_QUEUE": "Fraud queue",
                "AWAITING_CUSTOMER": "Awaiting customer", "RESOLVED": "Resolved automatically",
                "ANSWERED": "Answered (off-topic)", "APPROVED": "Approved and sent", "REJECTED": "Rejected",
                "SENT": "Resolved automatically (old)"}
AUTO_SENT = ["RESOLVED", "ANSWERED", "SENT"]          # replies that went out with no person involved
QUEUE_PAGE = {"PENDING_APPROVAL": "Approval queue", "FRAUD_QUEUE": "Fraud queue"}   # where a person acts on it

page = st.sidebar.radio("Page", ["Submit complaint", "Approval queue", "Fraud queue", "Awaiting customer",
                                 "Resolved automatically", "All cases"])
for status, n in sorted(store.counts().items(),
                        key=lambda x: list(STATUS_WORDS).index(x[0]) if x[0] in STATUS_WORDS else 99):
    st.sidebar.write(f"{STATUS_WORDS.get(status, status)}: **{n}**")


def money(v):
    return "-" if v is None else f"RM{v:.2f}"


def show_case(case, actions=False, headline=True):
    """At a glance first; everything else collapsed below. In a list the expander already shows the headline."""
    rec, cid = case["record"], case["complaint_id"]
    s = case_summary(rec, case["status"])
    if headline:
        st.subheader(s["headline"])
    box = {"warning": st.warning, "error": st.error, "info": st.info}.get(s["tone"], st.success)
    box("\n".join(f"- {w}" for w in s["why_here"]) if len(s["why_here"]) > 1 else s["why_here"][0])
    st.markdown(f"{s['story']}  \n**Decision:** {s['decision']}")
    for f in [a for a in case.get("audit", []) if a["action"] == "flagged_for_review"]:
        st.warning(f"Flagged for review by {f['actor']} ({f['ts']}): {f['detail']}")
    if s["key_row"]:
        st.code(s["key_row"], language=None)
    if s["warnings"]:
        st.error("\n".join(f"- {w}" for w in s["warnings"]))
    elif "DRAFT_REJECTED" in rec["decision"].get("flags", []):
        st.caption("✓ The standard reply in the box passes the self-check (the agent's own drafts did not)")
    else:
        st.caption("✓ Reply checked: every transaction, amount and date in it belongs to this case's evidence")

    if actions:
        text = st.text_area("Reply to the customer (edit before approving if needed)", case["reply_text"],
                            height=200, key=f"r-{cid}")
        officer = st.text_input("Officer", "officer1", key=f"o-{cid}")
        a, b = st.columns(2)
        if a.button("Approve and send", key=f"a-{cid}", type="primary"):
            try:
                store.approve(cid, officer, text if text != case["reply_text"] else None)
                st.rerun()
            except store.ReplyCheckFailed as e:
                st.error("Not sent: the reply failed the self-check.\n\n" + "\n".join(f"- {p}" for p in e.problems))
        if b.button("Reject", key=f"x-{cid}"):
            try:
                store.reject(cid, officer)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        if case["status"] in QUEUE_PAGE:
            st.info(f"Waiting in the **{QUEUE_PAGE[case['status']]}**: approve, edit or reject it there.")
        label = "Reply sent to the customer" if case["status"] in store.SENT_STATUSES else "Reply to the customer"
        st.text_area(label, case["reply_text"], height=180, disabled=True, key=f"r-{cid}")
        if case["status"] in store.SENT_STATUSES:
            flag_box(case)
    if case["status"] == "AWAITING_CUSTOMER":
        customer_reply_box(case)
    details(case)


def details(case):
    """Collapsed: the full record behind the summary."""
    rec = case["record"]
    d, ex, c = rec["decision"], rec["extraction"], rec["complaint"]
    ev = d.get("evidence", {})
    with st.expander("Customer's message", type="compact"):
        st.caption(f"{c['channel']} · received {c['received_at']}"
                   + (f" · subject: {c['subject']}" if c.get("subject") else ""))
        st.write(c["text"])
    with st.expander("Full evidence (customer, account, transactions, journal, fee schedule)", type="compact"):
        reply = ev.get("reply", {})
        facts = {
            "Customer": ev.get("customer"),
            "Priority": ev.get("priority"),
            "Reply language": {k: v for k, v in reply.items() if k.startswith("language")} or None,
            "Account": ev.get("account"),
            "Matched transaction": ev.get("txn"),
            "Identical earlier charge": ev.get("twin"),
            "Reversal": ev.get("reversal"),
            "ATM journal": ev.get("atm_journal"),
            "Fee schedule row": ev.get("fee_schedule"),
            "Fee that should have been charged": None if ev.get("fee_due") is None else money(ev["fee_due"]),
            "How the date was read": ev.get("date_resolution"),
            "Candidates considered (score, id)": ev.get("candidates"),
            "Policy settings in force": ev.get("policy"),
        }
        for label, value in facts.items():
            if value:
                st.markdown(f"**{label}**")
                if isinstance(value, (dict, list)):
                    st.json(value, expanded=False)
                else:
                    st.write(value)
    with st.expander("How the agent decided (steps, reasons, cost)", type="compact"):
        st.markdown("**Decision reasons (internal)**\n" + "\n".join(f"- {r}" for r in d.get("reasons", [])))
        st.markdown(f"**What it read from the message** (by {ex.get('source', 'rules')})")
        st.json({k: v for k, v in ex.items() if v not in ("", None, [], {}, False)}, expanded=False)
        reply = ev.get("reply", {})
        if reply:
            st.markdown(f"**Reply written by:** {reply.get('source', '?')}")
            for i, r in enumerate(reply.get("rejected_drafts", []), 1):
                st.warning(f"Draft {i} ({r['source']}) was rejected: " + "; ".join(r["problems"]))
                st.text(r["text"])
        st.markdown("**Steps**")
        st.table([{"step": t["step"], "ms": t["ms"]} for t in rec.get("trace", [])])
        u = rec.get("llm_usage", {})
        st.caption(f"LLM: {u.get('calls', 0)} calls, {u.get('input_tokens', 0)} input / {u.get('output_tokens', 0)} "
                   f"output tokens" + (f", failures: {u['failures']}" if u.get("failures") else ""))
    with st.expander("Audit log", type="compact"):
        st.table(case["audit"])


def flag_box(case):
    """Spot-check: question a case whose reply already went out. Audited for follow-up; changes nothing."""
    cid = case["complaint_id"]
    with st.popover("Flag for review"):
        note = st.text_input("What looks wrong?", key=f"fn-{cid}",
                             placeholder="e.g. wrong transaction refunded, reply tone")
        officer = st.text_input("Officer", "officer1", key=f"fo-{cid}")
        if st.button("Flag", key=f"fb-{cid}"):
            try:
                store.flag_for_review(cid, officer, note)
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def case_list(rows, actions=False):
    """One line per case (headline and why it is here); open one to see it."""
    for row in rows:
        case = store.get_case(row["complaint_id"])
        s = case_summary(case["record"], case["status"])
        with st.expander(f"{s['headline']} — {s['why_here'][0]}"):
            show_case(case, actions=actions, headline=False)


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
        complaint_id = st.text_input("Complaint ID (optional, e.g. LIVE-01; generated if empty)", "")
        customer_id = st.text_input("Customer ID", "CUS-00150")
        channel = st.selectbox("Channel", CHANNELS)
        received_at = st.text_input("Received at (YYYY-MM-DD HH:MM)", DEFAULT_RECEIVED)
        subject = st.text_input("Subject (optional)", "")
        text = st.text_area("Complaint text", height=150)
        sent = st.form_submit_button("Submit")
    if sent and text.strip():
        new = {"customer_id": customer_id.strip(), "channel": channel, "received_at": received_at.strip(),
               "subject": subject.strip(), "text": text}
        if complaint_id.strip():
            new["complaint_id"] = complaint_id.strip()
        cid = submit(new)
        st.info(f"{cid} dropped into the inbox; waiting for the worker...")
        for _ in range(60):
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
        case = store.get_case(row["complaint_id"])
        with st.expander(f"{case_summary(case['record'], case['status'])['headline']} · {row['text'][:60]}"):
            show_case(case, headline=False)

elif page in ("Approval queue", "Fraud queue"):
    status = "PENDING_APPROVAL" if page == "Approval queue" else "FRAUD_QUEUE"
    rows = store.list_cases(status)
    st.header(f"{page} ({len(rows)})")
    st.caption("Each case says why it needs you. Open one to review the decision and the reply.")
    case_list(rows, actions=True)

elif page == "Resolved automatically":
    rows = store.list_cases(AUTO_SENT)
    st.header(f"Resolved automatically ({len(rows)})")
    st.caption("Replies that went out with no person involved: refunds within the limit, service complaints and "
               "off-topic messages. Spot-check them; flag anything that looks wrong for follow-up.")
    flagged = store.flagged_ids()
    if flagged and st.toggle(f"Only flagged for review ({len([r for r in rows if r['complaint_id'] in flagged])})"):
        rows = [r for r in rows if r["complaint_id"] in flagged]
    case_list(rows)

else:
    choices = {"All": None, **{w: [st_] for st_, w in STATUS_WORDS.items() if st_ != "SENT"},
               "Flagged for review": "flagged"}
    pick = st.selectbox("Show", list(choices))
    want = choices[pick]
    rows = store.list_cases(None if want == "flagged" else want, limit=1000)
    if want == "flagged":
        flagged = store.flagged_ids()
        rows = [r for r in rows if r["complaint_id"] in flagged]
    st.header(f"{pick if pick != 'All' else 'All cases'} ({len(rows)})")
    st.caption("Click a row to open the case.")
    event = st.dataframe(
        [{"case": r["complaint_id"], "status": STATUS_WORDS.get(r["status"], r["status"]), "category": r["category"],
          "outcome": r["outcome"] or "-", "refund": money(r["refund_amount_myr"]), "priority": r["priority"],
          "reply checked": "yes" if r["check_ok"] else "NO", "updated": r["updated_at"]} for r in rows],
        width="stretch", on_select="rerun", selection_mode="single-row", key="all-cases")
    if event.selection.rows:
        case = store.get_case(rows[event.selection.rows[0]]["complaint_id"])
        st.divider()
        show_case(case, actions=case["status"] in ("PENDING_APPROVAL", "FRAUD_QUEUE"))
