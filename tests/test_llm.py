"""LLM layer tests with fake provider clients: no API key, no cost. Run: python -m unittest discover tests

Covers (1) reliability: every failure kind falls back to rules/templates and is recorded, and (2) intents:
vague complaints get a follow-up question, off-topic messages get a polite answer, fraud never waits.
"""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # tests never read .env ...
os.environ["LLM_PROVIDER"] = ""              # ... and never call a real LLM (LLM tests swap in fake clients)

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from agent import checks, extract, llm, reply, tools
from agent.pipeline import MAX_FOLLOW_UPS, follow_up_complaint, process_complaint
from agent.schemas import Decision
from app import store


def extraction(**over):
    d = {"intent": "COMPLAINT", "category": "SERVICE_QUALITY", "language": "EN", "confidence": "high",
         "missing_info": [], "amount": None, "amount_approx": False, "counterparty": "", "date_phrase": "",
         "card_last4": "", "fee_type": "", "fee_month_phrase": ""}
    d.update(over)
    return d


class APITimeoutError(Exception):
    """Same class name as the SDKs' timeout error; llm._classify maps by name."""


class FakeOpenAI:
    """responses.create: a schema request returns `extract` (dict, raw str or exception; a list gives one per call,
    e.g. [first reading, second look]); otherwise `reply`."""

    def __init__(self, extract=None, reply="Thank you for your message. Please tell us the date and what happened, "
                                           "and we will help.\n\nTeratai Bank Customer Care",
                 status="completed", refusal=False):
        self.extract, self.reply, self.status, self.refusal = extract, reply, status, refusal
        self.calls = []
        self.responses = self

    def create(self, **kw):
        self.calls.append(kw)
        out = self.extract if "text" in kw else self.reply
        if isinstance(out, list):
            out = out.pop(0)
        if isinstance(out, Exception):
            raise out
        text = "" if self.refusal else (json.dumps(out) if isinstance(out, dict) else out)
        output = [NS(type="message", content=[NS(type="refusal")])] if self.refusal else []
        return NS(output_text=text, output=output, status=self.status, incomplete_details=None,
                  usage=NS(input_tokens=50, output_tokens=20))


class FakeAnthropic:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop_reason = text, stop_reason
        self.beta = NS(messages=self)

    def create(self, **kw):
        return NS(content=[NS(type="text", text=self.text)], stop_reason=self.stop_reason,
                  usage=NS(input_tokens=50, output_tokens=20))


class LLMTestCase(unittest.TestCase):
    """Swap in a fake provider for each test and restore the real settings afterwards."""

    def setUp(self):
        self._saved = (llm.PROVIDER, llm.MODEL, llm._client)
        tools.get_db()

    def tearDown(self):
        llm.PROVIDER, llm.MODEL, llm._client = self._saved

    def use(self, client, provider="openai", model="test-model"):
        llm.PROVIDER, llm.MODEL, llm._client = provider, model, client
        return client

    def complaint(self, text, cid="TEST-1", customer="CUS-00150", received="2026-09-23 22:32", channel="App chat",
                  **extra):
        return {"complaint_id": cid, "customer_id": customer, "received_at": received, "channel": channel,
                "subject": "", "text": text, **extra}


