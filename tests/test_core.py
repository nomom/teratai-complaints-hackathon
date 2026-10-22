"""Fast offline tests for the deterministic parts. Run: python -m unittest discover tests
Person A's dates, matching and policy tests are in tests/test_decision.py."""
import unittest

from agent import checks, tools
from agent.pipeline import process_complaint


class EndToEnd(unittest.TestCase):
    def test_readme_examples(self):
        db = tools.get_db()
        rec = process_complaint(db.complaints["CMP-00165"])
        self.assertEqual((rec.decision.matched_txn_id, rec.decision.outcome, rec.decision.refund_amount_myr,
                          rec.reply_language), ("TXN-0115572", "REFUND", 46.66, "MS"))
        rec = process_complaint(db.complaints["CMP-00387"])
        self.assertEqual((rec.decision.outcome, rec.decision.route), ("INVESTIGATE", "FRAUD_TEAM"))

    def test_self_check_catches_invented_facts(self):
        db = tools.get_db()
        c = db.complaints["CMP-00244"]
        rec = process_complaint(c)
        self.assertEqual(checks.check(c, rec.decision, rec.reply_text, rec.reply_language), [])
        bad = "We have refunded RM600.00 for transaction TXN-0088299."
        self.assertTrue(checks.check(c, rec.decision, bad, "EN"))


if __name__ == "__main__":
    unittest.main()
