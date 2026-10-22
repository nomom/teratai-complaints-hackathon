"""Owner: C. Dashboard: log in, then each role works only its own cases (app/UserAccessControl/roles.py).

    streamlit run app/ui.py          (needs the worker running: python -m app.worker)

    officer1   the approval queue                         (staff are seeded in data/staff.csv, password 1234)
    fraud1     the fraud queue
    manager1   both queues, awaiting customer, the spot-check of automatic replies, all cases
    customer   signs up with their customer ID, then files complaints, follows them and answers our questions

Each case opens with the summary an officer needs to act (agent/summary.py): why it is in this queue, what happened,
the decision, the one transaction that proves it, and the reply. The full evidence, how the agent decided, and the
audit log are one click away, collapsed. A customer only ever sees roles.customer_view: never an unsent draft.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from agent.summary import case_summary  # noqa: E402
from app import store  # noqa: E402
from app.UserAccessControl import auth, roles  # noqa: E402
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
QUEUES = ("PENDING_APPROVAL", "FRAUD_QUEUE")
QUEUE_PAGE = {"PENDING_APPROVAL": "Approval queue", "FRAUD_QUEUE": "Fraud queue"}   # where a person acts on it

ROLE_WORDS = {roles.OFFICER: "Complaints officer", roles.FRAUD: "Fraud analyst", roles.MANAGER: "Manager",
              roles.CUSTOMER: "Customer"}
PAGES = {roles.OFFICER: ["Approval queue", "Submit complaint", "All cases"],
         roles.FRAUD: ["Fraud queue", "Submit complaint", "All cases"],
         roles.MANAGER: ["Approval queue", "Fraud queue", "Awaiting customer", "Resolved automatically", "All cases",
                         "Submit complaint"],
         roles.CUSTOMER: ["My cases", "New complaint"]}
# What a customer is told about their case. Both queues read the same: the customer is never told it is with fraud.
CUSTOMER_STATUS = {"AWAITING_CUSTOMER": "We need more details from you", "PENDING_APPROVAL": "Being reviewed",
                   "FRAUD_QUEUE": "Being reviewed", "RESOLVED": "Answered", "ANSWERED": "Answered",
                   "APPROVED": "Answered", "SENT": "Answered", "REJECTED": "Closed"}


def signed_in():
    """The account behind this browser session's token, checked again on every rerun (expiry, removed account)."""
    token = st.session_state.get("token")
    if not token:
        return None
    try:
        return auth.user_from_token(token)
    except auth.AuthError as e:
        del st.session_state["token"]
        st.session_state["auth_notice"] = e.message
        return None


def login_page():
    st.title("Teratai Bank complaints")
    if notice := st.session_state.pop("auth_notice", None):
        st.info(notice)
    log_in, sign_up = st.tabs(["Log in", "Sign up (customers)"])
    with log_in:
        with st.form("login"):
            username = st.text_input("Username or customer ID", placeholder="officer1 or CUS-00150")
            password = st.text_input("Password", type="password")
            go = st.form_submit_button("Log in", type="primary")
        if go:
            try:
                st.session_state["token"], _ = auth.login(username, password)
            except auth.AuthError as e:
                st.error(e.message)
            else:
                st.rerun()
        st.caption("Staff: officer1, fraud1 or manager1, password 1234. Customers: sign up first with your customer ID.")
    with sign_up:
        sign_up_form()


def sign_up_form():
    """Two steps, as in POST /auth/signup/verify then /auth/signup: check the customer ID, then create a password."""
    cid = st.session_state.get("signup_id")
    if not cid:
        with st.form("signup-id"):
            entered = st.text_input("Customer ID", placeholder="CUS-00150")
            go = st.form_submit_button("Continue", type="primary")
        if go:
            try:
                st.session_state["signup_id"] = auth.check_customer_id(entered).username
            except auth.AuthError as e:
                st.error(e.message)
            else:
                st.rerun()
        return
    st.write(f"Create a password for customer ID **{cid}**.")
    with st.form("signup-password"):
        password = st.text_input("Password", type="password",
                                 help=f"At least {auth.MIN_PASSWORD_LENGTH} characters")
        again = st.text_input("Confirm password", type="password")
        go = st.form_submit_button("Sign up", type="primary")
    if st.button("Use a different customer ID"):
        del st.session_state["signup_id"]
        st.rerun()
    if go:
        if password != again:
            st.error("The passwords don't match. Type the same password twice.")
            return
        try:
            auth.sign_up(cid, password)
        except auth.AuthError as e:
            st.error(e.message)
            return
        del st.session_state["signup_id"]
        st.session_state["auth_notice"] = f"Signed up. Log in with {cid} and your new password."
        st.rerun()


