"""Owner: B. UNDERSTAND step: complaint text -> Extraction (category, language, transaction clues).

Two paths with the same output:
  - extract_rules(): keyword/regex first pass, no LLM. Works offline, sets the floor.
  - extract_llm():   structured-output LLM call. Falls back to rules on any error.

TODO(B):
  - few-shot examples from data/labels_train.csv in the system prompt (category confusions first)
  - measure category and language accuracy per path: `python -m scripts.run_batch --split train --limit 200`
"""
from __future__ import annotations

import re

from . import llm, tools
from .dates import month_of
from .schemas import CATEGORIES, Extraction

KEYWORDS = [  # checked in order (from starter/baseline.py)
    ("SCAM_TRANSFER", ["scam", "tipu", "police", "polis", "safe account", "akaun selamat", "parcel", "bungkusan", "invest",
                       "part-time", "part time", "kerja sambilan", "emergency", "kecemasan", "romance", "lhdn", "court"]),
    ("ATM_NOT_DISPENSED", ["atm"]),
    ("DUPLICATE_CHARGE", ["twice", "two times", "dua kali", "2 kali", "double"]),
    ("UNAUTHORISED_CARD", ["did not make", "not authorise", "didn't make", "bukan saya", "tidak membuat", "tak buat",
                           "disputes a card", "don't recognise", "do not recognise", "tidak kenal"]),
    ("FEE_DISPUTE", ["fee", "charge", "caj", "yuran"]),
    ("FAILED_TRANSFER", ["transfer", "pindah", "duitnow", "ibg"]),
]
MALAY = {"saya", "dan", "tetapi", "tidak", "kepada", "pada", "akaun", "wang", "dengan", "untuk", "sila", "mohon",
         "kenapa", "telah", "sebanyak", "lepas", "semalam", "ini", "itu", "yang", "tak", "dicaj", "hari", "bantu", "anda", "kami"}
ENGLISH = {"the", "and", "my", "i", "was", "to", "but", "please", "for", "of", "is", "it", "on", "at", "this",
           "have", "not", "me", "why", "charged", "money", "help", "yesterday"}
APPROX = r"(about|around|approximately|approx\.?|roughly|almost|nearly|lebih kurang|kira-kira|sekitar|dalam)\s*"


def detect_language(text: str) -> str:
    words = re.findall(r"[a-z']+", text.lower())
    ms = sum(w in MALAY for w in words)
    en = sum(w in ENGLISH for w in words)
    if ms >= 2 and en >= 2:
        return "MIXED"
    return "MS" if ms >= 2 else "EN"


def reply_language(complaint: dict, written: str) -> str:
    """Policy rule (code, not LLM): as written; mixed or call-centre note -> customer's preferred_language."""
    if written == "MIXED" or complaint.get("channel") == "Call centre note":
        return tools.get_customer(complaint["customer_id"])["preferred_language"]
    return written


def extract_rules(complaint: dict) -> Extraction:
    text = (complaint.get("subject", "") + " " + complaint["text"]).strip()
    low = text.lower()
    category = next((c for c, words in KEYWORDS if any(w in low for w in words)), "SERVICE_QUALITY")

    amount, approx = None, False
    m = re.search(rf"({APPROX})?RM\s?([\d,]+(?:\.\d{{1,2}})?)", text, re.I)
    if m:
        amount = float(m.group(3).replace(",", ""))
        approx = bool(m.group(1))
    card = re.search(r"(?:ending|end(?:s|ing)? (?:with|in)|hujung|berakhir(?: dengan)?|last 4(?: digits)?)\D{0,6}(\d{4})", low)

    fee_type = ""
    if category == "FEE_DISPUTE":
        if re.search(r"credit card|kad kredit", low) and re.search(r"annual|tahunan", low):
            fee_type = "CC_ANNUAL"
        elif re.search(r"annual|tahunan", low):
            fee_type = "DEBIT_ANNUAL"
        elif re.search(r"service charge|monthly|bulanan|caj perkhidmatan", low):
            fee_type = "MONTHLY_SERVICE"

    return Extraction(
        category=category, language=detect_language(complaint["text"]),
        amount=amount, amount_approx=approx, card_last4=card.group(1) if card else "",
        date_phrase="", fee_type=fee_type,
        fee_month=month_of(low, tools.received(complaint)) if category == "FEE_DISPUTE" else "",
        source="rules",
    )


SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "language": {"type": "string", "enum": ["EN", "MS", "MIXED"]},
        "amount": {"type": ["number", "null"]},
        "amount_approx": {"type": "boolean"},
        "counterparty": {"type": "string"},
        "date_phrase": {"type": "string"},
        "card_last4": {"type": "string"},
        "fee_type": {"type": "string", "enum": ["", "MONTHLY_SERVICE", "DEBIT_ANNUAL", "CC_ANNUAL"]},
        "fee_month_phrase": {"type": "string"},
    },
    "required": ["category", "language", "amount", "amount_approx", "counterparty", "date_phrase", "card_last4",
                 "fee_type", "fee_month_phrase"],
    "additionalProperties": False,
}

SYSTEM = """You read customer complaints sent to a Malaysian bank (English, Malay or a mix) and extract structured fields.
Do not decide refunds. Copy clues as the customer wrote them; leave a field empty ("" or null) when it isn't stated.

Categories:
- DUPLICATE_CHARGE: a card purchase charged more than once
- FAILED_TRANSFER: a DuitNow/IBG transfer failed or didn't arrive but money left the account
- ATM_NOT_DISPENSED: an ATM gave less cash than requested
- UNAUTHORISED_CARD: the customer says they did not make a card transaction
- SCAM_TRANSFER: the customer was tricked into sending money themselves (fake police, job, parcel, investment, romance)
- FEE_DISPUTE: the customer disputes a bank fee
- SERVICE_QUALITY: branch, app, hotline or staff complaints with no money in dispute

language: EN, MS, or MIXED if the text uses both languages substantially.
date_phrase: the words that say when the transaction happened ("last Tuesday", "hari Sabtu lepas", "15 Sept"), or "".
amount_approx: true when the amount is hedged ("about", "lebih kurang", "kira-kira").
counterparty: merchant, recipient name, ATM location or biller.
fee_month_phrase: for fees, the month named ("June", "bulan Jun"), or ""."""
# TODO(B): append a handful of labelled examples here (few-shot) and keep this prefix stable so it caches.


def extract_llm(complaint: dict, usage: llm.Usage | None = None) -> Extraction:
    user = f"Channel: {complaint.get('channel', '')}\nSubject: {complaint.get('subject', '')}\nComplaint: {complaint['text']}"
    d = llm.complete_json(SYSTEM, user, SCHEMA, usage)
    recv = tools.received(complaint)
    return Extraction(
        category=d["category"], language=d["language"], amount=d["amount"], amount_approx=d["amount_approx"],
        counterparty=d["counterparty"], date_phrase=d["date_phrase"], card_last4=d["card_last4"][-4:],
        fee_type=d["fee_type"], fee_month=month_of(d["fee_month_phrase"], recv), source="llm",
    )


def extract(complaint: dict, usage: llm.Usage | None = None) -> Extraction:
    if llm.enabled():
        try:
            return extract_llm(complaint, usage)
        except Exception as e:  # noqa: BLE001 -- never lose a complaint over an LLM error
            ex = extract_rules(complaint)
            ex.source = f"rules (llm failed: {type(e).__name__})"
            return ex
    return extract_rules(complaint)
