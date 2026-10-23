"""The staff dashboard (GET /dashboard, app/dashboard.py): its numbers, its filters, and that each role only counts
the cases it may open. Runs on a throwaway case store with a handful of cases written straight into it."""

import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # tests never read .env ...
os.environ["LLM_PROVIDER"] = ""              # ... and never call a real LLM

import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import api, dashboard, store
from app.UserAccessControl import accounts, auth, roles

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 10, 1, 12, 0)

# id, route, status, category, outcome, refund, channel, received_at, created_at, sla_due
CASES = (
    ("A", "HUMAN_APPROVAL", "PENDING_APPROVAL", "FEE_DISPUTE", "REFUND", 50.0, "Email", "2026-09-01 09:00",
     "2026-09-30 12:00:00", "2026-09-02 09:00"),       # 24 h allowed, in the store for 24 h: due now, not overdue yet
    ("B", "HUMAN_APPROVAL", "APPROVED", "FEE_DISPUTE", "REFUND", 20.0, "App chat", "2026-09-02 10:00",
     "2026-09-01 00:00:00", "2026-09-03 10:00"),
    ("C", "FRAUD_TEAM", "FRAUD_QUEUE", "SCAM_TRANSFER", "INVESTIGATE", None, "App chat", "2026-09-02 11:00",
     "2026-09-29 12:00:00", "2026-09-02 15:00"),       # 4 h allowed, in the store for two days: overdue
    ("D", "AUTO_RESOLVE", "RESOLVED", "DUPLICATE_CHARGE", "REFUND", 30.0, "Email", "2026-09-03 08:00",
     "2026-09-03 08:00:00", "2026-09-04 08:00"),
    ("E", None, "AWAITING_CUSTOMER", "FAILED_TRANSFER", None, None, "Branch form", "2026-09-04 08:00",
     "2026-10-01 11:00:00", "2026-09-05 08:00"),
)


