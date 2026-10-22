"""Owner: C. Case store (SQLite): cases, the queues, and an audit log of every action and message.

Nothing in PENDING_APPROVAL or FRAUD_QUEUE is ever sent until a person acts on it here.
A case awaiting the customer has no decision yet: its matched_txn_id, outcome, refund and route are NULL.
The audit log doubles as the message thread: question_sent, customer_replied and reply_sent carry the text.
"""
import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CASE_DB", ROOT / "runtime" / "cases.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    complaint_id TEXT PRIMARY KEY, customer_id TEXT, received_at TEXT, channel TEXT, text TEXT,
    category TEXT, matched_txn_id TEXT, outcome TEXT, refund_amount_myr REAL, priority TEXT,
    reply_language TEXT, route TEXT, status TEXT, reply_text TEXT, check_ok INTEGER, flags TEXT,
    sla_due TEXT, record TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT, ts TEXT, actor TEXT, action TEXT, detail TEXT
);
"""


def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect():
    """One transaction: commit on success, roll back on error, and always close (sqlite3's own `with` doesn't)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        with con:
            yield con
    finally:
        con.close()


def audit(con, complaint_id, actor, action, detail=""):
    con.execute("INSERT INTO audit (complaint_id, ts, actor, action, detail) VALUES (?,?,?,?,?)",
                (complaint_id, _now(), actor, action, detail if isinstance(detail, str) else json.dumps(detail)))


def save_case(rec):
    """Insert a new case, or update one that was reopened by a customer reply (created_at is kept)."""
    c, d = rec.complaint, rec.decision
    decided = d.decided
    with connect() as con:
        old = con.execute("SELECT created_at FROM cases WHERE complaint_id = ?", (c.complaint_id,)).fetchone()
        con.execute("INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            c.complaint_id, c.customer_id, c.received_at, c.channel, c.text, rec.category,
            d.matched_txn_id if decided else None, d.outcome if decided else None,
            d.refund_amount_myr if decided else None, d.priority, rec.reply_language, d.route or None, rec.status,
            rec.reply_text, int(not rec.check_problems), json.dumps(d.flags), rec.sla_due,
            json.dumps(rec.to_dict(), default=str), old["created_at"] if old else _now(), _now()))
        audit(con, c.complaint_id, "agent", "decided" if decided else "processed",
              {"intent": rec.extraction.intent, "outcome": d.outcome or None, "route": d.route or None,
               "status": rec.status, "flags": d.flags})
        if rec.status == "AWAITING_CUSTOMER":
            audit(con, c.complaint_id, "agent", "question_sent", rec.reply_text)
        elif rec.status in ("RESOLVED", "ANSWERED"):
            audit(con, c.complaint_id, "agent", "reply_sent", rec.reply_text)


def log(complaint_id, actor, action, detail=""):
    with connect() as con:
        audit(con, complaint_id, actor, action, detail)


def list_cases(status=None, limit=200):
    with connect() as con:
        q = "SELECT * FROM cases" + (" WHERE status = ?" if status else "") + " ORDER BY updated_at DESC LIMIT ?"
        return [dict(r) for r in con.execute(q, (status, limit) if status else (limit,))]


def get_case(complaint_id):
    with connect() as con:
        r = con.execute("SELECT * FROM cases WHERE complaint_id = ?", (complaint_id,)).fetchone()
        if not r:
            return None
        case = dict(r)
        case["record"] = json.loads(case["record"])
        case["audit"] = [dict(a) for a in con.execute(
            "SELECT ts, actor, action, detail FROM audit WHERE complaint_id = ? ORDER BY id", (complaint_id,))]
        return case


def approve(complaint_id, officer, reply_text=None):
    """Officer approves (optionally edits) the reply; only now does it count as sent.

    An undecided case lands here only when its follow-up question failed the self-check. Once the officer approves
    the question, the case waits for the customer instead of closing.
    """
    with connect() as con:
        row = con.execute("SELECT status, outcome, reply_text FROM cases WHERE complaint_id = ?",
                          (complaint_id,)).fetchone()
        if not row or row["status"] not in ("PENDING_APPROVAL", "FRAUD_QUEUE"):
            raise ValueError(f"{complaint_id} is not waiting for approval")
        text = reply_text or row["reply_text"]
        decided = bool(row["outcome"])
        # TODO(C): re-run agent.checks.check on an edited reply before sending
        con.execute("UPDATE cases SET status=?, reply_text=?, updated_at=? WHERE complaint_id=?",
                    ("APPROVED" if decided else "AWAITING_CUSTOMER", text, _now(), complaint_id))
        audit(con, complaint_id, officer, "approved", "edited" if reply_text else "as drafted")
        audit(con, complaint_id, officer, "reply_sent" if decided else "question_sent", text)


def reject(complaint_id, officer, note=""):
    with connect() as con:
        con.execute("UPDATE cases SET status='REJECTED', updated_at=? WHERE complaint_id=?", (_now(), complaint_id))
        audit(con, complaint_id, officer, "rejected", note)


def counts():
    with connect() as con:
        return {r["status"]: r["n"] for r in con.execute("SELECT status, COUNT(*) n FROM cases GROUP BY status")}
