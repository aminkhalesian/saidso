"""Evidence-cited briefs and retention plans, built from every source we have for one account.

The LLM only sees numbered evidence and must cite ids for every statement. A reply with a missing or unknown
citation, a number that is not in the evidence, or a churn probability fails validation, and the account falls back to
a template built from the same evidence. Nothing here is sent anywhere: a CSM approves every customer-facing action."""
import re

from . import llm

CITED = {"type": "object", "additionalProperties": False, "required": ["text", "evidence"],
         "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}
DRIVER = {"type": "object", "additionalProperties": False, "required": ["title", "why_it_matters", "evidence"],
          "properties": {"title": {"type": "string"}, "why_it_matters": {"type": "string"},
                         "evidence": {"type": "array", "items": {"type": "string"}}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["sentences", "next_step", "drivers", "reassuring", "assessment"],
    "properties": {"sentences": {"type": "array", "items": CITED}, "next_step": CITED,
                   "drivers": {"type": "array", "items": DRIVER}, "reassuring": {"type": "array", "items": CITED},
                   "assessment": CITED},
}
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["problem", "objective", "questions", "interventions", "followup"],
    "properties": {"problem": CITED, "objective": CITED, "questions": {"type": "array", "items": CITED},
                   "interventions": {"type": "array", "items": CITED}, "followup": CITED},
}


# ------------------------------------------------------------------ evidence
def _add(ev: list, kind: str, text: str, polarity: str, label: str, **extra) -> dict:
    e = {"id": f"E{len(ev) + 1}", "kind": kind, "polarity": polarity, "label": label, "text": text, **extra}
    ev.append(e)
    return e


def build_evidence(ctx: dict, pack: dict) -> list[dict]:
    """Numbered facts about one account: what customers said, usage, support, invoices, contract. Each is marked
    as a risk, reassuring or neutral so a brief can show both sides."""
    v, ev = pack["vocabulary"], []
    sigs = sorted([s for s in ctx["signals"] if s["feedback"] != "dismissed"],
                  key=lambda s: -pack["signals"][s["signal_type"]]["weight"] * s["confidence"])
    for s in sigs:
        label = pack["signals"][s["signal_type"]]["label"]
        _add(ev, "signal", f'{label}: "{s["quote"]}" ({s["speaker"]}, {s["title"]}, {s["date"]})', "risk", label,
             signal_id=s["id"], signal_type=s["signal_type"], quote=s["quote"], speaker=s["speaker"], date=s["date"],
             title=s["title"], conversation_id=s["conversation_id"])
    for r in ctx.get("positives", []):
        _add(ev, "positive_quote", f'Reassuring: "{r["quote"]}" ({r["speaker"]}, {r["title"]}, {r["date"]})', "reassuring",
             "Customer reassurance", quote=r["quote"], speaker=r["speaker"], date=r["date"], title=r["title"],
             conversation_id=r["conversation_id"])
    sc, c = ctx["score"], ctx["contract"]
    if not sc.get("usage_known", True):
        _add(ev, "usage_unknown", f"No usable {v['activity'].lower()} data for this account, so usage is not part of the score.",
             "neutral", v["activity"])
    elif sc["activity_pct"] <= -0.08:
        _add(ev, "activity", f"{v['activity']} down {abs(sc['activity_pct']):.0%} over the last 14 days vs. the earlier baseline.",
             "risk", v["activity"], pct=sc["activity_pct"])
    elif sc["activity_pct"] >= 0.03:
        _add(ev, "activity", f"{v['activity']} up {sc['activity_pct']:.0%} over the last 14 days vs. the earlier baseline.",
             "reassuring", v["activity"], pct=sc["activity_pct"])
    if c["capacity_prev"] > c["capacity"]:
        _add(ev, "capacity", f"{v['capacity']} reduced from {c['capacity_prev']} to {c['capacity']}.", "risk", v["capacity"])

    src = ctx.get("sources") or {}
    us, sup, com = src.get("usage"), src.get("support"), src.get("commercial")
    if us:
        for f in [f for f in us["features"] if f["pct"] is not None and f["pct"] <= -0.4 and f["prev"] > 0][:2]:
            _add(ev, "feature", f'Use of "{f["name"]}" down {abs(f["pct"]):.0%} (from {f["prev"]:g} to {f["value"]:g}).',
                 "risk", "Feature use", feature=f["name"], pct=f["pct"])
        if us["features_total"] and us["features_used"] == us["features_total"] and sc["activity_pct"] >= 0:
            _add(ev, "adoption", f"All {us['features_total']} tracked features are in use.", "reassuring", "Feature adoption")
    if sup:
        for t in [t for t in sup["items"] if t["status"] in ("open", "pending")][:3]:
            _add(ev, "ticket", f'Open {t["category"].replace("_", " ")} ticket "{t["subject"]}" '
                               f'({t["priority"]} priority, open {t["age_days"]} days).',
                 "risk" if t["category"] == "complaint" or t["priority"] == "high" else "neutral", "Support ticket",
                 subject=t["subject"], category=t["category"], priority=t["priority"], age_days=t["age_days"])
        if sup["total"] and not sup["unresolved"]:
            _add(ev, "support_ok", f"No unresolved support tickets ({sup['total']} in total, all solved).", "reassuring", "Support")
    if com and com["invoices"]:
        if com["overdue"]:
            od = [i for i in com["invoices"] if i["status"] == "overdue"]
            _add(ev, "invoice", f"{com['overdue']} overdue invoice{'s' if com['overdue'] > 1 else ''} totalling "
                                f"€{com['overdue_amount']:,.0f} (oldest {max(i['days'] for i in od)} days past due).",
                 "risk", "Payment", number=od[0]["number"], count=com["overdue"])
        elif com["paid_late"]:
            _add(ev, "invoice", f"{com['paid_late']} invoice{'s' if com['paid_late'] > 1 else ''} paid late.", "risk", "Payment",
                 count=com["paid_late"])
        else:
            _add(ev, "invoice_ok", f"All {len(com['invoices'])} invoices were paid on time.", "reassuring", "Payment")
    _add(ev, "renewal", f"{v['renewal']} on {c['renewal_date']} ({sc['days_to_renewal']} days), €{c['monthly_value'] * 12:,.0f} per year.",
         "neutral", v["renewal"])
    return ev


# ------------------------------------------------------------------ validation: no invented facts
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BANNED = re.compile(r"probab|likelihood|chance of|odds of", re.I)


def _numbers(text: str) -> set:
    return {n.replace(",", "") for n in _NUM.findall(re.sub(r"\bE\d+\b", "", text))}


def _items(payload: dict) -> list[dict]:
    out = list(payload.get("sentences", [])) + [payload.get("next_step", {}), payload.get("assessment", {})]
    out += payload.get("reassuring", [])
    out += [{"text": d.get("title", "") + " " + d.get("why_it_matters", ""), "evidence": d.get("evidence")} for d in payload.get("drivers", [])]
    return out


def fingerprint(ctx: dict, ev: list[dict]) -> str:
    """Identifies the data a brief was written from. Day counters are left out so a brief does not go stale every midnight."""
    import hashlib
    parts = [ctx["score"]["band"]] + [e["text"] for e in ev if e["kind"] != "renewal"]
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:16]


