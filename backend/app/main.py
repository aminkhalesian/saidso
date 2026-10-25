"""HTTP API. Run: uvicorn app.main:app --reload   (serves the built frontend at / when frontend/dist exists)"""
from typing import Optional
import datetime as dt
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from . import pipeline, service
from .engine import actions as actions_mod
from .engine import brief as brief_mod
from .engine import extract, llm
from .engine.evaluate import evaluate
from .models import Action, Brief, Client, Conversation, SessionLocal, Signal, init_db
from .packs import load_pack, public_view

app = FastAPI(title="Renewal Radar API", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
init_db()


def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def get_client(client_id: str, session) -> tuple[Client, dict]:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(404, f"unknown client {client_id}")
    return client, load_pack(client.pack_id)


def action_dict(a: Action) -> dict:
    return {"id": a.id, "account_id": a.account_id, "signal_type": a.signal_type, "kind": a.kind, "title": a.title,
            "body": a.body, "status": a.status, "source": a.source,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None}


def brief_for(session, client_id: str, ctx, pack) -> tuple[dict, str]:
    payload, source = service.stored_brief(session, ctx["account"]["id"])
    if payload is None:
        service.with_sources(session, client_id, ctx, pack)
        payload, source = brief_mod.make(ctx, pack)
        session.add(Brief(account_id=ctx["account"]["id"], client_id=client_id, payload=payload, source=source))
        session.commit()
    return payload, source


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.enabled(), "model": llm.MODEL if llm.enabled() else "offline rules"}


@app.get("/api/clients")
def clients(session=Depends(db)):
    out = []
    for c in session.scalars(select(Client)):
        out.append({"id": c.id, "name": c.name, "user_name": c.user_name, "pack": public_view(load_pack(c.pack_id))})
    return out


# ------------------------------------------------------------------ CSM: my week + renewals
@app.get("/api/clients/{client_id}/overview")
def overview(client_id: str, window: int = 90, session=Depends(db)):
    client, pack = get_client(client_id, session)
    ctxs = service.contexts(session, client_id, window=window)
    drafts = defaultdict(list)
    for a in session.scalars(select(Action).where(Action.client_id == client_id, Action.status == "draft")):
        drafts[a.account_id].append(action_dict(a))
    high = [c for c in ctxs if c["score"]["band"] == "high"]
    week = []
    for c in ctxs:
        aid = c["account"]["id"]
        if c["score"]["band"] == "low" or not drafts[aid]:
            continue
        payload, _ = brief_for(session, client_id, c, pack)
        top = next((e for e in payload["evidence"] if e["kind"] == "signal"),
                   next((e for e in payload["evidence"] if e["kind"] in ("activity", "capacity")), None))
        week.append({**summary_row(c, pack), "reason": top, "action": drafts[aid][0], "more_actions": len(drafts[aid]) - 1})
        if len(week) == 4:
            break
    done = session.scalars(select(Action).where(Action.client_id == client_id, Action.status != "draft")).all()
    return {
        "client": {"id": client.id, "name": client.name, "user_name": client.user_name},
        "kpis": {"renewals": len(ctxs), "high_risk": len(high),
                 "value_at_risk": sum(c["contract"]["annual_value"] for c in high),
                 "total_value": sum(c["contract"]["annual_value"] for c in ctxs),
                 "signals": sum(len(c["signals"]) for c in ctxs),
                 "open_actions": sum(len(v) for v in drafts.values()),
                 "decided_actions": len(done)},
        "this_week": week,
        "renewals": [summary_row(c, pack) for c in ctxs],
    }


def summary_row(c: dict, pack: dict) -> dict:
    labels = list(dict.fromkeys(pack["signals"][s["signal_type"]]["label"] for s in c["signals"] if s["feedback"] != "dismissed"))
    return {"account_id": c["account"]["id"], "name": c["account"]["name"], "segment": c["account"]["segment"],
            "score": c["score"]["score"], "band": c["score"]["band"], "days_to_renewal": c["score"]["days_to_renewal"],
            "renewal_date": c["contract"]["renewal_date"], "annual_value": c["contract"]["annual_value"],
            "activity_pct": c["score"]["activity_pct"], "usage_known": c["score"].get("usage_known", True), "signals": labels}


