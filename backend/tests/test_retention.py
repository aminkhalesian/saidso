"""Retention analytics: the numbers on the cards are built from the rows behind them, follow the renewal horizon,
respect client isolation and say 'unavailable' when a source is not connected."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import pipeline
from app.main import app
from app.models import Client, Contract, Invoice, SessionLocal, Ticket
from scenario_lib import build

HEAVY = ["We are also looking at Vantora right now.", "The price is far too expensive for what we get.",
         "We had layoffs last month, so the budget for tools has been cut by about a third."]


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="module")
def http():
    return TestClient(app)


def kpi(data, id):
    return next(k for k in data["kpis"] if k["id"] == id)


def test_cards_reconcile_with_their_rows_and_follow_the_horizon(session, http):
    a = build(session, "ret", -0.7, HEAVY, days_to_renewal=15, name="Soon High")
    b = build(session, "ret", -0.7, HEAVY, days_to_renewal=75, name="Later High")
    c = build(session, "ret", 0.3, ["Everything is going well and the team loves it."], days_to_renewal=45, name="Calm Growing")
    session.get(Contract, session.query(Contract).filter_by(account_id=c).one().id).capacity = 80   # more seats than before
    session.query(Contract).filter_by(account_id=a).one().capacity_prev = 90                          # a seat cut: 60 now, 90 before
    session.commit()
    pipeline.build_outputs(session, session.get(Client, "ret"))

    d90 = http.get("/api/clients/ret/retention?window=90").json()
    d30 = http.get("/api/clients/ret/retention?window=30").json()
    assert d90["renewals"] == 3 and d30["renewals"] == 1                     # the horizon changes the cohort
    assert {r["name"] for r in kpi(d30, "at_risk")["rows"]} == {"Soon High"}

    risk = kpi(d90, "at_risk")
    assert risk["headline"] == f'{len(risk["rows"])} of 3' and len(risk["rows"]) == 2
    expo = kpi(d90, "exposure")
    exposed = sum(r["annual_value"] for r in expo["rows"])
    assert expo["n"] == pytest.approx((d90["total_value"] - exposed) / d90["total_value"])
    assert {r["account_id"] for r in expo["rows"]} == {r["account_id"] for r in risk["rows"]}
    assert len(kpi(d90, "health")["rows"]) == 3                               # one health row per renewal
    cut = kpi(d90, "contraction")["rows"]
    assert [r["name"] for r in cut] == ["Soon High"] and cut[0]["reduction"] == round(cut[0]["per_seat"] * 30)
    exp = kpi(d90, "expansion")["rows"]
    assert [r["name"] for r in exp] == ["Calm Growing"] and "grew" in exp[0]["why"]
    calls = kpi(d90, "calls")
    assert calls["status"] == "ok" and all(r["covered"] for r in calls["rows"])


def test_missing_sources_are_unavailable_never_zero(session, http):
    d = http.get("/api/clients/ret/retention?window=90").json()
    for id in ("tickets", "invoices", "utilisation", "features"):          # the scenario builder has no such records
        k = kpi(d, id)
        assert k["status"] == "none" and k["headline"] == "Data unavailable", id

    acc = session.query(Contract).filter_by(client_id="ret").first().account_id
    today = dt.date.today()
    session.add(Ticket(client_id="ret", account_id=acc, opened=today - dt.timedelta(days=12), last_update=today, status="open",
                       priority="high", category="bug", subject="Export fails"))
    session.add(Ticket(client_id="ret", account_id=acc, opened=today - dt.timedelta(days=30), last_update=today, status="solved",
                       priority="high", category="bug", subject="Old and solved"))
    session.add(Invoice(client_id="ret", account_id=acc, number="X-1", issued=today - dt.timedelta(days=60), due=today - dt.timedelta(days=30),
                        amount=1000.0, paid_on=None))
    session.add(Invoice(client_id="ret", account_id=acc, number="X-2", issued=today - dt.timedelta(days=60), due=today - dt.timedelta(days=30),
                        amount=500.0, paid_on=today - dt.timedelta(days=20)))
    session.commit()
    d = http.get("/api/clients/ret/retention?window=90").json()
    t, i = kpi(d, "tickets"), kpi(d, "invoices")
    assert t["status"] == "ok" and [r["subject"] for r in t["rows"]] == ["Export fails"] and t["rows"][0]["age_days"] == 12
    assert i["status"] == "ok" and [r["number"] for r in i["rows"]] == ["X-1"] and i["rows"][0]["days_overdue"] == 30


def test_a_connected_source_with_nothing_to_report_is_a_real_zero(session, http):
    acc = session.query(Contract).filter_by(client_id="ret").first().account_id
    session.query(Invoice).filter_by(client_id="ret").delete()
    today = dt.date.today()
    session.add(Invoice(client_id="ret", account_id=acc, number="OK-1", issued=today - dt.timedelta(days=40), due=today - dt.timedelta(days=10),
                        amount=100.0, paid_on=today - dt.timedelta(days=12)))
    session.commit()
    k = kpi(http.get("/api/clients/ret/retention?window=90").json(), "invoices")
    assert k["status"] == "ok" and k["headline"] == "0" and k["rows"] == []


def test_clients_are_isolated(session, http):
    build(session, "other", -0.7, HEAVY, days_to_renewal=20, name="Other Client Co")
    mine = {r["name"] for k in http.get("/api/clients/ret/retention?window=90").json()["kpis"] for r in k["rows"]}
    theirs = {r["name"] for k in http.get("/api/clients/other/retention?window=90").json()["kpis"] for r in k["rows"]}
    assert "Other Client Co" not in mine and "Other Client Co" in theirs and "Soon High" not in theirs


def test_unknown_horizon_falls_back_to_90(http):
    assert http.get("/api/clients/ret/retention?window=7").json()["window"] == 90
