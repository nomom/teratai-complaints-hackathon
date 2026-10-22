"""Owner: B. The only module that talks to an LLM. Everything else stays testable offline.

Off by default: with LLM_PROVIDER unset, callers use their rule-based fallbacks. To turn it on, set in your shell:
    LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY (or `ant auth login`)    model defaults to claude-opus-5-5
    LLM_PROVIDER=openai      + OPENAI_API_KEY    + LLM_MODEL=<an OpenAI model id>
See .env.example. Both providers return the same thing, so extract.py and reply.py don't care which one runs.

Every failure raises LLMError with a `kind` (timeout, rate_limit, refusal, bad_json, budget, ...). Callers fall back
to rules/templates and record the kind, so failures can be counted by cause.
"""
from __future__ import annotations

import json
import os
import threading

PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()
DEFAULT_MODEL = {"anthropic": "claude-opus-5-5"}
MODEL = os.environ.get("LLM_MODEL") or DEFAULT_MODEL.get(PROVIDER, "")
EFFORT = os.environ.get("LLM_EFFORT", "low")          # Anthropic: low is plenty for extraction and short replies
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "")   # only for OpenAI reasoning models

# Reliability and cost limits. The SDKs retry rate limits, 5xx and timeouts themselves (with back-off) up to
# MAX_RETRIES; permanent errors (bad key, bad request) fail at once.
TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", 30))
MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", 2))
MAX_CALLS_PER_COMPLAINT = int(os.environ.get("LLM_MAX_CALLS_PER_COMPLAINT", 6))
MAX_TOKENS_PER_COMPLAINT = int(os.environ.get("LLM_MAX_TOKENS_PER_COMPLAINT", 40000))
MAX_OUTPUT_TOKENS = 4000

_client = None
_lock = threading.Lock()


class LLMError(Exception):
    """kind: config | budget | timeout | rate_limit | connection | auth | api_error | refusal | incomplete |
    empty | bad_json"""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class Usage:
    """Per-complaint counter and budget; the pipeline puts it in the case record (cost and failures per complaint)."""

    def __init__(self):
        self.calls = self.input_tokens = self.output_tokens = 0
        self.failures: list[str] = []

    def check_budget(self):
        if self.calls >= MAX_CALLS_PER_COMPLAINT:
            raise LLMError("budget", f"{self.calls} calls already made for this complaint")
        if self.input_tokens + self.output_tokens >= MAX_TOKENS_PER_COMPLAINT:
            raise LLMError("budget", f"{self.input_tokens + self.output_tokens} tokens already used")

    def add(self, u):
        # Anthropic and OpenAI usage objects both expose input_tokens / output_tokens
        self.calls += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0

    def to_dict(self):
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "failures": self.failures, "provider": PROVIDER, "model": MODEL}


def enabled() -> bool:
    return PROVIDER in ("anthropic", "openai")


def _get_client():
    global _client
    with _lock:
        if _client is None:
            if PROVIDER == "openai":
                if not MODEL:
                    raise LLMError("config", "LLM_PROVIDER=openai needs LLM_MODEL set to an OpenAI model id")
                import openai
                _client = openai.OpenAI(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)   # reads OPENAI_API_KEY
            elif PROVIDER == "anthropic":
                import anthropic
                # reads ANTHROPIC_API_KEY or an `ant auth login` profile
                _client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
            else:
                raise LLMError("config", f"unknown LLM_PROVIDER {PROVIDER!r}")
    return _client


def _classify(exc: Exception) -> LLMError:
    """Map SDK exceptions (same class names in both SDKs) to an LLMError kind."""
    if isinstance(exc, LLMError):
        return exc
    name = type(exc).__name__
    for marker, kind in (("Timeout", "timeout"), ("RateLimit", "rate_limit"), ("Connection", "connection"),
                         ("Authentication", "auth"), ("PermissionDenied", "auth")):
        if marker in name:
            return LLMError(kind, str(exc)[:200])
    return LLMError("api_error", f"{name}: {str(exc)[:200]}")


