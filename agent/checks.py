"""Owner: B. CHECK step, in code: you can't use the model to check the model.

TODO(B): more checks the judges will try to break in the live round, e.g.
  - a REFUND reply that doesn't state the refund amount, or a non-REFUND reply that promises one
  - reply written in the wrong language
"""
from __future__ import annotations

import re

from . import tools
from .extract import detect_language
from .schemas import Decision

import check_reply as _starter_check  # noqa: E402  starter/check_reply.py (path set up by agent.tools)

def check(complaint: dict, decision: Decision, reply: str, lang: str) -> list[str]:
    """Return a list of problems; empty means VERIFIED."""
    tools.register_complaint(complaint)
    problems = _starter_check.check_reply(tools.get_db(), complaint["complaint_id"], reply)

    amounts = {round(float(a.replace(",", "")), 2) for a in re.findall(r"RM\s?([\d,]+(?:\.\d{1,2})?)", reply)}
    if decision.outcome == "REFUND" and round(decision.refund_amount_myr, 2) not in amounts:
        problems.append(f"reply does not state the decided refund RM{decision.refund_amount_myr:.2f}")
    if decision.outcome in ("DECLINE", "INVESTIGATE", "INFO_ONLY") and re.search(r"\b(will refund|akan memulangkan)\b", reply, re.I):
        problems.append(f"reply promises a refund but the outcome is {decision.outcome}")
    if detect_language(reply) not in (lang, "MIXED"):
        problems.append(f"reply does not look like it is written in {lang}")
    return problems
