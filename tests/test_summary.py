"""The officer's view and the record behind it. Run: python -m unittest discover tests

The summary must say, in plain words, why a case needs a person, what happened and what was decided; the record must
keep everything the decision used (customer, account, fee schedule row, dates, policy settings, reply provenance).
"""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # tests never read .env ...
os.environ["LLM_PROVIDER"] = ""              # ... and never call a real LLM

import json
import re
import unittest

from agent import checks, tools
from agent.pipeline import process_complaint
from agent.summary import case_summary

FLAG_CODE = re.compile(r"\b(NO_MATCH|AMBIGUOUS_MATCH|CHECK_FAILED|CROSSCHECK_UNRESOLVED|DETAILS_STILL_MISSING|"
                       r"VAGUE_FRAUD_REPORT|PENDING_APPROVAL|FRAUD_QUEUE|AUTO_RESOLVE|HUMAN_APPROVAL)\b")


def stored(rec):
    """The record as the app stores and reads it back."""
    return json.loads(json.dumps(rec.to_dict(), default=str))


def summary_of(cid=None, complaint=None):
    rec = process_complaint(complaint or tools.get_db().complaints[cid])
    return rec, case_summary(stored(rec))


class Summary(unittest.TestCase):
    def setUp(self):
        tools.get_db()

    def assertPlain(self, s):
        text = " ".join([s["headline"], *s["why_here"], s["story"], s["decision"], *s["warnings"]])
        self.assertIsNone(FLAG_CODE.search(text), text)          # officers never see internal codes

    def test_refund_over_the_limit(self):
        _, s = summary_of("CMP-00244")
        self.assertEqual(s["why_here"], ["Refund of RM550.00 is above the RM500.00 auto-approval limit"])
        self.assertEqual(s["story"], "The ATM at Miri Mall gave RM950.00 of RM1,500.00 on 17 Jul 2026.")
        self.assertEqual(s["decision"], "Refund RM550.00.")
        self.assertTrue(s["key_row"].startswith("TXN-0088211 · 17 Jul 2026, 07:20 · ATM Withdrawal · RM1,500.00"))
        self.assertEqual(s["tone"], "warning")
        self.assertPlain(s)

    def test_fraud_queue_says_why(self):
        _, s = summary_of("CMP-00387")
        self.assertIn("approved with a one-time password (3DS-OTP)", s["why_here"][0])
        self.assertEqual((s["decision"], s["tone"]), ("Fraud team investigates; no refund yet.", "error"))
        self.assertPlain(s)

    def test_resolved_automatically(self):
        _, s = summary_of("CMP-00165")
        self.assertEqual(s["why_here"], ["Resolved automatically: refund within the RM500.00 limit"])
        self.assertIn("Two identical charges of RM46.66 at GoRide", s["story"])
        self.assertEqual(s["tone"], "success")

    def test_no_match_is_explained_not_coded(self):
        _, s = summary_of(complaint={"complaint_id": "T-SUM", "customer_id": "CUS-00150", "channel": "App chat",
                                     "received_at": "2026-09-30 10:00", "subject": "",
                                     "text": "My DuitNow transfer failed, please help."})
        self.assertEqual(s["why_here"], ["Couldn't identify which transaction the customer means"])
        self.assertIn("No transaction could be matched", s["story"])
        self.assertEqual(s["key_row"], "")
        self.assertPlain(s)


class Record(unittest.TestCase):
    """Everything the decision used is recorded (collapsed on screen), never sent to the reply drafter."""

    def setUp(self):
        tools.get_db()

    def test_customer_priority_policy_and_reply_provenance(self):
        rec, _ = summary_of("CMP-00128")                           # an 83-year-old customer
        ev = rec.decision.evidence
        self.assertEqual(ev["priority"], {"priority": "P1",
                                          "why": "P2 for DUPLICATE_CHARGE, moved up to P1: customer is 83 (65+)"})
        self.assertEqual(ev["customer"]["age"], 83)
        self.assertIn(ev["customer"]["preferred_language"], ("EN", "MS"))
        self.assertEqual(ev["policy"]["AUTO_REFUND_LIMIT_MYR"], "500.00")
        self.assertTrue(ev["account"]["product"])
        self.assertEqual(set(ev["date_resolution"]), {"phrase", "from", "to", "rule"})
        self.assertEqual((ev["reply"]["source"], ev["reply"]["rejected_drafts"]), ("template", []))
        self.assertIn("reply in the same language", ev["reply"]["language_why"])

    def test_fee_decision_records_the_schedule_row(self):
        rec, s = summary_of("CMP-00008")
        ev = rec.decision.evidence
        self.assertEqual((ev["fee_schedule"]["fee_code"], ev["fee_schedule"]["amount_myr"]), ("MSC_SAVPLUS", "2.00"))
        self.assertIn("the fee schedule says RM2.00 for Savings Plus", s["story"])

    def test_call_centre_note_language_reason(self):
        rec, _ = summary_of("CMP-00387")
        self.assertEqual(rec.decision.evidence["reply"]["language_why"],
                         "call-centre note written by staff: customer's preferred language")


class ReplyDates(unittest.TestCase):
    def setUp(self):
        tools.get_db()

    def test_dates_must_come_from_the_case(self):
        rec = process_complaint(tools.get_db().complaints["CMP-00244"])          # transaction on 17 Jul 2026
        c, d = tools.get_db().complaints["CMP-00244"], rec.decision
        ok = rec.reply_text.replace("We have reviewed", "On 17 July 2026 we reviewed")
        self.assertEqual([p for p in checks.check(c, d, ok, "EN") if "date" in p], [])
        wrong = rec.reply_text.replace("We have reviewed", "On 18 July 2026 we reviewed")
        self.assertIn("reply mentions 18 Jul 2026, which is not a date in this case's evidence",
                      checks.check(c, d, wrong, "EN"))
        harmless = rec.reply_text.replace("We apologise", "Our 24/7 hotline is open. You may 5 times retry. We apologise")
        self.assertEqual([p for p in checks.check(c, d, harmless, "EN") if "date" in p], [])


if __name__ == "__main__":
    unittest.main()
