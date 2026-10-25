"""Read side: assembles accounts, scores, evidence and actions into what the screens need."""
from typing import Optional
import datetime as dt
from collections import defaultdict

from sqlalchemy import select

from .engine import scoring
from .models import (Reassurance, Account, ActivityPoint, Brief, Contract, Conversation, FeatureUsage, Invoice, Signal, Ticket,
                     UsageStat)
from .packs import load_pack


def _signal_dict(s: Signal, conv: Conversation) -> dict:
    return {"id": s.id, "signal_type": s.signal_type, "speaker": s.speaker, "confidence": s.confidence,
            "quote": s.quote, "source": s.source, "feedback": s.feedback, "conversation_id": s.conversation_id,
            "date": conv.date.isoformat(), "title": conv.title}


def _contract_dict(c: Contract) -> dict:
    return {"plan": c.plan, "capacity": c.capacity, "capacity_prev": c.capacity_prev, "monthly_value": c.monthly_value,
            "annual_value": c.monthly_value * 12, "renewal_date": c.renewal_date.isoformat(),
            "billing_name": c.billing_name, "match_confidence": c.match_confidence}


def _account_dict(a: Account) -> dict:
    return {"id": a.id, "name": a.name, "segment": a.segment, "employees": a.employees,
            "contact_name": a.contact_name, "contact_role": a.contact_role, "owner": a.owner}


def contexts(session, client_id: str, window: Optional[int] = None, today: Optional[dt.date] = None,
             include_pending: bool = False) -> list[dict]:
    """One context per account with a matched contract: account + contract + signals + score."""
    from .models import Client
    client = session.get(Client, client_id)
    pack = load_pack(client.pack_id)
    from .models import PENDING_EMPLOYEES, PENDING_KIND
    accounts = {a.id: a for a in session.scalars(select(Account).where(Account.client_id == client_id))
                if include_pending or a.employees != PENDING_EMPLOYEES}
    contracts = {c.account_id: c for c in session.scalars(
        select(Contract).where(Contract.client_id == client_id, Contract.account_id.is_not(None)))}
    activity = defaultdict(list)
    for p in session.scalars(select(ActivityPoint).where(ActivityPoint.client_id == client_id).order_by(ActivityPoint.day)):
        activity[p.account_id].append(p.value)
    convs = {c.id: c for c in session.scalars(select(Conversation).where(Conversation.client_id == client_id))}
    signals = defaultdict(list)
    for s in session.scalars(select(Signal).where(Signal.client_id == client_id)):
        if include_pending or convs[s.conversation_id].kind != PENDING_KIND:
            signals[s.account_id].append(s)

    positives = defaultdict(list)
    for r in session.scalars(select(Reassurance).where(Reassurance.client_id == client_id)):
        if r.conversation_id in convs and (include_pending or convs[r.conversation_id].kind != PENDING_KIND):
            positives[r.account_id].append({"id": r.id, "quote": r.quote, "speaker": r.speaker, "conversation_id": r.conversation_id,
                                            "date": convs[r.conversation_id].date.isoformat(), "title": convs[r.conversation_id].title})
    tickets, invoices = defaultdict(list), defaultdict(list)
    for t in session.scalars(select(Ticket).where(Ticket.client_id == client_id)):
        tickets[t.account_id].append(t)
    for i in session.scalars(select(Invoice).where(Invoice.client_id == client_id)):
        invoices[i.account_id].append(i)

    out = []
    for aid, acc in accounts.items():
        c = contracts.get(aid)
        if c is None:
            continue
        sc = scoring.score(c, activity[aid], signals[aid], pack, today, tickets[aid], invoices[aid], len(positives[aid]))
        if window is not None and not (0 <= sc["days_to_renewal"] <= window):
            continue
        sig = sorted((_signal_dict(s, convs[s.conversation_id]) for s in signals[aid]), key=lambda x: x["date"], reverse=True)
        out.append({"account": _account_dict(acc), "contract": _contract_dict(c), "score": sc, "signals": sig,
                    "positives": sorted(positives[aid], key=lambda x: x["date"], reverse=True)})
    return sorted(out, key=lambda x: (-x["score"]["score"], x["score"]["days_to_renewal"]))


def with_sources(session, client_id: str, ctx: dict, pack: dict) -> dict:
    """Attach usage, support and commercial evidence so briefs and plans can use every source."""
    ctx["sources"] = account_sources(session, client_id, ctx["account"]["id"], pack, ctx)
    return ctx


def context(session, client_id: str, account_id: int) -> Optional[dict]:
    return next((c for c in contexts(session, client_id) if c["account"]["id"] == account_id), None)


def stored_brief(session, account_id: int) -> tuple[Optional[dict], Optional[str]]:
    b = session.get(Brief, account_id)
    return (b.payload, b.source) if b else (None, None)


# ------------------------------------------------------------------ other data sources (usage, support, commercial)
def _pct(now: float, before: float) -> Optional[float]:
    return round((now - before) / before, 3) if before else None


