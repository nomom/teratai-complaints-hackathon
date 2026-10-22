"""Owner: B. Cross-check the LLM's category against the keyword rules, and settle disagreements with evidence.

    LLM category ─┬─ rules agree, or matched no keyword ──► keep it (recorded)
                  └─ rules matched a different category ──► second look:
                       the message + both categories, unlabelled (never "the rules said X")
                       + what each category would match in the customer's transactions (code facts)
                       the LLM picks one and quotes the message; code checks the quote is really there
                       ├─ quote checks out, confident enough ──► use its pick
                       └─ otherwise ──► keep the LLM's first category, flag for an officer

Stepping away from a fraud category needs high confidence: a missed scam is the costliest error. Strong scam
phrases never get here; they override the LLM outright (extract._fraud_safety_net).

Never raises: if the second look fails (timeout, budget, bad JSON), the case goes to an officer.
"""
from __future__ import annotations

import copy
import re

from . import llm, matching, tools
from .policy import FRAUD_CATEGORIES
from .schemas import CATEGORY_GUIDE, CONFIDENCE, Extraction

OFFICER_FLAG = "CROSSCHECK_UNRESOLVED"

SYSTEM = """Two readings of a message to a Malaysian bank's complaints channel disagree on its category.
Decide which of the two categories fits, from the customer's own words and the bank's records shown.

Categories:
""" + CATEGORY_GUIDE + """

Rules:
- Choose one of the two categories offered, even if neither is perfect.
- quote: copy the words from the message that best show your choice, exactly as written (a few words).
- The records show what each category would match in the customer's account. They support a reading; they do not
  prove it. "No matching transaction" makes that reading less likely, unless it is SERVICE_QUALITY.
- confidence: high only when the message is clear; low when it could be either."""


def schema(options: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": options}, "quote": {"type": "string"},
                       "confidence": {"type": "string", "enum": CONFIDENCE}},
        "required": ["category", "quote", "confidence"],
        "additionalProperties": False,
    }


def check(complaint: dict, ex: Extraction, rules_category: str | None, usage: llm.Usage | None = None) -> Extraction:
    if rules_category is None:
        ex.crosscheck |= {"result": "rules_no_opinion"}
        return ex
    if rules_category == ex.category:
        ex.crosscheck |= {"result": "agree"}
        return ex

    first = ex.category
    options = sorted({first, rules_category})          # fixed order: neither reading is marked as the first one
    facts = {c: _facts(complaint, ex, c) for c in options}
    record = {"result": "disagree", "llm": first, "rules": rules_category, "facts": facts}
    try:
        ans = llm.complete_json(SYSTEM, _prompt(complaint, options, facts), schema(options), usage)
    except llm.LLMError as e:
        ex.crosscheck |= {**record, "second_look": {"error": e.kind}, "resolution": "officer", "final": first}
        return ex

    quote_ok = _quote_in(ans["quote"], complaint)
    leaves_fraud = bool({first, rules_category} & FRAUD_CATEGORIES) and ans["category"] not in FRAUD_CATEGORIES
    if not quote_ok:
        why = "quote not found in the message"
    elif ans["confidence"] == "low":
        why = "low confidence"
    elif leaves_fraud and ans["confidence"] != "high":
        why = "stepping away from a fraud category needs high confidence"
    else:
        why = ""
    final = first if why else ans["category"]
    ex.category = final
    ex.crosscheck |= {**record, "second_look": ans, "quote_ok": quote_ok,
                     "resolution": "officer" if why else "second_look", "why": why, "final": final}
    return ex


def needs_officer(ex: Extraction) -> bool:
    return ex.crosscheck.get("resolution") == "officer"


def officer_reason(ex: Extraction) -> str:
    x = ex.crosscheck
    second = x.get("second_look", {})
    why = f"second look failed ({second['error']})" if "error" in second else x.get("why", "")
    return (f"Category unsure: the LLM read {x['llm']}, the keyword rules read {x['rules']}; {why}. "
            f"Kept {x['final']}: please confirm the category before approving")


def _facts(complaint: dict, ex: Extraction, category: str) -> str:
    """What this category would match in the customer's records, using A's matching as-is (read only)."""
    if category == "SERVICE_QUALITY":
        return "no transaction involved (service complaint)"
    tools.register_complaint(complaint)
    trial = copy.copy(ex)
    trial.category = category
    try:
        m = matching.find_transaction(complaint, trial)
    except Exception as e:  # noqa: BLE001 -- facts are a hint; a lookup bug must not stop the case
        return f"records unavailable ({type(e).__name__})"
    if not m.txn:
        return "no matching transaction in the 45 days before the message"
    t = tools.txn_summary(m.txn)
    shown = {k: t[k] for k in ("txn_time", "channel", "amount_myr", "merchant_or_counterparty", "auth_method",
                               "status") if t.get(k) not in ("", None)}
    return f"closest transaction {shown} ({len(m.candidates)} candidate(s) in total)"


def _prompt(complaint: dict, options: list[str], facts: dict) -> str:
    lines = [f"Channel: {complaint.get('channel', '')}", f"Subject: {complaint.get('subject', '')}",
             f"Message: {complaint['text']}", "", f"Categories to choose between: {' or '.join(options)}", "",
             "The customer's records:"]
    lines += [f"- If {c}: {facts[c]}" for c in options]
    return "\n".join(lines)


def _norm(s: str) -> str:
    """Compare words only: punctuation and spacing may differ ("RM1,500" vs "RM1500")."""
    return " ".join(re.findall(r"\w+", s.lower().replace(",", "")))


def _quote_in(quote: str, complaint: dict) -> bool:
    q = _norm(quote)
    return len(q) >= 4 and q in _norm(f"{complaint.get('subject', '')} {complaint['text']}")
