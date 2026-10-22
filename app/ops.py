"""Owner: C. Ops platform backend: staff users and roles, permission checks, and staff actions on cases.

Builds on app/store.py (same SQLite file) without changing it:
- The agent's decision and drafted reply in `cases` are never overwritten. What staff did (final reply, reason,
  old -> new status) lives in `staff_actions`, and every action is also written to the shared audit log.
- Every action is permission-checked here, so hiding a page in the UI is not the only guard.
- Any reply a person sends, edited or not, goes through agent.checks again first (README point 5).
- Two-tier approval: a refund above the user's approval_limit_myr is escalated to a manager (ESCALATED) and waits.

predictions.csv is unaffected: scripts/run_batch.py exports the agent's own output, never staff actions.
"""
import csv
import datetime as dt
import io
import json
import uuid
from contextlib import contextmanager

from app import store
from app.worker import INBOX, submit, submit_reply

ROLES = {"officer": "Complaints officer", "fraud": "Fraud analyst", "manager": "Manager", "admin": "Admin",
         "customer": "Customer"}
STAFF_ROLES = ("officer", "fraud", "manager", "admin")

# Seeded accounts for the demo (fictional). Limits: refunds above them go to a manager. None means no limit.
# Customers are real rows of customers.csv whose September transactions the agent can match from 30 Sep 2026.
SEED_USERS = [   # (user_id, name, role, approval_limit_myr, customer_id)
    ("aina", "Aina Rahman", "officer", 5000.0, None),
    ("hafiz", "Hafiz Ismail", "officer", 1000.0, None),  # junior officer: shows escalation on mid-size refunds
    ("meiling", "Lim Mei Ling", "fraud", 5000.0, None),
    ("ravi", "Ravi Kumar", "manager", None, None),
    ("admin", "Platform Admin", "admin", None, None),
    ("cus-00996", "Nur Sofea binti Salleh", "customer", None, "CUS-00996"),   # duplicate pharmacy charge, 28 Sep
    ("cus-02710", "Huda binti Razak", "customer", None, "CUS-02710"),         # ATM didn't dispense, 28 Sep
    ("cus-01272", "Siti Farah binti Omar", "customer", None, "CUS-01272"),    # failed IBG transfer RM2,584.75
    ("cus-02323", "Shahrul bin Razak", "customer", None, "CUS-02323"),        # card payment abroad, approved by OTP
]
DEMO_DAY = "2026-09-30"   # the bank's data ends on 30 Sep 2026, so portal complaints are dated that day

# Statuses the ops platform adds on top of agent/schemas.py (app-only, so the shared contract is untouched)
ESCALATED = "ESCALATED"            # open: over a first-tier limit or marked sensitive; waits for a manager
FRAUD_CLOSED = "FRAUD_CLOSED"      # closed: the fraud team recorded an outcome
OPEN = ["AWAITING_CUSTOMER", "PENDING_APPROVAL", "FRAUD_QUEUE", ESCALATED]
CLOSED = ["RESOLVED", "APPROVED", "REJECTED", "ANSWERED", FRAUD_CLOSED]
FRAUD_OUTCOMES = ["Confirmed fraud", "Not fraud", "Recall succeeded", "Recall failed"]
FRAUD_NOTES = ["Investigation note", "Recall requested", "Card blocked", "Customer contacted"]