class Reliability(LLMTestCase):
    def source_for(self, client, provider="openai", model="test-model"):
        self.use(client, provider, model)
        usage = llm.Usage()
        ex = extract.extract(self.complaint("I was charged twice at GoRide"), usage)
        return ex.source, usage

    def test_success(self):
        source, usage = self.source_for(FakeOpenAI(extraction(category="DUPLICATE_CHARGE")))
        self.assertEqual(source, "llm")
        self.assertEqual((usage.calls, usage.input_tokens, usage.failures), (1, 50, []))

    def test_request_shape(self):
        client = self.use(FakeOpenAI(extraction()))
        extract.extract(self.complaint("hello"), llm.Usage())
        fmt = client.calls[0]["text"]["format"]
        self.assertEqual((fmt["type"], fmt["strict"], client.calls[0]["store"]), ("json_schema", True, False))

    def test_failure_kinds_fall_back_to_rules(self):
        cases = {
            "refusal": FakeOpenAI(extraction(), refusal=True),
            "incomplete": FakeOpenAI(extraction(), status="incomplete"),
            "bad_json": FakeOpenAI("not json at all"),
            "timeout": FakeOpenAI(APITimeoutError("read timed out")),
        }
        for kind, client in cases.items():
            with self.subTest(kind=kind):
                source, usage = self.source_for(client)
                self.assertEqual(source, f"rules (llm failed: {kind})")
                self.assertIn(kind, usage.failures)

    def test_schema_violation_is_bad_json(self):
        source, _ = self.source_for(FakeOpenAI(extraction(category="NOT_A_CATEGORY")))
        self.assertEqual(source, "rules (llm failed: bad_json)")
        source, _ = self.source_for(FakeOpenAI({"category": "SERVICE_QUALITY"}))       # missing required fields
        self.assertEqual(source, "rules (llm failed: bad_json)")

    def test_missing_openai_model_is_config_error(self):
        source, _ = self.source_for(None, model="")
        self.assertEqual(source, "rules (llm failed: config)")

    def test_budget_stops_calls(self):
        client = self.use(FakeOpenAI(extraction()))
        usage = llm.Usage()
        usage.calls = llm.MAX_CALLS_PER_COMPLAINT
        ex = extract.extract(self.complaint("hello"), usage)
        self.assertEqual(ex.source, "rules (llm failed: budget)")
        self.assertEqual(client.calls, [])                       # no request was sent

    def test_anthropic_success_and_refusal(self):
        source, _ = self.source_for(FakeAnthropic(json.dumps(extraction())), provider="anthropic")
        self.assertEqual(source, "llm")
        source, _ = self.source_for(FakeAnthropic("", stop_reason="refusal"), provider="anthropic")
        self.assertEqual(source, "rules (llm failed: refusal)")

    def test_pipeline_survives_llm_outage(self):
        self.use(FakeOpenAI(APITimeoutError("down"), reply=APITimeoutError("down")))
        rec = process_complaint(tools.get_db().complaints["CMP-00165"])
        self.assertEqual((rec.decision.matched_txn_id, rec.decision.outcome, rec.decision.refund_amount_myr),
                         ("TXN-0115572", "REFUND", 46.66))           # rules + template still decide correctly
        self.assertEqual(rec.check_problems, [])
        self.assertIn("timeout", rec.llm_usage["failures"])


