"""End-to-end scenarios for the risk engine, on an isolated temporary database (see conftest.py).

Each scenario is raw data in (usage history + a call) and the engine's own analysis out. Expected results are derived from the
pack's scoring configuration or asserted as properties; nothing here is stored in the application."""
import re

import pytest

from app.engine import brief, llm, scoring
from app.models import ActivityPoint, SessionLocal, Signal, Reassurance
from sqlalchemy import select
from scenario_lib import PACK, analyse, build

CFG = PACK["score"]
A_TURNS = ["We had layoffs last month, so the budget for tools has been cut by about a third and every renewal now needs procurement sign-off."]
B_TURNS = ["To be honest, most of my employees don't understand how the product fits into their day, so it mostly sits there."]
C_TURNS = ["We are trialing Vantora with two of our team leads right now.",
           "But honestly, we are happy with Brightdesk and we plan to renew."]


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="module")
def A(session):
    aid = build(session, "scn-a", -0.60, A_TURNS)
    return (aid, *analyse(session, "scn-a", aid))


@pytest.fixture(scope="module")
def B(session):
    aid = build(session, "scn-b", -0.80, B_TURNS)
    return (aid, *analyse(session, "scn-b", aid))


@pytest.fixture(scope="module")
def C(session):
    aid = build(session, "scn-c", 0.07, C_TURNS)
    return (aid, *analyse(session, "scn-c", aid))


def comps(ctx):
    return {c["label"]: c["points"] for c in ctx["score"]["components"]}


def kinds(payload):
    return {e["kind"] for e in payload["evidence"]}


def all_text(plan):
    return " ".join([plan["problem"]["text"], plan["objective"]["text"], plan["followup"]["text"]]
                    + [q["text"] for q in plan["questions"]] + [i["text"] for i in plan["interventions"]]).lower()


def check_grounded(payload):
    """Every cited id exists, every number is in the evidence, and every quote is really in the source transcript."""
    ids = {e["id"] for e in payload["evidence"]}
    assert brief.validate(payload, payload["evidence"])
    for e in payload["evidence"]:
        if e["kind"] in ("signal", "positive_quote"):
            with SessionLocal() as s:
                from app.models import Conversation
                assert e["quote"] in s.get(Conversation, e["conversation_id"]).transcript
    plan = payload["plan"]
    if plan:
        for it in plan["questions"] + plan["interventions"] + [plan["problem"], plan["objective"], plan["followup"]]:
            assert it["evidence"] and set(it["evidence"]) <= ids


# ------------------------------------------------------------------ isolation
def test_tests_never_touch_the_demo_database():
    from app import models
    assert "engine.db" not in models.DB_URL and "saidso-tests-" in models.DB_URL


# ------------------------------------------------------------------ Scenario A: usage -60% + budget cuts
def test_A_both_risks_detected(A):
    aid, ctx, payload, source = A
    assert {s["signal_type"] for s in ctx["signals"]} == {"budget_cut"}
    assert ctx["score"]["activity_pct"] == pytest.approx(-0.60, abs=0.005)
    assert {"signal", "activity"} <= kinds(payload)


def test_A_score_follows_the_scoring_configuration(A):
    aid, ctx, payload, source = A
    c = comps(ctx)
    assert c["Daily active users trend"] == CFG["activity_drop_max"]                    # -60% is far past the cap
    assert c["Conversation signals"] == round(PACK["signals"]["budget_cut"]["weight"] * 0.6)   # rules baseline confidence is 0.6
    assert ctx["score"]["band"] == scoring.band(ctx["score"]["score"], PACK) != "low"   # elevated, band follows the thresholds


def test_A_explanation_cites_real_evidence(A):
    aid, ctx, payload, source = A
    check_grounded(payload)
    by_title = {d["title"]: d for d in payload["drivers"]}
    assert {"Budget pressure", "Daily active users"} <= set(by_title)
    ev = {e["id"]: e for e in payload["evidence"]}
    assert "down 60%" in ev[by_title["Daily active users"]["evidence"][0]]["text"]
    assert "budget" in ev[by_title["Budget pressure"]["evidence"][0]]["quote"].lower()


def test_A_playbook_is_about_value_and_right_sizing(A):
    aid, ctx, payload, source = A
    plan, text = payload["plan"], all_text(payload["plan"])
    assert "budget" in plan["problem"]["text"].lower()
    assert any(w in text for w in ("seat", "scope", "right-siz", "smaller"))              # right-sizing
    assert any(w in text for w in ("value", "justify", "cost per"))                         # customer value
    assert len(plan["questions"]) == 3 and len(plan["interventions"]) == 2
    check_grounded(payload)


def test_A_changing_the_inputs_changes_the_result(session, A):
    aid, ctx, payload, source = A
    before = ctx["score"]["score"]
    pts = session.scalars(select(ActivityPoint).where(ActivityPoint.account_id == aid).order_by(ActivityPoint.day)).all()
    for p in pts[-14:]:
        p.value = 100.0                                                   # usage recovers
    for s in session.scalars(select(Signal).where(Signal.account_id == aid)):
        s.feedback = "dismissed"                                          # the CSM says the budget flag is wrong
    session.commit()
    ctx2, payload2, _ = analyse(session, "scn-a", aid)
    assert ctx2["score"]["score"] < before and ctx2["score"]["band"] == "low"
    assert "Budget pressure" not in {d["title"] for d in payload2["drivers"]} and payload2["plan"] is None
    for p in pts[-14:]:                                                   # put the data back for the other tests
        p.value = 40.0
    for s in session.scalars(select(Signal).where(Signal.account_id == aid)):
        s.feedback = "open"
    session.commit()


