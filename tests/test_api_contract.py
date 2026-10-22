"""The organisers' API contract (docs/api.md), on a throwaway case store and inbox. Run: python -m unittest discover tests

Mirrors what scoring/api_check.py checks in the live round: intake, the case shape, case_state and sent, the robustness
probes (health, unknown case, missing text, unknown customer, the same complaint twice) and human in the loop.
"""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # tests never read .env ...
os.environ["LLM_PROVIDER"] = ""              # ... and never call a real LLM

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from agent import tools
from app import store, worker
from app.api import app

ROOT = Path(__file__).resolve().parent.parent

ATM = {"complaint_id": "CMP-00244", "customer_id": "CUS-02394", "received_at": "2026-07-20 22:32", "channel": "Email",
       "subject": "ATM did not dispense cash",
       "text": "Hello, the machine did not dispense all of the cash when I withdrew about RM1,500 last Friday, "
               "but the whole amount was deducted. Please resolve this quickly."}   # examples/live_complaint_example.json
DECISION = ("category", "matched_txn_id", "outcome", "refund_amount_myr", "priority", "reply_language", "route",
            "reply_text")


class Contract(unittest.TestCase):
    def setUp(self):
        tools.get_db()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for p in (mock.patch.object(store, "DB_PATH", tmp / "cases.db"),     # never runtime/cases.db or inbox/
                  mock.patch.object(worker, "INBOX", tmp / "inbox")):
            p.start()
            self.addCleanup(p.stop)
        (tmp / "inbox" / "failed").mkdir(parents=True)
        (tmp / "inbox" / "processed").mkdir()
        self.inbox = tmp / "inbox"
        self.api = TestClient(app)

    def work(self):
        """What the worker does: handle every complaint waiting in the inbox."""
        for path in sorted(self.inbox.glob("*.json")):
            worker.handle(path)
            path.replace(self.inbox / "processed" / path.name)

    def decided(self, complaint=ATM):
        self.assertEqual(self.api.post("/complaints", json=complaint).status_code, 202)
        self.work()
        return self.api.get(f"/cases/{complaint['complaint_id']}").json()

    def test_intake_then_processing_then_done(self):
        r = self.api.post("/complaints", json=ATM)
        self.assertEqual((r.status_code, r.json()), (202, {"complaint_id": "CMP-00244", "status": "processing"}))
        self.assertEqual(self.api.get("/cases/CMP-00244").json(), {"complaint_id": "CMP-00244", "status": "processing"})
        self.work()
        case = self.api.get("/cases/CMP-00244").json()
        self.assertEqual({k: case[k] for k in ("status", "category", "matched_txn_id", "outcome", "refund_amount_myr",
                                                "priority", "reply_language", "route", "self_check", "case_state",
                                                "sent", "human_action")},
                         {"status": "done", "category": "ATM_NOT_DISPENSED", "matched_txn_id": "TXN-0088211",
                          "outcome": "REFUND", "refund_amount_myr": "550.00", "priority": "P2", "reply_language": "EN",
                          "route": "HUMAN_APPROVAL", "self_check": "passed", "case_state": "awaiting_approval",
                          "sent": False, "human_action": None})
        self.assertTrue(case["reply_text"].strip())
        self.assertNotIn("record", case)                    # no evidence or customer details without a login

    def test_case_state_and_sent_follow_the_route(self):
        db = tools.get_db()
        for cid, state, sent in (("CMP-00165", "auto_resolved", True), ("CMP-00387", "with_fraud_team", False)):
            c = {k: db.complaints[cid][k] for k in ("complaint_id", "customer_id", "received_at", "channel", "subject",
                                                     "text")}
            with self.subTest(cid=cid):
                case = self.decided(c)
                self.assertEqual((case["case_state"], case["sent"]), (state, sent))

    def test_robustness_probes(self):
        self.assertEqual(self.api.get("/health").status_code, 200)
        self.assertEqual(self.api.get("/cases/NO-SUCH-CASE-123").status_code, 404)
        no_text = {k: v for k, v in ATM.items() if k != "text"}
        self.assertEqual(self.api.post("/complaints", json=no_text).status_code, 422)
        for bad in ({"text": "   "}, {"customer_id": "CUS-99999"}, {"received_at": "yesterday"},
                    {"complaint_id": "../../etc/x"}, {"complaint_id": ""}):
            with self.subTest(bad=bad):
                self.assertEqual(self.api.post("/complaints", json={**ATM, **bad}).status_code, 422)
        self.assertEqual(list(self.inbox.glob("*.json")), [])     # nothing bad reached the inbox

    def test_same_complaint_twice_is_one_case(self):
        before = self.decided()
        r = self.api.post("/complaints", json={**ATM, "text": "a different text this time"})
        self.assertEqual((r.status_code, r.json()["status"]), (200, "done"))
        self.assertEqual(list(self.inbox.glob("*.json")), [])     # not queued again
        self.assertEqual(self.api.get("/cases/CMP-00244").json(), before)

    def test_worker_never_reprocesses_a_stored_case(self):
        before = self.decided()
        worker.submit({**ATM, "text": "changed"})                 # e.g. dropped into inbox/ by hand
        self.work()
        self.assertEqual(self.api.get("/cases/CMP-00244").json(), before)

    def test_failed_complaint_reports_error(self):
        (self.inbox / "failed" / "BROKEN-1.error.txt").write_text("Traceback ...\nKeyError: 'CUS-0'\n", encoding="utf-8")
        self.assertEqual(self.api.get("/cases/BROKEN-1").json(),
                         {"complaint_id": "BROKEN-1", "status": "error", "error": "KeyError: 'CUS-0'"})

    def test_human_in_the_loop(self):
        case = self.decided()
        url = "/cases/CMP-00244/actions"
        bad = {"action": "edit_approve", "actor": "probe", "reason": "invented amount",
               "reply_text": case["reply_text"] + " We have also credited RM987.65 to your account."}
        self.assertEqual(self.api.post(url, json=bad).status_code, 422)
        held = self.api.get("/cases/CMP-00244").json()
        self.assertEqual((held["case_state"], held["sent"], held["human_action"]), ("awaiting_approval", False, None))
        for body in ({"action": "approve"}, {"action": "send", "actor": "x"}, {"action": "approve", "actor": " "},
                     {"action": "reject", "actor": "x"}, {"action": "edit_approve", "actor": "x", "reason": "r"}):
            with self.subTest(body=body):
                self.assertEqual(self.api.post(url, json=body).status_code, 422)
        r = self.api.post(url, json={"action": "approve", "actor": "Aina (complaints officer)",
                                     "reason": "Journal confirms RM950 dispensed of RM1,500"})
        done = r.json()
        self.assertEqual((r.status_code, done["case_state"], done["sent"]), (200, "approved", True))
        self.assertEqual({k: done["human_action"][k] for k in ("action", "actor", "reason", "reply_text")},
                         {"action": "approve", "actor": "Aina (complaints officer)",
                          "reason": "Journal confirms RM950 dispensed of RM1,500", "reply_text": case["reply_text"]})
        self.assertEqual({k: done[k] for k in DECISION}, {k: case[k] for k in DECISION})   # the agent's decision stays
        self.assertEqual(self.api.post(url, json={"action": "approve", "actor": "x"}).status_code, 409)
        self.assertEqual(self.api.post("/cases/NOPE/actions", json={"action": "approve", "actor": "x"}).status_code, 404)

    def test_edit_approve_and_reject(self):
        db = tools.get_db()
        case = self.decided()
        edited = case["reply_text"].replace("We apologise for the inconvenience.", "We are sorry for the trouble.")
        r = self.api.post("/cases/CMP-00244/actions", json={"action": "edit_approve", "actor": "Aina",
                                                            "reason": "warmer wording", "reply_text": edited})
        self.assertEqual((r.status_code, r.json()["human_action"]["reply_text"], r.json()["reply_text"]),
                         (200, edited, case["reply_text"]))                 # sent the edit, kept the agent's draft
        decline = {k: db.complaints["CMP-00008"][k] for k in ("complaint_id", "customer_id", "received_at", "channel",
                                                               "subject", "text")}
        self.decided(decline)
        r = self.api.post("/cases/CMP-00008/actions", json={"action": "reject", "actor": "Aina", "reason": "call them"})
        self.assertEqual((r.json()["case_state"], r.json()["sent"], r.json()["human_action"]["action"]),
                         ("rejected", False, "reject"))

    def test_fraud_cases_are_not_acted_on_through_actions(self):
        db = tools.get_db()
        fraud = {k: db.complaints["CMP-00387"][k] for k in ("complaint_id", "customer_id", "received_at", "channel",
                                                             "subject", "text")}
        self.decided(fraud)
        r = self.api.post("/cases/CMP-00387/actions", json={"action": "approve", "actor": "x", "reason": "y"})
        self.assertEqual(r.status_code, 409)

    def test_overloaded_intake_says_busy_instead_of_timing_out(self):
        from app import api
        with mock.patch.object(api, "MAX_BACKLOG", 2):
            for i in (1, 2):
                self.assertEqual(self.api.post("/complaints", json={**ATM, "complaint_id": f"Q-{i}"}).status_code, 202)
            r = self.api.post("/complaints", json={**ATM, "complaint_id": "Q-3"})
            self.assertEqual((r.status_code, r.headers.get("Retry-After")), (503, "15"))
            self.assertFalse((self.inbox / "Q-3.json").exists())                  # nothing half-accepted
            dup = self.api.post("/complaints", json={**ATM, "complaint_id": "Q-1"})  # a known one still answers
            self.assertEqual((dup.status_code, dup.json()["status"]), (200, "processing"))
            self.work()                                                            # the queue drains
            self.assertEqual(self.api.post("/complaints", json={**ATM, "complaint_id": "Q-3"}).status_code, 202)

    def test_case_store_uses_wal_and_a_cheap_existence_check(self):
        self.decided()
        with store.connect() as con:
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        self.assertEqual((store.has_case("CMP-00244"), store.has_case("NOPE")), (True, False))

    def test_customer_id_in_any_case_is_normalised(self):
        self.assertEqual(self.api.post("/complaints", json={**ATM, "customer_id": "cus-02394"}).status_code, 202)
        self.work()
        self.assertEqual(self.api.get("/cases/CMP-00244").json()["matched_txn_id"], "TXN-0088211")   # decided, no error

    def test_worker_job_outcomes(self):
        busy = {"CMP-00244.json", "GONE.json", "BAD.json"}
        worker.submit(ATM)
        worker.run(self.inbox / "CMP-00244.json", busy)                       # normal: decided, moved to processed/
        self.assertTrue((self.inbox / "processed" / "CMP-00244.json").exists())
        worker.run(self.inbox / "GONE.json", busy)          # handed out twice, already finished: not a failure
        self.assertEqual(list((self.inbox / "failed").iterdir()), [])
        (self.inbox / "BAD.json").write_text("{not json", encoding="utf-8")
        worker.run(self.inbox / "BAD.json", busy)                              # a real failure is still recorded
        self.assertEqual(sorted(p.name for p in (self.inbox / "failed").iterdir()), ["BAD.error.txt", "BAD.json"])
        self.assertEqual(busy, set())                                          # every job released its file

    def staff_token(self):
        from app.UserAccessControl import accounts, auth
        for target, name, value in ((accounts, "STAFF_CSV", ROOT / "data" / "staff.csv"),
                                    (auth, "_secret", lambda: b"contract-tests")):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        r = self.api.post("/auth/login", json={"username": "officer1", "password": "1234"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_same_endpoint_gives_staff_the_full_case_and_the_organisers_the_contract(self):
        self.decided()
        public = self.api.get("/cases/CMP-00244").json()                 # no credentials: the contract view
        self.assertEqual((public["status"], public["case_state"]), ("done", "awaiting_approval"))
        self.assertNotIn("record", public)
        staff = self.api.get("/cases/CMP-00244", headers=self.staff_token()).json()   # the React app's view
        self.assertIn("record", staff)
        self.assertIn("headline", staff["summary"])
        bad = self.api.get("/cases/CMP-00244", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual(bad.status_code, 401)                           # a bad token is never "no login"

    def test_signed_in_staff_may_leave_the_id_empty_the_organisers_may_not(self):
        no_id = {**ATM, "complaint_id": ""}
        self.assertEqual(self.api.post("/complaints", json=no_id).status_code, 422)
        missing = {k: v for k, v in ATM.items() if k != "complaint_id"}
        self.assertEqual(self.api.post("/complaints", json=missing).status_code, 422)
        r = self.api.post("/complaints", json=no_id, headers=self.staff_token())    # the React staff form
        self.assertEqual(r.status_code, 202)
        self.assertRegex(r.json()["complaint_id"], r"^LIVE-[0-9A-F]{8}$")


if __name__ == "__main__":
    unittest.main()
