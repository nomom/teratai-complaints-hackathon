"""Owner: C. The one workflow. The live app, the inbox worker and the 750-complaint batch all call process_complaint().

    UNDERSTAND (LLM/rules) ─┬─ COMPLAINT ─────► FIND (code) -> DECIDE (code) -> DRAFT -> CHECK (code) -> ROUTE (code)
                            ├─ NEEDS_DETAILS ─► ask the customer a follow-up question -> CHECK -> AWAITING_CUSTOMER
                            └─ OUT_OF_SCOPE ──► answer politely -> CHECK -> ANSWERED

Possible fraud never waits for a follow-up: a NEEDS_DETAILS message the extractor puts in a fraud category goes down
the complaint path to the fraud team. After MAX_FOLLOW_UPS unanswered rounds, the case goes to an officer.

A case awaiting the customer stays open with no decision (outcome and route ""): we are still gathering facts.
"""
from __future__ import annotations

import datetime as dt
import time

from . import checks, crosscheck, extract, llm, matching, policy, reply, tools
from .schemas import CaseRecord, Complaint, Decision

STATUS_BY_ROUTE = {"AUTO_RESOLVE": "RESOLVED","HUMAN_APPROVAL": "PENDING_APPROVAL", "FRAUD_TEAM": "FRAUD_QUEUE"}
MAX_FOLLOW_UPS = 2           # rounds of "please give us more details" before an officer takes over


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
        ex.category, ex.intent, ex.crosscheck = oracle_category, "COMPLAINT", {}
    trace[-1]["detail"] = ex.to_dict()
    lang = extract.reply_language(c, ex.language)
    follow_ups = int(c.get("follow_ups") or 0)

    if ex.intent == "OUT_OF_SCOPE":
        decision = _no_action(c, "SERVICE_QUALITY", "Not a banking complaint: answered on the complaints channel, no case action")
        draft = lambda fb="": reply.draft_out_of_scope(c, lang, usage, fb)          # noqa: E731
        template = lambda: reply.out_of_scope_template(c, lang)                     # noqa: E731
        status = "ANSWERED"
    elif (ex.intent == "NEEDS_DETAILS" and ex.category not in policy.FRAUD_CATEGORIES
          and follow_ups < MAX_FOLLOW_UPS):
        decision = _undecided(c, ex.category, f"Too general to act on (follow-up {follow_ups + 1} of {MAX_FOLLOW_UPS}): "
                                  f"asked the customer for {', '.join(ex.missing_info) or 'details'}")
        draft = lambda fb="": reply.draft_follow_up(c, ex.missing_info, lang, usage, fb)   # noqa: E731
        template = lambda: reply.follow_up_template(c, ex.missing_info, lang)              # noqa: E731
        status = "AWAITING_CUSTOMER"
    else:
        match = step("find_transaction", lambda: matching.find_transaction(c, ex))
        trace[-1]["detail"] = {"matched": match.txn["txn_id"] if match.txn else None, "candidates": match.candidates,
                               "flags": match.flags}
        if ex.intent == "NEEDS_DETAILS":           # fraud category, or follow-ups used up: never stall the case
            match.flags.append("DETAILS_STILL_MISSING" if follow_ups >= MAX_FOLLOW_UPS else "VAGUE_FRAUD_REPORT")
        if crosscheck.needs_officer(ex):           # LLM and rules disagreed and the second look didn't settle it
            match.flags.append(crosscheck.OFFICER_FLAG)
            match.reasons.append(crosscheck.officer_reason(ex))
        decision = step("decide", lambda: policy.decide(c, ex.category, match))
        trace[-1]["detail"] = {"outcome": decision.outcome, "refund": decision.refund_amount_myr,
                               "reasons": decision.reasons}
        draft = lambda fb="": reply.draft_reply(c, decision, lang, usage, fb)      # noqa: E731
        template = lambda: reply.draft_template(c, decision, lang)                 # noqa: E731
        status = None                                                              # set from the route below

    def attempt(name, feedback=""):
        """Draft once; record whether the LLM wrote it or the template stood in (an LLM failure falls back)."""
        before = len(usage.failures)
        out = step(name, lambda: draft(feedback))
        source = "llm" if llm.enabled() and len(usage.failures) == before else "template"
        trace[-1]["detail"] = {"source": source}
        return out, source

    rejected = []                                  # drafts the self-check turned down, kept for the audit
    text, source = attempt("draft_reply")
    problems = step("check", lambda: checks.check(c, decision, text, lang))
    if problems:                                   # redraft once with the problems as feedback (build guide step 5)
        rejected.append({"source": source, "text": text, "problems": problems})
        text, source = attempt("redraft", "; ".join(problems))
        problems = step("recheck", lambda: checks.check(c, decision, text, lang))
        if problems:                               # failed twice: a person decides; the template is their starting point
            rejected.append({"source": source, "text": text, "problems": problems})
            text, source = template(), "template"
            problems = checks.check(c, decision, text, lang)
    trace[-1]["detail"] = {"problems": problems}
    decision.evidence["reply"] = {"source": source, "language": lang,
                                  "language_why": extract.reply_language_why(c, ex.language),
                                  "rejected_drafts": rejected}

    # Nothing that failed the check goes out on its own: "redraft once, then flag it for a human"
    if len(rejected) == 2:
        decision.flags.append("DRAFT_REJECTED")    # both drafts failed; even a passing template waits for a person
    if problems:
        decision.flags.append("CHECK_FAILED")      # the reply in the box still fails: the officer must fix it
    if len(rejected) == 2 or problems:
        decision.route = policy.route(decision.outcome, decision.refund_amount_myr, decision.flags)
        status = None
    status = status or STATUS_BY_ROUTE[decision.route]
    trace.append({"step": "route", "ms": 0, "detail": {"intent": ex.intent, "route": decision.route, "status": status}})

    hours = int(tools.sla(decision.priority)["acknowledge_within_hours"])
    due = tools.received(c) + dt.timedelta(hours=hours)
    return CaseRecord(
        complaint=Complaint.from_dict(c), extraction=ex, decision=decision,
        category="SERVICE_QUALITY" if ex.intent == "OUT_OF_SCOPE" else ex.category,
        reply_language=lang, reply_text=text, check_problems=problems,
        status=status, sla_due=due.strftime("%Y-%m-%d %H:%M"),
        trace=trace, llm_usage=usage.to_dict(),
    )


def _no_action(c: dict, category: str, reason: str) -> Decision:
    """A message we answer without touching money: no transaction, no refund, auto-sent reply."""
    return Decision(matched_txn_id="", outcome="INFO_ONLY", refund_amount_myr=0.0,
                    priority=policy.priority(c, category), route="AUTO_RESOLVE", reasons=[reason],
                    evidence=policy.context(c, category))


def _undecided(c: dict, category: str, reason: str) -> Decision:
    """A case still gathering facts: no transaction, outcome or route yet. Priority is known, so the SLA clock runs."""
    return Decision(matched_txn_id="", outcome="", refund_amount_myr=0.0,
                    priority=policy.priority(c, category), route="", reasons=[reason],
                    evidence=policy.context(c, category))


def follow_up_complaint(original: dict, reply_text: str) -> dict:
    """Combine a case awaiting the customer with their reply into the complaint to reprocess.

    received_at stays the original time, so date phrases in the first message keep their meaning.
    TODO(B): a date phrase in the reply ("yesterday") is still read relative to the original time.
    """
    c = dict(original)
    c["text"] = f"{original['text']}\n\n[Customer follow-up] {reply_text.strip()}"
    c["follow_ups"] = int(original.get("follow_ups") or 0) + 1
    return c
