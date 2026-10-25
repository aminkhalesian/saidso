"""Core guarantees: no ungrounded flags, citations validated, packs load, clients isolated, API works."""
import os

os.environ["MOCK_LLM"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///./test_engine.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import pipeline  # noqa: E402
from app.engine import brief, extract, identity, llm  # noqa: E402
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
    if os.path.exists("test_engine.db"):
        os.remove("test_engine.db")


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
    ids = {"E1", "E2"}
    ok = {"sentences": [{"text": "Risky.", "evidence": ["E1"]}], "next_step": {"text": "Call.", "evidence": ["E2"]}}
    bad = {"sentences": [{"text": "Risky.", "evidence": ["E9"]}], "next_step": {"text": "Call.", "evidence": []}}
    assert brief.validate(ok, ids) and not brief.validate(bad, ids)


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
