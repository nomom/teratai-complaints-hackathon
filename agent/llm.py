"""Owner: B. The only module that talks to an LLM. Everything else stays testable offline.

Off by default: with LLM_PROVIDER unset, callers use their rule-based fallbacks. To turn it on, set in your shell:
    LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY (or `ant auth login`)    model defaults to claude-opus-5-5
    LLM_PROVIDER=openai      + OPENAI_API_KEY    + LLM_MODEL=<an OpenAI model id>
    LLM_PROVIDER=openrouter  + OPENROUTER_API_KEY + LLM_MODEL=<an OpenRouter model id, e.g. google/gemma-4-26b-a4b-it>
    LLM_PROVIDER=deepseek    + DEEPSEEK_API_KEY  model defaults to deepseek-flash (DeepSeek-V4.1-Flash)
See .env.example. All providers return the same thing, so extract.py and reply.py don't care which one runs.

Every failure raises LLMError with a `kind` (timeout, rate_limit, refusal, bad_json, budget, ...). Callers fall back
to rules/templates and record the kind, so failures can be counted by cause.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager

PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()
DEFAULT_MODEL = {"anthropic": "claude-opus-5-5", "deepseek": "deepseek-flash"}
MODEL = os.environ.get("LLM_MODEL") or DEFAULT_MODEL.get(PROVIDER, "")
EFFORT = os.environ.get("LLM_EFFORT", "low")          # Anthropic: low is plenty for extraction and short replies
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "")   # only for OpenAI reasoning models

# OpenRouter: open-weight models served by several hosts each, through the OpenAI-compatible chat completions API.
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_REASONING = os.environ.get("OPENROUTER_REASONING", "")   # "" model default | off | low | medium | high
OPENROUTER_DATA_COLLECTION = os.environ.get("OPENROUTER_DATA_COLLECTION", "deny")   # deny: hosts that keep no data
OPENROUTER_SORT = os.environ.get("OPENROUTER_SORT", "")             # "" OpenRouter default | price | throughput | latency
# hosts to skip, comma-separated (e.g. "darkbloom"): some say they enforce the JSON schema and don't
OPENROUTER_IGNORE = [h.strip() for h in os.environ.get("OPENROUTER_IGNORE", "").split(",") if h.strip()]

# DeepSeek's own platform (OpenAI-compatible chat completions). Thinking is on by default there; "none" turns it off.
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_REASONING_EFFORT = os.environ.get("DEEPSEEK_REASONING_EFFORT", "none")   # none | low | high | max

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
        # Anthropic and OpenAI Responses report input_tokens / output_tokens; chat completions (OpenRouter, DeepSeek) report
        # prompt_tokens / completion_tokens
        self.calls += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or getattr(u, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or getattr(u, "completion_tokens", 0) or 0

    def to_dict(self):
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "failures": self.failures, "provider": PROVIDER, "model": MODEL}


def enabled() -> bool:
    return PROVIDER in ("anthropic", "openai", "openrouter", "deepseek") and not getattr(_thread, "off", False)


_thread = threading.local()


@contextmanager
def off():
    """Rules and templates only on this thread, whatever LLM_PROVIDER says (the worker's backfill of past complaints)."""
    _thread.off = True
    try:
        yield
    finally:
        _thread.off = False


def _get_client():
    global _client
    with _lock:
        if _client is None:
            if PROVIDER == "openai":
                if not MODEL:
                    raise LLMError("config", "LLM_PROVIDER=openai needs LLM_MODEL set to an OpenAI model id")
                import openai
                _client = openai.OpenAI(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)   # reads OPENAI_API_KEY
            elif PROVIDER == "openrouter":
                if not MODEL:
                    raise LLMError("config", "LLM_PROVIDER=openrouter needs LLM_MODEL set to an OpenRouter model id")
                if not os.environ.get("OPENROUTER_API_KEY"):
                    raise LLMError("config", "LLM_PROVIDER=openrouter needs OPENROUTER_API_KEY")
                import openai
                _client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"],
                                        timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
            elif PROVIDER == "deepseek":
                if not os.environ.get("DEEPSEEK_API_KEY"):
                    raise LLMError("config", "LLM_PROVIDER=deepseek needs DEEPSEEK_API_KEY")
                import openai
                _client = openai.OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=os.environ["DEEPSEEK_API_KEY"],
                                        timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
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


def _call_openrouter(system: str, user: str, usage: Usage, schema: dict | None) -> str:
    # Each model has several hosts; route only to ones that honour every parameter we send (so the JSON schema is
    # enforced, not ignored) and, by default, that keep no complaint text.
    provider = {"require_parameters": True, "data_collection": OPENROUTER_DATA_COLLECTION}
    if OPENROUTER_SORT:
        provider["sort"] = OPENROUTER_SORT
    if OPENROUTER_IGNORE:
        provider["ignore"] = OPENROUTER_IGNORE
    extra = {"provider": provider}
    if OPENROUTER_REASONING == "off":
        extra["reasoning"] = {"enabled": False}
    elif OPENROUTER_REASONING:
        extra["reasoning"] = {"effort": OPENROUTER_REASONING, "exclude": True}   # think, but don't send it back
    kwargs = {}
    if schema:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": "extraction", "schema": schema, "strict": True}}
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=MAX_OUTPUT_TOKENS,
        extra_body=extra,
        **kwargs,
    )
    return _chat_text(resp, usage)


