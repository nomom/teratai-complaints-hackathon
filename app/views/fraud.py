"""Owner: C. Fraud analyst: the investigation workbench. Leads with the suspicious transaction and how it was
authorised; the customer only ever gets the holding reply, so the reply is secondary here.
Flow: acknowledge (holding reply) -> log investigation / recall -> record outcome.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views import case_view as cv
from app.views.common import current_user, queue_table, run_action

STAGES = ["NEW", "ACKNOWLEDGED", "INVESTIGATING", "CLOSED"]
AUTH = {   # how the payment was authorised -> (tone, explanation); strong auth is why it's investigated, not refunded
    "3DS-OTP": ("warning", "Approved with a one-time password"),
    "Chip+PIN": ("warning", "Approved with chip and PIN"),
    "App approval": ("warning", "Approved in the banking app"),
}


@st.cache_data(show_spinner=False)
def payers_into(account, exclude_customer):
    """Other customers who sent money to this account: a mule-account signal for scam transfers."""
    db = cv.bank().get_db()
    return len({t["customer_id"] for t in db.txns.values()
                if t.get("counterparty_account") == account and t["customer_id"] != exclude_customer})


def related(case, txn):
    """The customer's other transactions within 3 days of the disputed one."""
    db = cv.bank().get_db()
    when = dt.datetime.strptime(txn["txn_time"][:19], "%Y-%m-%d %H:%M:%S")
    rows = [t for t in db.txns_by_customer.get(case["customer_id"], [])
            if abs((t["time"] - when).total_seconds()) <= 3 * 86400]
    rows.sort(key=lambda t: t["time"])
    return pd.DataFrame([{
        "Time": t["txn_time"], "Transaction": t["txn_id"], "Channel": t["channel"],
        "Merchant / counterparty": t["merchant_or_counterparty"],
        "Amount": ui.money((-1 if t["direction"] == "DR" else 1) * float(t["amount_myr"])),
        "Auth": t.get("auth_method") or "None", "Status": t["status"],
        "Disputed": "◀" if t["txn_id"] == txn["txn_id"] else ""} for t in rows])


def suspicious(case, reveal):
    ev = case["record"]["decision"].get("evidence") or {}
    t = ev.get("txn")
    if not t:
        ui.alert("warning", "No transaction was matched. Investigate from the complaint text and the customer's history.")
        return None
    raw = cv.bank().get_txn(t["txn_id"]) or {}
    tone, why = AUTH.get(t.get("auth_method") or "", ("info", "No strong authentication recorded"))
    auth = ui.badge(tone, f'{t.get("auth_method") or "None"} · {why}', "🔐")
    pairs = [("Merchant / payee", ui.esc(t.get("merchant_or_counterparty"))), ("When", ui.esc(t.get("txn_time"))),
             ("Channel", ui.esc(t.get("channel"))), ("Country", ui.esc(t.get("merchant_country") or "—")),
             ("Status", ui.esc(t.get("status")))]
    if raw.get("counterparty_account"):
        acct = raw["counterparty_account"]
        n = payers_into(acct, case["customer_id"])
        pairs += [("Receiving account", ui.esc(acct if reveal else ui.mask(acct, 4))),
                  ("Receiving bank", ui.esc(raw.get("counterparty_bank") or "—")),
                  ("Other customers who paid it", ui.badge("error", f"{n} other customers", "⚑") if n
                   else ui.badge("neutral", "none in our data", "•"))]
    ui.render(ui.card(f'<p class="tk-label">Disputed amount</p><p class="tk-hero">{ui.esc(ui.money(t.get("amount_myr")))}</p>'
                      f'<div class="tk-row" style="margin:10px 0 14px 0">{auth}</div>{ui.kv(pairs)}',
                      f'Suspicious transaction · {t["txn_id"]}'))
    return t


def stage_strip(stage):
    parts = []
    for s in STAGES:
        i, cur = STAGES.index(s), STAGES.index(stage)
        tone, icon = ("accent", "●") if s == stage else (("success", "✓") if i < cur else ("neutral", "○"))
        parts.append(ui.badge(tone, ui.nice(s), icon))
    ui.render(f'<div class="tk-row" style="margin:6px 0 12px 0">{" ".join(parts)}</div>')


