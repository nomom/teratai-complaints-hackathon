"""Shared contracts between the three workstreams. Agree before changing a field: everyone depends on these.

    Extraction  (B -> A)  what the LLM/rules read out of the complaint text
    Decision    (A -> B, C) what code decided, with the evidence it used
    CaseRecord  (C)       what the app stores, queues and shows
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

CATEGORIES = ["DUPLICATE_CHARGE", "FAILED_TRANSFER", "ATM_NOT_DISPENSED", "UNAUTHORISED_CARD",
              "SCAM_TRANSFER", "FEE_DISPUTE", "SERVICE_QUALITY"]
OUTCOMES = ["REFUND", "DECLINE", "INVESTIGATE", "INFO_ONLY"]
ROUTES = ["AUTO_RESOLVE", "HUMAN_APPROVAL", "FRAUD_TEAM"]


@dataclass
class Complaint:
    complaint_id: str
    customer_id: str
    received_at: str          # "YYYY-MM-DD HH:MM", Malaysia time
    channel: str              # App chat | Email | Call centre note | Branch form | Social media DM
    text: str
    subject: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Complaint":
        return cls(**{k: (d.get(k) or "") for k in cls.__dataclass_fields__})


@dataclass
class Extraction:
    """Owner: B. Clues for finding the transaction. Every field is optional except category and language."""
    category: str
    language: str                       # EN | MS | MIXED (as written, before the preferred-language rule)
    amount: Optional[float] = None
    amount_approx: bool = False         # "about", "lebih kurang", "kira-kira"
    counterparty: str = ""              # merchant, recipient or ATM location, as the customer wrote it
    date_phrase: str = ""               # "last Tuesday", "hari Sabtu lepas", "15 September 2026"
    card_last4: str = ""
    fee_type: str = ""                  # MONTHLY_SERVICE | DEBIT_ANNUAL | CC_ANNUAL
    fee_month: str = ""                 # "2026-06"
    source: str = "rules"               # rules | llm

    def to_dict(self):
        return asdict(self)


@dataclass
class Decision:
    """Owner: A. Everything the leaderboard scores (except reply_language) comes from here."""
    matched_txn_id: str
    outcome: str
    refund_amount_myr: float
    priority: str
    route: str
    candidates: list = field(default_factory=list)   # other txn ids considered, best first
    evidence: dict = field(default_factory=dict)     # facts the decision used: txn, twin, reversal, journal, fee, age
    reasons: list = field(default_factory=list)      # human-readable "why", shown in the UI
    flags: list = field(default_factory=list)        # NO_MATCH, AMBIGUOUS_MATCH, CHECK_FAILED, ...

    def to_dict(self):
        return asdict(self)


@dataclass
class CaseRecord:
    """Owner: C. One row in the case store; also the source of a predictions.csv row."""
    complaint: Complaint
    extraction: Extraction
    decision: Decision
    category: str
    reply_language: str
    reply_text: str
    check_problems: list = field(default_factory=list)
    status: str = "NEW"                 # SENT | PENDING_APPROVAL | FRAUD_QUEUE | APPROVED | REJECTED
    sla_due: str = ""
    trace: list = field(default_factory=list)        # [{step, ms, detail}]
    llm_usage: dict = field(default_factory=dict)    # {input_tokens, output_tokens, calls}

    def to_dict(self):
        return asdict(self)

    def prediction_row(self):
        d = self.decision
        return {
            "complaint_id": self.complaint.complaint_id,
            "category": self.category,
            "matched_txn_id": d.matched_txn_id,
            "outcome": d.outcome,
            "refund_amount_myr": f"{d.refund_amount_myr:.2f}",
            "priority": d.priority,
            "reply_language": self.reply_language,
            "route": d.route,
            "reply_text": self.reply_text,
        }
