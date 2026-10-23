"""Owner: C. A signed-in customer's own bank records, for the app's Profile and Transactions pages (GET /me/...).

Read only, from the organisers' data (customers.csv, accounts.csv, transactions.csv) through agent/data/tools.py.
Each function copies out only what a customer sees on a bank statement: never auth_method, the counterparty's
account number, or anything the agent works out.
"""
import datetime as dt
from typing import Optional

from agent import tools

PROFILE_FIELDS = ("customer_id", "full_name", "date_of_birth", "state", "city", "segment", "preferred_language",
                  "email", "customer_since")
ACCOUNT_FIELDS = ("account_id", "product", "open_date", "status", "card_last4")
TXN_FIELDS = ("txn_id", "txn_time", "account_id", "direction", "channel", "merchant_or_counterparty",
              "counterparty_bank", "card_last4", "status", "description")


def profile(customer_id: str) -> Optional[dict]:
    """Personal details and accounts (oldest account first), or None for an ID that isn't in customers.csv."""
    customer = tools.get_customer(customer_id)
    if customer is None:
        return None
    out = {k: customer[k] for k in PROFILE_FIELDS}
    out["accounts"] = [{k: a[k] for k in ACCOUNT_FIELDS}
                       for a in sorted(tools.get_accounts(customer_id), key=lambda a: a["open_date"])]
    return out


def transactions(customer_id: str, as_of: str) -> dict:
    """Every transaction, newest first. `reportable`: inside the window a complaint filed at `as_of` can refer to
    (MATCH_WINDOW_DAYS before it), so the app only offers "Report a problem" where the agent can find the row."""
    window_days = int(tools.param("MATCH_WINDOW_DAYS"))
    until = dt.datetime.strptime(as_of, "%Y-%m-%d %H:%M")
    since = until - dt.timedelta(days=window_days)
    rows = sorted(tools.get_db().txns_by_customer.get(customer_id, []), key=lambda t: t["time"], reverse=True)
    return {"as_of": as_of, "report_window_days": window_days,
            "transactions": [{**{k: t[k] for k in TXN_FIELDS}, "amount_myr": t["amount"],
                              "reportable": since <= t["time"] <= until} for t in rows]}
