"""Owner: C. HTTP intake and queue API.

    uvicorn app.api:app --reload --port 8000      (docs at http://localhost:8000/docs)

POST /complaints drops the complaint into inbox/; the worker (python -m app.worker) picks it up.
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import store
from app.worker import submit, submit_reply

app = FastAPI(title="Teratai complaints agent")

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


class ApprovalIn(BaseModel):
    officer: str
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


@app.get("/cases")
def cases(status: Optional[str] = None, limit: int = 200):
    return store.list_cases(status, limit)


@app.get("/cases/{complaint_id}")
def case(complaint_id: str):
    c = store.get_case(complaint_id)
    if not c:
        raise HTTPException(404, "not processed yet (is the worker running?)")
    return c


@app.post("/cases/{complaint_id}/approve")
def approve(complaint_id: str, body: ApprovalIn):
    try:
        store.approve(complaint_id, body.officer, body.reply_text)
    except store.ReplyCheckFailed as e:          # nothing sent: the officer must fix the reply
        raise HTTPException(422, {"error": "reply failed the self-check", "problems": e.problems})
    except ValueError as e:
        raise HTTPException(409, str(e))
    return store.get_case(complaint_id)


@app.post("/cases/{complaint_id}/reject")
def reject(complaint_id: str, body: ApprovalIn):
    store.reject(complaint_id, body.officer, body.note)
    return store.get_case(complaint_id)


@app.get("/stats")
def stats():
    return store.counts()
