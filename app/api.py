"""Owner: C. HTTP intake and queue API.

    uvicorn app.api:app --reload --port 8000      (docs at http://localhost:8000/docs)

POST /complaints drops the complaint into inbox/; the worker (python -m app.worker) picks it up.

Access control (app/UserAccessControl): log in at POST /auth/login and send the token as a Bearer header.
The case endpoints show each role only its own cases: officer HUMAN_APPROVAL, fraud FRAUD_TEAM, manager all,
customer their own (and only the messages actually sent). Intake (POST /complaints and customer replies) stays open.
"""
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.summary import case_summary
from app import store
from app.UserAccessControl import roles
from app.UserAccessControl.accounts import Account
from app.UserAccessControl.deps import require_roles
from app.UserAccessControl.routes import router as auth_router
from app.worker import submit, submit_reply

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
    customer_id: str
    text: str
    channel: str = "App chat"
    subject: str = ""
    received_at: Optional[str] = None      # "YYYY-MM-DD HH:MM"; defaults to now
    complaint_id: Optional[str] = None


class ApprovalIn(BaseModel):       # the actor is the signed-in user, not a field
    reply_text: Optional[str] = None
    note: str = ""


@app.post("/complaints", status_code=202)
def create_complaint(body: ComplaintIn):
    cid = submit({k: v for k, v in body.model_dump().items() if v is not None})
    return {"complaint_id": cid, "status": "QUEUED"}


class CustomerReplyIn(BaseModel):
    text: str


@app.post("/cases/{complaint_id}/messages", status_code=202)
def customer_reply(complaint_id: str, body: CustomerReplyIn):
    """The customer answers a follow-up question; the worker reprocesses the case with the extra details."""
    case = store.get_case(complaint_id)
    if not case or case["status"] != "AWAITING_CUSTOMER":
        raise HTTPException(409, f"{complaint_id} is not waiting for a customer reply")
    return {"message_id": submit_reply(complaint_id, body.text), "status": "QUEUED"}


def _visible_case(complaint_id: str, user: Account) -> dict:
    c = store.get_case(complaint_id)
    if not c:
        raise HTTPException(404, "not processed yet (is the worker running?)")
    if not roles.can_view(user, c):
        raise HTTPException(403, {"code": "FORBIDDEN", "message": "This case is not in your queue."})
    return c


def _for(user: Account, case: dict) -> dict:
    return roles.customer_view(case) if user.role == roles.CUSTOMER else case


@app.get("/cases")
def cases(status: Optional[str] = None, limit: int = 200, user: Account = Depends(require_roles(*roles.ALL_ROLES))):
    """`status` may list several, comma-separated: ?status=RESOLVED,ANSWERED"""
    rows = store.list_cases(status.split(",") if status else None, limit, **roles.case_filter(user))
    return [_for(user, c) for c in rows]


@app.get("/cases/{complaint_id}")
def case(complaint_id: str, user: Account = Depends(require_roles(*roles.ALL_ROLES))):
    """The full case, plus `summary`: the at-a-glance view the dashboard shows first (agent/summary.py).
    A customer gets only roles.customer_view: no decision internals, no unsent draft."""
    c = _visible_case(complaint_id, user)
    if user.role == roles.CUSTOMER:
        return roles.customer_view(c)
    return {**c, "summary": case_summary(c["record"], c["status"])}


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
