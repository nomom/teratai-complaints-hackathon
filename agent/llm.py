"""Owner: B. The only module that talks to an LLM. Everything else stays testable offline.

Off by default: with LLM_PROVIDER unset, callers use their rule-based fallbacks. To turn it on:
    pip install anthropic
    set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY (or `ant auth login`)  -- see .env.example
"""
from __future__ import annotations

import json
import os
import threading

PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()
MODEL = os.environ.get("LLM_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("LLM_EFFORT", "low")          # low is plenty for extraction and short replies

_client = None
_lock = threading.Lock()


class Usage:
    """Per-complaint token counter; the pipeline puts it in the case record (cost per complaint)."""

    def __init__(self):
        self.calls = self.input_tokens = self.output_tokens = 0

    def add(self, u):
        self.calls += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0

    def to_dict(self):
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "model": MODEL}


def enabled() -> bool:
    return PROVIDER == "anthropic"


def _get_client():
    global _client
    with _lock:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic()
    return _client


def _call(system: str, user: str, usage: Usage | None, max_tokens: int, fmt: dict | None = None):
    output_config = {"effort": EFFORT}
    if fmt:
        output_config["format"] = fmt
    resp = _get_client().beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
        # If a safety classifier declines, the API retries on a fallback model inside the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if usage:
        usage.add(resp.usage)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request")
    return next(b.text for b in resp.content if b.type == "text")


def complete_json(system: str, user: str, schema: dict, usage: Usage | None = None) -> dict:
    """Structured output: the response is guaranteed to parse against `schema`."""
    text = _call(system, user, usage, 4000, {"type": "json_schema", "schema": schema})
    return json.loads(text)


def complete_text(system: str, user: str, usage: Usage | None = None) -> str:
    return _call(system, user, usage, 4000).strip()
