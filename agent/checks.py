"""Owner: B. CHECK step, in code: you can't use the model to check the model.

Every reply (LLM, template, or an officer's edit) must pass: IDs and amounts exist in the data, the decided refund is
stated and no other is promised, the language is right, no personal data such as age is disclosed, a fraud case is
not declared fraud before the fraud team has looked, and a reply with no money decision doesn't talk about refunds.
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
    if decision.outcome != "REFUND" and re.search(r"\b(will refund|akan memulangkan)\b", reply, re.I):
        problems.append(f"reply promises a refund but the outcome is {decision.outcome or 'not decided yet'}")
    if detect_language(reply) not in (lang, "MIXED"):
        problems.append(f"reply does not look like it is written in {lang}")
    if AGE.search(reply):
        problems.append("reply discloses the customer's age or date of birth")
    if decision.outcome == "INVESTIGATE" and FRAUD_CONFIRMED.search(reply):
        problems.append("reply declares fraud before the fraud team has reviewed the case")
    if decision.outcome in ("INFO_ONLY", "") and REFUND_TALK.search(reply):
        problems.append("reply talks about a refund, but there is no money decision on this case")
    return problems


AGE = re.compile(r"\b(aged?|umur|berumur|usia)\s*:?\s*\d{1,3}\b|\b\d{1,3}\s*(years? old|tahun)\b|"
                 r"\b(date of birth|tarikh lahir)\b", re.I)
# Declaring this case fraud, not a general warning ("anyone asking for your OTP is a scam" is fine)
FRAUD_CONFIRMED = re.compile(
    r"\b(confirmed|identified|verified|established|determined) (as|to be) (a |an )?(fraud|scam|fraudulent)|"
    r"\b(transaction|transfer|payment|charge) (is|was) (a |an )?(fraud|scam|fraudulent)\b|"
    r"\b(dikenal pasti|disahkan|dipastikan) (sebagai )?(penipuan|scam)|"
    r"\b(transaksi|pindahan|bayaran) (ini|tersebut) (adalah|merupakan) (satu )?penipuan\b", re.I)
REFUND_TALK = re.compile(r"\b(refund\w*|reimburse\w*|compensat\w*|bayaran balik|pampasan|memulangkan)\b", re.I)
