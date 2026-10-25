"""CSV upload: new customers and flags must land in the same lists the dashboard and All renewals read."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.connectors import csv_import
from app.main import app
from app.models import Client, SessionLocal, init_db


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="module")
def http():
    return TestClient(app)

SOON = (dt.date.today() + dt.timedelta(days=20)).strftime("%d.%m.%Y")
LATER = (dt.date.today() + dt.timedelta(days=55)).isoformat()
FILE = (
    "Company;Licences;ARR;Contract end;Usage trend;Notes\n"
    f"Nordwind Energie GmbH;80;\"€96.000\";{SOON};-41%;\"We looked at Vantora last month and their demo was impressive. | The budget is frozen until January.\"\n"
    f"Sonnental Foods;60;\"54,000\";{LATER};+18%;Everything is going well and the team loves it.\n"
    "Vergangenheit AG;5;1000;01.01.2020;0;hello\n"
    f"Sonnental Foods;60;54000;{LATER};0;duplicate row\n"
)


def _client(session, cid="imp"):
    init_db()
    if session.get(Client, cid) is None:
        session.add(Client(id=cid, name="Import test", pack_id="saas", user_name="Lena Vogt"))
        session.commit()


def test_parsing_tidies_messy_values():
    assert csv_import._number("€96.000") == 96000 and csv_import._number("21.000,50") == 21000.5
    assert csv_import._number("18,000") == 18000 and csv_import._number("32k") == 32000
    assert csv_import._percent("-41%") == -0.41 and csv_import._percent("-0.2") == -0.2 and csv_import._percent("12") == 0.12
    notes = []
    assert csv_import._date("15.11.2026", notes) == dt.date(2026, 11, 15) and notes
    assert csv_import._date("not a date", []) is None


def test_upload_waits_for_a_decision_then_lands_in_the_lists(session, http):
    _client(session)
    r = http.post("/api/clients/imp/import", json={"csv": FILE})
    assert r.status_code == 200, r.text
    assert r.json()["pending"] is True
    rep = {x["customer"]: x for x in reversed(r.json()["rows"])}
    assert rep["Nordwind Energie GmbH"]["status"] == "added" and rep["Sonnental Foods"]["status"] == "added"
    assert "past" in rep["Vergangenheit AG"]["reason"]
    assert any(x["status"] == "skipped" and "twice" in x["reason"] for x in r.json()["rows"])
    assert {"Competitor evaluation", "Budget pressure"} <= set(rep["Nordwind Energie GmbH"]["signals"])
    assert rep["Nordwind Energie GmbH"]["score"] > 0                       # the preview already shows where it would land
    over = http.get("/api/clients/imp/overview").json()
    assert over["renewals"] == [] and over["this_week"] == [] and over["kpis"]["open_actions"] == 0   # nothing counts yet

    http.post("/api/clients/imp/import/accept")
    over = http.get("/api/clients/imp/overview").json()
    names = {x["name"]: x for x in over["renewals"]}
    assert "Nordwind Energie GmbH" in names and "Vergangenheit AG" not in names
    for sig in rep["Nordwind Energie GmbH"]["signals"]:                      # flags are tied to a verbatim quote
        assert sig in names["Nordwind Energie GmbH"]["signals"]
    acc = http.get(f"/api/clients/imp/accounts/{names['Nordwind Energie GmbH']['account_id']}").json()
    assert all(s["quote"] in acc["conversations"][0]["transcript"] for s in acc["signals"])

    again = http.post("/api/clients/imp/import", json={"csv": FILE}).json()      # the same file again adds flags, no duplicate
    assert again["rows"][0]["status"] == "updated"
    still = http.get("/api/clients/imp/accounts/%d" % names["Nordwind Energie GmbH"]["account_id"]).json()
    assert len(still["conversations"]) == 1                                  # the waiting call is not shown yet
    http.delete("/api/clients/imp/import/pending")
    assert len([x for x in http.get("/api/clients/imp/overview").json()["renewals"] if x["name"] == "Nordwind Energie GmbH"]) == 1

    http.delete("/api/clients/imp/import")                                    # remove everything an upload added
    assert http.get("/api/clients/imp/overview").json()["renewals"] == []


def test_declining_removes_the_waiting_upload(session, http):
    _client(session, "imp3")
    http.post("/api/clients/imp3/import", json={"csv": FILE})
    http.delete("/api/clients/imp3/import/pending")
    assert http.get("/api/clients/imp3/overview").json()["renewals"] == []
    http.post("/api/clients/imp3/import/accept")                              # nothing waiting: nothing to add
    assert http.get("/api/clients/imp3/overview").json()["renewals"] == []


def test_upload_needs_a_customer_column(session, http):
    _client(session, "imp2")
    r = http.post("/api/clients/imp2/import", json={"csv": "foo,bar\n1,2\n"})
    assert r.status_code == 422 and "customer" in r.text