def validate(payload: dict, ev: list[dict]) -> bool:
    """Every statement cites known evidence, uses only numbers that appear in the evidence, and gives no probability."""
    ids = {e["id"] for e in ev}
    allowed = set().union(*(_numbers(e["text"]) for e in ev)) | _numbers(" ".join(str(e.get("date", "")) for e in ev))
    items = _items(payload)
    if not payload.get("sentences") or not payload.get("assessment", {}).get("text"):
        return False
    return all(it.get("text", "").strip() and it.get("evidence") and set(it["evidence"]) <= ids
               and _numbers(it["text"]) <= allowed and not _BANNED.search(it["text"]) for it in items)


def validate_plan(plan: dict, ev: list[dict]) -> bool:
    ids = {e["id"] for e in ev}
    allowed = set().union(*(_numbers(e["text"]) for e in ev))
    items = [plan.get("problem", {}), plan.get("objective", {}), plan.get("followup", {})] + plan.get("questions", []) + plan.get("interventions", [])
    return (len(plan.get("questions", [])) == 3 and len(plan.get("interventions", [])) == 2 and
            all(it.get("text", "").strip() and it.get("evidence") and set(it["evidence"]) <= ids
                and _numbers(it["text"]) <= allowed and not _BANNED.search(it["text"]) for it in items))


