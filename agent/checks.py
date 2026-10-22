"""Owner: B. CHECK step, in code: you can't use the model to check the model.

Every reply (LLM, template, or an officer's edit) must pass: IDs and amounts exist in the data, the decided refund is
stated and no other is promised, the language is right, no personal data such as age is disclosed, a fraud case is
not declared fraud before the fraud team has looked, and a reply with no money decision doesn't talk about refunds.
"""
from __future__ import annotations

import datetime as dt
import re

from . import tools
from .extract import detect_language
from .schemas import Decision

import check_reply as _starter_check  # noqa: E402  starter/check_reply.py (path set up by agent.tools)

def check(complaint: dict, decision: Decision, reply: str, lang: str) -> list[str]:
    """Return a list of problems; empty means VERIFIED."""
    tools.register_complaint(complaint)
    problems = _starter_check.check_reply(tools.get_db(), complaint["complaint_id"], reply)
    # The starter check allows any of the customer's transactions in the window; a reply may only name this case's
    for tid in sorted(set(re.findall(r"TXN-\d{7}", reply)) - case_txn_ids(decision)):
        if not any(tid in p for p in problems):
            problems.append(f"transaction {tid} is not part of this case's evidence")

    amounts = {round(float(a.replace(",", "")), 2) for a in re.findall(r"RM\s?([\d,]+(?:\.\d{1,2})?)", reply)}
    if decision.outcome == "REFUND" and round(decision.refund_amount_myr, 2) not in amounts:
        problems.append(f"reply does not state the decided refund RM{decision.refund_amount_myr:.2f}")
    if decision.outcome != "REFUND" and re.search(r"\b(will refund|akan memulangkan)\b", reply, re.I):
        problems.append(f"reply promises a refund but the outcome is {decision.outcome or 'not decided yet'}")
    if detect_language(reply) not in (lang, "MIXED"):
        problems.append(f"reply does not look like it is written in {lang}")
    for day in sorted(dates_in(reply, tools.received(complaint).year) - case_dates(complaint, decision)):
        problems.append(f"reply mentions {day:%d %b %Y}, which is not a date in this case's evidence")
    if AGE.search(reply):
        problems.append("reply discloses the customer's age or date of birth")
    if decision.outcome == "INVESTIGATE" and FRAUD_CONFIRMED.search(reply):
        problems.append("reply declares fraud before the fraud team has reviewed the case")
    if decision.outcome in ("INFO_ONLY", "") and REFUND_TALK.search(reply):
        problems.append("reply talks about a refund, but there is no money decision on this case")
    return problems


MONTHS = {m: i for i, names in enumerate([
    "jan january januari", "feb february februari", "mar march mac", "apr april", "may mei", "jun june",
    "jul july julai", "aug august ogos", "sep sept september", "oct october oktober", "nov november",
    "dec december disember"], start=1) for m in names.split()}
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:,?\s+(\d{{4}}))?\b", re.I)
# Month first ("September 13") is English only; skip names that are also words ("you may 5 times", "mar 3 tries")
_MONTH_FIRST = r"(" + "|".join(sorted((m for m in MONTHS if m not in {"may", "mar", "mac", "mei"}),
                                      key=len, reverse=True)) + r")\.?"
MONTH_DAY = re.compile(rf"\b{_MONTH_FIRST}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.I)
NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")       # with a year only: "24/7" is not a date


def dates_in(text: str, default_year: int) -> set[dt.date]:
    """Calendar dates written in the text, English or Malay. A date without a year takes `default_year`."""
    found = []
    found += [(int(d), MONTHS[m.lower()], y) for d, m, y in DAY_MONTH.findall(text)]
    found += [(int(d), MONTHS[m.lower()], y) for m, d, y in MONTH_DAY.findall(text)]
    found += [(int(d), int(m), y) for d, m, y in NUMERIC.findall(text)]
    out = set()
    for d, m, y in found:
        try:
            out.add(dt.date(int(y) if y else default_year, m, d))
        except ValueError:
            pass                                        # "31 Feb" is not a date
    return out


def case_dates(complaint: dict, decision: Decision) -> set[dt.date]:
    """Dates a reply may mention: this case's transactions, the day the complaint arrived, dates the customer wrote."""
    received = tools.received(complaint)
    days = {received.date()} | dates_in(complaint.get("text", ""), received.year)
    for tid in case_txn_ids(decision):
        t = tools.get_txn(tid)
        if t:
            days.add(t["time"].date())
            rev = tools.get_reversal(tid)
            if rev:
                days.add(rev["time"].date())
    return days


def case_txn_ids(decision: Decision) -> set[str]:
    """Transactions this case is about: the match, its twin or reversal, and the candidates matching considered."""
    ids = {decision.matched_txn_id, *decision.candidates}
    ids |= {(decision.evidence.get(k) or {}).get("txn_id") for k in ("txn", "twin", "reversal")}
    return ids - {"", None}


AGE = re.compile(r"\b(aged?|umur|berumur|usia)\s*:?\s*\d{1,3}\b|\b\d{1,3}\s*(years? old|tahun)\b|"
                 r"\b(date of birth|tarikh lahir)\b", re.I)
# Declaring this case fraud, not a general warning ("anyone asking for your OTP is a scam" is fine)
FRAUD_CONFIRMED = re.compile(
    r"\b(confirmed|identified|verified|established|determined) (as|to be) (a |an )?(fraud|scam|fraudulent)|"
    r"\b(transaction|transfer|payment|charge) (is|was) (a |an )?(fraud|scam|fraudulent)\b|"
    r"\b(dikenal pasti|disahkan|dipastikan) (sebagai )?(penipuan|scam)|"
    r"\b(transaksi|pindahan|bayaran) (ini|tersebut) (adalah|merupakan) (satu )?penipuan\b", re.I)
REFUND_TALK = re.compile(r"\b(refund\w*|reimburse\w*|compensat\w*|bayaran balik|pampasan|memulangkan)\b", re.I)
