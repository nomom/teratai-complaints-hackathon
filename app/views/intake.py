"""Owner: C. Live intake: the live-round screen. Judges hand us complaints.csv rows; we paste them in and the worker
decides each one on its own. A typed form is the fallback.
"""
import time

import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views import case_view as cv
from app.views.common import current_user

CHANNELS = ["App chat", "Email", "Call centre note", "Branch form", "Social media DM"]
DEFAULT_RECEIVED = "2026-09-30 10:00"    # live complaints are received on 30 Sep 2026 (README, "The live round")
EXAMPLE = ('complaint_id,customer_id,received_at,channel,subject,text\n'
           'LIVE-01,CUS-00566,2026-09-30 10:15,App chat,,"Hi, I was charged twice at GoRide for RM46.66..."')


def wait_and_show(user, ids):
    """Wait for the worker, show each case's steps as it is decided, then a compact result card."""
    pending = list(ids)
    with st.status(f"Processing {len(ids)} complaint{'s' if len(ids) > 1 else ''}…", expanded=True) as status:
        st.write(f"Dropped into the inbox: {', '.join(ids)}. The worker picks them up on its own.")
        for _ in range(60):
            for cid in list(pending):
                case = store.get_case(cid)
                if case:
                    pending.remove(cid)
                    steps = " → ".join(f"{ui.nice(s['step'])} {float(s.get('ms') or 0):.0f} ms"
                                       for s in case["record"].get("trace", []))
                    st.write(f"**{cid}** · {steps}")
            if not pending:
                status.update(label="Decided", state="complete", expanded=False)
                break
            time.sleep(0.5)
        else:
            status.update(label="The worker hasn't picked these up yet", state="error")
            ui.alert("error", f"Not processed after 30 s: {', '.join(pending)}. Is `python -m app.worker` running?")
    for cid in ids:
        case = store.get_case(cid)
        if case:
            result(user, case)


def result(user, case):
    where = {"RESOLVED": "Reply sent automatically", "PENDING_APPROVAL": "Waiting in the approval queue",
             "FRAUD_QUEUE": "Sent to the fraud team", "AWAITING_CUSTOMER": "Asked the customer for details",
             "ANSWERED": "Answered politely (not a banking complaint)"}.get(case["status"], ui.nice(case["status"]))
    with st.container(border=True):
        ui.render(f'<div class="tk-row"><span class="tk-title">{ui.esc(case["complaint_id"])}</span>'
                  f'{ui.status_badge(case["status"])}{ui.priority_badge(case["priority"])}'
                  f'{ui.check_badge(case["record"].get("check_problems"))}</div>'
                  f'<p class="tk-sub">{ui.esc(where)}</p>')
        if not ops.can(user, "view", case):
            ui.alert("info", "This case belongs to the fraud team, so its details are hidden from your role.")
            return
        cv.decision_strip(case)
        with st.expander("Why, evidence, trace and reply"):
            cv.why(case)
            st.text_area("Drafted reply", case["reply_text"] or "", height=150, disabled=True,
                         key=f"in-reply-{case['complaint_id']}")
            cv.explain(case, f"in-{case['complaint_id']}")


def take(user, complaints):
    try:
        ids, skipped = ops.take_in(user, complaints)
    except ops.PermissionDenied as e:
        ui.alert("error", str(e))
        return
    for cid, why in skipped:
        ui.alert("warning", f"{cid} was {why}, so it wasn't submitted again. Find it under All cases.")
    if ids:
        wait_and_show(user, ids)


def render():
    user = current_user()
    ui.page_header("Live intake", "New complaints in complaints.csv format. The agent reacts on its own.", glow=True)
    paste, typed = st.tabs(["Paste CSV rows", "Type a complaint"])
    with paste:
        st.caption("One or more rows, header line optional: complaint_id, customer_id, received_at, channel, subject, text")
        with st.form("paste-form", border=True):
            text = st.text_area("CSV rows", height=150, placeholder=EXAMPLE, label_visibility="collapsed")
            sent = st.form_submit_button("Take in", type="primary")
        if sent:
            if not text.strip():
                ui.alert("warning", "Paste at least one row first.")
            else:
                try:
                    complaints = ops.parse_csv_rows(text)
                except ValueError as e:
                    ui.alert("error", f"Couldn't read the rows: {e}")
                else:
                    take(user, complaints)
    with typed:
        with st.form("typed-form", border=True):
            c1, c2 = st.columns(2)
            cid = c1.text_input("Complaint ID", placeholder="leave empty to assign one")
            customer = c2.text_input("Customer ID", placeholder="CUS-00566")
            c3, c4 = st.columns(2)
            channel = c3.selectbox("Channel", CHANNELS)
            received = c4.text_input("Received at", DEFAULT_RECEIVED, help="YYYY-MM-DD HH:MM, Malaysia time")
            subject = st.text_input("Subject", placeholder="email only")
            body = st.text_area("Complaint text", height=130)
            sent = st.form_submit_button("Take in", type="primary")
        if sent:
            row = {"complaint_id": cid.strip(), "customer_id": customer.strip(), "received_at": received.strip(),
                   "channel": channel, "subject": subject.strip(), "text": body.strip()}
            missing = [k.replace("_", " ") for k in ("customer_id", "received_at", "text") if not row[k]]
            if missing:
                ui.alert("warning", f"Fill in: {', '.join(missing)}.")
            else:
                if not row["complaint_id"]:
                    del row["complaint_id"]
                take(user, [row])