# ------------------------------------------------------------------ template (no AI): same evidence, plain rules
def _risk_drivers(ctx: dict, ev: list[dict], pack: dict) -> list[dict]:
    from .actions import load_plays, fill
    plays = load_plays(pack["id"])
    out = []
    risks = [e for e in ev if e["polarity"] == "risk"]
    chosen = [e for e in risks if e["kind"] == "signal"][:2] + [e for e in risks if e["kind"] != "signal"][:3]
    for e in chosen:
        if e["kind"] == "signal":
            why = fill(plays.get(e["signal_type"], {}).get("why", ""), ctx, pack) or \
                f"{e['speaker']} raised this in the {e['title']} on {e['date']}."
            out.append({"title": e["label"], "why_it_matters": why, "evidence": [e["id"]]})
        else:
            why = {"activity": "Falling usage usually comes before a customer stops renewing.",
                   "capacity": "A smaller contract is already a reduction in what they pay us.",
                   "feature": "Dropping a feature they used before points to lost value in that workflow.",
                   "ticket": "An unresolved problem erodes trust while the renewal decision is being made.",
                   "invoice": "Late payment often reflects budget or approval trouble on their side."}.get(e["kind"], "")
            out.append({"title": e["label"], "why_it_matters": why, "evidence": [e["id"]]})
    return out


def template(ctx: dict, ev: list[dict], pack: dict) -> dict:
    v = pack["vocabulary"]
    by_kind = {e["kind"]: e for e in ev}
    sigs = [e for e in ev if e["kind"] == "signal"]
    sc = ctx["score"]
    out = [{"text": f"{ctx['account']['name']} comes up for {v['renewal'].lower()} in {sc['days_to_renewal']} days "
                    f"and is rated {sc['band']} risk.", "evidence": [by_kind["renewal"]["id"]]}]
    for e in sigs[:3]:
        out.append({"text": f"{e['label']}: {e['speaker']} raised it in the {e['title']} on {e['date']}.", "evidence": [e["id"]]})
    for e in ev:
        if e["kind"] in ("activity", "capacity", "feature", "invoice") or (e["kind"] == "ticket" and e["polarity"] == "risk"):
            out.append({"text": e["text"], "evidence": [e["id"]]})
    if sigs:
        nxt = {"text": pack["signals"][sigs[0]["signal_type"]]["playbook"]["title"].format(
            account=ctx["account"]["name"], contact_first=(ctx["account"]["contact_name"].split() or ["there"])[0]) + ".",
            "evidence": [sigs[0]["id"]]}
    elif "activity" in by_kind and sc["activity_pct"] < 0:
        nxt = {"text": "Ask which workflows the team stopped using and offer a short re-onboarding.", "evidence": [by_kind["activity"]["id"]]}
    else:
        nxt = {"text": "Send the renewal paperwork early and ask for a reference or case study.", "evidence": [by_kind["renewal"]["id"]]}
    good = [{"text": e["text"], "evidence": [e["id"]]} for e in ev if e["polarity"] == "reassuring"]
    risks = [e for e in ev if e["polarity"] == "risk"]
    kinds = sorted({e["label"] for e in risks})
    if risks:
        text = (f"Rated {sc['band']} risk. The main concerns are {', '.join(k.lower() for k in kinds[:4])}"
                + (", partly offset by reassuring evidence." if good else "."))
    else:
        text = f"Rated {sc['band']} risk. No risk evidence was found."
    cites = [e["id"] for e in risks[:4]] or [by_kind["renewal"]["id"]]
    return {"sentences": out, "next_step": nxt, "drivers": _risk_drivers(ctx, ev, pack), "reassuring": good,
            "assessment": {"text": text, "evidence": cites}}


def plan_template(ctx: dict, ev: list[dict], pack: dict) -> dict | None:
    """One conversation plan from the top signal's approved play plus the account's own support and payment facts."""
    from .actions import load_plays, fill
    sigs = [e for e in ev if e["kind"] == "signal"]
    risks = [e for e in ev if e["polarity"] == "risk"]
    top = sigs[0] if sigs else (risks[0] if risks else None)
    if top is None:
        return None
    play = load_plays(pack["id"]).get(top.get("signal_type"), {})
    f = lambda t: fill(t, ctx, pack)                                      # noqa: E731
    qs = [{"text": f(q), "evidence": [top["id"]]} for q in play.get("questions", [])[:3]]
    already_asked_about_usage = top.get("signal_type") == "low_adoption"       # its own questions already cover falling usage
    extra = next((e for e in risks if e["kind"] in ("ticket", "invoice", "feature", "activity") and e["id"] != top["id"]
                  and not (already_asked_about_usage and e["kind"] in ("activity", "feature"))), None)
    if extra is not None:                                                  # the third question is about a second source
        ask = {"ticket": f'Your ticket "{extra.get("subject")}" is still open. What would it take to close it?',
               "invoice": "Is anything blocking payment of the open invoices on your side?",
               "feature": f'Your team used "{extra.get("feature")}" much less recently. What changed?',
               "activity": f"We see less day-to-day use of {pack['synthetic']['product']} lately. Which workflows did the team stop using?"}[extra["kind"]]
        qs = (qs[:2] + [{"text": ask, "evidence": [extra["id"]]}]) if len(qs) >= 2 else qs + [{"text": ask, "evidence": [extra["id"]]}]
    while len(qs) < 3:
        qs.append({"text": "What would make renewing an easy decision for you?", "evidence": [top["id"]]})
    problem = (f'{top["speaker"]} said: "{top["quote"]}"' if top["kind"] == "signal" else top["text"])
    ivs = [{"text": f(t), "evidence": [top["id"]]} for t in play.get("interventions", [])[:2]]
    while len(ivs) < 2:
        ivs.append({"text": "A short review of how they use the product, with a clear proposal for next steps.", "evidence": [top["id"]]})
    return {"problem": {"text": problem, "evidence": [top["id"]]},
            "objective": {"text": f(play.get("goal", "Understand the concern and agree the next step before the renewal.")), "evidence": [top["id"]]},
            "questions": qs[:3], "interventions": ivs,
            "followup": {"text": f(play.get("followup", "Send a written summary and agree a date for the next conversation.")), "evidence": [top["id"]]}}