# Which pages each role sees (the UI builds its navigation from this)
PAGES = {
    "officer": ["desk", "intake", "cases"],
    "fraud": ["fraud", "cases"],
    "manager": ["console", "escalations", "desk", "fraud", "intake", "cases"],
    "admin": ["console", "escalations", "desk", "fraud", "intake", "cases", "admin"],
    "customer": ["portal_new", "portal_mine"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, name TEXT, role TEXT, approval_limit_myr REAL, customer_id TEXT
);
CREATE TABLE IF NOT EXISTS staff_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT, ts TEXT, user_id TEXT, role TEXT, action TEXT,
    from_status TEXT, to_status TEXT, reply_text TEXT, reason TEXT
);
"""


class PermissionDenied(Exception):
    pass


class SelfCheckFailed(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


@contextmanager
def connect():
    with store.connect() as con:
        con.executescript(SCHEMA)
        if "customer_id" not in {r[1] for r in con.execute("PRAGMA table_info(users)")}:   # stores made before customers
            con.execute("ALTER TABLE users ADD COLUMN customer_id TEXT")
        con.executemany("INSERT OR IGNORE INTO users (user_id, name, role, approval_limit_myr, customer_id) "
                        "VALUES (?,?,?,?,?)", SEED_USERS)
        yield con


# ---- Users ---------------------------------------------------------------------------------------------------------
def users(roles=None):
    with connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM users ORDER BY CASE role WHEN 'officer' THEN 1 WHEN 'fraud' THEN 2 WHEN 'manager' THEN 3 "
            "WHEN 'admin' THEN 4 ELSE 5 END, name")]
    return [u for u in rows if roles is None or u["role"] in roles]


def get_user(user_id):
    with connect() as con:
        r = con.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(r) if r else None


def set_limit(actor, user_id, limit):
    require(actor, "manage_users")
    with connect() as con:
        con.execute("UPDATE users SET approval_limit_myr = ? WHERE user_id = ?", (limit, user_id))


# ---- Permissions ---------------------------------------------------------------------------------------------------
def is_fraud_case(case):
    return case.get("route") == "FRAUD_TEAM" or case.get("status") in ("FRAUD_QUEUE", FRAUD_CLOSED) \
        or (case.get("status") == ESCALATED and _escalated_from(case["complaint_id"]) == "FRAUD_QUEUE")


def headroom(user, case):
    """How far over the user's approval limit this case's refund is (<= 0 means within the limit)."""
    limit = user.get("approval_limit_myr")
    return -1 if limit is None else (case.get("refund_amount_myr") or 0) - limit


def why_not(user, action, case=None):
    """None if the user may do this; otherwise a short reason. The single source of truth for permissions."""
    role = user["role"]
    status = case.get("status") if case else None
    if role == "customer":    # a customer only ever sends complaints and follows their own
        mine = case is not None and case.get("customer_id") == user.get("customer_id")
        if action == "submit_own":
            return None
        if action == "view":
            return None if mine else "customers see their own complaints only"
        if action == "customer_reply":
            if not mine:
                return "this is not your complaint"
            return None if status == "AWAITING_CUSTOMER" else "the bank isn't waiting for a reply on this complaint"
        return "customers can only send and follow their own complaints"
    if action in ("submit_own", "customer_reply"):
        return "only the customer can do this from their account"
    if role == "admin":
        if case is not None and action in _STATUS_FOR and status not in _STATUS_FOR[action]:
            return f"the case is {status}, not {' or '.join(_STATUS_FOR[action])}"
        if action == "approve" and status == ESCALATED and _escalated_from(case["complaint_id"]) == "FRAUD_QUEUE":
            return "a fraud escalation goes back to the fraud team with your guidance"
        return None
    if action in ("manage_users", "reset"):
        return "admins only"
    if action == "intake":
        return None if role in ("officer", "manager") else "your role does not take in complaints"
    if action == "view":
        if role == "manager":
            return None
        if role == "fraud":
            return None if is_fraud_case(case) else "fraud analysts see fraud cases only"
        return None if not is_fraud_case(case) else "fraud cases are handled by the fraud team"
    if status not in _STATUS_FOR.get(action, ()):
        return f"the case is {status}, not {' or '.join(_STATUS_FOR.get(action, ('?',)))}"
    if status == ESCALATED:
        if role != "manager":
            return "escalations are decided by a manager"
        if action == "approve" and _escalated_from(case["complaint_id"]) == "FRAUD_QUEUE":
            return "a fraud escalation goes back to the fraud team with your guidance"
        return None
    if action in ("approve", "reject", "rerun", "escalate") and status == "PENDING_APPROVAL":
        if role not in ("officer", "manager"):
            return "approval-queue cases are handled by complaints officers"
        if action == "approve" and headroom(user, case) > 0:
            return f"the refund is over your approval limit of {_rm(user['approval_limit_myr'])}: escalate it"
        return None
    if action.startswith("fraud_") or (action == "escalate" and status == "FRAUD_QUEUE"):
        if role not in ("fraud", "manager"):
            return "fraud cases are handled by the fraud team"
        if action in ("fraud_note", "fraud_outcome") and fraud_stage(case["complaint_id"]) == "NEW":
            return "acknowledge the case first (the customer gets the holding reply)"
        if action == "fraud_ack" and fraud_stage(case["complaint_id"]) != "NEW":
            return "already acknowledged"
        return None
    return "not allowed"


_STATUS_FOR = {   # which case statuses each action applies to
    "approve": ("PENDING_APPROVAL", ESCALATED), "reject": ("PENDING_APPROVAL", ESCALATED),
    "rerun": ("PENDING_APPROVAL",), "escalate": ("PENDING_APPROVAL", "FRAUD_QUEUE"),
    "fraud_ack": ("FRAUD_QUEUE",), "fraud_note": ("FRAUD_QUEUE",), "fraud_outcome": ("FRAUD_QUEUE",),
    "return": (ESCALATED,),
}


def can(user, action, case=None):
    return why_not(user, action, case) is None


def require(user, action, case=None):
    reason = why_not(user, action, case)
    if reason:
        raise PermissionDenied(f"{ROLES.get(user['role'], user['role'])} {user['name']} can't {action}: {reason}")


# ---- Self-check ----------------------------------------------------------------------------------------------------
def recheck(case, reply_text):
    """Run the agent's own code check on a reply a person is about to send. Empty list = VERIFIED."""
    from agent import checks
    from agent.schemas import Decision

    rec = case["record"]
    return checks.check(rec["complaint"], Decision(**rec["decision"]), reply_text, case["reply_language"])


