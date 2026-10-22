"""Owner: B. DRAFT step: Decision + evidence -> customer reply in reply_language.

The reply explains the decision; it never changes it. Templates are the offline fallback and the safety net
when the LLM draft fails the self-check twice.

What the customer may be told is decided here, in code. The drafter (LLM or template) gets a customer-safe fact
sheet: the transaction details and a plain explanation of the decision. It never sees the internal reasons
("fee applies (age 55)") or personal data such as the customer's age, so it cannot repeat them.

TODO(B): SLA wording from tools.sla(priority)
"""
from __future__ import annotations

import json
import re

from . import llm, tools
from .schemas import Decision

TEMPLATES = {
    "EN": {
        "REFUND": "Dear {name},\n\nThank you for contacting Teratai Bank. We have reviewed transaction {txn}. {why} We will refund RM{refund} to your account.\n\nWe apologise for the inconvenience.\n\nTeratai Bank Customer Care",
        "DECLINE": "Dear {name},\n\nThank you for contacting Teratai Bank. We have reviewed transaction {txn}. {why} We are therefore unable to make a refund. If you have further information, please reply to this message.\n\nTeratai Bank Customer Care",
        "INVESTIGATE": "Dear {name},\n\nThank you for reporting this. Your case about transaction {txn} has been passed to our fraud team as a priority, and they will contact you shortly. Please do not share your PIN or one-time passwords with anyone.\n\nTeratai Bank Customer Care",
        "INFO_ONLY": "Dear {name},\n\nThank you for your feedback, and we are sorry for your experience. We have shared it with the team concerned and will follow up with you on the next steps.\n\nTeratai Bank Customer Care",
    },
    "MS": {
        "REFUND": "Tuan/Puan {name},\n\nTerima kasih kerana menghubungi Teratai Bank. Kami telah menyemak transaksi {txn}. {why} Kami akan memulangkan RM{refund} ke akaun anda.\n\nKami memohon maaf atas kesulitan ini.\n\nKhidmat Pelanggan Teratai Bank",
        "DECLINE": "Tuan/Puan {name},\n\nTerima kasih kerana menghubungi Teratai Bank. Kami telah menyemak transaksi {txn}. {why} Oleh itu, kami tidak dapat membuat bayaran balik. Sekiranya anda mempunyai maklumat lanjut, sila balas mesej ini.\n\nKhidmat Pelanggan Teratai Bank",
        "INVESTIGATE": "Tuan/Puan {name},\n\nTerima kasih kerana melaporkan perkara ini. Kes anda berkenaan transaksi {txn} telah diserahkan kepada pasukan penipuan kami sebagai keutamaan, dan mereka akan menghubungi anda tidak lama lagi. Jangan kongsi PIN atau kata laluan sekali guna anda dengan sesiapa.\n\nKhidmat Pelanggan Teratai Bank",
        "INFO_ONLY": "Tuan/Puan {name},\n\nTerima kasih atas maklum balas anda, dan kami memohon maaf atas pengalaman anda. Kami telah memaklumkan pasukan berkenaan dan akan menghubungi anda tentang langkah seterusnya.\n\nKhidmat Pelanggan Teratai Bank",
    },
}

