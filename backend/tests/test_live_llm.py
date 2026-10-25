"""OPT-IN test against the real model. It spends a few cents and needs OPENROUTER_API_KEY in .env or the environment.
Run it on its own:   MOCK_LLM=0 LIVE_LLM=1 python -m pytest tests/test_live_llm.py -s
It is skipped in normal runs, so a normal run never calls the network."""
import os

import pytest

from app.engine import brief, extract, llm
from app.models import SessionLocal
from scenario_lib import PACK, analyse, build
from test_scenarios import A_TURNS, B_TURNS, C_TURNS, check_grounded

pytestmark = pytest.mark.skipif(os.getenv("LIVE_LLM") != "1" or not llm.enabled(),
                                reason="live LLM test: set LIVE_LLM=1 and MOCK_LLM=0 with a real key")


def run(cid, change, turns):
    with SessionLocal() as s:
        aid = build(s, cid, change, turns)
        # build() reads the call with the keyword rules; read it again with the real model
        from app.models import Client
        extract.run(s, s.get(Client, cid), PACK, use_llm=True)
        ctx, payload, source = analyse(s, cid, aid)
        return ctx, payload, source


def test_live_A_budget():
    ctx, payload, source = run("live-a", -0.60, A_TURNS)
    assert "budget_cut" in {x["signal_type"] for x in ctx["signals"]} and ctx["score"]["band"] != "low"
    check_grounded(payload)
    print("A:", ctx["score"]["score"], ctx["score"]["band"], "brief:", source, "plan:", payload["plan_source"])


def test_live_B_adoption():
    ctx, payload, source = run("live-b", -0.80, B_TURNS)
    assert "low_adoption" in {x["signal_type"] for x in ctx["signals"]} and ctx["score"]["band"] != "low"
    check_grounded(payload)
    print("B:", ctx["score"]["score"], ctx["score"]["band"], "brief:", source, "plan:", payload["plan_source"])


def test_live_C_competitor_but_happy():
    ctx, payload, source = run("live-c", 0.07, C_TURNS)
    assert "competitor_mention" in {x["signal_type"] for x in ctx["signals"]} and ctx["positives"]
    assert ctx["score"]["band"] != "high"
    check_grounded(payload)
    print("C:", ctx["score"]["score"], ctx["score"]["band"], "brief:", source, "plan:", payload["plan_source"])