class Intents(LLMTestCase):
    def test_vague_complaint_gets_follow_up_question(self):
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", missing_info=["what_happened", "date", "amount"])))
        rec = process_complaint(self.complaint("Hi, I have a problem with my account. Please help."))
        d = rec.decision
        self.assertEqual((rec.status, d.decided, d.outcome, d.route, d.matched_txn_id), ("AWAITING_CUSTOMER", False,
                                                                                          "", "", ""))
        self.assertEqual(rec.check_problems, [])
        row = rec.prediction_row()                            # the leaderboard file still gets valid values
        self.assertEqual((row["outcome"], row["route"], row["refund_amount_myr"]), ("INFO_ONLY", "AUTO_RESOLVE", "0.00"))

    def test_follow_up_template_lists_what_is_missing(self):
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", language="MS", missing_info=["date", "amount"]),
                            reply=APITimeoutError("down")))
        rec = process_complaint(self.complaint("Saya ada masalah dengan akaun saya, sila bantu", cid="TEST-MS"))
        self.assertEqual(rec.status, "AWAITING_CUSTOMER")
        self.assertIn("tarikh kejadian", rec.reply_text)     # Malay template, asks for the date
        self.assertIn("jumlah yang terlibat", rec.reply_text)

    def test_customer_reply_reopens_and_resolves_case(self):
        first = self.complaint("Hi, I have a problem with my account. Please help.", cid="TEST-FU")
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", missing_info=["what_happened"])))
        self.assertEqual(process_complaint(first).status, "AWAITING_CUSTOMER")

        second = follow_up_complaint(first, "My DuitNow transfer of RM46.54 to Shalini a/p Nair yesterday failed "
                                            "but the money was deducted.")
        self.assertEqual(second["follow_ups"], 1)
        self.assertIn("[Customer follow-up]", second["text"])
        self.use(FakeOpenAI(extraction(category="FAILED_TRANSFER", amount=46.54, counterparty="Shalini a/p Nair",
                                       date_phrase="yesterday")))
        rec = process_complaint(second)
        self.assertEqual((rec.decision.matched_txn_id, rec.decision.outcome, rec.decision.refund_amount_myr,
                          rec.status), ("TXN-0145614", "REFUND", 46.54, "RESOLVED"))

    def test_out_of_scope_is_answered_not_escalated(self):
        self.use(FakeOpenAI(extraction(intent="OUT_OF_SCOPE"),
                            reply="Thanks for your message! This channel handles complaints about your Teratai Bank "
                                  "accounts and transactions, so we can't help with the weather here. If you have a "
                                  "problem with your account, please tell us.\n\nTeratai Bank Customer Care"))
        rec = process_complaint(self.complaint("What's the weather tomorrow in KL?", cid="TEST-OOS"))
        self.assertEqual((rec.status, rec.decision.route, rec.category, rec.decision.refund_amount_myr),
                         ("ANSWERED", "AUTO_RESOLVE", "SERVICE_QUALITY", 0.0))
        self.assertEqual(rec.check_problems, [])

    def test_out_of_scope_reply_with_invented_amount_falls_back_to_template(self):
        self.use(FakeOpenAI(extraction(intent="OUT_OF_SCOPE"),
                            reply="Our fixed deposit rate is great, deposit RM12,345.67 today!"))
        rec = process_complaint(self.complaint("What are your FD rates?", cid="TEST-OOS2"))
        self.assertEqual(rec.status, "ANSWERED")
        self.assertNotIn("RM12,345.67", rec.reply_text)       # self-check rejected it; template sent instead
        self.assertEqual(rec.check_problems, [])

    def test_vague_fraud_report_never_waits(self):
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", category="SCAM_TRANSFER", missing_info=["amount"])))
        rec = process_complaint(self.complaint("I think I was scammed, someone made me transfer money", cid="TEST-F"))
        self.assertEqual((rec.decision.outcome, rec.decision.route), ("INVESTIGATE", "FRAUD_TEAM"))
        self.assertIn("VAGUE_FRAUD_REPORT", rec.decision.flags)

    def test_scam_wording_overrides_llm_category(self):
        self.use(FakeOpenAI(extraction(category="FAILED_TRANSFER", amount=4042.06, counterparty="Muthu")))
        ex = extract.extract(self.complaint("Saya melabur RM4,042.06 dalam skim pelaburan dari kumpulan chat dan "
                                            "pindahkan kepada Muthu hari Ahad lepas."), llm.Usage())
        self.assertEqual((ex.category, ex.amount, ex.counterparty), ("SCAM_TRANSFER", 4042.06, "Muthu"))
        self.assertIn("overridden", ex.source)

    def test_everyday_words_never_override_llm(self):
        cases = {   # the LLM is right; a loose scam word must not send these to the fraud queue
            "I was charged twice by the courier for my parcel delivery, RM15 each.": "DUPLICATE_CHARGE",
            "Someone scammed my card: RM500 at QUICKBUY that I did not make.": "UNAUTHORISED_CARD",
            "My card was stolen and I reported it to a police officer, then saw RM300 I didn't make.": "UNAUTHORISED_CARD",
            "I feel deceived by this RM12 annual fee on my debit card.": "FEE_DISPUTE",
            "Please investigate: my DuitNow transfer of RM200 failed but money was deducted.": "FAILED_TRANSFER",
        }
        for text, category in cases.items():
            with self.subTest(text=text[:40]):
                self.use(FakeOpenAI(extraction(category=category)))
                ex = extract.extract(self.complaint(text), llm.Usage())
                self.assertEqual((ex.category, ex.source), (category, "llm"))

    def test_code_owns_language_and_hedge_words(self):
        # The two misses from the 200-complaint run with a real model
        self.use(FakeOpenAI(extraction(category="SERVICE_QUALITY", language="MS")))
        ex = extract.extract(self.complaint("Tunggu 2 jam kat branch Kuantan, staff pun rude. Teruk betul service."),
                             llm.Usage())
        self.assertEqual((ex.language, ex.crosscheck["language"]), ("MIXED", {"llm": "MS", "code": "MIXED"}))

        self.use(FakeOpenAI(extraction(category="FAILED_TRANSFER", language="MIXED", amount=2200.0)))
        ex = extract.extract(self.complaint("DuitNow transfer dalam RM2200 to Siti Nadia binti Hassan pada 30/07/2026 "
                                            "tak masuk pun, tapi account saya dah kena deduct."), llm.Usage())
        self.assertTrue(ex.amount_approx)
        self.assertIn("amount_approx", ex.crosscheck)
        self.assertEqual(ex.crosscheck["result"], "agree")             # category check still recorded alongside

    def test_follow_ups_used_up_goes_to_officer(self):
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", missing_info=["what_happened"])))
        rec = process_complaint(self.complaint("still a problem", cid="TEST-MAX", follow_ups=MAX_FOLLOW_UPS))
        self.assertEqual(rec.decision.route, "HUMAN_APPROVAL")
        self.assertIn("DETAILS_STILL_MISSING", rec.decision.flags)


