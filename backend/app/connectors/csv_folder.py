"""CSV connector: the "bring your own export" path for a pilot before real API connectors exist.

Expected files in the folder:
  accounts.csv       name, segment, employees, contact_name, contact_role, owner
  contracts.csv      billing_name, plan, capacity, capacity_prev, monthly_value, renewal_date (YYYY-MM-DD)
  activity.csv       account_name, day (YYYY-MM-DD), value
  conversations.csv  account_name, date, title, transcript   (turns as "Name (Label): text" lines)
Optional, for the other sources (anything missing is simply not shown):
  tickets.csv        account_name, opened, last_update, status (open|pending|solved), priority, category, subject
  invoices.csv       account_name, number, issued, due, amount, paid_on (empty while unpaid)
  features.csv       account_name, feature, value, value_prev   (last 30 days and the 30 days before)
  usage.csv          account_name, logins, logins_prev, last_login
Contracts are linked to accounts by identity matching on billing_name, exactly like real billing data."""
from typing import Union
import csv
import datetime as dt
from pathlib import Path

from ..engine import identity
from ..models import Account, ActivityPoint, Contract, Conversation, FeatureUsage, Invoice, Ticket, UsageStat
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
        extra = {"tickets": 0, "invoices": 0, "features": 0}
        day = lambda v: dt.date.fromisoformat(v) if v else None                                # noqa: E731
        for r in _rows(self.folder, "tickets.csv"):
            aid = account_for(r["account_name"])
            if aid:
                session.add(Ticket(client_id=client.id, account_id=aid, opened=day(r["opened"]), last_update=day(r["last_update"]) or day(r["opened"]),
                                   status=r.get("status") or "open", priority=r.get("priority") or "normal",
                                   category=r.get("category") or "other", subject=r["subject"]))
                extra["tickets"] += 1
        for r in _rows(self.folder, "invoices.csv"):
            aid = account_for(r["account_name"])
            if aid:
                session.add(Invoice(client_id=client.id, account_id=aid, number=r.get("number", ""), issued=day(r["issued"]),
                                    due=day(r["due"]), amount=float(r["amount"]), paid_on=day(r.get("paid_on", ""))))
                extra["invoices"] += 1
        for r in _rows(self.folder, "features.csv"):
            aid = account_for(r["account_name"])
            if aid:
                session.add(FeatureUsage(client_id=client.id, account_id=aid, feature=r["feature"], value=float(r["value"]),
                                         value_prev=float(r.get("value_prev") or 0)))
                extra["features"] += 1
        session.commit()
        matched = match_contracts(session, client.id)
        self._usage(session, client, pack, account_for)
        return {"accounts": len(ids), "conversations": n_conv, **extra, **matched}

    def _usage(self, session, client, pack: dict, account_for):
        """usage.csv gives logins; the usage numbers come from the activity series and what was purchased."""
        from sqlalchemy import select
        from . import demo_sources
        mode = demo_sources.load_cfg(pack["id"])["mode"] if (demo_sources.DIR / f"{pack['id']}.yaml").exists() else "users"
        for r in _rows(self.folder, "usage.csv"):
            aid = account_for(r["account_name"])
            contract = session.scalars(select(Contract).where(Contract.account_id == aid)).first() if aid else None
            if not (aid and contract):
                continue
            series = [p.value for p in session.scalars(select(ActivityPoint).where(ActivityPoint.account_id == aid).order_by(ActivityPoint.day))]
            cur, prev, util = demo_sources.usage_numbers(series, contract.capacity, mode)
            session.add(UsageStat(account_id=aid, client_id=client.id, metric=cur, metric_prev=prev, utilization=util,
                                  logins=int(r["logins"]), logins_prev=int(r.get("logins_prev") or r["logins"]),
                                  last_login=dt.date.fromisoformat(r["last_login"]) if r.get("last_login") else None))
        session.commit()
