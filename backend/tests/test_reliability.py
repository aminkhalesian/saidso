"""Reliability and transparency: unknown usage is not zero, AI vs fallback is labelled honestly, failures do not crash,
clients are isolated, stale briefs are detected and refreshed, and secrets never reach the browser."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import pipeline, service
from app.engine import brief, llm
from app.main import app
from app.models import Action, ActivityPoint, Brief, Client, SessionLocal
from scenario_lib import PACK, analyse, build

BUDGET = ["We had layoffs last month, so the budget for tools has been cut by about a third."]


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="module")
def http():
    return TestClient(app)


def comps(ctx):
    return {c["label"]: c["points"] for c in ctx["score"]["components"]}


# ------------------------------------------------------------------ missing data is not zero
@pytest.mark.parametrize("cid,change,days", [("rel-none", None, 90), ("rel-short", -0.5, 10)])
def test_missing_or_too_little_usage_is_unknown_not_zero(session, cid, change, days):
    aid = build(session, cid, change, BUDGET, usage_days=days)
    ctx, payload, _ = analyse(session, cid, aid)
    assert ctx["score"]["usage_known"] is False and ctx["score"]["activity_pct"] == 0
    assert comps(ctx)["Daily active users trend"] == 0
    kinds = {e["kind"] for e in payload["evidence"]}
    assert "usage_unknown" in kinds and "activity" not in kinds
    assert not any("down" in e["text"] and "Daily active" in e["text"] for e in payload["evidence"])


# ------------------------------------------------------------------ AI vs fallback labelling
def test_offline_output_is_labelled_template_everywhere(session, http):
    aid = build(session, "rel-a", -0.6, BUDGET)
    pipeline.build_outputs(session, session.get(Client, "rel-a"))
    r = http.get(f"/api/clients/rel-a/accounts/{aid}").json()
    assert r["brief_source"] == "template" and r["brief"]["plan_source"] == "template"
    assert all(a["source"] != "llm" for a in r["actions"])
    assert all(s["source"] == "rules" for s in r["signals"])


def test_ai_label_only_when_the_ai_output_was_accepted(session, monkeypatch):
    aid = build(session, "rel-ai", -0.6, BUDGET)
    ctx, payload, _ = analyse(session, "rel-ai", aid)
    good = {k: payload[k] for k in ("sentences", "next_step", "drivers", "reassuring", "assessment")}
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda s, u, schema, name, **kw: payload["plan"] if name == "retention_plan" else good)
    p, src = brief.make(ctx, PACK)
    assert src == "llm" and p["plan_source"] == "llm"
    bad_plan = {**payload["plan"], "problem": {"text": "They will churn with 93% probability.", "evidence": ["E1"]}}
    monkeypatch.setattr(llm, "chat_json", lambda s, u, schema, name, **kw: bad_plan if name == "retention_plan" else good)
    p, src = brief.make(ctx, PACK)
    assert src == "llm" and p["plan_source"] == "template"            # brief accepted, fabricated plan rejected and labelled honestly


def test_failed_ai_requests_do_not_crash_and_fall_back(session, monkeypatch):
    aid = build(session, "rel-fail", -0.6, BUDGET)
    ctx, _, _ = analyse(session, "rel-fail", aid)

    def boom(*a, **k):
        raise RuntimeError("503 upstream unavailable")

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_json", boom)
    p, src = brief.make(ctx, PACK)
    assert src == "template" and p["plan_source"] == "template" and p["plan"] and p["assessment"]["text"]


# ------------------------------------------------------------------ evidence integrity
def test_unsupported_claims_are_rejected(session):
    aid = build(session, "rel-ev", -0.6, BUDGET)
    ctx, payload, _ = analyse(session, "rel-ev", aid)
    ok = {k: payload[k] for k in ("sentences", "next_step", "drivers", "reassuring", "assessment")}
    ev = payload["evidence"]
    assert brief.validate(ok, ev)
    for text in ("Churn probability is 80%.", "They will leave within 7 weeks.", "Revenue loss is €12,345."):
        assert not brief.validate({**ok, "assessment": {"text": text, "evidence": [ev[0]["id"]]}}, ev)
    assert not brief.validate({**ok, "drivers": [{"title": "x", "why_it_matters": "y", "evidence": ["E404"]}]}, ev)
    assert not brief.validate({**ok, "drivers": [{"title": "x", "why_it_matters": "y", "evidence": []}]}, ev)


# ------------------------------------------------------------------ dynamic updates, stale briefs
def test_changing_usage_updates_score_evidence_playbook_and_flags_stale_briefs(session, http):
    aid = build(session, "rel-dyn", -0.6, BUDGET)
    client = session.get(Client, "rel-dyn")
    pipeline.build_outputs(session, client)
    first = http.get(f"/api/clients/rel-dyn/accounts/{aid}").json()
    assert first["brief_stale"] is False
    draft_before = next(a for a in first["actions"] if a["status"] == "draft")["body"]

    for p in session.scalars(select(ActivityPoint).where(ActivityPoint.account_id == aid).order_by(ActivityPoint.day)).all()[-14:]:
        p.value = 100.0                                                    # usage recovers
    session.commit()
    stale = http.get(f"/api/clients/rel-dyn/accounts/{aid}").json()
    assert stale["brief_stale"] is True                                    # the old brief is flagged, never silently trusted
    assert stale["score"]["score"] < first["score"]["score"]               # the score is live and already updated

    pipeline.build_outputs(session, client)                                # the pipeline rewrites brief and playbook
    fresh = http.get(f"/api/clients/rel-dyn/accounts/{aid}").json()
    assert fresh["brief_stale"] is False
    assert not any("down 60%" in e["text"] for e in fresh["brief"]["evidence"])
    drafts = [a["body"] for a in fresh["actions"] if a["status"] == "draft"]
    assert not drafts or all("down 60%" not in d for d in drafts) and drafts[0] != draft_before


# ------------------------------------------------------------------ client isolation and secrets
def test_clients_cannot_read_or_change_each_others_data(session, http):
    aid_a = build(session, "iso-a", -0.6, BUDGET)
    build(session, "iso-b", -0.6, BUDGET)
    pipeline.build_outputs(session, session.get(Client, "iso-a"))
    action = session.scalars(select(Action).where(Action.client_id == "iso-a")).first()
    assert action is not None
    assert http.get(f"/api/clients/iso-b/accounts/{aid_a}").status_code == 404
    assert http.post(f"/api/clients/iso-b/actions/{action.id}", json={"status": "approved"}).status_code == 404
    sig = service.context(session, "iso-a", aid_a)["signals"][0]
    assert http.post(f"/api/clients/iso-b/signals/{sig['id']}/feedback", json={"feedback": "dismissed"}).status_code == 404
    session.expire_all()
    assert session.get(Action, action.id).status == "draft"
    assert http.post(f"/api/clients/iso-a/actions/{action.id}", json={"status": "approved"}).json()["status"] == "approved"
    over_b = http.get("/api/clients/iso-b/overview").json()
    assert all(r["name"] != "Acme iso-a" for r in over_b["renewals"])


def test_the_api_key_never_reaches_the_browser(session, http, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-VALUE-123")
    aid = build(session, "rel-key", -0.6, BUDGET)
    for url in ("/api/health", "/api/clients", "/api/clients/rel-key/overview", f"/api/clients/rel-key/accounts/{aid}",
                "/api/clients/rel-key/sources", "/api/clients/rel-key/trust"):
        r = http.get(url)
        assert r.status_code == 200 and "SECRET-VALUE" not in r.text, url


def test_dashboard_lists_every_high_risk_customer(session, http):
    heavy = BUDGET + ["The price is far too expensive for what we get.", "We are also looking at Vantora right now."]
    for i in range(6):                                   # six high-risk customers in one client: more than the old limit of four
        build(session, "dash", -0.7, heavy, days_to_renewal=15 + i, name=f"Heavy {i}")
    pipeline.build_outputs(session, session.get(Client, "dash"))
    over = http.get("/api/clients/dash/overview").json()
    high = [r for r in over["renewals"] if r["band"] == "high"]
    assert len(high) == 6 and len(over["this_week"]) == 6
    assert {r["account_id"] for r in over["this_week"]} == {r["account_id"] for r in high}
