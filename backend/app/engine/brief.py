"""Evidence-cited briefs. The LLM only sees numbered evidence and must cite an id in every sentence;
a brief with a missing or unknown citation fails validation and falls back to a template."""
from . import llm

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["sentences", "next_step"],
    "properties": {
        "sentences": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "evidence"],
            "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "next_step": {"type": "object", "additionalProperties": False, "required": ["text", "evidence"],
                      "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}},
    },
}


def build_evidence(ctx: dict, pack: dict) -> list[dict]:
    v, ev = pack["vocabulary"], []
    sigs = sorted([s for s in ctx["signals"] if s["feedback"] != "dismissed"],
                  key=lambda s: -pack["signals"][s["signal_type"]]["weight"] * s["confidence"])
    for s in sigs:
        ev.append({"id": f"E{len(ev) + 1}", "kind": "signal", "signal_id": s["id"], "signal_type": s["signal_type"],
                   "label": pack["signals"][s["signal_type"]]["label"], "quote": s["quote"], "speaker": s["speaker"],
                   "date": s["date"], "title": s["title"], "conversation_id": s["conversation_id"],
                   "text": f'{pack["signals"][s["signal_type"]]["label"]}: "{s["quote"]}" ({s["speaker"]}, {s["title"]}, {s["date"]})'})
    sc, c = ctx["score"], ctx["contract"]
    if sc["activity_pct"] <= -0.08:
        ev.append({"id": f"E{len(ev) + 1}", "kind": "activity",
                   "text": f"{v['activity']} down {abs(sc['activity_pct']):.0%} over the last 14 days vs. the earlier baseline."})
    elif sc["activity_pct"] >= 0.03:
        ev.append({"id": f"E{len(ev) + 1}", "kind": "activity",
                   "text": f"{v['activity']} up {sc['activity_pct']:.0%} over the last 14 days vs. the earlier baseline."})
    if c["capacity_prev"] > c["capacity"]:
        ev.append({"id": f"E{len(ev) + 1}", "kind": "capacity",
                   "text": f"{v['capacity']} reduced from {c['capacity_prev']} to {c['capacity']}."})
    ev.append({"id": f"E{len(ev) + 1}", "kind": "renewal",
               "text": f"{v['renewal']} on {c['renewal_date']} ({sc['days_to_renewal']} days), €{c['monthly_value'] * 12:,.0f} per year."})
    return ev


def validate(payload: dict, ids: set) -> bool:
    items = payload.get("sentences", []) + [payload.get("next_step", {})]
    return bool(payload.get("sentences")) and all(
        it.get("text", "").strip() and it.get("evidence") and set(it["evidence"]) <= ids for it in items)


def template(ctx: dict, ev: list[dict], pack: dict) -> dict:
    v = pack["vocabulary"]
    by_kind = {e["kind"]: e for e in ev}
    sigs = [e for e in ev if e["kind"] == "signal"]
    sc = ctx["score"]
    out = [{"text": f"{ctx['account']['name']} comes up for {v['renewal'].lower()} in {sc['days_to_renewal']} days "
                    f"and is rated {sc['band']} risk.", "evidence": [by_kind["renewal"]["id"]]}]
    for e in sigs[:3]:
        out.append({"text": f"{e['label']}: {e['speaker']} raised it in the {e['title']} on {e['date']}.",
                    "evidence": [e["id"]]})
    for kind in ("activity", "capacity"):
        if kind in by_kind:
            out.append({"text": by_kind[kind]["text"], "evidence": [by_kind[kind]["id"]]})
    if sigs:
        nxt = {"text": pack["signals"][sigs[0]["signal_type"]]["playbook"]["title"].format(
            account=ctx["account"]["name"], contact_first=ctx["account"]["contact_name"].split()[0]) + ".",
            "evidence": [sigs[0]["id"]]}
    elif "activity" in by_kind and sc["activity_pct"] < 0:
        nxt = {"text": "Ask which workflows the team stopped using and offer a short re-onboarding.",
               "evidence": [by_kind["activity"]["id"]]}
    else:
        nxt = {"text": "Send the renewal paperwork early and ask for a reference or case study.",
               "evidence": [by_kind["renewal"]["id"]]}
    return {"sentences": out, "next_step": nxt}


def make(ctx: dict, pack: dict) -> tuple[dict, str]:
    ev = build_evidence(ctx, pack)
    if llm.enabled():
        try:
            v = pack["vocabulary"]
            system = (f"You write {v['renewal'].lower()}-prep briefs for a {v['owner_role']}. Use ONLY the numbered evidence. "
                      "Write 2-4 short sentences explaining the risk (or why the account looks healthy), then one concrete "
                      "next step. Every sentence and the next step must cite at least one evidence id like E1. Never invent "
                      "facts, numbers or names not in the evidence. Plain, direct language.")
            user = (f"{v['account']}: {ctx['account']['name']} (risk {ctx['score']['score']}/100, {ctx['score']['band']})\n"
                    "Evidence:\n" + "\n".join(f"{e['id']}: {e['text']}" for e in ev))
            payload = llm.chat_json(system, user, SCHEMA, "renewal_brief", temperature=0.2)
            if validate(payload, {e["id"] for e in ev}):
                return {"evidence": ev, "sentences": payload["sentences"], "next_step": payload["next_step"]}, "llm"
        except Exception as e:  # noqa: BLE001
            llm.record_failure()
            print("  AI brief failed, using the template for this account:", str(e)[:160])
    return {"evidence": ev, **template(ctx, ev, pack)}, "template"
