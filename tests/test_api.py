"""The HTTP API the React app (web/) uses: sign-in, role-filtered lists and counts, case detail, actions, intake.

Runs on a throwaway case store, inbox and account files, with real training complaints decided by the agent with the
LLM off. No real file is written.
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

from agent import llm, tools
from agent.pipeline import process_complaint
from app import api, store, worker
from app.UserAccessControl import accounts, auth

ROOT = Path(__file__).resolve().parent.parent
APPROVAL, FRAUD, RESOLVED = "CMP-00244", "CMP-00387", "CMP-00001"     # customers CUS-02394, CUS-02323, CUS-00150


class Api(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy(ROOT / "data" / "staff.csv", tmp / "staff.csv")
        (tmp / "inbox").mkdir()
        self.inbox = tmp / "inbox"
        for target, name, value in ((store, "DB_PATH", tmp / "cases.db"), (worker, "INBOX", self.inbox),
                                    (accounts, "STAFF_CSV", tmp / "staff.csv"),
                                    (accounts, "CUSTOMER_ACCOUNTS_CSV", tmp / "customer_accounts.csv"),
                                    (auth, "_secret", lambda: b"api-tests"), (llm, "PROVIDER", "")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for cid in (APPROVAL, FRAUD, RESOLVED):
            store.save_case(process_complaint(tools.get_db().complaints[cid]))
        self.client = TestClient(api.app)

    def headers(self, username, password="1234"):
        r = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def customer(self, customer_id):
        self.client.post("/auth/signup", json={"customer_id": customer_id, "password": "secret1"})
        return self.headers(customer_id, "secret1")

    def test_case_list_is_role_filtered_and_light(self):
        rows = self.client.get("/cases", headers=self.headers("officer1")).json()
        self.assertEqual([r["complaint_id"] for r in rows], [APPROVAL])
        self.assertNotIn("record", rows[0])
        self.assertIs(rows[0]["flagged"], False)
        self.assertEqual(self.client.get("/cases").status_code, 401)

    def test_flagged_shows_in_the_list(self):
        store.flag_for_review(RESOLVED, "manager1", "check the refund")
        rows = {r["complaint_id"]: r for r in self.client.get("/cases", headers=self.headers("manager1")).json()}
        self.assertEqual((rows[RESOLVED]["flagged"], rows[APPROVAL]["flagged"]), (True, False))

    def test_counts_follow_the_role(self):
        self.assertEqual(self.client.get("/cases/counts", headers=self.headers("officer1")).json(),
                         {"PENDING_APPROVAL": 1})
        self.assertEqual(sum(self.client.get("/cases/counts", headers=self.headers("manager1")).json().values()), 3)
        self.assertEqual(self.client.get("/cases/counts", headers=self.customer("CUS-00150")).status_code, 403)

    def test_case_detail_has_the_summary_for_staff_only(self):
        staff = self.client.get(f"/cases/{APPROVAL}", headers=self.headers("officer1")).json()
        self.assertIn("headline", staff["summary"])
        self.assertIn("record", staff)
        own = self.client.get(f"/cases/{RESOLVED}", headers=self.customer("CUS-00150")).json()
        self.assertNotIn("summary", own)
        self.assertNotIn("reply_text", own)
        self.assertEqual([m["from"] for m in own["messages"]], ["bank"])

    def test_another_teams_case_says_where_it_went(self):
        r = self.client.get(f"/cases/{FRAUD}", headers=self.headers("officer1"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["route"], "FRAUD_TEAM")
        r = self.client.get(f"/cases/{FRAUD}", headers=self.customer("CUS-00150"))
        self.assertNotIn("route", r.json()["detail"])

    def test_edited_reply_failing_the_self_check_is_refused(self):
        draft = store.get_case(APPROVAL)["reply_text"]
        r = self.client.post(f"/cases/{APPROVAL}/approve", headers=self.headers("officer1"),
                             json={"reply_text": draft + "\nWe also refunded TXN-9999999."})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(any("TXN-9999999" in p for p in r.json()["detail"]["problems"]))
        self.assertEqual(store.get_case(APPROVAL)["status"], "PENDING_APPROVAL")

    def test_customer_files_under_their_own_id(self):
        r = self.client.post("/me/complaints", headers=self.customer("CUS-00150"),
                             json={"text": "My DuitNow transfer of RM46.54 failed.", "customer_id": "CUS-00001"})
        self.assertEqual(r.status_code, 202)
        filed = json.loads((self.inbox / f"{r.json()['complaint_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual((filed["customer_id"], filed["channel"], filed["received_at"]),
                         ("CUS-00150", "App chat", "2026-09-30 18:00"))
        self.assertEqual(self.client.post("/me/complaints", headers=self.headers("officer1"),
                                          json={"text": "x"}).status_code, 403)

    def test_customer_reads_their_own_profile(self):
        me = self.client.get("/me/profile", headers=self.customer("CUS-00001")).json()
        self.assertEqual((me["customer_id"], me["full_name"], me["city"], me["preferred_language"]),
                         ("CUS-00001", "Chan Zhi Hao", "Petaling Jaya", "EN"))
        self.assertEqual([(a["account_id"], a["product"], a["card_last4"]) for a in me["accounts"]],
                         [("ACC-000001", "Savings Plus", "2462"), ("ACC-000002", "Credit Card Classic", "1882")])

    def test_customer_reads_their_own_transactions(self):
        body = self.client.get("/me/transactions", headers=self.customer("CUS-00001")).json()
        rows = body["transactions"]
        self.assertEqual((body["as_of"], body["report_window_days"]), ("2026-09-30 18:00", 45))
        self.assertEqual(len(rows), len(tools.get_db().txns_by_customer["CUS-00001"]))
        self.assertEqual([r["txn_time"] for r in rows], sorted((r["txn_time"] for r in rows), reverse=True))
        self.assertTrue(all(r["txn_id"] in {t["txn_id"] for t in tools.get_db().txns_by_customer["CUS-00001"]}
                            for r in rows))
        by_id = {r["txn_id"]: r for r in rows}
        self.assertEqual(by_id["TXN-0119292"]["amount_myr"], 90.90)
        for field in ("auth_method", "counterparty_account", "customer_id", "time", "amount"):
            self.assertNotIn(field, rows[0])                    # statement fields only, nothing internal
        # reportable = within the 45 days before the app's date, 2026-09-30 18:00
        self.assertEqual({t: by_id[t]["reportable"] for t in ("TXN-0113570", "TXN-0115590", "TXN-0152536",
                                                               "TXN-0153369")},
                         {"TXN-0113570": False, "TXN-0115590": True, "TXN-0152536": True, "TXN-0153369": False})

    def test_own_records_are_for_customers_only(self):
        for path in ("/me/profile", "/me/transactions"):
            self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.client.get(path, headers=self.headers("manager1")).status_code, 403)
            self.assertEqual(self.client.get(path, headers=self.headers("officer1")).status_code, 403)
        other = self.client.get("/me/transactions", headers=self.customer("CUS-00150")).json()["transactions"]
        self.assertNotIn("TXN-0119292", {r["txn_id"] for r in other})     # CUS-00001's charge, not theirs


if __name__ == "__main__":
    unittest.main()
