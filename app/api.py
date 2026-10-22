"""Owner: C. HTTP intake and queue API.

    uvicorn app.api:app --host 0.0.0.0 --port 8000     (docs at http://localhost:8000/docs; needs python -m app.worker)

The organisers' contract (docs/api.md), open with no login because the live round calls it without credentials:
    POST /complaints                  one complaint (the six fields of a complaints.csv row) -> 202 processing
    GET  /cases/{id}                  processing / done with the decision, self_check, case_state, sent, human_action
    POST /cases/{id}/actions          approve / reject / edit_approve a case awaiting approval (actor + reason)
    GET  /health
POST /complaints drops the complaint into inbox/; the worker picks it up, several at a time. Check this service the way
the live round will: python scoring/api_check.py http://localhost:8000

Everything else needs a login (app/UserAccessControl: POST /auth/login, then a Bearer token) and shows each role only
its own cases: officer HUMAN_APPROVAL, fraud FRAUD_TEAM, manager all, customer their own (and only messages sent).
The React app in web/ is the client: it calls the same GET /cases/{id} and POST /complaints with its token, and gets the
staff view (full record and summary) instead of the contract view. A signed-in customer files with POST /me/complaints.
"""
import datetime as dt
import os
import re
import threading
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.summary import case_summary
from app import contract, store
from app.UserAccessControl import roles
from app.UserAccessControl.accounts import Account, get_customer
from app.UserAccessControl.deps import optional_user, require_roles
from app.UserAccessControl.routes import router as auth_router
from app.worker import inbox_state, new_complaint_id, submit, submit_reply

app = FastAPI(title="Teratai complaints agent")
app.include_router(auth_router)

# Lets a browser frontend on another port (e.g. the optional React app in web/) call this API.
# Default: Vite (5173) and Create React App (3000) dev servers. Override with a comma-separated CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ComplaintIn(BaseModel):
    """The six fields of a complaints.csv row (docs/api.md). A missing customer_id, received_at or text is a 422 from
    FastAPI itself; complaint_id is checked below (signed-in staff may leave it empty)."""
    complaint_id: str = ""
    customer_id: str
    received_at: str                       # "YYYY-MM-DD HH:MM": dates in the text are read from this, not today
    text: str
    channel: str = ""
    subject: str = ""


class ApprovalIn(BaseModel):       # the actor is the signed-in user, not a field
    reply_text: Optional[str] = None
    note: str = ""


SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")    # the id becomes a file name in inbox/
_intake = threading.Lock()                       # check-then-submit, so a double POST can't make two cases


def _status_of(complaint_id: str) -> Optional[str]:
    if store.get_case(complaint_id):
        return "done"
    state = inbox_state(complaint_id)
    return state[0] if state else None