class Dashboard(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy(ROOT / "data" / "staff.csv", tmp / "staff.csv")
        for target, name, value in ((store, "DB_PATH", tmp / "cases.db"), (accounts, "STAFF_CSV", tmp / "staff.csv"),
                                    (accounts, "CUSTOMER_ACCOUNTS_CSV", tmp / "customer_accounts.csv"),
                                    (auth, "_secret", lambda: b"dashboard-tests")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with store.connect() as con:
            for cid, route, status, category, outcome, refund, channel, received, created, due in CASES:
                con.execute("INSERT INTO cases (complaint_id, customer_id, route, status, category, outcome, "
                            "refund_amount_myr, priority, reply_language, channel, received_at, created_at, sla_due, "
                            "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (cid, "CUS-00150", route, status, category, outcome, refund, "P2", "EN", channel, received,
                             created, due, created))
            for cid, actor, action, detail in (
                    ("B", "officer1", "human_action", {"action": "edit_approve"}),
                    ("B", "officer1", "approved", "edited"),
                    ("C", "fraud1", "holding_reply_sent", "as drafted"),
                    ("A", "api_check probe", "human_action", {"action": "reject"}),
                    ("A", "officer1", "human_action", "not json")):        # an odd entry is skipped, not a crash
                store.audit(con, cid, actor, action, detail)
        self.client = TestClient(api.app)

    def headers(self, username, password="1234"):
        r = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def get(self, username, **params):
        return self.client.get("/dashboard", headers=self.headers(username), params=params)

    def test_numbers_for_the_manager(self):
        d = dashboard.summary(scope={}, people=True, now=NOW)
        self.assertEqual(d["total"], 5)
        self.assertEqual(d["kpis"], {"waiting": 2, "awaiting_customer": 1, "auto_sent": 1, "open": 3, "overdue": 1,
                                     "refund_sent_myr": 50.0, "refund_waiting_myr": 50.0})
        self.assertIsNone(d["previous"])                               # all dates: nothing before to compare with
        self.assertEqual(d["daily"][1], {"day": "2026-09-02", "received": 2, "waiting": 1, "awaiting_customer": 0,
                                         "auto_sent": 0, "open": 1, "overdue": 1, "refund_sent_myr": 20.0,
                                         "refund_waiting_myr": 0})
        self.assertEqual(d["categories"][0], {"category": "FEE_DISPUTE", "n": 2, "refund_sent_myr": 20.0,
                                              "outcomes": {"REFUND": 2}})
        self.assertEqual(d["categories"][-1]["outcomes"], {"INVESTIGATE": 1})
        self.assertEqual(d["breakdowns"]["status"], {"APPROVED": 1, "AWAITING_CUSTOMER": 1, "FRAUD_QUEUE": 1,
                                                     "PENDING_APPROVAL": 1, "RESOLVED": 1})
        self.assertEqual(d["breakdowns"]["outcome"], {"REFUND": 3, "INVESTIGATE": 1, "NONE": 1})   # undecided: NONE
        self.assertEqual(d["breakdowns"]["route"]["NONE"], 1)
        self.assertEqual(d["by_day"][:2], [{"day": "2026-09-01", "status": "PENDING_APPROVAL", "n": 1},
                                           {"day": "2026-09-02", "status": "APPROVED", "n": 1}])
        self.assertEqual(d["date_range"], {"first": "2026-09-01", "last": "2026-09-04"})
        self.assertEqual(d["options"]["channel"], ["App chat", "Branch form", "Email"])
        self.assertEqual(d["people"], [
            {"actor": "api_check probe", "name": "api_check probe", "approve": 0, "edit_approve": 0, "reject": 1,
             "holding_reply": 0},
            {"actor": "fraud1", "name": "Daniel Lim Wei Jie", "approve": 0, "edit_approve": 0, "reject": 0,
             "holding_reply": 1},
            {"actor": "officer1", "name": "Aisyah binti Rahman", "approve": 0, "edit_approve": 1, "reject": 0,
             "holding_reply": 0}])

    def test_filters_narrow_every_number_together(self):
        d = dashboard.summary(dashboard.parse_filters({"outcome": "REFUND", "channel": "Email,App chat"}), scope={})
        self.assertEqual(d["total"], 3)
        self.assertEqual(d["breakdowns"]["category"], {"FEE_DISPUTE": 2, "DUPLICATE_CHARGE": 1})
        self.assertEqual(len(d["options"]["category"]), 4)             # the choices are not narrowed by the filters
        self.assertEqual(dashboard.summary(dashboard.parse_filters({"outcome": "NONE"}), scope={})["total"], 1)
        self.assertEqual(dashboard.summary(dashboard.parse_filters({"outcome": "NONE,INVESTIGATE"}), scope={})["total"], 2)
        # dates are whole days, both ends included
        self.assertEqual(dashboard.summary(None, "2026-09-02", "2026-09-03", scope={})["total"], 3)
        self.assertEqual(dashboard.summary(None, "2026-09-04", None, scope={})["total"], 1)
        self.assertEqual(dashboard.summary(None, None, "2026-09-01", scope={})["total"], 1)

    def test_last_days_counts_back_from_the_newest_complaint_the_role_can_see(self):
        d = dashboard.summary(None, scope={}, last_days=2, now=NOW)      # newest overall: 4 Sep
        self.assertEqual((d["total"], d["applied"]), (2, {"date_from": "2026-09-03", "date_to": "2026-09-04"}))
        # compared with the two days before: 1 and 2 Sep (A, B and C)
        self.assertEqual((d["previous"]["date_from"], d["previous"]["date_to"], d["previous"]["total"]),
                         ("2026-09-01", "2026-09-02", 3))
        self.assertEqual((d["previous"]["kpis"]["waiting"], d["previous"]["kpis"]["overdue"]), (2, 1))
        officer = self.get("officer1", last_days=1).json()               # the officer's newest: 2 Sep
        self.assertEqual((officer["total"], officer["applied"]["date_from"]), (1, "2026-09-02"))
        self.assertEqual(self.get("manager1", last_days=0).status_code, 422)
        self.assertEqual(self.get("manager1", last_days="soon").status_code, 422)

    def test_each_role_counts_only_its_own_cases(self):
        officer = self.get("officer1").json()
        self.assertEqual(officer["total"], 2)
        self.assertEqual(set(officer["breakdowns"]["route"]), {"HUMAN_APPROVAL"})
        self.assertEqual(officer["options"]["route"], ["HUMAN_APPROVAL"])
        self.assertIsNone(officer["people"])                           # names staff: the manager's view only
        self.assertEqual(self.get("officer1", route="FRAUD_TEAM").json()["total"], 0)    # a filter never widens it
        fraud = self.get("fraud1").json()
        self.assertEqual((fraud["total"], fraud["breakdowns"]["status"]), (1, {"FRAUD_QUEUE": 1}))
        self.assertIsNone(fraud["people"])
        manager = self.get("manager1", status="PENDING_APPROVAL,FRAUD_QUEUE").json()
        self.assertEqual(manager["total"], 2)
        self.assertEqual(len(manager["people"]), 2)                    # only actions on those two cases

    def test_customers_and_strangers_are_refused(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 401)
        self.client.post("/auth/signup", json={"customer_id": "CUS-00150", "password": "secret1"})
        self.assertEqual(self.client.get("/dashboard", headers=self.headers("CUS-00150", "secret1")).status_code, 403)

    def test_bad_dates_are_422(self):
        self.assertEqual(self.get("manager1", date_from="01/09/2026").status_code, 422)
        r = self.get("manager1", date_from="2026-09-05", date_to="2026-09-01")
        self.assertEqual((r.status_code, r.json()["detail"]), (422, "date_from is after date_to"))

    def test_a_filter_value_is_data_not_sql(self):
        r = self.get("manager1", category="x') OR 1=1 --", channel="Email")
        self.assertEqual((r.status_code, r.json()["total"]), (200, 0))
        self.assertEqual(sum(store.counts().values()), 5)              # and nothing was changed

    def test_empty_store(self):
        with store.connect() as con:
            con.execute("DELETE FROM cases")
        d = dashboard.summary(scope={}, people=True)
        self.assertEqual((d["total"], d["by_day"], d["people"], d["date_range"]), (0, [], [], {"first": None, "last": None}))
        self.assertEqual(d["kpis"]["refund_sent_myr"], 0)
        self.assertEqual(json.loads(json.dumps(d))["breakdowns"]["status"], {})


if __name__ == "__main__":
    unittest.main()
