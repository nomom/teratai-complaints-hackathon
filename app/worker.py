"""Owner: C. Event trigger: watches inbox/ and processes each complaint the moment it lands.

    python -m app.worker

A complaint is a JSON file: {"customer_id", "received_at", "channel", "text", ["subject"], ["complaint_id"]}.
The API and the UI both drop files here, so there is one intake path. Done files move to inbox/processed/,
broken ones to inbox/failed/ with the error alongside.

On start it also backfills: every complaint in data/complaints.csv that isn't in the case store yet is processed in
the background, so customers see their history and the queues are full without a separate batch run.
"""
import datetime as dt
import json
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
POLL_SECONDS = 1.0
# The backfill uses rules and templates only: 2,500 past complaints through the LLM would be slow and costly.
# BACKFILL_LLM=1 sends them through the LLM too, when it is on. Live complaints always follow LLM_PROVIDER.
BACKFILL_LLM = os.environ.get("BACKFILL_LLM", "") == "1"


def submit(complaint: dict) -> str:
    """Drop a complaint into the inbox; returns its id. Used by the API and the UI."""
    c = dict(complaint)
    c.setdefault("complaint_id", "LIVE-" + uuid.uuid4().hex[:8].upper())
    c.setdefault("received_at", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    c.setdefault("subject", "")
    INBOX.mkdir(exist_ok=True)
    tmp = INBOX / f".{c['complaint_id']}.tmp"
    tmp.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INBOX / f"{c['complaint_id']}.json")          # atomic: the watcher never sees half a file
    return c["complaint_id"]


def submit_reply(case_id: str, text: str) -> str:
    """Drop a customer's answer to a follow-up question into the inbox; the worker reprocesses the case."""
    msg_id = f"REPLY-{case_id}-{uuid.uuid4().hex[:6].upper()}"
    INBOX.mkdir(exist_ok=True)
    tmp = INBOX / f".{msg_id}.tmp"
    tmp.write_text(json.dumps({"in_reply_to": case_id, "text": text}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INBOX / f"{msg_id}.json")
    return msg_id


def handle(path: Path):
    from agent.pipeline import follow_up_complaint, process_complaint
    from app import store

    c = json.loads(path.read_text(encoding="utf-8"))
    if c.get("in_reply_to"):
        case = store.get_case(c["in_reply_to"])
        if not case or case["status"] != "AWAITING_CUSTOMER":
            raise ValueError(f"{c['in_reply_to']} is not waiting for a customer reply")
        store.log(c["in_reply_to"], "customer", "customer_replied", c["text"])
        c = follow_up_complaint(case["record"]["complaint"], c["text"])
    rec = process_complaint(c)
    store.save_case(rec)
    d = rec.decision
    what = f"{d.outcome} RM{d.refund_amount_myr:.2f} -> {d.route}" if d.decided else "no decision yet"
    print(f"{c['complaint_id']}: {rec.category} {what} ({rec.status})", flush=True)


def backfill():
    """Process the complaints in data/complaints.csv that the case store has never seen. A stored case is never
    reprocessed, so an officer's action or a customer's follow-up is kept, and a restart only picks up what is new."""
    from agent import llm, tools
    from agent.pipeline import process_complaint
    from app import store

    done = store.case_ids()
    known = list(tools.get_db().complaints.items())       # a snapshot: live complaints get registered meanwhile
    todo = sorted((c for cid, c in known if cid not in done),
                  key=lambda c: c["received_at"], reverse=True)              # most recent first
    if not todo:
        return
    how = "with the LLM" if BACKFILL_LLM and llm.enabled() else "rules only"
    print(f"backfill: {len(todo)} complaints from data/complaints.csv not in the case store, "
          f"processing in the background ({how})", flush=True)
    t0, saved = time.time(), []

    def one(c):
        try:
            with nullcontext() if BACKFILL_LLM else llm.off():
                rec = process_complaint(c)
            if store.get_case(c["complaint_id"]) is None:         # the inbox may have taken it meanwhile
                store.save_case(rec)
                saved.append(c["complaint_id"])
                if len(saved) % 250 == 0:
                    print(f"backfill: {len(saved)}/{len(todo)}", flush=True)
        except Exception as e:  # noqa: BLE001 -- one bad complaint must not stop the rest
            print(f"backfill FAILED {c['complaint_id']}: {type(e).__name__}: {e}", flush=True)

    with ThreadPoolExecutor(int(os.environ.get("BATCH_WORKERS", 8))) as pool:
        list(pool.map(one, todo))
    print(f"backfill done: {len(saved)} cases in {time.time() - t0:.0f}s", flush=True)


def main():
    from agent import tools

    for d in ("processed", "failed"):
        (INBOX / d).mkdir(parents=True, exist_ok=True)
    print("loading data...", flush=True)
    tools.get_db()
    threading.Thread(target=backfill, name="backfill", daemon=True).start()
    print(f"watching {INBOX} (Ctrl+C to stop)", flush=True)
    while True:
        for path in sorted(INBOX.glob("*.json")):
            try:
                handle(path)
                path.replace(INBOX / "processed" / path.name)
            except Exception:  # noqa: BLE001
                (INBOX / "failed" / (path.stem + ".error.txt")).write_text(traceback.format_exc(), encoding="utf-8")
                path.replace(INBOX / "failed" / path.name)
                print(f"FAILED {path.name}, see inbox/failed/", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
