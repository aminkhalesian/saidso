"""Core guarantees: no ungrounded flags, citations validated, packs load, clients isolated, API works."""
import os


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import pipeline  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import service  # noqa: E402
from app.engine import actions, brief, extract, identity, llm  # noqa: E402
from app.models import ActivityPoint, Signal, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.packs import list_packs, load_pack  # noqa: E402

PACK = load_pack("saas")
STAFF = extract.staff_label(PACK)
TRANSCRIPT = (f"Lena Vogt ({STAFF}): Thanks for joining. How are things?\n"
              "Mia Novak (Ops Lead, Acme): We have a trial of Vantora running with two of our team leads right now.\n"
              f"Lena Vogt ({STAFF}): We hate the price, by the way.\n"
              "Mia Novak (Ops Lead, Acme): Sounds good, send it over.")


@pytest.fixture(scope="module")
def api():
    pipeline.seed()
    yield TestClient(app)


def test_all_packs_load_and_have_playbooks():
    packs = list_packs()
    assert {p["id"] for p in packs} >= {"saas", "agency"}
    for p in packs:
        for sig in p["signals"].values():
            assert sig["playbook"]["title"] and sig["weight"] > 0


def test_grounding_drops_invented_and_staff_quotes():
    turns = extract.parse_turns(TRANSCRIPT, STAFF)
    raw = [{"signal_type": "competitor_mention", "confidence": 0.9, "quote": "trial of Vantora running"},
           {"signal_type": "pricing_complaint", "confidence": 0.9, "quote": "We hate the price"},       # staff said it
           {"signal_type": "budget_cut", "confidence": 0.9, "quote": "Our budget was cut in half"},     # never said
           {"signal_type": "not_a_type", "confidence": 0.9, "quote": "Sounds good, send it over"}]     # unknown type
    out = extract.ground(raw, turns, PACK["signals"].keys())
    assert [s["signal_type"] for s in out] == ["competitor_mention"]
    assert out[0]["speaker"] == "Mia Novak"


def test_brief_validation_rejects_bad_citations():
    ev = [{"id": "E1", "text": "x"}, {"id": "E2", "text": "y"}]
    ok = {"sentences": [{"text": "Risky.", "evidence": ["E1"]}], "next_step": {"text": "Call.", "evidence": ["E2"]},
          "assessment": {"text": "Watch it.", "evidence": ["E1"]}}
    bad = {"sentences": [{"text": "Risky.", "evidence": ["E9"]}], "next_step": {"text": "Call.", "evidence": []},
           "assessment": {"text": "Watch it.", "evidence": ["E1"]}}
    assert brief.validate(ok, ev) and not brief.validate(bad, ev)


def test_identity_matching_handles_messy_names():
    accounts = {1: "Weißdorn Insurance", 2: "Brandt & Sohn Maschinenbau", 3: "Celsia Health"}
    assert identity.best_match("WEISSDORN INSURANCE GMBH & CO. KG", accounts)[0] == 1
    assert identity.best_match("Brandt und Sohn Maschinenbau GmbH", accounts)[0] == 2
    assert identity.best_match("Totally Unrelated Ltd", accounts)[0] is None


def test_llm_offline_by_default():
    assert not llm.enabled()


def test_api_overview_and_isolation(api):
    clients = api.get("/api/clients").json()
    assert {c["id"] for c in clients} == {"brightdesk", "kranich"}
    a = api.get("/api/clients/brightdesk/overview").json()
    b = api.get("/api/clients/kranich/overview").json()
    ids_a = {r["account_id"] for r in a["renewals"]}
    ids_b = {r["account_id"] for r in b["renewals"]}
    assert ids_a and ids_b and not ids_a & ids_b
    assert api.get(f"/api/clients/kranich/accounts/{next(iter(ids_a))}").status_code == 404