# Internal decision reasons (agent/policy.py, written for officers) -> what the customer may be told.
# Matched on the start of the reason; anything not listed gets no explanation rather than the internal text.
CUSTOMER_WHY = [
    ("Identical charge", "We found two identical charges a few minutes apart, and neither had been reversed.",
     "Kami mendapati dua caj yang sama dalam masa beberapa minit, dan kedua-duanya belum dipulangkan."),
    ("Already reversed", "The extra charge has already been reversed to your account.",
     "Caj tambahan tersebut telah pun dipulangkan ke akaun anda."),
    ("No identical charge", "We could not find a second, identical charge for this purchase.",
     "Kami tidak menemui caj kedua yang sama bagi pembelian ini."),
    ("Status Failed", "The transfer did not go through, and the money had not been returned to your account.",
     "Pindahan tersebut tidak berjaya, dan wang belum dikembalikan ke akaun anda."),
    ("Reversed by", "The transfer has already been reversed to your account.",
     "Pindahan tersebut telah pun dipulangkan ke akaun anda."),
    ("Transfer completed", "Our records show the transfer was completed to the recipient's account.",
     "Rekod kami menunjukkan pindahan tersebut telah berjaya ke akaun penerima."),
    ("Journal: requested", "Our ATM records show the machine gave out less cash than you requested.",
     "Rekod ATM kami menunjukkan mesin mengeluarkan wang tunai kurang daripada jumlah yang anda minta."),
    ("Journal shows the full", "Our ATM records show the full amount was dispensed.",
     "Rekod ATM kami menunjukkan jumlah penuh telah dikeluarkan."),
    ("Card not present", "The online payment was made without the additional security check, so you are protected.",
     "Bayaran dalam talian tersebut dibuat tanpa semakan keselamatan tambahan, jadi anda dilindungi."),
    ("Approved with", "The payment passed your card's security check, so our fraud team will review it before any decision.",
     "Bayaran tersebut melepasi semakan keselamatan kad anda, jadi pasukan penipuan kami akan menyemaknya sebelum sebarang keputusan."),
    ("Authorised push-payment", "Our fraud team will review the transfer and try to recover the money, although recovery cannot be guaranteed.",
     "Pasukan penipuan kami akan menyemak pindahan tersebut dan cuba mendapatkan semula wang anda, walaupun ini tidak dapat dijamin."),
    ("Debit card fee waived", "You are eligible for a waiver of this fee.", "Anda layak untuk pengecualian caj ini."),
    ("Card opened", "The annual fee is waived in your card's first year.",
     "Yuran tahunan dikecualikan bagi tahun pertama kad anda."),
    ("No transaction found", "We could not identify the transaction from the details provided.",
     "Kami tidak dapat mengenal pasti transaksi tersebut daripada maklumat yang diberikan."),
]
FEE_CORRECT = ("This fee was charged correctly under the terms of your account.",
               "Caj ini dikenakan dengan betul mengikut terma akaun anda.")


def customer_why(decision: Decision, lang: str) -> str:
    """A plain, customer-safe explanation of the decision, from the policy reason. "" when there is nothing to say."""
    i = 1 if lang == "MS" else 0
    for reason in reversed(decision.reasons):
        for prefix, en, ms in CUSTOMER_WHY:
            if reason.startswith(prefix):
                return (en, ms)[i]
    if "fee_due" in decision.evidence and decision.outcome == "DECLINE":
        return FEE_CORRECT[i]
    return ""


SAFE_TXN_FIELDS = ("txn_time", "channel", "amount_myr", "merchant_or_counterparty", "card_last4", "status")


def customer_facts(decision: Decision) -> dict:
    """The evidence the reply may draw on: transaction details only. No age, account IDs or internal notes."""
    ev, out = decision.evidence, {}
    for key in ("txn", "twin", "reversal"):
        if ev.get(key):
            out[key] = {f: ev[key][f] for f in SAFE_TXN_FIELDS if ev[key].get(f)}
    if ev.get("atm_journal"):
        j = ev["atm_journal"]
        out["atm"] = {"location": j.get("atm_location"), "requested_myr": j.get("requested_myr"),
                      "dispensed_myr": j.get("dispensed_myr")}
    return out


def draft_template(complaint: dict, decision: Decision, lang: str) -> str:
    cust = tools.get_customer(complaint["customer_id"])
    return TEMPLATES[lang][decision.outcome].format(
        name=cust["full_name"], txn=decision.matched_txn_id or "-", refund=f"{decision.refund_amount_myr:.2f}",
        why=customer_why(decision, lang),
    ).replace("transaction - ", "your transaction ").replace("transaksi - ", "transaksi anda ").replace("  ", " ")


SYSTEM = """You write replies from Teratai Bank (Malaysia) to customers who complained.
Rules:
- Write in the language given: EN = English, MS = Bahasa Melayu. Warm, short (under 120 words), plain text only:
  no Markdown, no asterisks or bold, no headings, no emojis.
- The outcome was already decided under bank policy. Explain it using WHY; never change it, soften it into a different
  outcome, or promise anything else. That instruction is for you: never tell the customer the decision is final,
  cannot be changed or cannot be appealed (EN "final", MS "muktamad").
- Only mention transaction IDs, amounts and dates that appear in DECISION or FACTS. Never invent numbers.
- Never mention the customer's age, date of birth or other personal details beyond their name, and never mention
  internal rules, thresholds, codes or how cases are routed.
- REFUND: state the refund amount. DECLINE: explain why, kindly, and invite them to reply with more information.
- INVESTIGATE: say the fraud team is reviewing the case and will contact them. Never say the transaction is confirmed or
  identified as fraud or a scam, and never promise the money will be recovered. Warn them not to share their PIN or OTP.
- INFO_ONLY: apologise and explain the next step. Do not mention refunds, compensation or eligibility at all.
- Sign off as "Teratai Bank Customer Care" (EN) or "Khidmat Pelanggan Teratai Bank" (MS)."""


