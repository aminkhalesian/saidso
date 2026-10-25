"""Read side: assembles accounts, scores, evidence and actions into what the screens need."""
from typing import Optional
import datetime as dt
from collections import defaultdict

from sqlalchemy import select

from .engine import scoring
from .models import Account, ActivityPoint, Brief, Contract, Conversation, Signal
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


def contexts(session, client_id: str, window: Optional[int] = None, today: Optional[dt.date] = None) -> list[dict]:
    """One context per account with a matched contract: account + contract + signals + score."""
    from .models import Client
    client = session.get(Client, client_id)
    pack = load_pack(client.pack_id)
    accounts = {a.id: a for a in session.scalars(select(Account).where(Account.client_id == client_id))}
    contracts = {c.account_id: c for c in session.scalars(
        select(Contract).where(Contract.client_id == client_id, Contract.account_id.is_not(None)))}
    activity = defaultdict(list)
    for p in session.scalars(select(ActivityPoint).where(ActivityPoint.client_id == client_id).order_by(ActivityPoint.day)):
        activity[p.account_id].append(p.value)
    convs = {c.id: c for c in session.scalars(select(Conversation).where(Conversation.client_id == client_id))}
    signals = defaultdict(list)
    for s in session.scalars(select(Signal).where(Signal.client_id == client_id)):
        signals[s.account_id].append(s)

    out = []
    for aid, acc in accounts.items():
        c = contracts.get(aid)
        if c is None:
            continue
        sc = scoring.score(c, activity[aid], signals[aid], pack, today)
        if window is not None and not (0 <= sc["days_to_renewal"] <= window):
            continue
        sig = sorted((_signal_dict(s, convs[s.conversation_id]) for s in signals[aid]), key=lambda x: x["date"], reverse=True)
        out.append({"account": _account_dict(acc), "contract": _contract_dict(c), "score": sc, "signals": sig})
    return sorted(out, key=lambda x: (-x["score"]["score"], x["score"]["days_to_renewal"]))


def context(session, client_id: str, account_id: int) -> Optional[dict]:
    return next((c for c in contexts(session, client_id) if c["account"]["id"] == account_id), None)


def stored_brief(session, account_id: int) -> tuple[Optional[dict], Optional[str]]:
    b = session.get(Brief, account_id)
    return (b.payload, b.source) if b else (None, None)
