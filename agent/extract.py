"""Owner: B. UNDERSTAND step: complaint text -> Extraction (category, language, transaction clues).

Two paths with the same output:
  - extract_rules(): keyword/regex first pass, no LLM. Works offline, sets the floor.
  - extract_llm():   structured-output LLM call. Falls back to rules on any error.

TODO(B): with an API key, measure the LLM path against the rules (`run_batch --split train --sample 200`).
The rules score 100% on category and language on train, so the LLM must earn its place on unseen phrasing.
"""
from __future__ import annotations

import re

from . import llm, tools
from .dates import month_of
from .schemas import CATEGORIES, CONFIDENCE, INTENTS, Extraction

MISSING_INFO = ["what_happened", "transaction_type", "date", "amount", "merchant_or_recipient", "card_last4"]

KEYWORDS = [  # checked in order: fraud first, so a scam that mentions a transfer is never a FAILED_TRANSFER
    ("SCAM_TRANSFER", ["scam", "tipu", "police", "polis", "safe account", "akaun selamat", "parcel", "bungkusan", "invest",
                       "part-time", "part time", "kerja sambilan", "emergency", "kecemasan", "romance", "lhdn", "court",
                       "melabur", "pelaburan", "deceived", "acquaintance", "kenalan dalam talian"]),
    ("ATM_NOT_DISPENSED", ["atm", "withdrew", "withdraw", "mengeluarkan", "dispense", "duit tak keluar",
                           "wang tidak keluar", "did not give me the cash"]),
    ("DUPLICATE_CHARGE", ["twice", "two times", "dua kali", "2 kali", "double"]),
    ("UNAUTHORISED_CARD", ["did not make", "not authorise", "didn't make", "bukan saya", "tidak membuat", "tak buat",
                           "disputes a card", "don't recognise", "do not recognise", "tidak kenal"]),
    ("FEE_DISPUTE", ["fee", "charge", "caj", "yuran"]),
    ("FAILED_TRANSFER", ["transfer", "pindah", "duitnow", "ibg"]),
]
# Language: Malay words count anywhere; English words only in lowercase (or as the first word), because
# capitalised English is usually part of a name ("Shah Alam Branch", "BETZONE ONLINE"). Colloquial messages that
# mix the two ("app asyik logout sendiri 3 hari dah") are MIXED, and get a reply in the preferred language.
MALAY = set("""
saya dan tetapi tidak kepada pada akaun wang dengan untuk sila mohon kenapa telah sebanyak lepas semalam ini itu yang
tak dicaj hari bantu anda kami di sudah mesin cawangan rosak seminggu tunai ke dari dalam ada tiada boleh bayar bil
kena tolak duit keluar masuk pun dah kat je nak tapi ni lah tu orang suruh dia ya tolong segera terima kasih
mengeluarkan sepenuhnya tetap ditolak semak pulangkan harap dapat diselesaikan bulan kad tahunan perkhidmatan beli
sekali kali dua siapa guna buat asyik sendiri tunggu jam teruk betul angkat minta kawan barang haram rasa tipu melabur
skim pelaburan kumpulan sekarang hilang pindahkan berakhir hujung jumlah tarikh bila tahu mahal sangat setuju pernah
baru lain percuma mengapa adakah belum lagi juga atau oleh kerana sebab pindahan sampai penerima baki berkurang
seseorang telefon kata atas nama mengandungi terlarang perlu denda menerima panggilan daripada lelaki mengaku pegawai
mengatakan terlibat kes pengubahan kenalan talian perubatan terus membuat pembayaran sekat kecemasan
""".split())
ENGLISH = set("""
the and my i was to but please for of is it on at this have not me why charged money help yesterday an in with from
your you we our they he she did didn't do does no yes today last week month day account card transfer received
deducted debited withdrew machine give gave cash still refund check advise thank thanks kindly assist resolve quickly
whole amount all dispense same been has had would could should will can there their which what when who how never
twice each only once made make bought purchase called customer reports asks recover being into by online acquaintance
distressed disputes says possession app logout call hotline branch staff rude service monthly annual fee charge
urgent repair cdm pls asap
""".split())
APPROX = r"(about|around|approximately|approx\.?|roughly|almost|nearly|lebih kurang|kira-kira|sekitar|dalam)\s*"


