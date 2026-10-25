"""CSV connector: the "bring your own export" path for a pilot before real API connectors exist.

Expected files in the folder:
  accounts.csv       name, segment, employees, contact_name, contact_role, owner
  contracts.csv      billing_name, plan, capacity, capacity_prev, monthly_value, renewal_date (YYYY-MM-DD)
  activity.csv       account_name, day (YYYY-MM-DD), value
  conversations.csv  account_name, date, title, transcript   (turns as "Name (Label): text" lines)
Contracts are linked to accounts by identity matching on billing_name, exactly like real billing data."""
from typing import Union
import csv
import datetime as dt
from pathlib import Path

from ..engine import identity
from ..models import Account, ActivityPoint, Contract, Conversation
from .base import Connector, match_contracts
from .synthetic import wipe


def _rows(folder: Path, name: str):
    path = folder / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


class CsvFolderConnector(Connector):
    name = "csv"

    def __init__(self, folder: Union[str, Path]):
        self.folder = Path(folder)

    def sync(self, session, client, pack: dict) -> dict:
        wipe(session, client.id)
        ids = {}
        for r in _rows(self.folder, "accounts.csv"):
            a = Account(client_id=client.id, name=r["name"], segment=r.get("segment", ""),
                        employees=int(r.get("employees") or 0), contact_name=r.get("contact_name", ""),
                        contact_role=r.get("contact_role", ""), owner=r.get("owner") or client.user_name)
            session.add(a)
            session.flush()
            ids[a.id] = a.name
        for r in _rows(self.folder, "contracts.csv"):
            session.add(Contract(client_id=client.id, billing_name=r["billing_name"], plan=r.get("plan", ""),
                                 capacity=int(r["capacity"]), capacity_prev=int(r.get("capacity_prev") or r["capacity"]),
                                 monthly_value=float(r["monthly_value"]),
                                 renewal_date=dt.date.fromisoformat(r["renewal_date"])))

        def account_for(name):
            return identity.best_match(name, ids)[0]

        for r in _rows(self.folder, "activity.csv"):
            aid = account_for(r["account_name"])
            if aid:
                session.add(ActivityPoint(client_id=client.id, account_id=aid,
                                          day=dt.date.fromisoformat(r["day"]), value=float(r["value"])))
        n_conv = 0
        for r in _rows(self.folder, "conversations.csv"):
            aid = account_for(r["account_name"])
            if aid:
                session.add(Conversation(client_id=client.id, account_id=aid, date=dt.date.fromisoformat(r["date"]),
                                         title=r.get("title", "Call"), transcript=r["transcript"]))
                n_conv += 1
        session.commit()
        return {"accounts": len(ids), "conversations": n_conv, **match_contracts(session, client.id)}
