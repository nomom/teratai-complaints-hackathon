"""Demo only: run the worker with a reply drafter that invents facts, to show the self-check catching it live.

    python -m scripts.demo_bad_drafts          (instead of python -m app.worker; Ctrl+C to stop)

The LLM still reads each complaint for real. Every reply draft it would write is replaced with the README's bad
example, which invents a transaction and an amount. Both drafts fail the self-check, so the case gets DRAFT_REJECTED
and waits in the approval queue with a standard reply in the box, instead of going out. Nothing in agent/ changes;
the substitution exists only in this process. Use a normal worker again afterwards.
"""
from agent import llm
from app import worker

BAD_REPLY = ("Dear customer,\n\nWe have refunded RM600.00 for transaction TXN-0088299. It will reach your account "
             "today.\n\nTeratai Bank Customer Care")


def bad_draft(system, user, usage=None):
    """Stands in for llm.complete_text (reply drafting only; extraction uses complete_json and stays real)."""
    if usage is not None:
        usage.calls += 1
    return BAD_REPLY


if __name__ == "__main__":
    llm.complete_text = bad_draft
    print("DEMO: every reply draft invents a transaction and an amount; the self-check should stop each one", flush=True)
    worker.main()