# ---- Staff actions -------------------------------------------------------------------------------------------------
def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rm(v):
    return "no limit" if v is None else f"RM{v:,.2f}"


def _act(con, user, case, action, to_status=None, reply_text=None, reason="", audit_detail=None):
    """Record one staff action (and its audit line); move the case's status if to_status is given."""
    cid, old = case["complaint_id"], case["status"]
    new = to_status or old
    con.execute("INSERT INTO staff_actions (complaint_id, ts, user_id, role, action, from_status, to_status, "
                "reply_text, reason) VALUES (?,?,?,?,?,?,?,?,?)",
                (cid, _now(), user["user_id"], user["role"], action, old, new, reply_text, reason))
    if new != old:
        con.execute("UPDATE cases SET status = ?, updated_at = ? WHERE complaint_id = ?", (new, _now(), cid))
    detail = {"by": f"{user['name']} ({ROLES[user['role']]})", "status": f"{old} -> {new}" if new != old else old}
    if reason:
        detail["reason"] = reason
    detail.update(audit_detail or {})
    store.audit(con, cid, user["user_id"], action, detail)


def _load(cid):
    case = store.get_case(cid)
    if not case:
        raise ValueError(f"{cid} not found")
    return case


def _send(con, user, case, action, reply_text, edited, reason="", to_status=None):
    """Self-check a reply, then record it as sent. Raises SelfCheckFailed (and logs the block) if it fails."""
    problems = recheck(case, reply_text)
    if problems:
        _act(con, user, case, "send_blocked", reply_text=reply_text, reason="; ".join(problems),
             audit_detail={"edited": edited})
        raise SelfCheckFailed(problems)
    decided = bool(case["outcome"])
    status = to_status or ("APPROVED" if decided else "AWAITING_CUSTOMER")
    _act(con, user, case, action, status, reply_text, reason, {"edited": edited})
    store.audit(con, case["complaint_id"], user["user_id"], "reply_sent" if decided else "question_sent", reply_text)


def approve(user, cid, reply_text, reason=""):
    """Approve and send. On an escalated case the manager sends the officer's proposed reply (or their own edit)."""
    case = _load(cid)
    require(user, "approve", case)
    proposed = escalated_reply(cid) if case["status"] == ESCALATED else case["reply_text"]
    reply_text = reply_text if reply_text is not None else proposed
    blocked = None
    with connect() as con:
        try:
            _send(con, user, case, "approved", reply_text, edited=reply_text != case["reply_text"], reason=reason)
        except SelfCheckFailed as e:
            blocked = e      # leave the with-block normally so the send_blocked audit line is committed
    if blocked:
        raise blocked


def reject(user, cid, reason):
    case = _load(cid)
    require(user, "reject", case)
    if not reason.strip():
        raise ValueError("a reason is required to reject")
    with connect() as con:
        _act(con, user, case, "rejected", "REJECTED", reason=reason.strip())