def _call_deepseek(system: str, user: str, usage: Usage, schema: dict | None) -> str:
    kwargs = {}
    if schema:
        # DeepSeek's JSON mode guarantees JSON but not our fields, so the prompt carries the schema (its docs ask for
        # the word "json" and the expected format in the prompt); validate() still checks every reply
        kwargs["response_format"] = {"type": "json_object"}
        system += ("\n\nReply with one JSON object that follows this JSON schema, every property included:\n"
                   + json.dumps(schema))
    if DEEPSEEK_REASONING_EFFORT == "none":
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    else:
        kwargs["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=MAX_OUTPUT_TOKENS,
        **kwargs,
    )
    return _chat_text(resp, usage)


def _chat_text(resp, usage: Usage) -> str:
    """The reply text of a chat completion (OpenRouter, DeepSeek), or the LLMError kind that explains why there is none."""
    if resp.usage:
        usage.add(resp.usage)
    else:
        usage.calls += 1
    if not resp.choices:                                   # an upstream error can come back as a reply with no choices
        raise LLMError("empty")
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise LLMError("incomplete", "hit max_tokens")
    if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
        raise LLMError("refusal")
    text = choice.message.content or ""
    if not text:
        raise LLMError("empty")
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
        if PROVIDER == "openrouter":
            return _call_openrouter(system, user, usage, schema)
        if PROVIDER == "deepseek":
            return _call_deepseek(system, user, usage, schema)
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


def _null_text_to_empty(obj, schema: dict):
    """null in a text-only field means "not stated", the same as "": some OpenRouter hosts don't enforce the schema
    and some models (Gemma 4) write null there. Fields that allow null, and every other check, stay as they are; a null
    category or intent still fails validate(), because "" is not one of its values."""
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        return {k: "" if v is None and props.get(k, {}).get("type") == "string" else
                _null_text_to_empty(v, props.get(k, {})) for k, v in obj.items()}
    if isinstance(obj, list) and "items" in schema:
        return [_null_text_to_empty(v, schema["items"]) for v in obj]
    return obj


def complete_json(system: str, user: str, schema: dict, usage: Usage | None = None) -> dict:
    """Structured output, parsed and validated against `schema`."""
    text = _call(system, user, usage, schema)
    try:
        obj = _null_text_to_empty(json.loads(text), schema)
        validate(obj, schema)
    except (json.JSONDecodeError, LLMError) as e:
        err = e if isinstance(e, LLMError) else LLMError("bad_json", str(e)[:200])
        if usage is not None:
            usage.failures.append(err.kind)
        raise err from e
    return obj


def complete_text(system: str, user: str, usage: Usage | None = None) -> str:
    return _call(system, user, usage).strip()