@st.dialog("Record the outcome and close")
def outcome_dialog(user, cid):
    outcome = st.radio("Outcome", ops.FRAUD_OUTCOMES, key=f"outcome-{cid}")
    reason = st.text_area("Summary for the record", key=f"outcome-why-{cid}")
    st.caption("The case closes as a fraud case. Any refund after a confirmed fraud follows the card-dispute process.")
    if st.button("Close case", type="primary", key=f"outcome-go-{cid}", disabled=not reason.strip()):
        run_action(ops.fraud_outcome, f"{cid} closed: {outcome}.", user, cid, outcome, reason)


@st.dialog("Escalate to a manager")
def escalate_dialog(user, cid, reply):
    reason = st.text_area("Why does a manager need to decide?", placeholder="e.g. high value; customer is vulnerable")
    if st.button("Escalate", type="primary", key=f"fesc-go-{cid}", disabled=not reason.strip()):
        run_action(ops.escalate, f"{cid} escalated to a manager.", user, cid, reply, reason)


def work(user, case):
    cid = case["complaint_id"]
    stage = ops.fraud_stage(cid)
    stage_strip(stage)
    if stage == "NEW":
        reply, problems = cv.reply_editor(case, f"fraud-{cid}", case["reply_text"], label="Holding reply to the customer")
        c1, c2 = st.columns([1.4, 1])
        if c1.button("Acknowledge & send holding reply", type="primary", key=f"ack-{cid}", width="stretch",
                     disabled=bool(problems)):
            run_action(ops.fraud_ack, f"{cid} acknowledged; the holding reply was sent.", user, cid, reply)
        if c2.button("Escalate to manager", key=f"fesc-{cid}", width="stretch"):
            escalate_dialog(user, cid, reply)
        return
    with st.form(f"note-{cid}", clear_on_submit=True, border=True):
        st.markdown("**Log investigation step**")
        kind = st.selectbox("Step", ops.FRAUD_NOTES, key=f"kind-{cid}")
        text = st.text_area("What was done", key=f"note-text-{cid}", height=90)
        if st.form_submit_button("Log step"):
            run_action(ops.fraud_note, f"{kind} logged on {cid}.", user, cid, kind, text)
    c1, c2 = st.columns([1.4, 1])
    if c1.button("Record outcome & close", type="primary", key=f"close-{cid}", width="stretch"):
        outcome_dialog(user, cid)
    if c2.button("Escalate to manager", key=f"fesc2-{cid}", width="stretch"):
        escalate_dialog(user, cid, case["reply_text"])


def render():
    user = current_user()
    ui.page_header("Fraud workbench", "Scams, and card payments the customer disputes that were approved with strong authentication")
    rows = ops.cases(["FRAUD_QUEUE"], user)
    if not rows:
        ui.empty_state("No open fraud cases", "Cases the agent routes to the fraud team appear here.")
        if st.button("Refresh", key="fraud-refresh"):
            st.rerun()
        return
    head, refresh = st.columns([2.4, 1], vertical_alignment="bottom")
    head.markdown(f"**{len(rows)} open** · select a row to open it")
    if refresh.button("Refresh", key="fraud-refresh", width="stretch", icon=":material/refresh:"):
        st.rerun()
    cid = queue_table(rows, "fraud-queue", extra_cols={"Stage": lambda r: ui.nice(ops.fraud_stage(r["complaint_id"]))})
    case = store.get_case(cid)
    st.divider()
    if not case or case["status"] != "FRAUD_QUEUE":
        ui.alert("info", f"{cid} has just left the queue.")
        return
    cv.header(case)
    reveal = st.toggle("Reveal account numbers", key=f"fraud-reveal-{cid}")
    txn = suspicious(case, reveal)
    work(user, case)
    cv.why(case)
    cv.agent_vs_staff(case)
    extra = []
    if txn:
        extra = [("Account activity ±3 days", lambda: st.dataframe(
            related(case, txn), hide_index=True, width="stretch",
            column_config={"Amount": st.column_config.TextColumn(alignment="right")}))]
    cv.explain(case, f"fraud-{cid}", extra_tabs=extra)