def detect_language(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text)
    ms = sum(w.lower() in MALAY for w in words)
    en = sum(w.lower() in ENGLISH and (w.islower() or w == "I" or i == 0) for i, w in enumerate(words))
    if ms and en:
        return "MIXED"
    return "MS" if ms > en else "EN"


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
        "intent": {"type": "string", "enum": INTENTS},
        "confidence": {"type": "string", "enum": CONFIDENCE},
        "missing_info": {"type": "array", "items": {"type": "string", "enum": MISSING_INFO}},
    },
    "required": ["intent", "category", "language", "confidence", "missing_info", "amount", "amount_approx",
                 "counterparty", "date_phrase", "card_last4", "fee_type", "fee_month_phrase"],
    "additionalProperties": False,
}

SYSTEM = """You read messages sent to a Malaysian bank's complaints channel (English, Malay or a mix) and extract structured fields.
Do not decide refunds. Copy clues as the customer wrote them; leave a field empty ("" or null) when it isn't stated.
A message may contain the original complaint followed by "[Customer follow-up]" replies: read them together as one case.

intent (decide this first):
- COMPLAINT: the customer describes a specific problem, even if some details (amount, date) are missing.
  "I was charged twice at GoRide" is a COMPLAINT. Anything that could be fraud or a scam is ALWAYS a COMPLAINT.
- NEEDS_DETAILS: a complaint, greeting or request for help so general that you cannot tell what went wrong,
  e.g. "my account has a problem", "I want to complain", "hi, need help". List what to ask for in missing_info.
- OUT_OF_SCOPE: not a banking complaint at all: weather, chit-chat, general knowledge, questions about bank
  products or rates, requests for advice.
Still fill category with the closest match for every intent (SERVICE_QUALITY when nothing fits).

confidence: how sure you are of intent and category: high, medium or low.
missing_info: for NEEDS_DETAILS only (else []): what the customer should tell us. Use: what_happened, transaction_type,
date, amount, merchant_or_recipient, card_last4.

Categories:
- DUPLICATE_CHARGE: a card purchase charged more than once
- FAILED_TRANSFER: a DuitNow/IBG transfer failed or didn't arrive but money left the account
- ATM_NOT_DISPENSED: an ATM gave less cash than requested
- UNAUTHORISED_CARD: the customer says they did not make a card transaction
- SCAM_TRANSFER: the customer was tricked into sending money themselves (fake police, job, parcel, investment, romance)
- FEE_DISPUTE: the customer disputes a bank fee
- SERVICE_QUALITY: branch, app, hotline or staff complaints with no money in dispute

Watch for these, which are easy to miss:
- An ATM complaint need not say "ATM": "the machine did not dispense", "I withdrew ... did not give me the cash",
  "saya mengeluarkan ... wang tidak keluar", "withdraw ... duit tak keluar full" are all ATM_NOT_DISPENSED.
- Money the customer sent because someone tricked them is SCAM_TRANSFER even if it reads like a transfer:
  investment schemes ("skim pelaburan", "melabur", returns that cannot be withdrawn), an online friend or
  acquaintance asking for money, fake police/court/LHDN calls, parcel fines, part-time job deposits.

language: how the customer wrote, not their name or the bank's place names.
- EN or MS: written in one language. English words inside a name ("Shah Alam Branch", "BETZONE ONLINE") don't count.
- MIXED: colloquial Malay-English mixing, e.g. "card saya kena charge 2 kali", "app asyik logout sendiri 3 hari dah".
date_phrase: the words that say when the transaction happened ("last Tuesday", "hari Sabtu lepas", "15 Sept"), or "".
amount_approx: true when the amount is hedged ("about", "lebih kurang", "kira-kira", "dalam RM400").
counterparty: merchant, recipient name, ATM location or biller.
fee_month_phrase: for fees, the month named ("June", "bulan Jun"), or "".

Examples (input, then the JSON to return; fields not shown are "", null, false or [] as appropriate):

Channel: Social media DM | Complaint: Salam, withdraw RM500.00 kat Klang Mall last Tuesday, duit tak keluar full. Mohon bantu, urgent.
{"intent": "COMPLAINT", "category": "ATM_NOT_DISPENSED", "language": "MIXED", "confidence": "high", "amount": 500.0, "counterparty": "Klang Mall", "date_phrase": "last Tuesday"}

Channel: App chat | Complaint: Mesin ATM di Shah Alam Branch tidak mengeluarkan wang RM 500.00 hari Isnin lepas tetapi akaun saya ditolak.
{"intent": "COMPLAINT", "category": "ATM_NOT_DISPENSED", "language": "MS", "confidence": "high", "amount": 500.0, "counterparty": "Shah Alam Branch", "date_phrase": "hari Isnin lepas"}

Channel: App chat | Complaint: Saya melabur RM4,042.06 dalam skim pelaburan dari kumpulan chat dan pindahkan kepada Muthu hari Ahad lepas. Sekarang tak boleh keluarkan duit dan admin hilang.
{"intent": "COMPLAINT", "category": "SCAM_TRANSFER", "language": "MS", "confidence": "high", "amount": 4042.06, "counterparty": "Muthu", "date_phrase": "hari Ahad lepas"}

Channel: Call centre note | Complaint: Customer called, distressed. Reports being deceived by an online acquaintance into transferring about RM5,500 to Shalini a/p Krishnan on 22/08/2026. Asks for help to recover the money.
{"intent": "COMPLAINT", "category": "SCAM_TRANSFER", "language": "EN", "confidence": "high", "amount": 5500.0, "amount_approx": true, "counterparty": "Shalini a/p Krishnan", "date_phrase": "22/08/2026"}

Channel: App chat | Complaint: Hi, kenapa ada annual fee credit card RM150 bulan Julai? Bank lain free je. Mohon bantu, urgent.
{"intent": "COMPLAINT", "category": "FEE_DISPUTE", "language": "MIXED", "confidence": "high", "amount": 150.0, "fee_type": "CC_ANNUAL", "fee_month_phrase": "bulan Julai"}

Channel: App chat | Complaint: Hi, I have a problem with my account. Please help.
{"intent": "NEEDS_DETAILS", "category": "SERVICE_QUALITY", "language": "EN", "confidence": "medium", "missing_info": ["what_happened", "date", "amount"]}

Channel: Email | Complaint: Boleh tak bagitahu cuaca esok di KL?
{"intent": "OUT_OF_SCOPE", "category": "SERVICE_QUALITY", "language": "MS", "confidence": "high"}"""
# Keep SYSTEM fixed (no per-complaint text in it) so providers can cache the prefix across complaints.


