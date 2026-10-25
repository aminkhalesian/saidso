"""Write a client's data in exactly the shape the CSV pilot folder expects. Shows a customer what to send."""
import csv
from pathlib import Path

from sqlalchemy import select

from ..models import (Account, ActivityPoint, Contract, Conversation, FeatureUsage, Invoice, Ticket, UsageStat)


def _write(folder: Path, name: str, header: list[str], rows: list[list]) -> int:
    with (folder / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def export_csv(session, client_id: str, folder: str) -> dict:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    names = {a.id: a.name for a in session.scalars(select(Account).where(Account.client_id == client_id))}
    q = lambda model: session.scalars(select(model).where(model.client_id == client_id))     # noqa: E731
    n = {}
    n["accounts.csv"] = _write(out, "accounts.csv", ["name", "segment", "employees", "contact_name", "contact_role", "owner"],
                               [[a.name, a.segment, a.employees, a.contact_name, a.contact_role, a.owner] for a in q(Account)])
    n["contracts.csv"] = _write(out, "contracts.csv", ["billing_name", "plan", "capacity", "capacity_prev", "monthly_value", "renewal_date"],
                                [[c.billing_name, c.plan, c.capacity, c.capacity_prev, c.monthly_value, c.renewal_date.isoformat()] for c in q(Contract)])
    n["activity.csv"] = _write(out, "activity.csv", ["account_name", "day", "value"],
                               [[names[p.account_id], p.day.isoformat(), p.value] for p in q(ActivityPoint)])
    n["conversations.csv"] = _write(out, "conversations.csv", ["account_name", "date", "title", "transcript"],
                                    [[names[c.account_id], c.date.isoformat(), c.title, c.transcript] for c in q(Conversation)])
    n["tickets.csv"] = _write(out, "tickets.csv", ["account_name", "opened", "last_update", "status", "priority", "category", "subject"],
                              [[names[t.account_id], t.opened.isoformat(), t.last_update.isoformat(), t.status, t.priority, t.category, t.subject]
                               for t in q(Ticket)])
    n["invoices.csv"] = _write(out, "invoices.csv", ["account_name", "number", "issued", "due", "amount", "paid_on"],
                               [[names[i.account_id], i.number, i.issued.isoformat(), i.due.isoformat(), i.amount,
                                 i.paid_on.isoformat() if i.paid_on else ""] for i in q(Invoice)])
    n["features.csv"] = _write(out, "features.csv", ["account_name", "feature", "value", "value_prev"],
                               [[names[f.account_id], f.feature, f.value, f.value_prev] for f in q(FeatureUsage)])
    n["usage.csv"] = _write(out, "usage.csv", ["account_name", "logins", "logins_prev", "last_login"],
                            [[names[u.account_id], u.logins, u.logins_prev, u.last_login.isoformat() if u.last_login else ""] for u in q(UsageStat)])
    return n