def account_sources(session, client_id: str, account_id: int, pack: dict, ctx: dict) -> dict:
    """Everything we know about one account, grouped by source. Empty groups mean that source is not connected."""
    from .connectors import demo_sources
    cfg = demo_sources.load_cfg(pack["id"]) if (demo_sources.DIR / f"{pack['id']}.yaml").exists() else None
    today = dt.date.today()
    labels = (cfg or {}).get("labels", {})

    us = session.get(UsageStat, account_id)
    feats = session.scalars(select(FeatureUsage).where(FeatureUsage.account_id == account_id)).all()
    usage = None
    if us is not None:
        usage = {"metric": us.metric, "metric_prev": us.metric_prev, "metric_pct": _pct(us.metric, us.metric_prev),
                 "utilization": us.utilization, "logins": us.logins, "logins_prev": us.logins_prev,
                 "logins_pct": _pct(us.logins, us.logins_prev),
                 "last_login": us.last_login.isoformat() if us.last_login else None,
                 "days_since_login": (today - us.last_login).days if us.last_login else None,
                 "features_used": sum(1 for f in feats if f.value > 0), "features_total": len(feats),
                 "features": sorted(({"name": f.feature, "value": f.value, "prev": f.value_prev, "pct": _pct(f.value, f.value_prev)}
                                     for f in feats), key=lambda f: (f["pct"] if f["pct"] is not None else 0))}

    tickets = session.scalars(select(Ticket).where(Ticket.account_id == account_id).order_by(Ticket.opened.desc())).all()
    unresolved = [t for t in tickets if t.status in ("open", "pending")]
    rank = {"high": 0, "normal": 1, "low": 2}
    support = None
    if tickets:
        shown = sorted(tickets, key=lambda t: (t.status == "solved", rank.get(t.priority, 1), -t.opened.toordinal()))[:5]
        support = {"total": len(tickets), "unresolved": len(unresolved),
                   "high_priority": sum(1 for t in unresolved if t.priority == "high"),
                   "oldest_open_days": max(((today - t.opened).days for t in unresolved), default=0),
                   "items": [{"id": t.id, "subject": t.subject, "status": t.status, "priority": t.priority, "category": t.category,
                              "opened": t.opened.isoformat(), "age_days": (today - t.opened).days,
                              "idle_days": (today - t.last_update).days} for t in shown]}

    invs = session.scalars(select(Invoice).where(Invoice.account_id == account_id).order_by(Invoice.issued.desc())).all()

    def inv_status(i: Invoice) -> tuple[str, int]:
        if i.paid_on is None:
            return ("overdue", (today - i.due).days) if i.due < today else ("open", 0)
        return ("paid_late", (i.paid_on - i.due).days) if i.paid_on > i.due else ("paid", 0)

    rows = [{"number": i.number, "issued": i.issued.isoformat(), "due": i.due.isoformat(), "amount": i.amount,
             "paid_on": i.paid_on.isoformat() if i.paid_on else None, "status": inv_status(i)[0], "days": inv_status(i)[1]} for i in invs]
    c = ctx["contract"]
    commercial = {"annual_value": c["annual_value"], "monthly_value": c["monthly_value"], "plan": c["plan"],
                  "seats": c["capacity"], "seats_prev": c["capacity_prev"], "renewal_date": c["renewal_date"],
                  "days_to_renewal": ctx["score"]["days_to_renewal"], "invoices": rows,
                  "overdue": sum(1 for r in rows if r["status"] == "overdue"),
                  "overdue_amount": sum(r["amount"] for r in rows if r["status"] == "overdue"),
                  "paid_late": sum(1 for r in rows if r["status"] == "paid_late")}

    convs = session.scalars(select(Conversation).where(Conversation.account_id == account_id).order_by(Conversation.date.desc())).all()
    conversations = {"count": len(convs), "last": convs[0].date.isoformat() if convs else None,
                     "signals": list(dict.fromkeys(pack["signals"][s["signal_type"]]["label"] for s in ctx["signals"]
                                                   if s["feedback"] != "dismissed"))}
    return {"labels": labels, "usage": usage, "conversations": conversations, "support": support, "commercial": commercial}


def sources_overview(session, client_id: str, pack: dict) -> dict:
    """The Data sources screen: what each source provides, how it connects, and how much we hold."""
    from sqlalchemy import func
    from .connectors import demo_sources
    from .pipeline import DEMO_CLIENTS
    cfg = demo_sources.load_cfg(pack["id"])
    n = lambda model, *where: session.scalar(select(func.count()).select_from(model).where(model.client_id == client_id, *where)) or 0   # noqa: E731
    today = dt.date.today()
    n_overdue = n(Invoice, Invoice.paid_on.is_(None), Invoice.due < today)
    counts = {
        "usage": [f"{n(UsageStat)} accounts", f"{n(ActivityPoint)} daily readings", f"{n(FeatureUsage)} feature readings"],
        "conversations": [f"{n(Conversation)} transcripts"],
        "support": [f"{n(Ticket)} tickets", f"{n(Ticket, Ticket.status != 'solved')} unresolved"],
        "commercial": [f"{n(Contract)} contracts", f"{n(Invoice)} invoices", f"{n_overdue} overdue"],
    }
    demo = client_id in {d["id"] for d in DEMO_CLIENTS}
    return {"labels": cfg["labels"], "demo": demo,
            "sources": [{"key": k, **cfg["connections"][k], "counts": counts[k],
                         "status": "Sample data" if demo else "Connected by CSV export"} for k in ("usage", "conversations", "support", "commercial")],
            "files": [
                {"file": "accounts.csv", "holds": "One row per customer", "columns": "name, segment, employees, contact_name, contact_role, owner"},
                {"file": "contracts.csv", "holds": "Renewals, ARR, seats", "columns": "billing_name, plan, capacity, capacity_prev, monthly_value, renewal_date"},
                {"file": "activity.csv", "holds": "Daily usage", "columns": "account_name, day, value"},
                {"file": "usage.csv", "holds": "Logins", "columns": "account_name, logins, logins_prev, last_login"},
                {"file": "features.csv", "holds": "Features used", "columns": "account_name, feature, value, value_prev"},
                {"file": "conversations.csv", "holds": "Call transcripts", "columns": "account_name, date, title, transcript"},
                {"file": "tickets.csv", "holds": "Support tickets", "columns": "account_name, opened, last_update, status, priority, category, subject"},
                {"file": "invoices.csv", "holds": "Invoices and payments", "columns": "account_name, number, issued, due, amount, paid_on"},
            ]}