class Replies(LLMTestCase):
    """What a reply may say. Cases come from the first run with a real model, where these slipped through."""

    FEE = {"customer_id": "CUS-00890", "received_at": "2026-09-30 11:41", "channel": "Email", "subject": "",
           "complaint_id": "T-FEE", "text": "Why did you take RM12 annual fee from my account on 26 September?"}

    def fee_case(self):
        self.use(FakeOpenAI(extraction(category="FEE_DISPUTE", amount=12.0, fee_type="DEBIT_ANNUAL"),
                            reply=APITimeoutError("down")))              # template reply
        return process_complaint(self.FEE)

    def test_drafter_never_sees_age_or_internal_reasons(self):
        rec = self.fee_case()
        self.assertTrue(any("age" in r for r in rec.decision.reasons))     # the officer still sees it
        self.assertIn("customer_age", rec.decision.evidence)
        client = self.use(FakeOpenAI(extraction(category="FEE_DISPUTE", amount=12.0, fee_type="DEBIT_ANNUAL")))
        process_complaint(self.FEE)
        prompt = client.calls[1]["input"]                                  # the reply request
        age = str(rec.decision.evidence["customer_age"])
        for leaked in ("customer_age", "(age", f" {age}", "account_id", "applies ("):
            self.assertNotIn(leaked, prompt)

    def test_template_explains_without_internal_text(self):
        rec = self.fee_case()
        self.assertEqual(rec.decision.outcome, "DECLINE")
        self.assertIn("charged correctly under the terms of your account", rec.reply_text)
        self.assertNotRegex(rec.reply_text, r"\bage\b|applies \(")

    def test_checks_catch_what_a_bank_must_not_say(self):
        rec = self.fee_case()
        c, d = self.FEE, rec.decision
        base = "Dear Kavitha,\n\nWe have reviewed transaction {}. ".format(d.matched_txn_id)
        self.assertTrue(checks.check(c, d, base + "This fee applies at age 55.\n\nTeratai Bank Customer Care", "EN"))
        investigate = Decision("", "INVESTIGATE", 0.0, "P1", "FRAUD_TEAM")
        bad = "Dear Kavitha,\n\nThis transaction was identified as a scam. Our fraud team will contact you.\n\nTeratai Bank Customer Care"
        self.assertTrue(checks.check(c, investigate, bad, "EN"))
        fine = ("Dear Kavitha,\n\nOur fraud team is reviewing your case and will contact you. Remember, anyone asking for "
                "your OTP is a scam.\n\nTeratai Bank Customer Care")
        self.assertEqual(checks.check(c, investigate, fine, "EN"), [])
        info = Decision("", "INFO_ONLY", 0.0, "P3", "AUTO_RESOLVE")
        self.assertTrue(checks.check(c, info, "Dear Kavitha,\n\nSorry about the app. This does not qualify for a "
                                              "refund.\n\nTeratai Bank Customer Care", "EN"))

    def test_markdown_is_stripped(self):
        self.assertEqual(reply.plain_text("## Update\nRefund of **RM1,500.00** is on its way.\n* item"),
                         "Update\nRefund of RM1,500.00 is on its way.\n- item")


