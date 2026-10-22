"""Fast offline tests for the deterministic parts. Run: python -m unittest discover tests"""
import datetime as dt
import unittest
from unittest import mock

from agent import checks, matching, policy, tools
from agent.dates import resolve_dates
from agent.extract import extract_rules
from agent.pipeline import process_complaint
from agent.schemas import Extraction

RECV = dt.datetime(2026, 8, 25, 10, 0)   # a Tuesday


def _debit(txn_id, amount, name="Foo Wei Ming"):
    return {"txn_id": txn_id, "amount": amount, "merchant_or_counterparty": name, "card_last4": "",
            "time": dt.datetime(2026, 8, 20, 12, 0), "txn_time": "2026-08-20 12:00:00", "description": ""}


def _match(text, ex, debits):
    """Match against synthetic debits instead of the customer's real ones."""
    complaint = {"customer_id": "CUS-TEST", "received_at": "2026-08-25 10:00", "text": text}
    with mock.patch.object(tools, "find_debits", return_value=debits):
        return matching.find_transaction(complaint, ex)


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


class Matching(unittest.TestCase):
    ABOUT_100 = Extraction(category="FAILED_TRANSFER", language="EN", amount=100.0, amount_approx=True)

    def test_hedged_amount_20_percent_off_is_kept(self):
        m = _match("about RM100 transfer failed", self.ABOUT_100, [_debit("T1", 120.00)])
        self.assertEqual(m.txn["txn_id"], "T1")

    def test_hedged_amount_over_20_percent_off_is_dropped(self):
        m = _match("about RM100 transfer failed", self.ABOUT_100, [_debit("T1", 123.25)])
        self.assertIsNone(m.txn)
        self.assertEqual(m.flags, ["NO_MATCH"])

    def test_exact_amount_must_match_to_the_cent(self):
        ex = Extraction(category="FAILED_TRANSFER", language="EN", amount=227.11)
        m = _match("RM227.11 transfer failed", ex, [_debit("T1", 227.12)])
        self.assertIsNone(m.txn)

    def test_closer_hedged_amount_ranks_higher(self):
        m = _match("about RM100 transfer failed", self.ABOUT_100, [_debit("FAR", 115.00), _debit("NEAR", 101.00)])
        self.assertEqual(m.txn["txn_id"], "NEAR")
        self.assertEqual([t for _, t in m.candidates], ["NEAR", "FAR"])

    def test_real_hedged_amounts_beyond_5_percent(self):
        db = tools.get_db()
        for cid, want in [("CMP-00464", "TXN-0090984"),     # "dalam RM100", real RM107.13
                          ("CMP-00295", "TXN-0146195")]:    # "about RM250", real RM227.11; the later of the pair
            c = db.complaints[cid]
            m = matching.find_transaction(c, extract_rules(c))
            self.assertEqual(m.txn["txn_id"] if m.txn else None, want, cid)

    def test_town_words(self):
        self.assertTrue({"melaka", "lepas", "kota"} <= tools.town_words())
        self.assertIs(tools.town_words(), tools.town_words())

    def test_town_name_alone_is_not_a_name_match(self):
        ex = Extraction(category="DUPLICATE_CHARGE", language="EN")
        text = "charged twice at Butik Ayu Melaka"
        self.assertNotIn("name", _match(text, ex, [_debit("T1", 50.0, "Kedai Buku Ilmu Melaka")]).reasons[0])
        self.assertIn("name", _match(text, ex, [_debit("T1", 50.0, "Butik Ayu Melaka")]).reasons[0])

    def test_extracted_counterparty_with_town_still_matches(self):
        ex = Extraction(category="ATM_NOT_DISPENSED", language="EN", counterparty="Melaka Station")
        m = _match("the ATM at Melaka Station did not dispense", ex, [_debit("T1", 50.0, "Melaka Station")])
        self.assertIn("name", m.reasons[0])


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