def escalate(user, cid, reply_text, reason):
    """First tier hands the case to a manager with the reply they propose. It is not sent until the manager acts."""
    case = _load(cid)
    require(user, "escalate", case)
    if not reason.strip():
        raise ValueError("a reason is required to escalate")
    with connect() as con:
        _act(con, user, case, "escalated", ESCALATED, reply_text, reason.strip(),
             {"from_queue": case["status"], "self_check": recheck(case, reply_text) or "verified"})


def return_escalation(user, cid, guidance):
    """Manager sends an escalated case back to the queue it came from, with guidance for the first tier."""
    case = _load(cid)
    require(user, "return", case)
    if not guidance.strip():
        raise ValueError("write guidance for the team")
    back = _escalated_from(cid) or "PENDING_APPROVAL"
    with connect() as con:
        _act(con, user, case, "returned", back, reason=guidance.strip())


def rerun(user, cid, reason=""):
    """Send the case back to the agent: the worker reprocesses the original complaint under the same ID."""
    case = _load(cid)
    require(user, "rerun", case)
    with connect() as con:
        _act(con, user, case, "sent_back", reason=reason.strip() or "re-run the agent")
    submit(dict(case["record"]["complaint"]))


def fraud_ack(user, cid, reply_text):
    """Acknowledge: the customer gets the holding reply (self-checked). The case stays in the fraud queue."""
    case = _load(cid)
    require(user, "fraud_ack", case)
    blocked = None
    with connect() as con:
        try:
            _send(con, user, case, "acknowledged", reply_text, edited=reply_text != case["reply_text"],
                  to_status="FRAUD_QUEUE")
        except SelfCheckFailed as e:
            blocked = e
    if blocked:
        raise blocked


def fraud_note(user, cid, kind, text):
    case = _load(cid)
    require(user, "fraud_note", case)
    if not text.strip():
        raise ValueError("write what was done")
    with connect() as con:
        _act(con, user, case, kind.lower().replace(" ", "_"), reason=text.strip(), audit_detail={"note": kind})


def fraud_outcome(user, cid, outcome, reason):
    case = _load(cid)
    require(user, "fraud_outcome", case)
    if outcome not in FRAUD_OUTCOMES:
        raise ValueError(f"outcome must be one of {FRAUD_OUTCOMES}")
    with connect() as con:
        _act(con, user, case, "fraud_outcome", FRAUD_CLOSED, reason=reason.strip(), audit_detail={"outcome": outcome})


# ---- Reads ---------------------------------------------------------------------------------------------------------
def actions_for(cid):
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM staff_actions WHERE complaint_id = ? ORDER BY id", (cid,))]


def _escalated_from(cid):
    for a in reversed(actions_for(cid)):
        if a["action"] == "escalated":
            return a["from_status"]
    return None


def escalation(cid):
    """The latest escalation on a case: who, from which queue, why, and the reply they proposed."""
    for a in reversed(actions_for(cid)):
        if a["action"] == "escalated":
            return a
    return None


def escalated_reply(cid):
    e = escalation(cid)
    return e["reply_text"] if e else None


def fraud_stage(cid):
    """NEW -> ACKNOWLEDGED -> INVESTIGATING -> CLOSED, from the staff actions on a fraud case."""
    acts = {a["action"] for a in actions_for(cid)}
    if "fraud_outcome" in acts:
        return "CLOSED"
    if acts - {"acknowledged", "send_blocked", "escalated"} and "acknowledged" in acts:
        return "INVESTIGATING"
    return "ACKNOWLEDGED" if "acknowledged" in acts else "NEW"


def final_action(cid):
    """The last decisive staff action (approved / rejected / fraud outcome), or None."""
    for a in reversed(actions_for(cid)):
        if a["action"] in ("approved", "rejected", "fraud_outcome", "acknowledged"):
            return a
    return None


def cases(statuses=None, user=None, limit=5000):
    """Cases (newest first), optionally only some statuses and only what this user may view."""
    rows = store.list_cases(limit=limit)
    if statuses:
        rows = [r for r in rows if r["status"] in statuses]
    if user is not None:
        rows = [r for r in rows if can(user, "view", r)]
    return rows


def recent_actions(limit=20):
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM staff_actions ORDER BY id DESC LIMIT ?", (limit,))]