# ------------------------------------------------------------------ account detail
@app.get("/api/clients/{client_id}/accounts/{account_id}")
def account(client_id: str, account_id: int, session=Depends(db)):
    client, pack = get_client(client_id, session)
    ctx = service.context(session, client_id, account_id)
    if ctx is None:
        raise HTTPException(404, "account not found")
    payload, source = brief_for(session, client_id, ctx, pack)
    from .models import ActivityPoint
    act = session.scalars(select(ActivityPoint).where(ActivityPoint.account_id == account_id).order_by(ActivityPoint.day)).all()
    convs = session.scalars(select(Conversation).where(Conversation.account_id == account_id).order_by(Conversation.date.desc())).all()
    acts = session.scalars(select(Action).where(Action.account_id == account_id).order_by(Action.id)).all()
    timeline = [{"date": c.date.isoformat(), "kind": "conversation", "title": c.title, "conversation_id": c.id,
                 "signals": [pack["signals"][s["signal_type"]]["label"] for s in ctx["signals"] if s["conversation_id"] == c.id]}
                for c in convs]
    if ctx["contract"]["capacity_prev"] != ctx["contract"]["capacity"]:
        timeline.append({"date": (dt.date.today() - dt.timedelta(days=40)).isoformat(), "kind": "capacity",
                         "title": f"{pack['vocabulary']['capacity']}: {ctx['contract']['capacity_prev']} → {ctx['contract']['capacity']}"})
    timeline.append({"date": ctx["contract"]["renewal_date"], "kind": "renewal", "title": pack["vocabulary"]["renewal"]})
    timeline.sort(key=lambda t: t["date"], reverse=True)
    service.with_sources(session, client_id, ctx, pack)
    fresh = brief_mod.fingerprint(ctx, brief_mod.build_evidence(ctx, pack))
    return {**ctx, "brief": payload, "brief_source": source,
            "brief_stale": bool(payload.get("fingerprint")) and payload["fingerprint"] != fresh,
            "activity": [{"day": p.day.isoformat(), "value": p.value} for p in act],
            "conversations": [{"id": c.id, "date": c.date.isoformat(), "title": c.title, "transcript": c.transcript} for c in convs],
            "actions": [action_dict(a) for a in acts], "timeline": timeline,
            "sources": ctx["sources"]}


# ------------------------------------------------------------------ write side: people stay in control
class ActionUpdate(BaseModel):
    status: str
    body: Optional[str] = None


@app.post("/api/clients/{client_id}/actions/{action_id}")
def update_action(client_id: str, action_id: int, upd: ActionUpdate, session=Depends(db)):
    a = session.get(Action, action_id)
    if a is None or a.client_id != client_id:                 # another client's action is "not found", never editable
        raise HTTPException(404)
    if upd.status not in {"approved", "dismissed", "draft"}:
        raise HTTPException(422, "status must be approved, dismissed or draft")
    if upd.body is not None:
        a.body = upd.body
    a.status = upd.status
    a.decided_at = dt.datetime.now() if upd.status != "draft" else None
    session.commit()
    return action_dict(a)


class Feedback(BaseModel):
    feedback: str


@app.post("/api/clients/{client_id}/signals/{signal_id}/feedback")
def signal_feedback(client_id: str, signal_id: int, fb: Feedback, session=Depends(db)):
    s = session.get(Signal, signal_id)
    if s is None or s.client_id != client_id:
        raise HTTPException(404)
    if fb.feedback not in {"confirmed", "dismissed", "open"}:
        raise HTTPException(422, "feedback must be confirmed, dismissed or open")
    s.feedback = fb.feedback
    session.commit()
    client, pack = get_client(s.client_id, session)
    ctx = service.context(session, s.client_id, s.account_id)
    if ctx:  # a dismissed flag changes the score, the brief and the drafted actions
        service.with_sources(session, s.client_id, ctx, pack)
        payload, source = brief_mod.make(ctx, pack)
        b = session.get(Brief, s.account_id)
        if b:
            b.payload, b.source = payload, source
        actions_mod.draft_for(session, s.client_id, ctx, pack, plan=payload.get("plan"), plan_source=payload.get("plan_source", "template"))
        session.commit()
    return {"id": s.id, "feedback": s.feedback}


