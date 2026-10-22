"""Owner: C. The ops platform's rules: roles, the self-check before sending, two-tier approval, the fraud flow, intake.

Uses a throwaway case store and inbox, and real training complaints run through the agent (LLM off).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from agent import tools
from agent.pipeline import process_complaint
from app import ops, store, worker


def user(uid):
    return ops.get_user(uid)


class OpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._db, self._inbox = store.DB_PATH, worker.INBOX
        store.DB_PATH = self.tmp / "cases.db"
        worker.INBOX = ops.INBOX = self.tmp / "inbox"
        db = tools.get_db()
        # Real complaints, under test IDs: ATM refund RM550, card fraud (OTP), failed transfer refund RM2,584.75
        for src, cid in (("CMP-00244", "T-ATM"), ("CMP-00387", "T-FRAUD"), ("CMP-01014", "T-BIG")):
            store.save_case(process_complaint(dict(db.complaints[src], complaint_id=cid)))
        self.aina, self.hafiz, self.mei, self.ravi = user("aina"), user("hafiz"), user("meiling"), user("ravi")

    def tearDown(self):
        store.DB_PATH, worker.INBOX, ops.INBOX = self._db, self._inbox, self._inbox
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cases_land_where_expected(self):
        self.assertEqual(store.get_case("T-ATM")["status"], "PENDING_APPROVAL")
        self.assertEqual(store.get_case("T-FRAUD")["status"], "FRAUD_QUEUE")
        self.assertEqual(store.get_case("T-BIG")["status"], "PENDING_APPROVAL")

    def test_each_role_sees_only_its_cases(self):
        fraud, atm = store.get_case("T-FRAUD"), store.get_case("T-ATM")
        self.assertFalse(ops.can(self.aina, "view", fraud))
        self.assertTrue(ops.can(self.aina, "view", atm))
        self.assertTrue(ops.can(self.mei, "view", fraud))
        self.assertFalse(ops.can(self.mei, "view", atm))
        self.assertTrue(ops.can(self.ravi, "view", fraud) and ops.can(self.ravi, "view", atm))
        self.assertEqual([r["complaint_id"] for r in ops.cases(user=self.mei)], ["T-FRAUD"])

    def test_bad_reply_is_blocked_and_logged(self):
        with self.assertRaises(ops.SelfCheckFailed) as e:
            ops.approve(self.aina, "T-ATM", "We have refunded RM600.00 for transaction TXN-0088299.")
        self.assertTrue(any("TXN-0088299" in p for p in e.exception.problems))
        self.assertEqual(store.get_case("T-ATM")["status"], "PENDING_APPROVAL")
        self.assertEqual(ops.actions_for("T-ATM")[-1]["action"], "send_blocked")
        self.assertIn("send_blocked", [a["action"] for a in store.get_case("T-ATM")["audit"]])

    def test_approve_keeps_the_agents_draft(self):
        draft = store.get_case("T-ATM")["reply_text"]
        edited = draft.replace("Thank you", "Many thanks")
        ops.approve(self.aina, "T-ATM", edited)
        case = store.get_case("T-ATM")
        self.assertEqual(case["status"], "APPROVED")
        self.assertEqual(case["reply_text"], draft)                       # agent's draft untouched
        self.assertEqual(ops.final_action("T-ATM")["reply_text"], edited)  # what was sent lives in staff_actions

    def test_over_limit_goes_to_a_manager(self):
        with self.assertRaises(ops.PermissionDenied):
            ops.approve(self.hafiz, "T-BIG", store.get_case("T-BIG")["reply_text"])
        ops.escalate(self.hafiz, "T-BIG", store.get_case("T-BIG")["reply_text"], "above my RM1,000 limit")
        self.assertEqual(store.get_case("T-BIG")["status"], ops.ESCALATED)
        with self.assertRaises(ops.PermissionDenied):
            ops.approve(self.aina, "T-BIG", None)                         # another officer can't clear it
        ops.approve(self.ravi, "T-BIG", None)                             # manager sends the proposed reply
        self.assertEqual(store.get_case("T-BIG")["status"], "APPROVED")

    def test_fraud_flow(self):
        reply = store.get_case("T-FRAUD")["reply_text"]
        with self.assertRaises(ops.PermissionDenied):
            ops.fraud_ack(self.aina, "T-FRAUD", reply)                    # officers don't work fraud cases
        with self.assertRaises(ops.PermissionDenied):
            ops.fraud_note(self.mei, "T-FRAUD", "Recall requested", "x")  # acknowledge first
        ops.fraud_ack(self.mei, "T-FRAUD", reply)
        self.assertEqual((store.get_case("T-FRAUD")["status"], ops.fraud_stage("T-FRAUD")), ("FRAUD_QUEUE", "ACKNOWLEDGED"))
        ops.fraud_note(self.mei, "T-FRAUD", "Card blocked", "blocked card ending 4969")
        self.assertEqual(ops.fraud_stage("T-FRAUD"), "INVESTIGATING")
        ops.fraud_outcome(self.mei, "T-FRAUD", "Not fraud", "customer confirmed the OTP")
        self.assertEqual(store.get_case("T-FRAUD")["status"], ops.FRAUD_CLOSED)

    def test_fraud_escalation_returns_to_the_fraud_team(self):
        ops.escalate(self.mei, "T-FRAUD", store.get_case("T-FRAUD")["reply_text"], "high value, abroad")
        with self.assertRaises(ops.PermissionDenied):
            ops.approve(self.ravi, "T-FRAUD", None)
        ops.return_escalation(self.ravi, "T-FRAUD", "call the customer before closing")
        self.assertEqual(store.get_case("T-FRAUD")["status"], "FRAUD_QUEUE")

    def test_reject_needs_a_reason(self):
        with self.assertRaises(ValueError):
            ops.reject(self.aina, "T-ATM", " ")
        ops.reject(self.aina, "T-ATM", "wrong ATM")
        self.assertEqual(store.get_case("T-ATM")["status"], "REJECTED")

    def test_csv_intake(self):
        rows = ops.parse_csv_rows('complaint_id,customer_id,received_at,channel,subject,text\n'
                                  'LIVE-01,CUS-00566,2026-09-30 10:15,App chat,,"Hi, charged twice, RM46.66"')
        self.assertEqual(rows[0]["text"], "Hi, charged twice, RM46.66")
        for bad in ("LIVE-02,CUS-1,2026-09-30 10:15,App chat,,Hi, charged twice",   # unquoted comma: 7 columns
                    "LIVE-03,CUS-1,30/09/2026,App chat,,hello"):                    # wrong date format
            with self.assertRaises(ValueError):
                ops.parse_csv_rows(bad)
        with self.assertRaises(ops.PermissionDenied):
            ops.take_in(self.mei, rows)                                     # fraud analysts don't take in complaints
        ids, skipped = ops.take_in(self.aina, rows)
        self.assertEqual((ids, skipped), (["LIVE-01"], []))
        self.assertTrue((ops.INBOX / "LIVE-01.json").exists())
        self.assertEqual(ops.take_in(self.aina, rows), ([], [("LIVE-01", "already taken in")]))


    def test_customer_sees_and_acts_on_own_complaints_only(self):
        shahrul, siti = user("cus-02323"), user("cus-01272")            # T-FRAUD is Shahrul's, T-BIG is Siti's
        self.assertEqual([r["complaint_id"] for r in ops.cases(user=shahrul)], ["T-FRAUD"])
        self.assertFalse(ops.can(shahrul, "view", store.get_case("T-BIG")))
        for action in ("approve", "reject", "fraud_ack", "intake"):
            self.assertFalse(ops.can(siti, action, store.get_case("T-BIG")))
        with self.assertRaises(ops.PermissionDenied):
            ops.customer_reply(siti, "T-BIG", "more details")           # the bank isn't waiting for a reply
        with self.assertRaises(ops.PermissionDenied):
            ops.submit_own(self.aina, "staff can't post as a customer")

    def test_customer_thread_hides_unsent_drafts(self):
        siti = user("cus-01272")
        msgs = ops.thread(store.get_case("T-BIG"))                       # refund waiting for approval: nothing sent yet
        self.assertEqual([m["from"] for m in msgs], ["customer"])
        ops.approve(self.ravi, "T-BIG", None)
        msgs = ops.thread(store.get_case("T-BIG"))
        self.assertEqual([m["from"] for m in msgs], ["customer", "bank"])
        self.assertTrue(ops.can(siti, "view", store.get_case("T-BIG")))

    def test_customer_submits_from_the_portal(self):
        siti = user("cus-01272")
        cid = ops.submit_own(siti, "My IBG transfer of RM2,584.75 to Wei Ming on 26 September failed.")
        c = ops.waiting_in_inbox("CUS-01272")[0]
        self.assertEqual((c["complaint_id"], c["customer_id"], c["channel"]), (cid, "CUS-01272", "App chat"))
        self.assertTrue(c["received_at"].startswith(ops.DEMO_DAY))
        self.assertEqual(ops.waiting_in_inbox("CUS-02323"), [])

    def test_old_store_gets_the_customer_column(self):
        store.DB_PATH = self.tmp / "old.db"
        import sqlite3
        con = sqlite3.connect(store.DB_PATH)
        con.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, name TEXT, role TEXT, approval_limit_myr REAL)")
        con.execute("INSERT INTO users VALUES ('aina', 'Aina Rahman', 'officer', 5000)")
        con.commit()
        con.close()
        self.assertEqual(user("cus-00996")["customer_id"], "CUS-00996")
        self.assertEqual(user("aina")["approval_limit_myr"], 5000)


if __name__ == "__main__":
    unittest.main()
