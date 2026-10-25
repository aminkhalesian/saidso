"""Run the engine for one client: sync -> extract -> briefs -> draft actions."""
from typing import Optional
import datetime as dt

from sqlalchemy import delete

from . import service
from .engine import actions, brief, extract, llm
from .models import Brief, Client, SessionLocal, init_db
from .packs import load_pack

DEMO_CLIENTS = [
    {"id": "brightdesk", "name": "Brightdesk", "pack_id": "saas", "user_name": "Lena Vogt"},
    {"id": "kranich", "name": "Kranich Studio", "pack_id": "agency", "user_name": "Marta Lewandowska"},
]


def build_outputs(session, client: Client, window: int = 90, llm_emails: bool = False) -> dict:
    pack = load_pack(client.pack_id)
    session.execute(delete(Brief).where(Brief.client_id == client.id))
    n_actions = 0
    ctxs = service.contexts(session, client.id, window=window)
    if llm.enabled():
        print(f"  {client.name}: writing {len(ctxs)} briefs with the AI…")
    for ctx in ctxs:
        service.with_sources(session, client.id, ctx, pack)
        payload, source = brief.make(ctx, pack)
        session.add(Brief(account_id=ctx["account"]["id"], client_id=client.id, payload=payload, source=source,
                          created_at=dt.datetime.now()))
        if brief.wants_plan(ctx):
            n_actions += actions.draft_for(session, client.id, ctx, pack, use_llm_emails=llm_emails, plan=payload.get("plan"), plan_source=payload.get("plan_source", "template"))
    session.commit()
    return {"actions": n_actions}


def rebuild_actions(session, client: Client, window: int = 90, llm_emails: bool = False) -> dict:
    """Redraft next steps from the current playbooks without re-reading any call. Signals, scores and briefs
    stay as they are; drafts are replaced, approved and dismissed actions are kept."""
    pack = load_pack(client.pack_id)
    n = 0
    for ctx in service.contexts(session, client.id, window=window):
        if brief.wants_plan(ctx):
            payload, _ = service.stored_brief(session, ctx["account"]["id"])
            if payload is None or "plan" not in payload:           # an older brief: write a fresh one
                service.with_sources(session, client.id, ctx, pack)
                payload, source = brief.make(ctx, pack)
                b = session.get(Brief, ctx["account"]["id"])
                if b:
                    b.payload, b.source = payload, source
                else:
                    session.add(Brief(account_id=ctx["account"]["id"], client_id=client.id, payload=payload, source=source))
            n += actions.draft_for(session, client.id, ctx, pack, use_llm_emails=llm_emails, plan=payload.get("plan"), plan_source=payload.get("plan_source", "template"))
    session.commit()
    return {"actions": n}


def run_client(session, client: Client, connector, use_llm: Optional[bool] = None, llm_emails: bool = False) -> dict:
    pack = load_pack(client.pack_id)
    summary = connector.sync(session, client, pack)
    summary["signals"] = extract.run(session, client, pack, use_llm=use_llm)
    if connector.name == "synthetic":                       # usage, tickets and invoices that match each account's story
        from .connectors import demo_sources
        summary.update(demo_sources.add_sources(session, client, pack))
    summary.update(build_outputs(session, client, llm_emails=llm_emails))
    return summary


def seed(llm_transcripts: bool = False, llm_emails: bool = False, seed_value: int = 7):
    from .connectors.synthetic import SyntheticConnector
    from .engine.evaluate import evaluate
    init_db(drop=True)
    with SessionLocal() as s:
        for c in DEMO_CLIENTS:
            client = Client(**c)
            s.add(client)
            s.commit()
            summary = run_client(s, client, SyntheticConnector(seed=seed_value, llm_transcripts=llm_transcripts),
                                 llm_emails=llm_emails)
            r = evaluate(s, client.id, load_pack(client.pack_id))
            print(f"[{client.name} · {client.pack_id}] {summary} | {r['source']}: precision {r['precision']:.0%}, "
                  f"recall {r['recall']:.0%}, decoys resisted {r['decoys_resisted']}/{r['decoys']}")
    if llm.USAGE["calls"]:
        print("LLM usage:", llm.usage_summary())
