"""Owner: C. The one case view every role sees. Pages add their own actions; the explanation is always the same:
header -> decision -> why -> agent vs staff -> complaint, then Evidence / Trace / Audit tabs.
"""
import json

import streamlit as st

from app import ops
from app import ui_kit as ui

ROUTE_LABEL = {"AUTO_RESOLVE": "Auto-resolve", "HUMAN_APPROVAL": "Human approval", "FRAUD_TEAM": "Fraud team"}


@st.cache_resource(show_spinner="Loading bank data…")
def bank():
    """The CSVs, loaded once per server process (agent.tools caches them too)."""
    from agent import tools
    tools.get_db()
    return tools


def header(case):
    rec = case["record"]
    age = rec["decision"].get("evidence", {}).get("customer_age")
    vuln = ui.badge("info", f"Age {age}: priority raised", "♿") if age and age >= 65 else ""
    lang = ui.badge("neutral", f"Reply {case['reply_language']}", "文")
    ui.render(f'<div class="tk-row" style="margin-bottom:6px"><span class="tk-title">{ui.esc(case["complaint_id"])}</span>'
              f'{ui.status_badge(case["status"])}{ui.priority_badge(case["priority"])}'
              f'{ui.sla_badge(ops.sla_left(case))}{lang}{vuln}</div>'
              f'<p class="tk-sub">{ui.esc(case["channel"])} · received {ui.esc(case["received_at"])} · '
              f'customer {ui.esc(case["customer_id"])}</p>')


def decision_strip(case):
    if not case["outcome"]:
        ui.alert("info", "No decision yet: the agent asked the customer for details and is waiting for their reply.")
    ui.render(ui.grid([
        ui.tile("Category", ui.esc(ui.nice(case["category"]))),
        ui.tile("Matched transaction", ui.esc(case["matched_txn_id"] or "—")),
        ui.tile("Outcome", ui.esc(ui.nice(case["outcome"]) if case["outcome"] else "—")),
        ui.tile("Refund", f'<span class="tk-num">{ui.esc(ui.money(case["refund_amount_myr"]))}</span>'),
        ui.tile("Route", ui.esc(ROUTE_LABEL.get(case["route"], "—"))),
    ]))


def why(case):
    rec = case["record"]
    reasons = rec["decision"].get("reasons") or ["No reasons recorded"]
    flags = json.loads(case["flags"] or "[]")
    flag_html = "".join(ui.badge("warning", ui.nice(f), "!") for f in flags)
    body = '<ul class="tk-why">' + "".join(f"<li>{ui.esc(r)}</li>" for r in reasons) + "</ul>"
    if flag_html:
        body += f'<div class="tk-row" style="margin-top:10px">{flag_html}</div>'
    ex = rec.get("extraction", {})
    src = ex.get("source", "rules")
    body += (f'<p class="tk-sub" style="margin-top:10px">Read by {ui.esc(src)}'
             f'{" · " + ui.esc(ex["confidence"]) + " confidence" if ex.get("confidence") else ""}'
             f' · intent {ui.esc(ui.nice(ex.get("intent", "COMPLAINT")))}</p>')
    ui.render(ui.card(body, "Why the agent decided this"))


def agent_vs_staff(case):
    """The agent's decision is never overwritten: show it next to what a person did."""
    agent = f'{ui.esc(ui.nice(case["outcome"]) if case["outcome"] else "No decision")} · ' \
            f'{ui.esc(ui.money(case["refund_amount_myr"]))} · {ui.esc(ROUTE_LABEL.get(case["route"], "—"))}'
    fin = ops.final_action(case["complaint_id"])
    esc_ = ops.escalation(case["complaint_id"]) if case["status"] == ops.ESCALATED else None
    if fin:
        user = ops.get_user(fin["user_id"]) or {"name": fin["user_id"]}
        detail = {"approved": "Approved & sent", "rejected": "Rejected", "acknowledged": "Acknowledged (holding reply sent)",
                  "fraud_outcome": "Fraud outcome recorded"}[fin["action"]]
        edited = " · reply edited" if fin["reply_text"] and fin["reply_text"] != case["reply_text"] else ""
        staff = f'{ui.esc(detail)} by {ui.esc(user["name"])} · {ui.esc(fin["ts"])}{ui.esc(edited)}'
        if fin["reason"]:
            staff += f'<br><span class="tk-muted">Reason: {ui.esc(fin["reason"])}</span>'
    elif esc_:
        user = ops.get_user(esc_["user_id"]) or {"name": esc_["user_id"]}
        staff = f'Escalated by {ui.esc(user["name"])} · {ui.esc(esc_["ts"])}<br>' \
                f'<span class="tk-muted">Reason: {ui.esc(esc_["reason"])}</span>'
    elif case["status"] in ("RESOLVED", "ANSWERED"):
        staff = '<span class="tk-muted">No person needed: the agent sent the reply</span>'
    else:
        staff = '<span class="tk-muted">Waiting for a person</span>'
    ui.render(ui.card(ui.kv([("Agent proposed", agent), ("Staff final", staff)]), "Agent vs staff"))