def draft_llm(complaint: dict, decision: Decision, lang: str, usage=None, feedback: str = "") -> str:
    cust = tools.get_customer(complaint["customer_id"])
    user = (f"LANGUAGE: {lang}\nCUSTOMER NAME: {cust['full_name']}\n"
            f"COMPLAINT: {complaint['text']}\n"
            f"DECISION: outcome={decision.outcome}, refund=RM{decision.refund_amount_myr:.2f}, "
            f"transaction={decision.matched_txn_id or 'none'}\n"
            f"WHY: {customer_why(decision, 'EN') or 'no further explanation needed'}\n"
            f"FACTS: {json.dumps(customer_facts(decision), default=str)}")
    if feedback:
        user += f"\n\nYour previous draft failed the check: {feedback}. Rewrite it using only the facts above."
    return llm.complete_text(SYSTEM, user, usage)


# Typographic punctuation the model likes, as plain characters every SMS gateway, email client and spreadsheet shows
PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                       "…": "...", " ": " "})


def plain_text(reply: str) -> str:
    """Replies go out by SMS, app chat and email: strip Markdown the model may add anyway (**bold**, # headings),
    and use plain quotes, dashes and spaces (We’re -> We're)."""
    reply = reply.translate(PLAIN)
    reply = re.sub(r"(\*\*|__|`)", "", reply)
    reply = re.sub(r"(?m)^\s*#{1,6}\s*", "", reply)
    return re.sub(r"(?m)^(\s*)\* ", r"\1- ", reply).strip()


def _with_fallback(llm_draft, template_draft, usage):
    """LLM draft when enabled; the template on any failure (the failure kind is already in usage.failures)."""
    if llm.enabled():
        try:
            return plain_text(llm_draft())
        except llm.LLMError:
            pass
        except Exception:  # noqa: BLE001 -- a bug must not lose the reply; record it
            if usage is not None:
                usage.failures.append("unexpected")
    return template_draft()


def draft_reply(complaint: dict, decision: Decision, lang: str, usage=None, feedback: str = "") -> str:
    return _with_fallback(lambda: draft_llm(complaint, decision, lang, usage, feedback),
                          lambda: draft_template(complaint, decision, lang), usage)


# ---- Messages that are not (yet) actionable complaints -------------------------------------------------------

ASK = {
    "EN": {"what_happened": "what went wrong", "transaction_type": "the type of transaction (card payment, transfer, ATM withdrawal or fee)",
           "date": "the date it happened", "amount": "the amount involved", "merchant_or_recipient": "the merchant or recipient name",
           "card_last4": "the last 4 digits of the card used"},
    "MS": {"what_happened": "apa yang berlaku", "transaction_type": "jenis transaksi (bayaran kad, pindahan, pengeluaran ATM atau caj)",
           "date": "tarikh kejadian", "amount": "jumlah yang terlibat", "merchant_or_recipient": "nama peniaga atau penerima",
           "card_last4": "4 digit terakhir kad yang digunakan"},
}
FOLLOW_UP_TEMPLATE = {
    "EN": "Dear {name},\n\nThank you for contacting Teratai Bank. We'd like to help, and to look into this we need a few more details:\n{asks}\n\nPlease reply to this message with these details and we will continue with your case.\n\nTeratai Bank Customer Care",
    "MS": "Tuan/Puan {name},\n\nTerima kasih kerana menghubungi Teratai Bank. Kami ingin membantu, dan untuk menyemak perkara ini kami memerlukan beberapa maklumat lanjut:\n{asks}\n\nSila balas mesej ini dengan maklumat tersebut dan kami akan meneruskan kes anda.\n\nKhidmat Pelanggan Teratai Bank",
}
OUT_OF_SCOPE_TEMPLATE = {
    "EN": "Dear {name},\n\nThank you for your message. This channel handles complaints about your Teratai Bank accounts and transactions, such as card charges, transfers, ATM withdrawals, fees and our service, so we are not able to help with this request here. If you have a problem with your account, please reply with the details and we will look into it.\n\nTeratai Bank Customer Care",
    "MS": "Tuan/Puan {name},\n\nTerima kasih atas mesej anda. Saluran ini mengendalikan aduan berkenaan akaun dan transaksi Teratai Bank anda, seperti caj kad, pindahan, pengeluaran ATM, caj perkhidmatan dan perkhidmatan kami, jadi kami tidak dapat membantu permintaan ini di sini. Sekiranya anda mempunyai masalah dengan akaun anda, sila balas dengan butirannya dan kami akan menyemaknya.\n\nKhidmat Pelanggan Teratai Bank",
}
DEFAULT_ASKS = ["what_happened", "date", "amount"]

