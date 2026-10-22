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


def draft_reply(complaint: dict, decision: Decision, lang: str, usage=None, feedback: str = "") -> str:
    if llm.enabled():
        try:
            return draft_llm(complaint, decision, lang, usage, feedback)
        except Exception:  # noqa: BLE001
            pass
    return draft_template(complaint, decision, lang)