# ------------------------------------------------------------------ LLM
def _evidence_prompt(ctx: dict, ev: list[dict]) -> str:
    return (f"Account: {ctx['account']['name']} (rated {ctx['score']['band']} risk)\nEvidence (R = risk, G = reassuring, N = neutral):\n"
            + "\n".join(f"{e['id']} [{ {'risk': 'R', 'reassuring': 'G'}.get(e['polarity'], 'N') }]: {e['text']}" for e in ev))


def wants_plan(ctx: dict) -> bool:
    """Medium and high risk accounts, and any account where the customer raised a live risk on a call. A low score must not
    hide a customer who says they are trialing a competitor: the CSM still gets a drafted conversation to approve."""
    return ctx["score"]["band"] != "low" or any(s["feedback"] != "dismissed" for s in ctx["signals"])


def make_plan(ctx: dict, ev: list[dict], pack: dict) -> tuple[dict | None, str]:
    """Retention plan for accounts that need one (see wants_plan). Drafts for the CSM to approve, never sent automatically."""
    if not wants_plan(ctx):
        return None, "none"
    if llm.enabled():
        try:
            v = pack["vocabulary"]
            system = (f"You prepare a retention conversation for a {v['owner_role']}. Use ONLY the numbered evidence. Return: the main problem "
                      "to address, the objective of the conversation, exactly three specific questions to ask, exactly two possible retention "
                      "interventions, and one follow-up. Each item must cite evidence ids like E1. Interventions are options to discuss, "
                      "not promises; do not offer specific discounts. Never invent facts, numbers, names or probabilities.")
            payload = llm.chat_json(system, _evidence_prompt(ctx, ev), PLAN_SCHEMA, "retention_plan", temperature=0.2)
            if validate_plan(payload, ev):
                return payload, "llm"
        except Exception as e:  # noqa: BLE001
            llm.record_failure()
            print("  AI plan failed, using the template for this account:", str(e)[:160])
    return plan_template(ctx, ev, pack), "template"


def make(ctx: dict, pack: dict) -> tuple[dict, str]:
    ev = build_evidence(ctx, pack)
    result, source = None, "template"
    if llm.enabled():
        try:
            v = pack["vocabulary"]
            system = (f"You write {v['renewal'].lower()}-prep briefs for a {v['owner_role']}. Use ONLY the numbered evidence. Return: "
                      "2-4 short sentences explaining the risk (or why the account looks healthy); one concrete next step; the main risk "
                      "drivers, each with why it matters; any reassuring or contradictory evidence; and an overall assessment. Every "
                      "statement must cite evidence ids like E1. Never invent facts, numbers, names or churn probabilities. Plain, direct language.")
            payload = llm.chat_json(system, _evidence_prompt(ctx, ev), SCHEMA, "renewal_brief", temperature=0.2)
            if validate(payload, ev):
                result, source = payload, "llm"
        except Exception as e:  # noqa: BLE001
            llm.record_failure()
            print("  AI brief failed, using the template for this account:", str(e)[:160])
    if result is None:
        result = template(ctx, ev, pack)
    plan, plan_source = make_plan(ctx, ev, pack)
    return {"evidence": ev, **result, "plan": plan, "plan_source": plan_source, "fingerprint": fingerprint(ctx, ev)}, source
