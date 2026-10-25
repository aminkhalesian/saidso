"""Thin LLM wrapper. Talks to OpenRouter (OpenAI-compatible API) using the key in .env.
Without a key (or with MOCK_LLM=1) everything falls back to rules, so the app always runs offline.

Rate limits: new OpenRouter accounts get ~20 requests/minute per model. Every call goes through a
shared limiter (LLM_RPM, default 15/min) and waits + retries on 429 instead of failing."""
import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # repo root .env
except ImportError:  # python-dotenv not installed: rely on exported env vars
    pass

BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = os.getenv("LLM_MODEL", "~anthropic/claude-sonnet-latest")
RPM = max(1, int(os.getenv("LLM_RPM", "15")))
MAX_RETRIES = 6

_client = None
_lock = threading.Lock()
_rate_lock = threading.Lock()
_sent = deque()
_schema_supported = None  # learned on first call: does the provider accept json_schema?
USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "waits": 0, "failed": 0}


def api_key():
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")


def enabled() -> bool:
    return bool(api_key()) and os.getenv("MOCK_LLM") != "1"


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        # max_retries=0: we handle retries ourselves so hidden retries don't burn the rate limit
        _client = OpenAI(api_key=api_key(), base_url=BASE_URL, max_retries=0, timeout=90)
    return _client


def _throttle():
    """Block until sending one more request keeps us under RPM in any 60-second window."""
    while True:
        with _rate_lock:
            now = time.monotonic()
            while _sent and now - _sent[0] >= 60:
                _sent.popleft()
            if len(_sent) < RPM:
                _sent.append(now)
                return
            wait = 60 - (now - _sent[0]) + 0.1
        time.sleep(wait)


def _status(e) -> int:
    return getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None) or 0


def _create(**kwargs):
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            resp = client().chat.completions.create(**kwargs)
            _track(resp)
            return resp
        except Exception as e:  # noqa: BLE001
            code = _status(e)
            if code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = min(60, 10 * (attempt + 1))
                with _lock:
                    USAGE["waits"] += 1
                print(f"  AI {'rate limit' if code == 429 else 'server error'} ({code}), waiting {wait}s and retrying…")
                time.sleep(wait)
                continue
            raise


def _track(resp):
    u = getattr(resp, "usage", None)
    with _lock:
        USAGE["calls"] += 1
        if u:
            USAGE["prompt_tokens"] += u.prompt_tokens or 0
            USAGE["completion_tokens"] += u.completion_tokens or 0


def record_failure():
    with _lock:
        USAGE["failed"] += 1


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def chat_json(system: str, user: str, schema: dict, name: str, temperature: float = 0.0) -> dict:
    """Ask for JSON matching `schema`. Uses native structured output when the provider supports it;
    otherwise puts the schema in the prompt. Only a 400 (unsupported) triggers the fallback."""
    global _schema_supported
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if _schema_supported is not False:
        try:
            resp = _create(model=MODEL, temperature=temperature, messages=messages, max_tokens=1500,
                           response_format={"type": "json_schema",
                                            "json_schema": {"name": name, "strict": True, "schema": schema}})
            _schema_supported = True
            return _parse_json(resp.choices[0].message.content)
        except Exception as e:  # noqa: BLE001
            if _status(e) not in (400, 422):
                raise
            _schema_supported = False
    messages[0]["content"] = (system + "\n\nReply with ONLY a JSON object matching this JSON schema, "
                              "no prose, no code fences:\n" + json.dumps(schema))
    resp = _create(model=MODEL, temperature=temperature, messages=messages, max_tokens=1500)
    return _parse_json(resp.choices[0].message.content)


def chat_text(system: str, user: str, temperature: float = 0.8) -> str:
    resp = _create(model=MODEL, temperature=temperature, max_tokens=2500,
                   messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return resp.choices[0].message.content


def usage_summary() -> str:
    s = (f"{USAGE['calls']} AI calls, {USAGE['prompt_tokens']:,} input + {USAGE['completion_tokens']:,} output tokens")
    if USAGE["waits"]:
        s += f", {USAGE['waits']} rate-limit waits"
    if USAGE["failed"]:
        s += f", {USAGE['failed']} calls fell back to rules/templates"
    return s