def complaint_block(case, key):
    cust = bank().get_customer(case["customer_id"]) or {}
    reveal = st.toggle("Reveal customer details", key=f"reveal-{key}",
                       help="Customer and account details are masked by default.")
    name = cust.get("full_name", "—") if reveal else ui.mask(cust.get("full_name", ""), 3)
    email = cust.get("email", "—") if reveal else ui.mask(cust.get("email", ""), 12)
    subject = f'<p class="tk-sub">Subject: {ui.esc(case["record"]["complaint"].get("subject"))}</p>' \
        if case["record"]["complaint"].get("subject") else ""
    pairs = [("Customer", ui.esc(name)), ("Email", ui.esc(email)),
             ("Segment", ui.esc(cust.get("segment", "—"))), ("Preferred language", ui.esc(cust.get("preferred_language", "—")))]
    ui.render(ui.card(f'{subject}<p class="tk-quote">{ui.esc(case["text"])}</p>'
                      f'<div style="margin-top:12px">{ui.kv(pairs)}</div>', "Complaint"))
    return reveal


def txn_card(t, title, reveal):
    if not t:
        return ""
    pairs = [("Transaction", ui.esc(t.get("txn_id"))), ("Time", ui.esc(t.get("txn_time"))),
             ("Channel", ui.esc(t.get("channel"))), ("Merchant / counterparty", ui.esc(t.get("merchant_or_counterparty"))),
             ("Amount", f'<span class="tk-num">{ui.esc(ui.money(t.get("amount_myr")))}</span>'),
             ("Status", ui.esc(t.get("status"))), ("Authentication", ui.esc(t.get("auth_method") or "None"))]
    if t.get("card_last4"):
        pairs.append(("Card", ui.esc(("•••• " + t["card_last4"]) if reveal else "•••• ••••")))
    if t.get("account_id"):
        pairs.append(("Account", ui.esc(t["account_id"] if reveal else ui.mask(t["account_id"], 2))))
    if t.get("merchant_country"):
        pairs.append(("Country", ui.esc(t["merchant_country"])))
    if t.get("description"):
        pairs.append(("Description", ui.esc(t["description"])))
    return ui.card(ui.kv(pairs), title)


def evidence_tab(case, reveal):
    ev = case["record"]["decision"].get("evidence") or {}
    blocks = [txn_card(ev.get("txn"), "Matched transaction", reveal),
              txn_card(ev.get("twin"), "Identical earlier charge (twin)", reveal),
              txn_card(ev.get("reversal"), "Reversal already made", reveal)]
    j = ev.get("atm_journal")
    if j:
        blocks.append(ui.card(ui.kv([
            ("ATM", ui.esc(f'{j.get("atm_id")} · {j.get("atm_location")}')),
            ("Requested", f'<span class="tk-num">{ui.esc(ui.money(j.get("requested_myr")))}</span>'),
            ("Dispensed", f'<span class="tk-num">{ui.esc(ui.money(j.get("dispensed_myr")))}</span>'),
            ("Journal status", ui.esc(j.get("journal_status")))]), "ATM journal"))
    if "fee_due" in ev:
        blocks.append(ui.card(ui.kv([("Fee that should have been charged",
                                      f'<span class="tk-num">{ui.esc(ui.money(ev["fee_due"]))}</span>')]), "Fee schedule"))
    if ev.get("customer_age") is not None:
        blocks.append(ui.card(ui.kv([("Customer age on the day received", ui.esc(ev["customer_age"]))]), "Customer"))
    cands = ev.get("candidates") or []
    if cands:
        rows = "".join(f'<dt>{ui.esc(c[1] if isinstance(c, (list, tuple)) else c)}</dt>'
                       f'<dd>score {ui.esc(c[0] if isinstance(c, (list, tuple)) else "—")}</dd>' for c in cands)
        blocks.append(ui.card(f'<dl class="tk-kv">{rows}</dl>', "Transactions considered (best first)"))
    blocks = [b for b in blocks if b]
    if blocks:
        ui.render("".join(blocks))
    else:
        ui.empty_state("No evidence", "No transaction was involved in this decision.")


