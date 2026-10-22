"""Owner: C. Accounts, kept in CSVs.

    data/staff.csv               seeded staff: one officer, one fraud analyst, one manager (password 1234 for all three)
    data/customers.csv           the bank's customers (organiser data): who may sign up, and their names. Read only.
    data/customer_accounts.csv   customer_id, full_name, password: one row per customer who has signed up.
                                 Created on the first sign-up; git-ignored, so each laptop keeps its own sign-ups.

Both password columns hold PBKDF2 hashes (see passwords.py), never the password itself.
STAFF_CSV, CUSTOMERS_CSV and CUSTOMER_ACCOUNTS_CSV override the paths (the tests point them at copies).
"""
import csv
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.UserAccessControl.roles import CUSTOMER

ROOT = Path(__file__).resolve().parents[2]
STAFF_CSV = Path(os.environ.get("STAFF_CSV", ROOT / "data" / "staff.csv"))
CUSTOMERS_CSV = Path(os.environ.get("CUSTOMERS_CSV", ROOT / "data" / "customers.csv"))
CUSTOMER_ACCOUNTS_CSV = Path(os.environ.get("CUSTOMER_ACCOUNTS_CSV", ROOT / "data" / "customer_accounts.csv"))
ACCOUNT_FIELDS = ["customer_id", "full_name", "password"]

_write_lock = threading.Lock()      # one sign-up at a time appends to customer_accounts.csv


class AlreadySignedUp(Exception):
    pass


@dataclass
class Account:
    username: str                                # staff username, or the customer ID for a customer
    role: str                                    # see roles.ALL_ROLES
    full_name: str
    password_hash: str                           # "" = a customer who has not signed up yet
    approval_limit_myr: Optional[float] = None   # staff only; None = no limit (manager)

    @property
    def signed_up(self) -> bool:
        return bool(self.password_hash)

    def public(self) -> dict:
        """What the API may return about an account: never the hash."""
        return {"username": self.username, "role": self.role, "full_name": self.full_name,
                "approval_limit_myr": self.approval_limit_myr}


def _read(path: Path):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def normalise_customer_id(customer_id: str) -> str:
    return customer_id.strip().upper()


def get_staff(username: str) -> Optional[Account]:
    name = username.strip().lower()
    for r in _read(STAFF_CSV)[1]:
        if r["username"].lower() == name:
            limit = r.get("approval_limit_myr") or ""
            return Account(r["username"], r["role"], r["full_name"], r.get("password") or "",
                           float(limit) if limit else None)
    return None


def _password_hash(customer_id: str) -> str:
    """The customer's stored hash, or "" if they haven't signed up (or nobody has yet: no file)."""
    if not CUSTOMER_ACCOUNTS_CSV.exists():
        return ""
    return next((r["password"] for r in _read(CUSTOMER_ACCOUNTS_CSV)[1] if r["customer_id"] == customer_id), "")


def get_customer(customer_id: str) -> Optional[Account]:
    """A customer of the bank (customers.csv), with their password hash if they have signed up."""
    cid = normalise_customer_id(customer_id)
    for r in _read(CUSTOMERS_CSV)[1]:
        if r["customer_id"] == cid:
            return Account(cid, CUSTOMER, r["full_name"], _password_hash(cid))
    return None


def find(username: str) -> Optional[Account]:
    """Staff first, then customers: staff usernames never look like a customer ID (CUS-00001)."""
    return get_staff(username) or get_customer(username)


def set_customer_password(customer_id: str, password_hash: str):
    """Sign the customer up: append (customer_id, full_name, password hash) to customer_accounts.csv.
    Raises KeyError if not a customer, AlreadySignedUp if they already have a row. customers.csv is never written."""
    cid = normalise_customer_id(customer_id)
    with _write_lock:
        customer = get_customer(cid)
        if customer is None:
            raise KeyError(cid)
        if customer.signed_up:
            raise AlreadySignedUp(cid)
        new_file = not CUSTOMER_ACCOUNTS_CSV.exists()
        CUSTOMER_ACCOUNTS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOMER_ACCOUNTS_CSV, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, ACCOUNT_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({"customer_id": cid, "full_name": customer.full_name, "password": password_hash})
