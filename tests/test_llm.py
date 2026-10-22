"""LLM layer tests with fake provider clients: no API key, no cost. Run: python -m unittest discover tests

Covers (1) reliability: every failure kind falls back to rules/templates and is recorded, and (2) intents:
vague complaints get a follow-up question, off-topic messages get a polite answer, fraud never waits.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from agent import extract, llm, tools
from agent.pipeline import MAX_FOLLOW_UPS, follow_up_complaint, process_complaint
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
    """responses.create: a schema request returns `extract` (dict, raw str or exception); otherwise `reply`."""

    def __init__(self, extract=None, reply="Thank you for your message. Please tell us the date and what happened, "
                                           "and we will help.\n\nTeratai Bank Customer Care",
                 status="completed", refusal=False):
        self.extract, self.reply, self.status, self.refusal = extract, reply, status, refusal
        self.calls = []
        self.responses = self

    def create(self, **kw):
        self.calls.append(kw)
        out = self.extract if "text" in kw else self.reply
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

    def test_follow_ups_used_up_goes_to_officer(self):
        self.use(FakeOpenAI(extraction(intent="NEEDS_DETAILS", missing_info=["what_happened"])))
        rec = process_complaint(self.complaint("still a problem", cid="TEST-MAX", follow_ups=MAX_FOLLOW_UPS))
        self.assertEqual(rec.decision.route, "HUMAN_APPROVAL")
        self.assertIn("DETAILS_STILL_MISSING", rec.decision.flags)


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