def test_api_account_actions_feedback_trust_analyze(api):
    ov = api.get("/api/clients/brightdesk/overview").json()
    top = ov["this_week"][0]
    detail = api.get(f"/api/clients/brightdesk/accounts/{top['account_id']}").json()
    assert detail["brief"]["sentences"] and detail["activity"] and detail["timeline"]
    ev_ids = {e["id"] for e in detail["brief"]["evidence"]}
    assert all(set(s["evidence"]) <= ev_ids for s in detail["brief"]["sentences"])

    act = api.post(f"/api/actions/{top['action']['id']}", json={"status": "approved"}).json()
    assert act["status"] == "approved"

    sig = detail["signals"][0]
    before = detail["score"]["score"]
    api.post(f"/api/signals/{sig['id']}/feedback", json={"feedback": "dismissed"})
    after = api.get(f"/api/clients/brightdesk/accounts/{top['account_id']}").json()["score"]["score"]
    assert after <= before

    t = api.get("/api/clients/brightdesk/trust").json()
    assert t["planted"] > 0 and 0 <= t["precision"] <= 1 and t["feedback"]["dismissed"] == 1

    sample = api.get("/api/clients/kranich/sample-transcript").json()["transcript"]
    res = api.post("/api/clients/kranich/analyze", json={"transcript": sample}).json()
    assert res["signals"] and all(s["quote"] in sample for s in res["signals"])


def test_every_signal_has_a_full_play():
    from app.engine.actions import load_plays
    for p in list_packs():
        plays = load_plays(p["id"])
        assert set(plays) == set(p["signals"]), f"{p['id']}: plays must cover every signal"
        for key, play in plays.items():
            for field in ("goal", "steps", "say", "pushback", "bring", "done_when"):
                assert play[field], f"{p['id']}.{key} is missing {field}"


def test_drafted_actions_are_plays_with_the_real_quote(api):
    ov = api.get("/api/clients/brightdesk/overview").json()
    assert ov["this_week"], "expected at least one account needing attention"
    for row in ov["this_week"]:
        body = row["action"]["body"]
        assert body.startswith("WHY NOW\n") and "STEPS" in body and "IF THEY PUSH BACK" in body
        detail = api.get(f"/api/clients/brightdesk/accounts/{row['action']['account_id']}").json()
        quotes = [s["quote"] for s in detail["signals"]]
        assert any(q in body for q in quotes)                    # the play cites a quote the customer really said
        assert "{" not in body and "}" not in body               # no unfilled placeholders


def test_every_account_shows_four_sources_that_agree_with_the_score(api):
    ov = api.get("/api/clients/brightdesk/overview").json()
    for row in ov["renewals"][:10]:
        d = api.get(f"/api/clients/brightdesk/accounts/{row['account_id']}").json()
        s = d["sources"]
        assert s["usage"] and s["commercial"] and s["conversations"]["count"] >= 1
        assert abs(s["usage"]["metric_pct"] - d["score"]["activity_pct"]) <= 0.02       # same windows as the score
        assert s["commercial"]["annual_value"] == d["contract"]["annual_value"]
        if s["support"]:
            assert s["support"]["unresolved"] <= s["support"]["total"]


def test_sources_overview_and_csv_export(api, tmp_path):
    ov = api.get("/api/clients/kranich/sources").json()
    assert [s["key"] for s in ov["sources"]] == ["usage", "conversations", "support", "commercial"]
    assert len(ov["files"]) == 8
    from app.connectors.csv_export import export_csv
    from app.models import SessionLocal
    with SessionLocal() as session:
        written = export_csv(session, "kranich", str(tmp_path))
    assert set(written) == {f["file"] for f in ov["files"]} and written["tickets.csv"] > 0 and written["invoices.csv"] > 0


# ------------------------------------------------------------------ one complete customer journey


@pytest.fixture(scope="module")
def session(api):
    with SessionLocal() as s:
        yield s


def _target(session):
    """An account that is both losing usage and has a budget concern on a call."""
    for ctx in service.contexts(session, "brightdesk"):
        if ctx["score"]["activity_pct"] <= -0.08 and any(s["signal_type"] == "budget_cut" for s in ctx["signals"]) \
                and ctx["score"]["band"] != "low":
            return ctx["account"]["id"]
    pytest.fail("the demo data has no account with falling usage and a budget concern")


def _full(session, account_id):
    ctx = service.context(session, "brightdesk", account_id)
    service.with_sources(session, "brightdesk", ctx, PACK)
    payload, source = brief.make(ctx, PACK)
    return ctx, payload


def test_both_risks_are_found_and_both_move_the_score(session):
    ctx, payload = _full(session, _target(session))
    comp = {c["label"]: c["points"] for c in ctx["score"]["components"]}
    assert comp["Conversation signals"] > 0
    assert comp["Daily active users trend"] > 0                  # usage, from the activity data
    labels = {d["title"] for d in payload["drivers"]}
    assert "Budget pressure" in labels and "Daily active users" in labels