# ------------------------------------------------------------------ RevOps: portfolio
@app.get("/api/clients/{client_id}/portfolio")
def portfolio(client_id: str, window: int = 180, session=Depends(db)):
    client, pack = get_client(client_id, session)
    ctxs = service.contexts(session, client_id, window=window)
    by_segment, by_signal, by_month = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: {"count": 0, "value": 0.0}), defaultdict(lambda: defaultdict(float))
    for c in ctxs:
        val, b = c["contract"]["annual_value"], c["score"]["band"]
        by_segment[c["account"]["segment"]][b] += val
        by_month[c["contract"]["renewal_date"][:7]][b] += val
        for t in {s["signal_type"] for s in c["signals"] if s["feedback"] != "dismissed"}:
            by_signal[t]["count"] += 1
            by_signal[t]["value"] += val
    def rows(d):
        return [{"key": k, "high": v.get("high", 0), "medium": v.get("medium", 0), "low": v.get("low", 0)} for k, v in d.items()]
    return {
        "segments": sorted(rows(by_segment), key=lambda r: -(r["high"] + r["medium"])),
        "months": sorted(rows(by_month), key=lambda r: r["key"]),
        "drivers": sorted([{"signal_type": t, "label": pack["signals"][t]["label"], **v} for t, v in by_signal.items()],
                          key=lambda r: -r["value"]),
        "total_value": sum(c["contract"]["annual_value"] for c in ctxs),
        "at_risk_value": sum(c["contract"]["annual_value"] for c in ctxs if c["score"]["band"] == "high"),
        "accounts": len(ctxs),
    }


# ------------------------------------------------------------------ data sources
@app.get("/api/clients/{client_id}/sources")
def sources(client_id: str, session=Depends(db)):
    client, pack = get_client(client_id, session)
    return service.sources_overview(session, client_id, pack)


# ------------------------------------------------------------------ trust
@app.get("/api/clients/{client_id}/trust")
def trust(client_id: str, session=Depends(db)):
    client, pack = get_client(client_id, session)
    n_conv = len(session.scalars(select(Conversation.id).where(Conversation.client_id == client_id)).all())
    return {**evaluate(session, client_id, pack), "conversations": n_conv, "pack": pack["name"],
            "model": llm.MODEL if llm.enabled() else "offline rules"}


# ------------------------------------------------------------------ live: analyze a new conversation
class AnalyzeIn(BaseModel):
    transcript: str


@app.post("/api/clients/{client_id}/analyze")
def analyze(client_id: str, body: AnalyzeIn, session=Depends(db)):
    client, pack = get_client(client_id, session)
    if len(body.transcript) > 20000:
        raise HTTPException(413, "transcript too long for the demo (max 20,000 characters)")
    sigs, source = extract.analyze(body.transcript, pack, pack["synthetic"]["product"], extract.staff_label(pack))
    for s in sigs:
        s["label"] = pack["signals"][s["signal_type"]]["label"]
        s["playbook"] = pack["signals"][s["signal_type"]]["playbook"]["title"].format(
            account="this account", contact_first="the customer")
    return {"signals": sigs, "source": source, "turns": len(extract.parse_turns(body.transcript, extract.staff_label(pack)))}


@app.get("/api/clients/{client_id}/sample-transcript")
def sample_transcript(client_id: str, session=Depends(db)):
    client, pack = get_client(client_id, session)
    syn, staff = pack["synthetic"], extract.staff_label(pack)
    first, second = list(pack["signals"])[:2]
    fill = {"co": "Northwind", "nxt": "Sam Keller", "capacity": 40, **{k: v[0] for k, v in syn.get("fill", {}).items()}}
    cust = "Priya Raman (Operations Lead, Northwind)"
    lines = [f"{client.user_name} ({staff}): {syn['owner_open'][0]}",
             f"{cust}: {syn['neutral'][0]}",
             f"{client.user_name} ({staff}): {syn['owner_mid'][0]}",
             f"{cust}: {syn['signal_lines'][first][0].format(**fill)}",
             f"{client.user_name} ({staff}): {syn['owner_mid'][3]}",
             f"{cust}: {next(iter(syn['decoys'].values())).format(**fill)}",
             f"{client.user_name} ({staff}): {syn['owner_mid'][2]}",
             f"{cust}: {syn['signal_lines'][second][1].format(**fill)}",
             f"{client.user_name} ({staff}): {syn['owner_close'][0]}"]
    return {"transcript": "\n".join(lines)}


@app.post("/api/admin/reseed")
def reseed():
    """Reset the demo data (no LLM calls unless a key is configured)."""
    pipeline.seed()
    return {"ok": True}


# ------------------------------------------------------------------ frontend
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = DIST / path
        return FileResponse(target if path and target.is_file() else DIST / "index.html")
