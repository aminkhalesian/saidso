"""Rate-limit handling: 429s are retried (not turned into a second request or a fallback),
the limiter caps requests per minute, and an unsupported json_schema falls back exactly once."""
import json
import types

import pytest

from app.engine import llm


class FakeError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def response(payload: dict):
    msg = types.SimpleNamespace(content=json.dumps(payload))
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)],
                                 usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5))


class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(llm, "_schema_supported", None)
    monkeypatch.setattr(llm, "_sent", llm.deque())

    def install(script, rpm=100):
        c = FakeClient(script)
        monkeypatch.setattr(llm, "_client", c)
        monkeypatch.setattr(llm, "RPM", rpm)
        return c, sleeps
    return install


def test_429_is_retried_then_succeeds(fake):
    c, sleeps = fake([FakeError(429), FakeError(429), response({"signals": []})])
    assert llm.chat_json("s", "u", {}, "x") == {"signals": []}
    assert len(c.calls) == 3 and len(sleeps) == 2
    assert all("response_format" in call for call in c.calls)  # no fallback request on a 429


def test_unsupported_schema_falls_back_once(fake):
    c, _ = fake([FakeError(400), response({"a": 1}), response({"b": 2})])
    assert llm.chat_json("s", "u", {}, "x") == {"a": 1}
    assert llm.chat_json("s", "u", {}, "x") == {"b": 2}
    assert "response_format" in c.calls[0] and "response_format" not in c.calls[1]
    assert "response_format" not in c.calls[2]  # learned: skip json_schema next time


def test_gives_up_after_max_retries(fake):
    c, _ = fake([FakeError(429)] * llm.MAX_RETRIES)
    with pytest.raises(FakeError):
        llm.chat_text("s", "u")
    assert len(c.calls) == llm.MAX_RETRIES


def test_limiter_waits_when_over_rpm(fake, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])

    def fake_sleep(s):
        clock[0] += s
    monkeypatch.setattr(llm.time, "sleep", fake_sleep)
    c = FakeClient([response({}) for _ in range(5)])
    monkeypatch.setattr(llm, "_client", c)
    monkeypatch.setattr(llm, "RPM", 2)
    for _ in range(5):
        llm.chat_text("s", "u")
    assert clock[0] - 1000.0 >= 120  # 5 requests at 2/min need at least two full minutes of waiting