def test_every_statement_cites_real_evidence_and_no_numbers_are_invented(session):
    ctx, payload = _full(session, _target(session))
    ev = {e["id"]: e for e in payload["evidence"]}
    assert brief.validate(payload, payload["evidence"])
    budget = next(e for e in ev.values() if e["kind"] == "signal" and e["signal_type"] == "budget_cut")
    driver = next(d for d in payload["drivers"] if d["title"] == "Budget pressure")
    assert budget["id"] in driver["evidence"] and budget["quote"] in budget["text"]
    for q in payload["plan"]["questions"] + payload["plan"]["interventions"]:
        assert q["evidence"] and set(q["evidence"]) <= set(ev)


def test_ai_output_with_an_invented_number_or_probability_is_rejected(session):
    ctx, payload = _full(session, _target(session))
    ev = payload["evidence"]
    ok = {k: payload[k] for k in ("sentences", "next_step", "drivers", "reassuring", "assessment")}
    assert brief.validate(ok, ev)
    bad = {**ok, "assessment": {"text": "There is a 87% chance they churn.", "evidence": [ev[0]["id"]]}}
    assert not brief.validate(bad, ev)
    bad = {**ok, "assessment": {"text": "Revenue at risk is €99,999.", "evidence": [ev[0]["id"]]}}
    assert not brief.validate(bad, ev)
    bad = {**ok, "assessment": {"text": "Looks risky.", "evidence": ["E999"]}}
    assert not brief.validate(bad, ev)


def test_ai_path_is_used_when_valid_and_template_when_not(session, monkeypatch):
    ctx, payload = _full(session, _target(session))
    good = {k: payload[k] for k in ("sentences", "next_step", "drivers", "reassuring", "assessment")}
    monkeypatch.setattr(llm, "enabled", lambda: True)
    plan = payload["plan"]
    monkeypatch.setattr(llm, "chat_json", lambda s, u, schema, name, **kw: plan if name == "retention_plan" else good)
    _, source = brief.make(ctx, PACK)
    assert source == "llm"
    bad = {**good, "assessment": {"text": "Churn probability is 87%.", "evidence": [good["drivers"][0]["evidence"][0]]}}
    monkeypatch.setattr(llm, "chat_json", lambda s, u, schema, name, **kw: plan if name == "retention_plan" else bad)
    _, source = brief.make(ctx, PACK)
    assert source == "template"


def test_playbook_addresses_this_customers_situation(session):
    aid = _target(session)
    ctx, payload = _full(session, aid)
    plan = payload["plan"]
    quote = next(e["quote"] for e in payload["evidence"] if e["kind"] == "signal" and e["signal_type"] == "budget_cut")
    assert quote in plan["problem"]["text"]
    assert len(plan["questions"]) == 3 and len(plan["interventions"]) == 2 and plan["followup"]["text"]
    body = actions.play_body(actions.load_plays("saas")["budget_cut"],
                             next(s for s in ctx["signals"] if s["signal_type"] == "budget_cut"), ctx, PACK, plan=plan)
    for head in ("MAIN PROBLEM", "OBJECTIVE", "QUESTIONS TO ASK", "RETENTION OPTIONS", "FOLLOW-UP"):
        assert head in body
    assert quote in body and "[E" in body                          # facts and evidence ids are visible to the CSM


def test_changing_the_data_changes_the_assessment(session):
    aid = _target(session)
    before_ctx, before = _full(session, aid)
    # usage recovers and the budget concern is dismissed by the CSM
    pts = session.scalars(select(ActivityPoint).where(ActivityPoint.account_id == aid).order_by(ActivityPoint.day)).all()
    base = sum(p.value for p in pts[:45]) / 45
    for p in pts[-14:]:
        p.value = base * 1.1
    for s in session.scalars(select(Signal).where(Signal.account_id == aid)):
        if s.signal_type == "budget_cut":
            s.feedback = "dismissed"
    session.commit()
    after_ctx, after = _full(session, aid)
    assert after_ctx["score"]["score"] < before_ctx["score"]["score"]
    assert "Budget pressure" not in {d["title"] for d in after["drivers"]}
    assert after["plan"] is None or after["plan"]["problem"]["text"] != before["plan"]["problem"]["text"]
    assert any(r["text"].startswith("Daily active users up") for r in after["reassuring"])