# ---- SLA -----------------------------------------------------------------------------------------------------------
def sla_left(case, now=None):
    """Time left to acknowledge. The data lives in 2026, so the clock starts when the case entered our store:
    left = (sla_due - received_at) - (now - created_at). None once the case is closed."""
    if case["status"] not in OPEN or not case.get("sla_due"):
        return None
    try:
        due = dt.datetime.strptime(case["sla_due"][:16], "%Y-%m-%d %H:%M")
        rec = dt.datetime.strptime(case["received_at"][:16], "%Y-%m-%d %H:%M")
        created = dt.datetime.strptime(case["created_at"][:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return (due - rec) - ((now or dt.datetime.now()) - created)


# ---- Intake --------------------------------------------------------------------------------------------------------
CSV_FIELDS = ["complaint_id", "customer_id", "received_at", "channel", "subject", "text"]


def parse_csv_rows(text):
    """complaints.csv rows (header optional) -> complaint dicts. Raises ValueError naming the bad row."""
    rows = [r for r in csv.reader(io.StringIO(text.strip())) if any(cell.strip() for cell in r)]
    if rows and [c.strip().lower() for c in rows[0]] == CSV_FIELDS:
        rows = rows[1:]
    if not rows:
        raise ValueError("no rows found")
    out = []
    for n, r in enumerate(rows, 1):
        if len(r) != len(CSV_FIELDS):
            raise ValueError(f"row {n} has {len(r)} columns, expected {len(CSV_FIELDS)} "
                             f"({', '.join(CSV_FIELDS)}). Is the text in double quotes?")
        c = {k: v.strip() for k, v in zip(CSV_FIELDS, r)}
        missing = [k for k in ("customer_id", "received_at", "channel", "text") if not c[k]]
        if missing:
            raise ValueError(f"row {n} is missing {', '.join(missing)}")
        try:
            dt.datetime.strptime(c["received_at"][:16], "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError(f"row {n}: received_at must look like 2026-09-30 10:15") from None
        if not c["complaint_id"]:
            del c["complaint_id"]                    # submit() assigns a LIVE-… id
        out.append(c)
    return out


def take_in(user, complaints):
    """Drop complaints into the worker's inbox. Returns (submitted ids, skipped [(id, why)])."""
    require(user, "intake")
    done, skipped = [], []
    for c in complaints:
        cid = c.get("complaint_id")
        if cid and (store.get_case(cid) or (INBOX / f"{cid}.json").exists()):
            skipped.append((cid, "already taken in"))
            continue
        c = dict(c, complaint_id=cid or "LIVE-" + uuid.uuid4().hex[:8].upper())
        # Log first: the worker may decide the case the moment the file lands
        store.log(c["complaint_id"], user["user_id"], "taken_in", {"by": user["name"], "channel": c.get("channel")})
        done.append(submit(c))
    return done, skipped


# ---- Customer portal -------------------------------------------------------------------------------------------------
def submit_own(user, text):
    """A signed-in customer sends a complaint from the app. It enters the same inbox as every other channel."""
    require(user, "submit_own")
    if not text.strip():
        raise ValueError("tell us what happened")
    cid = "APP-" + uuid.uuid4().hex[:8].upper()
    c = {"complaint_id": cid, "customer_id": user["customer_id"], "channel": "App chat", "subject": "",
         "received_at": f"{DEMO_DAY} {dt.datetime.now():%H:%M}", "text": text.strip()}
    # Log first (with the message, so the customer's thread keeps their original words): the worker may be quick
    store.log(cid, user["user_id"], "taken_in", {"by": user["name"], "channel": "App chat (customer portal)",
                                                  "text": c["text"]})
    return submit(c)


def customer_reply(user, cid, text):
    """The customer answers the bank's follow-up question; the worker reopens and decides the case."""
    case = _load(cid)
    require(user, "customer_reply", case)
    if not text.strip():
        raise ValueError("write your answer first")
    return submit_reply(cid, text.strip())


def waiting_in_inbox(customer_id):
    """This customer's complaints that the worker hasn't picked up yet (they aren't in the case store)."""
    out = []
    for p in sorted(INBOX.glob("*.json")) if INBOX.exists() else []:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("customer_id") == customer_id and not c.get("in_reply_to"):
            out.append(c)
    return out


def demo_time(case, ts):
    """A real timestamp on the case's own clock (the same clock as sla_left): received_at + time since it was stored."""
    try:
        rec = dt.datetime.strptime(case["received_at"][:16], "%Y-%m-%d %H:%M")
        gap = dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S") - \
            dt.datetime.strptime(case["created_at"][:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ts
    return (rec + max(gap, dt.timedelta(0))).strftime("%Y-%m-%d %H:%M")


def thread(case):
    """The conversation the customer sees: their messages and what the bank actually sent. Nothing internal."""
    msgs = []
    for a in case["audit"]:
        when = demo_time(case, a["ts"])
        if a["action"] == "taken_in":
            try:
                text = json.loads(a["detail"]).get("text")
            except (TypeError, ValueError, AttributeError):
                text = None
            if text:
                msgs.append({"from": "customer", "ts": when, "text": text})
        elif a["action"] in ("reply_sent", "question_sent"):
            msgs.append({"from": "bank", "ts": when, "text": a["detail"]})
        elif a["action"] == "customer_replied":
            msgs.append({"from": "customer", "ts": when, "text": a["detail"]})
    if not any(m["from"] == "customer" for m in msgs[:1]):     # complaints that came in through another channel
        msgs.insert(0, {"from": "customer", "ts": case["received_at"], "text": case["record"]["complaint"]["text"]})
    return msgs


# ---- Platform health and demo reset ---------------------------------------------------------------------------------
def health():
    pending = sorted(INBOX.glob("*.json")) if INBOX.exists() else []
    oldest = max(((dt.datetime.now().timestamp() - p.stat().st_mtime) for p in pending), default=0)
    return {
        "pending": len(pending),
        "oldest_pending_s": round(oldest),
        "worker_ok": oldest < 10,            # the worker polls every second; a file waiting longer means it's down
        "inbox_idle": not pending,           # nothing waiting, so we can't tell from the inbox alone
        "processed": len(list((INBOX / "processed").glob("*.json"))) if (INBOX / "processed").exists() else 0,
        "failed": sorted(p.name for p in (INBOX / "failed").glob("*.json")) if (INBOX / "failed").exists() else [],
    }


def reset(user):
    """Admin: empty the case store and inbox before a demo. Users and their limits are kept."""
    require(user, "reset")
    with connect() as con:
        for t in ("cases", "audit", "staff_actions"):
            con.execute(f"DELETE FROM {t}")
    for sub in ("", "processed", "failed"):
        d = INBOX / sub
        if d.exists():
            for p in d.iterdir():
                if p.is_file():
                    p.unlink()


def metrics():
    """Numbers for the manager console, from the case store and staff actions."""
    rows = store.list_cases(limit=100000)
    with connect() as con:
        acts = [dict(r) for r in con.execute("SELECT complaint_id, action, reply_text FROM staff_actions")]
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    decided = [r for r in rows if r["outcome"]]
    auto = sum(1 for r in decided if r["route"] == "AUTO_RESOLVE")
    human_final = {a["complaint_id"]: a for a in acts if a["action"] in ("approved", "rejected")}
    overridden = 0
    for cid, a in human_final.items():
        drafted = next((r["reply_text"] for r in rows if r["complaint_id"] == cid), None)
        overridden += a["action"] == "rejected" or (a["reply_text"] or "") != (drafted or "")
    ms, tokens, open_by_category = [], 0, {}
    for r in rows:
        rec = json.loads(r["record"])
        ms.append(sum(float(t.get("ms") or 0) for t in rec.get("trace", [])))
        u = rec.get("llm_usage", {})
        tokens += int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0)
        if r["status"] in OPEN:
            open_by_category[r["category"] or "UNKNOWN"] = open_by_category.get(r["category"] or "UNKNOWN", 0) + 1
    now = dt.datetime.now()
    open_rows = [r for r in rows if r["status"] in OPEN]
    lefts = [sla_left(r, now) for r in open_rows]
    return {
        "total": len(rows), "by_status": by_status, "open": len(open_rows),
        "auto_rate": auto / len(decided) if decided else None,
        "override_rate": overridden / len(human_final) if human_final else None, "human_final": len(human_final),
        "avg_ms": sum(ms) / len(ms) if ms else None, "tokens": tokens,
        "tokens_per_case": tokens / len(rows) if rows else None,
        "sla_overdue": sum(1 for x in lefts if x is not None and x.total_seconds() < 0),
        "sla_at_risk": sum(1 for x in lefts if x is not None and 0 <= x.total_seconds() < 3600),
        "open_by_category": open_by_category,
    }