def trace_tab(case):
    rec = case["record"]
    steps = rec.get("trace") or []
    if not steps:
        ui.empty_state("No trace recorded")
        return
    longest = max((float(s.get("ms") or 0) for s in steps), default=1) or 1
    total = sum(float(s.get("ms") or 0) for s in steps)
    li = "".join(f'<li><span>{ui.esc(ui.nice(s["step"]))}</span>'
                 f'<span class="tk-bar"><span style="width:{max(2, 100 * float(s.get("ms") or 0) / longest):.0f}%"></span></span>'
                 f'<span class="tk-num tk-muted" style="text-align:right">{float(s.get("ms") or 0):.1f} ms</span></li>'
                 for s in steps)
    u = rec.get("llm_usage") or {}
    llm = (f'{u.get("calls", 0)} LLM calls · {u.get("input_tokens", 0):,} in / {u.get("output_tokens", 0):,} out tokens'
           f'{" · " + ui.esc(u["model"]) if u.get("model") and u.get("calls") else ""}')
    fails = u.get("failures") or []
    ui.render(ui.card(f'<ul class="tk-steps">{li}</ul><p class="tk-sub" style="margin-top:12px">'
                      f'Total {total:.1f} ms · {ui.esc(llm)}</p>', "Pipeline steps"))
    if fails:
        ui.alert("warning", "LLM fell back to rules on this case", [json.dumps(f) for f in fails])
    with st.expander("Raw trace (JSON)"):
        st.json({"trace": steps, "llm_usage": u, "extraction": rec.get("extraction")})


AUDIT_LABEL = {"taken_in": "Taken in", "decided": "Agent decided", "processed": "Agent processed",
               "reply_sent": "Reply sent", "question_sent": "Follow-up question sent", "customer_replied": "Customer replied",
               "approved": "Approved", "rejected": "Rejected", "escalated": "Escalated to manager",
               "send_blocked": "Send blocked by self-check", "sent_back": "Sent back to the agent",
               "acknowledged": "Acknowledged", "fraud_outcome": "Fraud outcome recorded",
               "returned": "Returned to the team by a manager"}


def audit_tab(case):
    items = []
    for a in case["audit"]:
        try:
            d = json.loads(a["detail"])
            text = " · ".join(f"{k}: {v}" for k, v in d.items() if v not in (None, "", [])) if isinstance(d, dict) else str(d)
        except (TypeError, ValueError):
            text = a["detail"] or ""
        cls = "tk-t-staff" if a["actor"] not in ("agent", "customer") else ""
        label = AUDIT_LABEL.get(a["action"], ui.nice(a["action"]))
        items.append(f'<li class="{cls}"><span class="tk-ts">{ui.esc(a["ts"])} · {ui.esc(a["actor"])}</span><br>'
                     f'<strong>{ui.esc(label)}</strong><div class="tk-d">{ui.esc(text)}</div></li>')
    if items:
        ui.render(ui.card(f'<ul class="tk-timeline">{"".join(items)}</ul>', "Audit log (append-only)"))
    else:
        ui.empty_state("No audit entries yet")


def explain(case, key, extra_tabs=None):
    """Everything below the actions: complaint, then the evidence / trace / audit tabs."""
    reveal = complaint_block(case, key)
    names = ["Evidence", "Trace", "Audit log"] + [n for n, _ in (extra_tabs or [])]
    tabs = st.tabs(names)
    with tabs[0]:
        evidence_tab(case, reveal)
    with tabs[1]:
        trace_tab(case)
    with tabs[2]:
        audit_tab(case)
    for tab, (_, fn) in zip(tabs[3:], extra_tabs or []):
        with tab:
            fn()


def reply_editor(case, key, initial, editable=True, label="Reply to the customer"):
    """Reply box with a live self-check. Returns (text, problems)."""
    text = st.text_area(label, initial or "", height=190, key=f"reply-{key}", disabled=not editable)
    problems = ops.recheck(case, text) if text.strip() else ["the reply is empty"]
    ui.render(f'<div class="tk-row">{ui.check_badge(problems)}'
              f'{ui.badge("neutral", "edited", "✎") if text != (case["reply_text"] or "") else ""}</div>')
    if problems:
        ui.alert("error", "This reply can't be sent until it passes the self-check:", problems)
    return text, problems


def read_only(case, key):
    """The full case for viewers who can't act on it."""
    header(case)
    decision_strip(case)
    why(case)
    agent_vs_staff(case)
    reply = ops.final_action(case["complaint_id"])
    sent = reply["reply_text"] if reply and reply.get("reply_text") else case["reply_text"]
    st.text_area("Reply", sent or "", height=170, disabled=True, key=f"ro-reply-{key}")
    ui.render(ui.check_badge(case["record"].get("check_problems")))
    explain(case, key)
