"""Owner: C. Event trigger: watches inbox/ and processes each complaint the moment it lands.

    python -m app.worker

A complaint is a JSON file: {"customer_id", "received_at", "channel", "text", ["subject"], ["complaint_id"]}.
The API and the UI both drop files here, so there is one intake path. Done files move to inbox/processed/,
broken ones to inbox/failed/ with the error alongside.
"""
import datetime as dt
import json
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
POLL_SECONDS = 1.0


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


def handle(path: Path):
    from agent.pipeline import process_complaint
    from app import store

    c = json.loads(path.read_text(encoding="utf-8"))
    rec = process_complaint(c)
    store.save_case(rec)
    print(f"{c['complaint_id']}: {rec.category} {rec.decision.outcome} RM{rec.decision.refund_amount_myr:.2f} "
          f"-> {rec.decision.route} ({rec.status})", flush=True)


def main():
    from agent import tools

    for d in ("processed", "failed"):
        (INBOX / d).mkdir(parents=True, exist_ok=True)
    print("loading data...", flush=True)
    tools.get_db()
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
