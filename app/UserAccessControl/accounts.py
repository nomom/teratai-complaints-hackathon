"""Owner: C. Accounts, kept in the data CSVs.

    data/staff.csv       seeded staff: one officer, one fraud analyst, one manager (password 1234 for all three)
    data/customers.csv   every bank customer; the `password` column is empty until the customer signs up

Both password columns hold PBKDF2 hashes (see passwords.py), never the password itself.
STAFF_CSV and CUSTOMERS_CSV override the paths (the tests point them at copies).
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

_write_lock = threading.Lock()      # one signup at a time rewrites customers.csv


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


def get_customer(customer_id: str) -> Optional[Account]:
    cid = normalise_customer_id(customer_id)
    for r in _read(CUSTOMERS_CSV)[1]:
        if r["customer_id"] == cid:
            return Account(cid, CUSTOMER, r["full_name"], r.get("password") or "")
    return None


def find(username: str) -> Optional[Account]:
    """Staff first, then customers: staff usernames never look like a customer ID (CUS-00001)."""
    return get_staff(username) or get_customer(username)


def set_customer_password(customer_id: str, password_hash: str):
    """Fill this customer's empty password cell. Raises KeyError if not a customer, AlreadySignedUp if already set.

    Rewrites customers.csv through a temp file, so a crash never leaves it half written; every other cell is kept.
    """
    cid = normalise_customer_id(customer_id)
    with _write_lock:
        fields, rows = _read(CUSTOMERS_CSV)
        if "password" not in fields:
            fields.append("password")
        row = next((r for r in rows if r["customer_id"] == cid), None)
        if row is None:
            raise KeyError(cid)
        if row.get("password"):
            raise AlreadySignedUp(cid)
        row["password"] = password_hash
        tmp = CUSTOMERS_CSV.with_name(CUSTOMERS_CSV.name + ".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fields, restval="")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, CUSTOMERS_CSV)
