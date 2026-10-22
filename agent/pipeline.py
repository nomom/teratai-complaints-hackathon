"""Owner: C. The one workflow. The live app, the inbox worker and the 750-complaint batch all call process_complaint().

    UNDERSTAND (LLM/rules) -> FIND (code) -> DECIDE (code) -> DRAFT (LLM/template) -> CHECK (code) -> ROUTE (code)
"""
from __future__ import annotations

import datetime as dt
import time

from . import checks, extract, llm, matching, policy, reply, tools
from .schemas import CaseRecord, Complaint

STATUS_BY_ROUTE = {"AUTO_RESOLVE": "SENT", "HUMAN_APPROVAL": "PENDING_APPROVAL", "FRAUD_TEAM": "FRAUD_QUEUE"}


def process_complaint(c: dict, oracle_category: str | None = None) -> CaseRecord:
    """`oracle_category` (training only) skips category errors so A can measure matching + policy on their own."""
    tools.get_db()
    tools.register_complaint(c)
    usage = llm.Usage()
    trace = []

    def step(name, fn):
        t0 = time.perf_counter()
        out = fn()
        trace.append({"step": name, "ms": round((time.perf_counter() - t0) * 1000, 1)})
        return out

    ex = step("understand", lambda: extract.extract(c, usage))
    if oracle_category:
        ex.category = oracle_category
    trace[-1]["detail"] = ex.to_dict()

    match = step("find_transaction", lambda: matching.find_transaction(c, ex))
    trace[-1]["detail"] = {"matched": match.txn["txn_id"] if match.txn else None, "candidates": match.candidates,
                           "flags": match.flags}

    decision = step("decide", lambda: policy.decide(c, ex.category, match))
    trace[-1]["detail"] = {"outcome": decision.outcome, "refund": decision.refund_amount_myr, "reasons": decision.reasons}

    lang = extract.reply_language(c, ex.language)
    text = step("draft_reply", lambda: reply.draft_reply(c, decision, lang, usage))
    problems = step("check", lambda: checks.check(c, decision, text, lang))
    if problems:                                   # redraft once with the problems as feedback, then fall back
        text = step("redraft", lambda: reply.draft_reply(c, decision, lang, usage, feedback="; ".join(problems)))
        problems = step("recheck", lambda: checks.check(c, decision, text, lang))
        if problems:
            text = reply.draft_template(c, decision, lang)
            problems = checks.check(c, decision, text, lang)
    trace[-1]["detail"] = {"problems": problems}

    if problems:
        decision.flags.append("CHECK_FAILED")
        decision.route = policy.route(decision.outcome, decision.refund_amount_myr, decision.flags)
    trace.append({"step": "route", "ms": 0, "detail": {"route": decision.route}})

    hours = int(tools.sla(decision.priority)["acknowledge_within_hours"])
    due = tools.received(c) + dt.timedelta(hours=hours)
    return CaseRecord(
        complaint=Complaint.from_dict(c), extraction=ex, decision=decision, category=ex.category,
        reply_language=lang, reply_text=text, check_problems=problems,
        status=STATUS_BY_ROUTE[decision.route], sla_due=due.strftime("%Y-%m-%d %H:%M"),
        trace=trace, llm_usage=usage.to_dict(),
    )