user = signed_in()
if user is None:
    login_page()
    st.stop()

st.sidebar.markdown(f"**{user.full_name}**  \n{ROLE_WORDS[user.role]} · `{user.username}`")
if st.sidebar.button("Log out"):
    del st.session_state["token"]
    st.rerun()
page = st.sidebar.radio("Page", PAGES[user.role])
if user.role != roles.CUSTOMER:
    for status, n in sorted(store.counts(**roles.case_filter(user)).items(),
                            key=lambda x: list(STATUS_WORDS).index(x[0]) if x[0] in STATUS_WORDS else 99):
        st.sidebar.write(f"{STATUS_WORDS.get(status, status)}: **{n}**")


def my_cases(status=None, limit=200):
    """store.list_cases limited to what the signed-in user may see."""
    return store.list_cases(status, limit, **roles.case_filter(user))


def queue_header(title, rows, statuses):
    """The header counts every case in these statuses; the list itself stops at the most recent few hundred."""
    counts = store.counts(**roles.case_filter(user))
    total = sum(counts.get(s, 0) for s in statuses)
    st.header(f"{title} ({total})")
    if len(rows) < total:
        st.caption(f"Showing the {len(rows)} most recently updated. All cases lists every one.")


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

    if actions and roles.can_act(user, case):
        text = st.text_area("Reply to the customer (edit before approving if needed)", case["reply_text"],
                            height=200, key=f"r-{cid}")
        a, b = st.columns(2)
        if a.button("Approve and send", key=f"a-{cid}", type="primary"):
            try:
                store.approve(cid, user.username, text if text != case["reply_text"] else None)
                st.rerun()
            except store.ReplyCheckFailed as e:
                st.error("Not sent: the reply failed the self-check.\n\n" + "\n".join(f"- {p}" for p in e.problems))
        if b.button("Reject", key=f"x-{cid}"):
            try:
                store.reject(cid, user.username)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        if case["status"] in QUEUE_PAGE:
            where = QUEUE_PAGE[case["status"]]
            if roles.can_act(user, case):
                st.info(f"Waiting in the **{where}**: approve, edit or reject it there.")
            else:
                who = "the fraud team" if case["status"] == "FRAUD_QUEUE" else "a complaints officer"
                st.info(f"Waiting in the **{where}** for {who}.")
        label = "Reply sent to the customer" if case["status"] in store.SENT_STATUSES else "Reply to the customer"
        st.text_area(label, case["reply_text"], height=180, disabled=True, key=f"r-{cid}")
        if case["status"] in store.SENT_STATUSES:
            flag_box(case)
    if case["status"] == "AWAITING_CUSTOMER":
        customer_reply_box(cid, "Customer's answer to the follow-up question")
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
        if st.button("Flag", key=f"fb-{cid}"):
            try:
                store.flag_for_review(cid, user.username, note)
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


def wait_for_worker(cid, before=None):
    """Poll until the worker has (re)processed the case, i.e. its updated_at moved on from `before`."""
    with st.spinner("Waiting for the worker..."):
        for _ in range(60):
            case = store.get_case(cid)
            if case and case["updated_at"] != before:
                return case
            time.sleep(0.5)
    st.warning("Not processed yet. Is `python -m app.worker` running?")
    return None


def customer_reply_box(cid, label):
    """Answer the follow-up question; the worker reprocesses the case. Staff use it to play the customer's side."""
    answer = st.text_area(label, key=f"c-{cid}")
    if st.button("Send reply", key=f"s-{cid}") and answer.strip():
        before = store.get_case(cid)["updated_at"]
        submit_reply(cid, answer)
        wait_for_worker(cid, before)
        st.rerun()