def _call_anthropic(system: str, user: str, usage: Usage, schema: dict | None) -> str:
    output_config = {"effort": EFFORT}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    resp = _get_client().beta.messages.create(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
        # If a safety classifier declines, the API retries on a fallback model inside the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    usage.add(resp.usage)
    if resp.stop_reason == "refusal":
        raise LLMError("refusal")
    if resp.stop_reason == "max_tokens":
        raise LLMError("incomplete", "hit max_tokens")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise LLMError("empty")
    return text


def _call_openai(system: str, user: str, usage: Usage, schema: dict | None) -> str:
    kwargs = {}
    if schema:
        # Structured Outputs: strict mode needs every property in "required" and additionalProperties false
        kwargs["text"] = {"format": {"type": "json_schema", "name": "extraction", "schema": schema, "strict": True}}
    if OPENAI_REASONING_EFFORT:
        kwargs["reasoning"] = {"effort": OPENAI_REASONING_EFFORT}
    resp = _get_client().responses.create(
        model=MODEL,
        instructions=system,
        input=user,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        store=False,                                       # don't keep complaint text on OpenAI's side
        **kwargs,
    )
    if resp.usage:
        usage.add(resp.usage)
    else:
        usage.calls += 1
    if resp.status == "incomplete":
        raise LLMError("incomplete", str(resp.incomplete_details))
    text = resp.output_text
    if not text:                                           # e.g. a refusal block instead of output_text
        raise LLMError("refusal" if _has_refusal(resp) else "empty")
    return text


def _has_refusal(resp) -> bool:
    for item in getattr(resp, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", "") == "refusal":
                return True
    return False


def _call(system: str, user: str, usage: Usage | None, schema: dict | None = None) -> str:
    usage = usage if usage is not None else Usage()
    usage.check_budget()
    try:
        if PROVIDER == "openai":
            return _call_openai(system, user, usage, schema)
        return _call_anthropic(system, user, usage, schema)
    except Exception as e:  # noqa: BLE001 -- every failure leaves as an LLMError with a kind
        err = _classify(e)
        usage.failures.append(err.kind)
        raise err from e


def validate(obj, schema: dict, path: str = "$"):
    """Check obj against the subset of JSON Schema we use (object/array/string/number/boolean/null, enum,
    required, additionalProperties). Structured outputs should guarantee this; we check anyway because the
    data drives money decisions downstream."""
    types = schema.get("type")
    types = types if isinstance(types, list) else [types] if types else []
    py = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    ok = any((t == "number" and isinstance(obj, (int, float)) and not isinstance(obj, bool))
             or (t in py and isinstance(obj, py[t])) for t in types) if types else True
    if not ok:
        raise LLMError("bad_json", f"{path}: expected {types}, got {type(obj).__name__}")
    if "enum" in schema and obj not in schema["enum"]:
        raise LLMError("bad_json", f"{path}: {obj!r} not in {schema['enum']}")
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in obj:
                raise LLMError("bad_json", f"{path}: missing {key!r}")
        if schema.get("additionalProperties") is False:
            extra = set(obj) - set(props)
            if extra:
                raise LLMError("bad_json", f"{path}: unexpected {sorted(extra)}")
        for key, sub in props.items():
            if key in obj:
                validate(obj[key], sub, f"{path}.{key}")
    if isinstance(obj, list) and "items" in schema:
        for i, item in enumerate(obj):
            validate(item, schema["items"], f"{path}[{i}]")


def complete_json(system: str, user: str, schema: dict, usage: Usage | None = None) -> dict:
    """Structured output, parsed and validated against `schema`."""
    text = _call(system, user, usage, schema)
    try:
        obj = json.loads(text)
        validate(obj, schema)
    except (json.JSONDecodeError, LLMError) as e:
        err = e if isinstance(e, LLMError) else LLMError("bad_json", str(e)[:200])
        if usage is not None:
            usage.failures.append(err.kind)
        raise err from e
    return obj


def complete_text(system: str, user: str, usage: Usage | None = None) -> str:
    return _call(system, user, usage).strip()
