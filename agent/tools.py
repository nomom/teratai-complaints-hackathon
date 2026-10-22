"""Owner: A. Data-access tools. Every lookup goes through here, never a whole table in a prompt.

These are also the functions an LLM may call as tools (see agent/llm.py TOOL_SPECS, optional).
"""
from __future__ import annotations

import datetime as dt
import functools
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "starter"))

import data as _starter  # noqa: E402  starter/data.py

_db = None
_lock = threading.Lock()


def get_db():
    """Load the CSVs once per process (takes a few seconds)."""
    global _db
    with _lock:
        if _db is None:
            _db = _starter.load()
    return _db


def register_complaint(c: dict):
    """Live complaints aren't in complaints.csv; add them so the evidence/check tools can see them."""
    get_db().complaints.setdefault(c["complaint_id"], c)


def received(c) -> dt.datetime:
    return dt.datetime.strptime(c["received_at"][:16], "%Y-%m-%d %H:%M")


def get_customer(customer_id):
    return get_db().customers.get(customer_id)


def get_accounts(customer_id):
    return get_db().accounts_by_customer.get(customer_id, [])


def get_account(account_id):
    return get_db().accounts.get(account_id)


def age_on(customer_id, day: dt.date) -> int:
    return _starter.age_on(get_customer(customer_id)["date_of_birth"], day)


@functools.lru_cache(maxsize=1)
def town_words() -> frozenset:
    """Lower-case words of every customer's city ("Bayan Lepas" -> bayan, lepas). Built once."""
    return frozenset(w for c in get_db().customers.values() for w in re.findall(r"[a-z0-9]+", c["city"].lower()))


def find_debits(customer_id, since: dt.datetime, until: dt.datetime, channels=None):
    """The customer's debits in [since, until], optionally limited to some channels. Newest first."""
    out = [t for t in get_db().txns_by_customer.get(customer_id, [])
           if t["direction"] == "DR" and since <= t["time"] <= until
           and (channels is None or t["channel"] in channels)]
    return sorted(out, key=lambda t: t["time"], reverse=True)


def get_txn(txn_id):
    return get_db().txns.get(txn_id)


def get_reversal(txn_id):
    """The Reversal credit that names this transaction, or None."""
    return get_db().reversal_of.get(txn_id)


def get_atm_journal(txn_id):
    return get_db().atm_journal.get(txn_id)


def get_fee_schedule():
    return get_db().fee_schedule


def param(name):
    return get_db().params[name]


def policy(category):
    return get_db().policy[category]


def sla(priority):
    return get_db().sla[priority]


def txn_summary(t):
    """Compact, JSON-safe view of a transaction for evidence and the UI."""
    if t is None:
        return None
    keep = ["txn_id", "txn_time", "account_id", "channel", "amount_myr", "merchant_or_counterparty",
            "card_last4", "auth_method", "status", "description", "merchant_country"]
    return {k: t.get(k, "") for k in keep}