FOLLOW_UP_SYSTEM = """You write a short follow-up message from Teratai Bank (Malaysia) to a customer whose complaint is too general to act on.
Rules:
- Write in the language given: EN = English, MS = Bahasa Melayu. Warm and brief (under 90 words).
- Acknowledge their message in one sentence, then ask only for the details listed under ASK FOR, as a short list.
- Do not promise any outcome, refund or timeline. Do not mention any amounts, dates or transaction IDs.
- Never ask for a PIN, password, OTP or full card number.
- Sign off as "Teratai Bank Customer Care" (EN) or "Khidmat Pelanggan Teratai Bank" (MS)."""

OUT_OF_SCOPE_SYSTEM = """You reply for Teratai Bank (Malaysia) on its complaints channel to a message that is not a banking complaint.
Rules:
- Write in the language given: EN = English, MS = Bahasa Melayu. Friendly and brief (under 70 words).
- Acknowledge what they said naturally. Explain that this channel handles complaints about their Teratai Bank accounts and
  transactions (card charges, transfers, ATM withdrawals, fees, service), and invite them to describe any such problem.
- Do not answer the off-topic question itself, give financial or other advice, or quote any rates, prices, products,
  phone numbers or web addresses. Do not mention any amounts.
- Sign off as "Teratai Bank Customer Care" (EN) or "Khidmat Pelanggan Teratai Bank" (MS)."""


def _name(complaint):
    return tools.get_customer(complaint["customer_id"])["full_name"]


def follow_up_template(complaint: dict, missing: list, lang: str) -> str:
    asks = "\n".join(f"- {ASK[lang][m]}" for m in (missing or DEFAULT_ASKS) if m in ASK[lang])
    return FOLLOW_UP_TEMPLATE[lang].format(name=_name(complaint), asks=asks)


def draft_follow_up(complaint: dict, missing: list, lang: str, usage=None, feedback: str = "") -> str:
    def via_llm():
        user = (f"LANGUAGE: {lang}\nCUSTOMER NAME: {_name(complaint)}\nMESSAGE: {complaint['text']}\n"
                f"ASK FOR: {', '.join(ASK['EN'][m] for m in (missing or DEFAULT_ASKS) if m in ASK['EN'])}")
        if feedback:
            user += f"\n\nYour previous draft failed the check: {feedback}. Rewrite it."
        return llm.complete_text(FOLLOW_UP_SYSTEM, user, usage)
    return _with_fallback(via_llm, lambda: follow_up_template(complaint, missing, lang), usage)


def out_of_scope_template(complaint: dict, lang: str) -> str:
    return OUT_OF_SCOPE_TEMPLATE[lang].format(name=_name(complaint))


def draft_out_of_scope(complaint: dict, lang: str, usage=None, feedback: str = "") -> str:
    def via_llm():
        user = f"LANGUAGE: {lang}\nCUSTOMER NAME: {_name(complaint)}\nMESSAGE: {complaint['text']}"
        if feedback:
            user += f"\n\nYour previous draft failed the check: {feedback}. Rewrite it."
        return llm.complete_text(OUT_OF_SCOPE_SYSTEM, user, usage)
    return _with_fallback(via_llm, lambda: out_of_scope_template(complaint, lang), usage)