def extract_llm(complaint: dict, usage: llm.Usage | None = None) -> Extraction:
    user = f"Channel: {complaint.get('channel', '')}\nSubject: {complaint.get('subject', '')}\nComplaint: {complaint['text']}"
    d = llm.complete_json(SYSTEM, user, SCHEMA, usage)
    recv = tools.received(complaint)
    return Extraction(
        category=d["category"], language=d["language"], amount=d["amount"], amount_approx=d["amount_approx"],
        counterparty=d["counterparty"], date_phrase=d["date_phrase"], card_last4=d["card_last4"][-4:],
        fee_type=d["fee_type"], fee_month=month_of(d["fee_month_phrase"], recv),
        intent=d["intent"], confidence=d["confidence"],
        missing_info=d["missing_info"] if d["intent"] == "NEEDS_DETAILS" else [], source="llm",
    )


def extract(complaint: dict, usage: llm.Usage | None = None) -> Extraction:
    """The rules path always returns intent COMPLAINT: only the LLM can tell a vague or off-topic message apart."""
    if llm.enabled():
        try:
            return _fraud_safety_net(complaint, extract_llm(complaint, usage))
        except llm.LLMError as e:          # never lose a complaint over an LLM error
            reason = e.kind
        except Exception as e:  # noqa: BLE001 -- e.g. a bug in parsing; still fall back, but say so
            reason = f"unexpected {type(e).__name__}"
            if usage is not None:
                usage.failures.append("unexpected")
        ex = extract_rules(complaint)
        ex.source = f"rules (llm failed: {reason})"
        return ex
    return extract_rules(complaint)


def _fraud_safety_net(complaint: dict, ex: Extraction) -> Extraction:
    """Scam wording outranks the LLM: a missed scam is a critical error and the worst outcome for the customer,
    while a wrongly suspected one only costs an investigator's look. Off-topic messages are left alone."""
    if ex.category != "SCAM_TRANSFER" and ex.intent != "OUT_OF_SCOPE":
        if extract_rules(complaint).category == "SCAM_TRANSFER":
            ex.category, ex.intent = "SCAM_TRANSFER", "COMPLAINT"
            ex.source = "llm (scam wording: category overridden by rules)"
    return ex
