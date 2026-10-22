"""Access control: customer sign-up, login for all four roles, tokens, and who sees which case.
Runs on temp copies of data/staff.csv and data/customers.csv and a temp customer_accounts.csv, so no real file is written."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.UserAccessControl import accounts, auth, roles

DATA = Path(__file__).resolve().parent.parent / "data"


class AccessControl(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.customers = tmp / "customers.csv"
        shutil.copy(DATA / "staff.csv", tmp / "staff.csv")
        shutil.copy(DATA / "customers.csv", self.customers)
        self.signups = tmp / "customer_accounts.csv"                     # absent until the first sign-up
        for name, path in (("STAFF_CSV", tmp / "staff.csv"), ("CUSTOMERS_CSV", self.customers),
                           ("CUSTOMER_ACCOUNTS_CSV", self.signups)):
            patcher = mock.patch.object(accounts, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assertRefused(self, code, fn, *args):
        with self.assertRaises(auth.AuthError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_staff_log_in_with_1234(self):
        for username, role in (("officer1", roles.OFFICER), ("fraud1", roles.FRAUD), ("manager1", roles.MANAGER)):
            token, account = auth.login(username, "1234")
            self.assertEqual(account.role, role)
            self.assertEqual(auth.user_from_token(token).username, username)
        self.assertRefused("INVALID_CREDENTIALS", auth.login, "officer1", "wrong")
        self.assertIsNone(accounts.get_staff("manager1").approval_limit_myr)

    def test_customer_sign_up_then_log_in(self):
        self.assertRefused("NOT_A_CUSTOMER", auth.check_customer_id, "CUS-99999")
        self.assertRefused("NOT_SIGNED_UP", auth.login, "CUS-00150", "secret1")
        self.assertEqual(auth.check_customer_id(" cus-00150 ").username, "CUS-00150")
        self.assertRefused("PASSWORD_TOO_SHORT", auth.sign_up, "CUS-00150", "abc")

        self.assertFalse(self.signups.exists())
        before = self.customers.read_bytes()
        auth.sign_up("CUS-00150", "secret1")
        auth.sign_up("CUS-00001", "secret2")
        self.assertEqual(self.customers.read_bytes(), before)                   # the organisers' data is untouched
        rows = self.signups.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], "customer_id,full_name,password")
        self.assertEqual([r.split(",")[:2] for r in rows[1:]],
                         [["CUS-00150", "Ravi a/l Rajan"], ["CUS-00001", "Chan Zhi Hao"]])
        stored = accounts.get_customer("CUS-00150").password_hash
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))           # a hash, not the password itself
        self.assertNotIn("secret1", self.signups.read_text(encoding="utf-8"))

        self.assertRefused("ALREADY_SIGNED_UP", auth.sign_up, "CUS-00150", "another")
        self.assertRefused("INVALID_CREDENTIALS", auth.login, "CUS-00150", "wrong")
        token, account = auth.login("CUS-00150", "secret1")
        self.assertEqual((account.role, auth.user_from_token(token).username), (roles.CUSTOMER, "CUS-00150"))

    def test_tampered_token_is_refused(self):
        token, _ = auth.login("officer1", "1234")
        body, sig = token.split(".")
        forged = auth._b64(auth._unb64(body).replace(b'"officer"', b'"manager"'))
        self.assertRefused("INVALID_TOKEN", auth.user_from_token, f"{forged}.{sig}")
        self.assertRefused("INVALID_TOKEN", auth.user_from_token, "not-a-token")

    def test_who_sees_which_case(self):
        approval = {"customer_id": "CUS-00150", "route": "HUMAN_APPROVAL"}
        fraud = {"customer_id": "CUS-00001", "route": "FRAUD_TEAM"}
        awaiting = {"customer_id": "CUS-00150", "route": None}
        officer, analyst, manager = (accounts.get_staff(u) for u in ("officer1", "fraud1", "manager1"))
        customer = accounts.get_customer("CUS-00150")

        self.assertEqual([roles.can_view(officer, c) for c in (approval, fraud, awaiting)], [True, False, False])
        self.assertEqual([roles.can_view(analyst, c) for c in (approval, fraud, awaiting)], [False, True, False])
        self.assertEqual([roles.can_view(manager, c) for c in (approval, fraud, awaiting)], [True, True, True])
        self.assertEqual([roles.can_view(customer, c) for c in (approval, fraud, awaiting)], [True, False, True])
        self.assertFalse(roles.can_act(customer, approval))
        self.assertFalse(roles.can_act(officer, fraud))
        self.assertTrue(roles.can_act(manager, fraud))

    def test_customer_never_sees_an_unsent_draft(self):
        case = {"complaint_id": "CMP-1", "status": "PENDING_APPROVAL", "reply_text": "DRAFT awaiting approval",
                "outcome": "REFUND", "audit": [
                    {"ts": "t1", "actor": "agent", "action": "decided", "detail": "{}"},
                    {"ts": "t2", "actor": "agent", "action": "question_sent", "detail": "Which card?"},
                    {"ts": "t3", "actor": "customer", "action": "customer_replied", "detail": "The 4421 one"}]}
        view = roles.customer_view(case)
        self.assertNotIn("reply_text", view)
        self.assertNotIn("outcome", view)
        self.assertEqual([m["from"] for m in view["messages"]], ["bank", "customer"])

    def test_case_lists_and_counts_follow_the_role(self):
        from app import store
        db = Path(tempfile.mkdtemp()) / "cases.db"
        self.addCleanup(shutil.rmtree, db.parent, ignore_errors=True)
        patcher = mock.patch.object(store, "DB_PATH", db)         # a throwaway database, never runtime/cases.db
        patcher.start()
        self.addCleanup(patcher.stop)
        with store.connect() as con:
            for cid, customer, route, status in (("A", "CUS-00150", "HUMAN_APPROVAL", "PENDING_APPROVAL"),
                                                 ("B", "CUS-00001", "HUMAN_APPROVAL", "APPROVED"),
                                                 ("C", "CUS-00150", "FRAUD_TEAM", "FRAUD_QUEUE"),
                                                 ("D", "CUS-00150", "AUTO_RESOLVE", "RESOLVED")):
                con.execute("INSERT INTO cases (complaint_id, customer_id, route, status, updated_at) VALUES (?,?,?,?,?)",
                            (cid, customer, route, status, cid))
        officer, manager = accounts.get_staff("officer1"), accounts.get_staff("manager1")
        customer = accounts.get_customer("CUS-00150")

        def ids(account, status=None):
            return sorted(c["complaint_id"] for c in store.list_cases(status, **roles.case_filter(account)))

        self.assertEqual(ids(officer), ["A", "B"])
        self.assertEqual(ids(officer, ["PENDING_APPROVAL", "FRAUD_QUEUE"]), ["A"])     # several statuses AND the role
        self.assertEqual(ids(manager, ["PENDING_APPROVAL", "FRAUD_QUEUE"]), ["A", "C"])
        self.assertEqual(ids(customer), ["A", "C", "D"])
        self.assertEqual(store.counts(**roles.case_filter(officer)), {"PENDING_APPROVAL": 1, "APPROVED": 1})
        self.assertEqual(sum(store.counts().values()), 4)


if __name__ == "__main__":
    unittest.main()
