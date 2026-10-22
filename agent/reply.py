"""Owner: B. DRAFT step: Decision + evidence -> customer reply in reply_language.

The reply explains the decision; it never changes it. Templates are the offline fallback and the safety net
when the LLM draft fails the self-check twice.

TODO(B):
  - better templates per category (judges read 10 replies: tone, correct language, no invented facts)
  - SLA wording from tools.sla(priority)
"""
from __future__ import annotations

import json

from . import llm, tools
from .schemas import Decision

TEMPLATES = {
    "EN": {
        "REFUND": "Dear {name},\n\nThank you for contacting Teratai Bank. We have reviewed transaction {txn} and will refund RM{refund} to your account. {why}\n\nWe apologise for the inconvenience.\n\nTeratai Bank Customer Care",
        "DECLINE": "Dear {name},\n\nThank you for contacting Teratai Bank. We have reviewed transaction {txn}. {why} We are therefore unable to make a refund. If you have further information, please reply to this message.\n\nTeratai Bank Customer Care",
        "INVESTIGATE": "Dear {name},\n\nThank you for reporting this. Your case about transaction {txn} has been passed to our fraud team as a priority, and they will contact you shortly. Please do not share your PIN or one-time passwords with anyone.\n\nTeratai Bank Customer Care",
        "INFO_ONLY": "Dear {name},\n\nThank you for your feedback, and we are sorry for your experience. We have shared it with the team concerned and will follow up with you on the next steps.\n\nTeratai Bank Customer Care",
    },
    "MS": {
        "REFUND": "Tuan/Puan {name},\n\nTerima kasih kerana menghubungi Teratai Bank. Kami telah menyemak transaksi {txn} dan akan memulangkan RM{refund} ke akaun anda.\n\nKami memohon maaf atas kesulitan ini.\n\nKhidmat Pelanggan Teratai Bank",
        "DECLINE": "Tuan/Puan {name},\n\nTerima kasih kerana menghubungi Teratai Bank. Kami telah menyemak transaksi {txn} dan mendapati tiada bayaran balik yang perlu dibuat. Sekiranya anda mempunyai maklumat lanjut, sila balas mesej ini.\n\nKhidmat Pelanggan Teratai Bank",
        "INVESTIGATE": "Tuan/Puan {name},\n\nTerima kasih kerana melaporkan perkara ini. Kes anda berkenaan transaksi {txn} telah diserahkan kepada pasukan penipuan kami sebagai keutamaan, dan mereka akan menghubungi anda tidak lama lagi. Jangan kongsi PIN atau kata laluan sekali guna anda dengan sesiapa.\n\nKhidmat Pelanggan Teratai Bank",
        "INFO_ONLY": "Tuan/Puan {name},\n\nTerima kasih atas maklum balas anda, dan kami memohon maaf atas pengalaman anda. Kami telah memaklumkan pasukan berkenaan dan akan menghubungi anda tentang langkah seterusnya.\n\nKhidmat Pelanggan Teratai Bank",
    },
}


def draft_template(complaint: dict, decision: Decision, lang: str) -> str:
    cust = tools.get_customer(complaint["customer_id"])
    why = decision.reasons[-1] + "." if decision.reasons and lang == "EN" and decision.outcome == "DECLINE" else ""
    return TEMPLATES[lang][decision.outcome].format(
        name=cust["full_name"], txn=decision.matched_txn_id or "-", refund=f"{decision.refund_amount_myr:.2f}", why=why,
    ).replace("transaction - ", "your transaction ").replace("transaksi - ", "transaksi anda ").replace(" \n", "\n")


SYSTEM = """You write replies from Teratai Bank (Malaysia) to customers who complained.
Rules:
- Write in the language given: EN = English, MS = Bahasa Melayu. Warm, short (under 120 words), plain.
- The decision is final and was made by bank policy. Explain it; never change, soften into a different outcome, or promise anything else.
- Only mention transaction IDs, amounts and dates that appear in the DECISION or EVIDENCE. Never invent numbers.
- REFUND: state the refund amount. DECLINE: explain why, kindly. INVESTIGATE: say the fraud team is on it; no refund promise; warn not to share PIN/OTP.
  INFO_ONLY: apologise and explain the next step.
- Sign off as "Teratai Bank Customer Care" (EN) or "Khidmat Pelanggan Teratai Bank" (MS)."""


def draft_llm(complaint: dict, decision: Decision, lang: str, usage=None, feedback: str = "") -> str:
    cust = tools.get_customer(complaint["customer_id"])
    user = (f"LANGUAGE: {lang}\nCUSTOMER NAME: {cust['full_name']}\n"
            f"COMPLAINT: {complaint['text']}\n"
            f"DECISION: outcome={decision.outcome}, refund=RM{decision.refund_amount_myr:.2f}, "
            f"transaction={decision.matched_txn_id or 'none'}\nREASONS: {'; '.join(decision.reasons)}\n"
            f"EVIDENCE: {json.dumps(decision.evidence, default=str)}")
    if feedback:
        user += f"\n\nYour previous draft failed the fact check: {feedback}. Rewrite it using only facts above."
    return llm.complete_text(SYSTEM, user, usage)


def _with_fallback(llm_draft, template_draft, usage):
    """LLM draft when enabled; the template on any failure (the failure kind is already in usage.failures)."""
    if llm.enabled():
        try:
            return llm_draft()
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
