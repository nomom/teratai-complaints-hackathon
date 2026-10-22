"""Owner: C. Customer portal: a signed-in customer sends a complaint and follows it as a conversation.

The customer sees only their own complaints and only what the bank actually sent them. Drafts waiting for approval,
evidence, routing and staff notes stay inside the bank.
"""
import time

import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views.common import current_user, run_action

# What the customer is told, by case status: (tone, icon, label, what happens next)
CUSTOMER_STATUS = {
    "AWAITING_CUSTOMER": ("info", "…", "We need a few more details", "Please answer the question below."),
    "PENDING_APPROVAL": ("warning", "⏳", "Being reviewed", "A member of our team is checking your case."),
    "ESCALATED": ("warning", "⏳", "Being reviewed", "A senior member of our team is checking your case."),
    "FRAUD_QUEUE": ("warning", "⏳", "With our fraud team", "Our fraud team is investigating and will contact you."),
    "RESOLVED": ("success", "✓", "Resolved", ""),
    "APPROVED": ("success", "✓", "Resolved", ""),
    "ANSWERED": ("neutral", "↩", "Answered", ""),
    "FRAUD_CLOSED": ("neutral", "■", "Investigation closed", ""),
    "REJECTED": ("neutral", "•", "Closed", "Our team will contact you about this complaint."),
}

# A complaint each demo customer can send that matches their real September transactions
EXAMPLES = {
    "CUS-00996": "Assalamualaikum, bayaran RM69.46 di Farmasi Sejahtera keluar dua kali dalam akaun saya pada "
                 "28 September. Mohon pulangkan bayaran yang berlebihan.",
    "CUS-02710": "ATM di Kepong Market tak keluar duit pada 28 September, tapi akaun saya kena tolak RM400. Tolong semak.",
    "CUS-01272": "My IBG transfer of RM2,584.75 to Wei Ming on 26 September failed, but my account was still debited. "
                 "The recipient did not receive it.",
    "CUS-02323": "There is a card payment of RM2,213.95 at LUXEGOODS LONDON on 19 September that I did not make. "
                 "My card is still with me.",
}


def status_badge(case):
    tone, icon, label, _ = CUSTOMER_STATUS.get(case["status"], ("neutral", "•", ui.nice(case["status"]), ""))
    return ui.badge(tone, label, icon)


def next_step(case):
    note = CUSTOMER_STATUS.get(case["status"], ("", "", "", ""))[3]
    left = ops.sla_left(case)
    if left is not None and left.total_seconds() > 0 and case["status"] != "AWAITING_CUSTOMER":
        note += f" We'll reply within {ui.duration(left)}."
    return note.strip()


def thread_html(case):
    items = []
    for m in ops.thread(case):
        who = "You" if m["from"] == "customer" else "Teratai Bank"
        cls = "tk-msg tk-me" if m["from"] == "customer" else "tk-msg"
        items.append(f'<div class="{cls}"><p class="tk-ts">{ui.esc(who)} · {ui.esc(m["ts"])}</p><p>{ui.esc(m["text"])}</p></div>')
    return f'<div class="tk-thread">{"".join(items)}</div>'


def show(user, case, key):
    ui.render(f'<div class="tk-row"><span class="tk-title">{ui.esc(case["complaint_id"])}</span>{status_badge(case)}</div>'
              f'<p class="tk-sub">Sent {ui.esc(case["received_at"])} · {ui.esc(case["channel"])}</p>')
    note = next_step(case)
    if note:
        ui.alert("info", note)
    ui.render(thread_html(case))
    if ops.can(user, "customer_reply", case):
        with st.form(f"answer-{key}", clear_on_submit=True, border=True):
            text = st.text_area("Your answer", height=100, placeholder="e.g. the date, the amount and where it happened")
            if st.form_submit_button("Send answer", type="primary"):
                run_action(ops.customer_reply, "Thanks, your answer was sent. We'll take it from here.", user,
                           case["complaint_id"], text)


def wait_for(cid):
    """Give the worker a few seconds so the customer sees the outcome straight away when it's automatic."""
    with st.spinner("Sending to Teratai Bank…"):
        for _ in range(24):
            case = store.get_case(cid)
            if case:
                return case
            time.sleep(0.5)
    return None


def _fill_example(customer_id):
    st.session_state["portal-text"] = EXAMPLES.get(customer_id, "")


def _send(user):
    """Click handler: send, then clear the box (a widget's value can only be reset before it is drawn)."""
    try:
        st.session_state["portal-sent"] = ops.submit_own(user, st.session_state.get("portal-text", ""))
        st.session_state["portal-text"] = ""
    except (ops.PermissionDenied, ValueError) as e:
        st.session_state["portal-error"] = str(e)


def new_complaint():
    user = current_user()
    ui.page_header("Tell us what went wrong", "We read every message. Write in English or Bahasa Melayu.", glow=True)
    with st.container(border=True):
        st.caption("Include what happened, the amount, the date and where (merchant, ATM or recipient). "
                   f"Demo: the bank's records end on 30 Sep 2026, so messages you send are dated {ops.DEMO_DAY}.")
        st.text_area("Your complaint", height=150, key="portal-text",
                     placeholder=EXAMPLES.get(user["customer_id"], "Describe what happened…"))
        c1, c2 = st.columns([1.2, 1])
        c1.button("Send to Teratai Bank", type="primary", key="portal-send", width="stretch", on_click=_send, args=(user,))
        if user["customer_id"] in EXAMPLES:
            c2.button("Use an example", key="portal-example", width="stretch",
                      on_click=_fill_example, args=(user["customer_id"],))
    if "portal-error" in st.session_state:
        ui.alert("warning", st.session_state.pop("portal-error").capitalize() + ".")
    cid = st.session_state.pop("portal-sent", None)
    if cid:
        case = wait_for(cid)
        st.write("")
        with st.container(border=True):
            if case:
                show(user, case, f"new-{cid}")
            else:
                ui.alert("info", f"We've received your complaint (reference {cid}). You'll find our reply under My complaints.")


def my_complaints():
    user = current_user()
    ui.page_header("My complaints", "Everything you've sent us, and our replies")
    rows = ops.cases(user=user)
    waiting = [c for c in ops.waiting_in_inbox(user["customer_id"]) if not any(r["complaint_id"] == c["complaint_id"] for r in rows)]
    if not rows and not waiting:
        ui.empty_state("No complaints yet", "Send one from New complaint and you'll see our reply here.")
        return
    if st.button("Refresh", key="portal-refresh", icon=":material/refresh:"):
        st.rerun()
    for c in waiting:
        with st.container(border=True):
            ui.render(f'<div class="tk-row"><span class="tk-title">{ui.esc(c["complaint_id"])}</span>'
                      f'{ui.badge("neutral", "Received", "•")}</div><p class="tk-sub">We are reading your message.</p>')
    for i, r in enumerate(sorted(rows, key=lambda r: r["created_at"], reverse=True)):
        case = store.get_case(r["complaint_id"])
        tone, icon, label, _ = CUSTOMER_STATUS.get(case["status"], ("neutral", "•", case["status"], ""))
        with st.expander(f"{case['complaint_id']} · {label} · {case['text'][:70]}", expanded=i == 0):
            show(user, case, f"mine-{case['complaint_id']}")