@app.post("/complaints", status_code=202)
def create_complaint(body: ComplaintIn, user: Optional[Account] = Depends(optional_user)):
    """Contract intake. The same complaint_id again returns the existing case's status (200): no second case.
    Signed-in staff (the React form) may leave complaint_id empty: one is made up. Without a login it is required."""
    c = {k: v.strip() for k, v in body.model_dump().items()}
    if not c["complaint_id"] and user is not None and user.role in roles.STAFF_ROLES:
        c["complaint_id"] = new_complaint_id()
    for field in ("complaint_id", "customer_id", "received_at", "text"):
        if not c[field]:
            raise HTTPException(422, f"{field} is empty")
    if not SAFE_ID.fullmatch(c["complaint_id"]) or c["complaint_id"].startswith("."):
        raise HTTPException(422, "complaint_id may only use letters, digits, '.', '_' and '-' (up to 64)")
    try:
        dt.datetime.strptime(c["received_at"][:16], "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "received_at must be 'YYYY-MM-DD HH:MM'")
    if get_customer(c["customer_id"]) is None:
        raise HTTPException(422, f"unknown customer {c['customer_id']}")
    c["text"] = body.text                       # keep the customer's own spacing and line breaks
    with _intake:
        status = _status_of(c["complaint_id"])
        if status:
            return JSONResponse({"complaint_id": c["complaint_id"], "status": status}, status_code=200)
        submit(c)
    return {"complaint_id": c["complaint_id"], "status": "processing"}


@app.get("/health")
def health():
    return {"ok": True}


class CustomerReplyIn(BaseModel):
    text: str


@app.post("/cases/{complaint_id}/messages", status_code=202)
def customer_reply(complaint_id: str, body: CustomerReplyIn):
    """The customer answers a follow-up question; the worker reprocesses the case with the extra details."""
    case = store.get_case(complaint_id)
    if not case or case["status"] != "AWAITING_CUSTOMER":
        raise HTTPException(409, f"{complaint_id} is not waiting for a customer reply")
    return {"message_id": submit_reply(complaint_id, body.text), "status": "QUEUED"}


class OwnComplaintIn(BaseModel):   # a signed-in customer files under their own ID, from the app
    text: str
    subject: str = ""


# The bank's data ends on 30 Sep 2026, so complaints filed from the customer app are received then (as in the live round)
APP_RECEIVED_AT = "2026-09-30 18:00"


@app.post("/me/complaints", status_code=202)
def file_own_complaint(body: OwnComplaintIn, user: Account = Depends(require_roles(roles.CUSTOMER))):
    if not body.text.strip():
        raise HTTPException(422, "tell us what happened")
    cid = submit({"customer_id": user.username, "channel": "App chat", "received_at": APP_RECEIVED_AT,
                  "subject": body.subject.strip(), "text": body.text})
    return {"complaint_id": cid, "status": "QUEUED"}


def _visible_case(complaint_id: str, user: Account) -> dict:
    c = store.get_case(complaint_id)
    if not c:
        raise HTTPException(404, "not processed yet (is the worker running?)")
    if not roles.can_view(user, c):
        detail = {"code": "FORBIDDEN", "message": "This case is not in your queue."}
        if user.role in roles.STAFF_ROLES:     # staff may know where it went (e.g. after taking in a complaint)
            detail["route"] = c["route"] or c["status"]
        raise HTTPException(403, detail)
    return c


def _row(user: Account, case: dict, flagged: set) -> dict:
    """A list row: the case's columns without the full record (GET /cases/{id} has it), plus whether it is flagged."""
    if user.role == roles.CUSTOMER:
        return roles.customer_view(case)
    return {**{k: v for k, v in case.items() if k != "record"}, "flagged": case["complaint_id"] in flagged}


@app.get("/cases")
def cases(status: Optional[str] = None, limit: int = 200, user: Account = Depends(require_roles(*roles.ALL_ROLES))):
    """`status` may list several, comma-separated: ?status=RESOLVED,ANSWERED. Rows are the case's columns, newest
    first, without the full record."""
    rows = store.list_cases(status.split(",") if status else None, limit, **roles.case_filter(user))
    flagged = store.flagged_ids() if user.role != roles.CUSTOMER else set()
    return [_row(user, c, flagged) for c in rows]


@app.get("/cases/counts")
def case_counts(user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    """Cases per status, only those the signed-in role may see."""
    return store.counts(**roles.case_filter(user))


@app.get("/cases/{complaint_id}")
def case(complaint_id: str, user: Optional[Account] = Depends(optional_user)):
    """Without a login: the contract view (docs/api.md): processing, error, or done with the decision and where the
    case is. With a login (the React app): the full case for staff, plus `summary`, the at-a-glance view
    (agent/summary.py), 404 until the worker has stored it and 403 outside the role's queue; a customer gets only
    roles.customer_view (no decision internals, no unsent draft)."""
    if user is not None:
        c = _visible_case(complaint_id, user)
        if user.role == roles.CUSTOMER:
            return roles.customer_view(c)
        return {**c, "summary": case_summary(c["record"], c["status"])}
    c = store.get_case(complaint_id)
    if c:
        return contract.case_view(c)
    state = inbox_state(complaint_id)
    if state is None:
        raise HTTPException(404, "unknown complaint")
    status, why = state
    return {"complaint_id": complaint_id, "status": status, **({"error": why} if why else {})}


class ActionIn(BaseModel):
    action: Literal["approve", "reject", "edit_approve"]     # anything else: 422
    actor: str
    reason: str = ""
    reply_text: Optional[str] = None


@app.post("/cases/{complaint_id}/actions")
def act(complaint_id: str, body: ActionIn):
    """Contract: a person acts on a case awaiting approval. An edited reply must pass the self-check (else 422,
    nothing sent). The agent's decision never changes; the action is stored as human_action."""
    c = store.get_case(complaint_id)
    if c is None:
        raise HTTPException(404, "unknown complaint")
    if contract.STATE.get(c["status"], ("",))[0] != "awaiting_approval":
        raise HTTPException(409, f"case is {contract.STATE.get(c['status'], (c['status'],))[0]}, not awaiting_approval")
    if not body.actor.strip():
        raise HTTPException(422, "actor is required")
    if body.action in ("reject", "edit_approve") and not body.reason.strip():
        raise HTTPException(422, f"reason is required for {body.action}")
    if body.action == "edit_approve" and not (body.reply_text or "").strip():
        raise HTTPException(422, "reply_text is required for edit_approve")
    try:
        if body.action == "reject":
            store.reject(complaint_id, body.actor.strip(), body.reason.strip())
        else:
            store.approve(complaint_id, body.actor.strip(), body.reply_text if body.action == "edit_approve" else None,
                          reason=body.reason.strip())
    except store.ReplyCheckFailed as e:          # nothing sent: the edited reply invents something
        raise HTTPException(422, {"error": "edited reply failed the self-check", "problems": e.problems})
    except ValueError as e:
        raise HTTPException(409, str(e))
    return contract.case_view(store.get_case(complaint_id))


@app.post("/cases/{complaint_id}/approve")
def approve(complaint_id: str, body: ApprovalIn, user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    _visible_case(complaint_id, user)
    try:
        store.approve(complaint_id, user.username, body.reply_text)
    except store.ReplyCheckFailed as e:          # nothing sent: the officer must fix the reply
        raise HTTPException(422, {"error": "reply failed the self-check", "problems": e.problems})
    except ValueError as e:
        raise HTTPException(409, str(e))
    return store.get_case(complaint_id)


@app.post("/cases/{complaint_id}/reject")
def reject(complaint_id: str, body: ApprovalIn, user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    _visible_case(complaint_id, user)
    try:
        store.reject(complaint_id, user.username, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return store.get_case(complaint_id)


class FlagIn(BaseModel):           # the actor is the signed-in user
    note: str


@app.post("/cases/{complaint_id}/flag")
def flag(complaint_id: str, body: FlagIn, user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    """Question a case whose reply has already gone out (spot-check of automatic decisions). Audited; changes nothing."""
    _visible_case(complaint_id, user)
    try:
        store.flag_for_review(complaint_id, user.username, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return store.get_case(complaint_id)


@app.get("/stats")
def stats(user: Account = Depends(require_roles(roles.MANAGER))):
    return store.counts()
