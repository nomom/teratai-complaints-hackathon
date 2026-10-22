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
    return [_for(user, c) for c in store.list_cases(status, limit, **roles.case_filter(user))]


@app.get("/cases/{complaint_id}")
def case(complaint_id: str, user: Account = Depends(require_roles(*roles.ALL_ROLES))):
    return _for(user, _visible_case(complaint_id, user))


@app.post("/cases/{complaint_id}/approve")
def approve(complaint_id: str, body: ApprovalIn, user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    _visible_case(complaint_id, user)
    try:
        store.approve(complaint_id, user.username, body.reply_text)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return store.get_case(complaint_id)


@app.post("/cases/{complaint_id}/reject")
def reject(complaint_id: str, body: ApprovalIn, user: Account = Depends(require_roles(*roles.STAFF_ROLES))):
    _visible_case(complaint_id, user)
    store.reject(complaint_id, user.username, body.note)
    return store.get_case(complaint_id)


@app.get("/stats")
def stats(user: Account = Depends(require_roles(roles.MANAGER))):
    return store.counts()