class CrossCheck(LLMTestCase):
    """LLM vs keyword rules on category; a disagreement gets one evidence-based second look, else an officer."""

    ATM = "CMP-01057"     # "The machine did not dispense all of the cash when I withdrew RM1500.00 today" -> TXN-0143117

    def atm(self):
        return tools.get_db().complaints[self.ATM]

    def second_look(self, category, quote, confidence="high"):
        return {"category": category, "quote": quote, "confidence": confidence}

    def test_agreement_needs_no_second_look(self):
        client = self.use(FakeOpenAI(extraction(category="ATM_NOT_DISPENSED", amount=1500.0)))
        ex = extract.extract(self.atm(), llm.Usage())
        self.assertEqual((ex.category, ex.crosscheck, len(client.calls)), ("ATM_NOT_DISPENSED", {"result": "agree"}, 1))

    def test_rules_without_a_keyword_have_no_opinion(self):
        client = self.use(FakeOpenAI(extraction(category="SERVICE_QUALITY")))
        ex = extract.extract(self.complaint("Your new statement layout is confusing to read."), llm.Usage())
        self.assertEqual((ex.crosscheck["result"], len(client.calls)), ("rules_no_opinion", 1))

    def test_second_look_corrects_the_llm(self):
        client = self.use(FakeOpenAI([extraction(category="SERVICE_QUALITY", amount=1500.0),
                                      self.second_look("ATM_NOT_DISPENSED", "did not dispense all of the cash")]))
        rec = process_complaint(self.atm())
        self.assertEqual((rec.category, rec.decision.matched_txn_id), ("ATM_NOT_DISPENSED", "TXN-0143117"))
        self.assertEqual(rec.extraction.crosscheck["resolution"], "second_look")
        self.assertNotIn("CROSSCHECK_UNRESOLVED", rec.decision.flags)
        prompt = client.calls[1]["input"]                       # the second look's question
        self.assertIn("ATM_NOT_DISPENSED or SERVICE_QUALITY", prompt)
        self.assertIn("ATM Withdrawal", prompt)                 # it was shown the customer's records
        self.assertNotIn("rules", prompt.lower())               # and not told which reading came from where

    def test_second_look_can_keep_the_llm_reading(self):
        self.use(FakeOpenAI([extraction(category="FEE_DISPUTE", amount=12.0),
                             self.second_look("FEE_DISPUTE", "RM12 annual fee")]))
        ex = extract.extract(self.complaint("I feel deceived by this RM12 annual fee on my debit card."), llm.Usage())
        self.assertEqual((ex.category, ex.crosscheck["rules"], ex.crosscheck["resolution"]),
                         ("FEE_DISPUTE", "SCAM_TRANSFER", "second_look"))

    def test_invented_quote_goes_to_an_officer(self):
        self.use(FakeOpenAI([extraction(category="SERVICE_QUALITY", amount=1500.0),
                             self.second_look("ATM_NOT_DISPENSED", "the ATM swallowed my card")]))
        rec = process_complaint(self.atm())
        self.assertEqual((rec.category, rec.decision.route), ("SERVICE_QUALITY", "HUMAN_APPROVAL"))
        self.assertIn("CROSSCHECK_UNRESOLVED", rec.decision.flags)
        self.assertTrue(any("please confirm the category" in r for r in rec.decision.reasons))

    def test_leaving_a_fraud_category_needs_high_confidence(self):
        text = "I feel deceived by this RM12 annual fee on my debit card."
        for confidence, resolution in [("medium", "officer"), ("high", "second_look")]:
            with self.subTest(confidence=confidence):
                self.use(FakeOpenAI([extraction(category="FEE_DISPUTE", amount=12.0),
                                     self.second_look("FEE_DISPUTE", "annual fee", confidence)]))
                ex = extract.extract(self.complaint(text), llm.Usage())
                self.assertEqual((ex.category, ex.crosscheck["resolution"]), ("FEE_DISPUTE", resolution))

    def test_second_look_failure_goes_to_an_officer(self):
        self.use(FakeOpenAI([extraction(category="SERVICE_QUALITY", amount=1500.0), APITimeoutError("down")]))
        usage = llm.Usage()
        ex = extract.extract(self.atm(), usage)
        self.assertEqual((ex.category, ex.source, ex.crosscheck["resolution"]), ("SERVICE_QUALITY", "llm", "officer"))
        self.assertIn("timeout", usage.failures)