def customer_case(case):
    """A customer's own case: what they sent and the messages exchanged. roles.customer_view, never the internals."""
    st.caption(f"{case['channel']} · sent {case['received_at']} · {CUSTOMER_STATUS.get(case['status'], 'Being reviewed')}")
    with st.chat_message("user"):
        st.write(case["text"])
    for m in case.get("messages", []):
        with st.chat_message("user" if m["from"] == "customer" else "assistant"):
            st.write(m["text"])
            st.caption(m["ts"])
    if case["status"] in ("PENDING_APPROVAL", "FRAUD_QUEUE"):
        st.info("Our team is reviewing your case. We'll reply here.")
    if case["status"] == "AWAITING_CUSTOMER":
        customer_reply_box(case["complaint_id"], "Your answer")


if page == "Submit complaint":
    st.header("New complaint")
    st.caption("Intake for any customer, e.g. a call-centre note or a live-round row.")
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
        st.info(f"{cid} dropped into the inbox.")
        case = wait_for_worker(cid)
        if case and roles.can_view(user, case):
            show_case(case)
        elif case:
            st.success(f"{cid} was processed and routed to {case['route'] or case['status']}: not your queue.")

elif page == "New complaint":
    st.header("Tell us what went wrong")
    with st.form("new"):
        subject = st.text_input("Subject (optional)", "")
        text = st.text_area("What happened? Include the amount, the date and the merchant if you know them.",
                            height=150)
        sent = st.form_submit_button("Send", type="primary")
    if sent and text.strip():
        # The demo's transactions end on 30 Sep 2026, so a customer's complaint is received then, like the live round.
        cid = submit({"customer_id": user.username, "channel": "App chat", "received_at": DEFAULT_RECEIVED,
                      "subject": subject.strip(), "text": text})
        st.success(f"Thanks, we've received your complaint ({cid}).")
        if case := wait_for_worker(cid):
            customer_case(roles.customer_view(case))

elif page == "My cases":
    rows = my_cases(limit=1000)
    st.header(f"My cases ({len(rows)})")
    if not rows:
        st.info("You have no complaints with us. Use New complaint to tell us what went wrong.")
    for row in rows:
        case = roles.customer_view(store.get_case(row["complaint_id"]))
        waiting = case["status"] == "AWAITING_CUSTOMER"
        with st.expander(f"{case['complaint_id']} · {CUSTOMER_STATUS.get(case['status'], 'Being reviewed')} · "
                         f"{case['text'][:60]}", expanded=waiting):
            customer_case(case)

elif page == "Awaiting customer":
    rows = my_cases("AWAITING_CUSTOMER")
    queue_header("Awaiting customer", rows, ["AWAITING_CUSTOMER"])
    st.caption("Open cases with no decision yet: we asked these customers for more details. "
               "Their reply continues the case automatically.")
    for row in rows:
        case = store.get_case(row["complaint_id"])
        with st.expander(f"{case_summary(case['record'], case['status'])['headline']} · {row['text'][:60]}"):
            show_case(case, headline=False)

elif page in ("Approval queue", "Fraud queue"):
    status = "PENDING_APPROVAL" if page == "Approval queue" else "FRAUD_QUEUE"
    rows = my_cases(status)
    queue_header(page, rows, [status])
    st.caption("Each case says why it needs you. Open one to review the decision and the reply.")
    case_list(rows, actions=True)

elif page == "Resolved automatically":
    rows = my_cases(AUTO_SENT)
    queue_header("Resolved automatically", rows, AUTO_SENT)
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
    rows = my_cases(None if want == "flagged" else want, limit=100_000)
    if want == "flagged":
        flagged = store.flagged_ids()
        rows = [r for r in rows if r["complaint_id"] in flagged]
    st.header(f"{pick if pick != 'All' else 'All cases'} ({len(rows)})")
    st.caption("Click a row to open the case." + ("" if user.role == roles.MANAGER else " Only cases in your queue."))
    event = st.dataframe(
        [{"case": r["complaint_id"], "status": STATUS_WORDS.get(r["status"], r["status"]), "category": r["category"],
          "outcome": r["outcome"] or "-", "refund": money(r["refund_amount_myr"]), "priority": r["priority"],
          "reply checked": "yes" if r["check_ok"] else "NO", "updated": r["updated_at"]} for r in rows],
        width="stretch", on_select="rerun", selection_mode="single-row", key="all-cases")
    if event.selection.rows:
        case = store.get_case(rows[event.selection.rows[0]]["complaint_id"])
        st.divider()
        show_case(case, actions=case["status"] in QUEUES)
