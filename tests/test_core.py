"""Fast offline tests for the deterministic parts. Run: python -m unittest discover tests"""
import datetime as dt
import unittest

from agent import checks, policy, tools
from agent.dates import resolve_dates
from agent.pipeline import process_complaint

RECV = dt.datetime(2026, 8, 25, 10, 0)   # a Tuesday


class Dates(unittest.TestCase):
    def test_last_weekday_en_ms(self):
        self.assertEqual(resolve_dates("last Tuesday", RECV).start, dt.date(2026, 8, 18))
        self.assertEqual(resolve_dates("hari Selasa lepas", RECV).start, dt.date(2026, 8, 18))

    def test_yesterday(self):
        self.assertEqual(resolve_dates("semalam", RECV).start, dt.date(2026, 8, 24))

    def test_explicit(self):
        self.assertEqual(resolve_dates("on 15 September 2026", dt.datetime(2026, 9, 19)).start, dt.date(2026, 9, 15))


class Rules(unittest.TestCase):
    def test_route(self):
        self.assertEqual(policy.route("INVESTIGATE", 0), "FRAUD_TEAM")
        self.assertEqual(policy.route("DECLINE", 0), "HUMAN_APPROVAL")
        self.assertEqual(policy.route("REFUND", 500.00), "AUTO_RESOLVE")
        self.assertEqual(policy.route("REFUND", 500.01), "HUMAN_APPROVAL")


class EndToEnd(unittest.TestCase):
    def test_readme_examples(self):
        db = tools.get_db()
        rec = process_complaint(db.complaints["CMP-00165"])
        self.assertEqual((rec.decision.matched_txn_id, rec.decision.outcome, rec.decision.refund_amount_myr,
                          rec.reply_language), ("TXN-0115572", "REFUND", 46.66, "MS"))
        rec = process_complaint(db.complaints["CMP-00387"])
        self.assertEqual((rec.decision.outcome, rec.decision.route), ("INVESTIGATE", "FRAUD_TEAM"))

    def test_no_clue_never_pins_a_transaction(self):
        # CUS-00150 has exactly one transfer (TXN-0145614) in the window. Nothing in these messages points at it,
        # so neither may be matched to it, let alone refunded on it.
        tools.get_db()
        for text in ["My DuitNow transfer failed, please help.", "what's the weather today? lol safe account"]:
            with self.subTest(text=text):
                rec = process_complaint({"complaint_id": "T-NOCLUE", "customer_id": "CUS-00150", "channel": "App chat",
                                         "received_at": "2026-09-30 10:00", "subject": "", "text": text})
                d = rec.decision
                self.assertEqual((d.matched_txn_id, d.refund_amount_myr), ("", 0.0))
                self.assertIn("NO_MATCH", d.flags)
                self.assertNotEqual(d.route, "AUTO_RESOLVE")          # a person looks at it
                self.assertIn("TXN-0145614", d.candidates)             # still shown to the officer as a candidate
        rec = process_complaint({"complaint_id": "T-CLUE", "customer_id": "CUS-00150", "channel": "App chat",
                                 "received_at": "2026-09-30 10:00", "subject": "",
                                 "text": "My DuitNow transfer of RM46.54 failed, please help."})
        self.assertEqual(rec.decision.matched_txn_id, "TXN-0145614")   # one real clue is enough

    def test_self_check_catches_invented_facts(self):
        db = tools.get_db()
        c = db.complaints["CMP-00244"]
        rec = process_complaint(c)
        self.assertEqual(checks.check(c, rec.decision, rec.reply_text, rec.reply_language), [])
        bad = "We have refunded RM600.00 for transaction TXN-0088299."
        self.assertTrue(checks.check(c, rec.decision, bad, "EN"))


if __name__ == "__main__":
    unittest.main()