class CaseLifecycle(LLMTestCase):
    """The case store: a case awaiting the customer is open with no decision, and the thread is in the audit log."""

    def setUp(self):
        super().setUp()
        self.store, self._db = store, store.DB_PATH            # a throwaway database, never runtime/cases.db
        self._tmp = tempfile.TemporaryDirectory()
        store.DB_PATH = Path(self._tmp.name) / "cases.db"

    def tearDown(self):
        self.store.DB_PATH = self._db
        self._tmp.cleanup()
        super().tearDown()

    def test_awaiting_customer_has_no_decision_until_the_reply(self):
        first = self.complaint("Hi, I have a problem with my account. Please help.", cid="TEST-LC")
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", missing_info=["what_happened"])))
        self.store.save_case(process_complaint(first))
        case = self.store.get_case("TEST-LC")
        self.assertEqual((case["status"], case["outcome"], case["route"], case["refund_amount_myr"],
                          case["matched_txn_id"]), ("AWAITING_CUSTOMER", None, None, None, None))
        self.assertEqual([a["action"] for a in case["audit"]], ["processed", "question_sent"])
        created = case["created_at"]

        self.store.log("TEST-LC", "customer", "customer_replied", "My DuitNow transfer of RM46.54 failed")
        second = follow_up_complaint(first, "My DuitNow transfer of RM46.54 to Shalini a/p Nair yesterday failed "
                                            "but the money was deducted.")
        self.use(FakeOpenAI(extraction(category="FAILED_TRANSFER", amount=46.54, counterparty="Shalini a/p Nair",
                                       date_phrase="yesterday")))
        self.store.save_case(process_complaint(second))
        case = self.store.get_case("TEST-LC")
        self.assertEqual((case["status"], case["outcome"], case["route"], case["refund_amount_myr"], case["created_at"]),
                         ("RESOLVED", "REFUND", "AUTO_RESOLVE", 46.54, created))
        self.assertEqual([a["action"] for a in case["audit"]],
                         ["processed", "question_sent", "customer_replied", "decided", "reply_sent"])


if __name__ == "__main__":
    unittest.main()