# ------------------------------------------------------------------ Scenario B: usage -80% + "employees don't understand the product"
def test_B_both_risks_detected_and_score_is_elevated(B):
    aid, ctx, payload, source = B
    assert {s["signal_type"] for s in ctx["signals"]} == {"low_adoption"}
    assert ctx["score"]["activity_pct"] == pytest.approx(-0.80, abs=0.005)
    assert comps(ctx)["Daily active users trend"] == CFG["activity_drop_max"]
    assert ctx["score"]["band"] == scoring.band(ctx["score"]["score"], PACK) != "low"
    check_grounded(payload)


def test_B_playbook_is_onboarding_training_and_adoption(B):
    aid, ctx, payload, source = B
    text = all_text(payload["plan"])
    assert "don't understand" in payload["plan"]["problem"]["text"]
    assert "training" in text and "onboarding" in text
    qs = [q["text"] for q in payload["plan"]["questions"]]
    assert len(set(qs)) == 3 and not any("less day-to-day use" in q for q in qs)       # no repeated usage question
    assert "budget" not in text and "procurement" not in text            # not the wrong playbook
    assert "Low adoption" in {d["title"] for d in payload["drivers"]}


# ------------------------------------------------------------------ Scenario C: usage +7%, trialing a competitor but happy
def test_C_competitor_detected_and_good_news_considered(C):
    aid, ctx, payload, source = C
    assert {s["signal_type"] for s in ctx["signals"]} == {"competitor_mention"}
    assert len(ctx["positives"]) == 1 and "happy" in ctx["positives"][0]["quote"]
    assert ctx["score"]["activity_pct"] == pytest.approx(0.07, abs=0.005)
    assert {"positive_quote", "activity"} <= kinds(payload)
    assert any(e["kind"] == "activity" and e["polarity"] == "reassuring" for e in payload["evidence"])
    assert "Competitor evaluation" in {d["title"] for d in payload["drivers"]}
    assert payload["reassuring"] and "Reassuring evidence" in comps(ctx) and comps(ctx)["Reassuring evidence"] < 0
    check_grounded(payload)


def test_C_is_not_automatically_high_risk(session, C, A):
    aid, ctx, payload, source = C
    assert ctx["score"]["band"] != "high"
    assert ctx["score"]["score"] < A[1]["score"]["score"]
    assert payload["plan"] and "Vantora" in payload["plan"]["problem"]["text"]      # a live trial still gets a drafted conversation
    assert "budget" not in all_text(payload["plan"]) and "training" not in all_text(payload["plan"])
    # same competitor trial, but flat usage and no good news: must score higher than with the good news
    bid = build(session, "scn-c0", 0.0, C_TURNS[:1])
    ctx0, _, _ = analyse(session, "scn-c0", bid)
    assert ctx0["score"]["score"] > ctx["score"]["score"]


def test_C_good_news_in_the_same_sentence_still_counts(session):
    bid = build(session, "scn-c1", 0.07, ["We are trialing Vantora with two team leads, but we are happy with Brightdesk and plan to renew."])
    ctx, payload, _ = analyse(session, "scn-c1", bid)
    assert {s["signal_type"] for s in ctx["signals"]} == {"competitor_mention"} and len(ctx["positives"]) == 1


def test_negated_good_news_is_not_counted(session):
    bid = build(session, "scn-c2", 0.0, ["We are not happy with Brightdesk and we do not plan to renew."])
    ctx, _, _ = analyse(session, "scn-c2", bid)
    assert ctx["positives"] == []


# ------------------------------------------------------------------ the AI path (mocked: no key in tests)
def test_AI_prompts_contain_both_usage_and_the_transcript_quote(session, A, monkeypatch):
    aid, ctx, payload, source = A
    seen = []

    def fake(system, user, schema, name, **kw):
        seen.append((name, user))
        if name == "retention_plan":
            return payload["plan"]
        return {k: payload[k] for k in ("sentences", "next_step", "drivers", "reassuring", "assessment")}

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_json", fake)
    _, src = brief.make(ctx, PACK)
    assert src == "llm" and {n for n, _ in seen} == {"renewal_brief", "retention_plan"}
    for _, prompt in seen:
        assert "down 60%" in prompt and "layoffs last month" in prompt          # usage data and conversation evidence together


def test_AI_extraction_drops_quotes_that_are_not_in_the_call(session, monkeypatch):
    from app.engine import extract
    turns_text = "\n".join(["Lena Vogt (Brightdesk Customer Success Manager): hello",
                            "Mia Novak (Ops Lead, Acme): We had layoffs last month and budgets are frozen."])
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {
        "signals": [{"signal_type": "budget_cut", "speaker": "Mia Novak", "confidence": 0.9, "quote": "We had layoffs last month"},
                    {"signal_type": "competitor_mention", "speaker": "Mia Novak", "confidence": 0.9, "quote": "We switched to Flowbird yesterday"}],
        "reassurances": [{"speaker": "Mia Novak", "confidence": 0.9, "quote": "We love everything about it"}]})
    sigs, good, src = extract.analyze_full(turns_text, PACK, "Brightdesk", extract.staff_label(PACK), use_llm=True)
    assert [s["signal_type"] for s in sigs] == ["budget_cut"] and good == [] and src == "llm"
