"""Draft next steps from the pack's playbooks. Drafts only: nothing is sent or written to another
system until a person approves it (Orchera's read-only-first rule).

Each signal has a short playbook (title, kind, first move) in packs/<id>.yaml and a full play in
plays/<id>.yaml: why now, goal, steps, what to say, how to handle pushback, what to bring and when it is done.
The "why now" part is filled from the real quote and account facts; the rest is written by people."""
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import delete

from ..models import Action
from . import llm

MAX_PER_ACCOUNT = 2
PLAY_DIR = Path(__file__).resolve().parents[1] / "plays"


class _Safe(dict):
    def __missing__(self, key):          # leave unknown {placeholders} visible instead of crashing
        return "{" + key + "}"


def _vars(ctx: dict, pack: dict) -> dict:
    a = ctx["account"]
    days = ctx["score"]["days_to_renewal"]
    return dict(account=a["name"], contact_first=a["contact_name"].split()[0], owner=a["owner"],
                product=pack["synthetic"]["product"], days=days,
                early=(f"this week, the renewal is only {days} days away" if days <= 45
                       else "at least 45 days before the renewal date"),
                paperwork=(f"today, the renewal is only {days} days away" if days < 60
                           else "about 60 days before the renewal date"))


def fill(text: str, ctx: dict, pack: dict) -> str:
    return text.format_map(_Safe(_vars(ctx, pack))).replace("s's ", "s' ")


@lru_cache
def load_plays(pack_id: str) -> dict:
    path = PLAY_DIR / f"{pack_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _euro(x: float) -> str:
    return f"€{x:,.0f}"


def why_now(sig: dict, ctx: dict, pack: dict) -> str:
    """Facts only: the real quote and the account numbers. Nothing here is generated."""
    c, sc = ctx["contract"], ctx["score"]
    lines = [f"{sig['speaker'] or 'The customer'} said ({sig['date']}): \"{sig['quote']}\""]
    facts = [f"renews in {sc['days_to_renewal']} days", f"{_euro(c['annual_value'])} a year"]
    if sc["activity_pct"] <= -0.08:
        facts.append(f"{pack['vocabulary']['activity'].lower()} down {abs(round(sc['activity_pct'] * 100))}%")
    if c["capacity_prev"] > c["capacity"]:
        facts.append(f"{pack['vocabulary']['capacity'].lower()} cut from {c['capacity_prev']} to {c['capacity']}")
    lines.append(", ".join(facts).capitalize() + ".")
    others = [pack["signals"][s["signal_type"]]["label"] for s in ctx["signals"]
              if s["signal_type"] != sig["signal_type"] and s["feedback"] != "dismissed"]
    if others:
        lines.append("Also raised: " + ", ".join(sorted(set(others))) + ".")
    return "\n".join(lines)


def _cite(item: dict) -> str:
    return " [" + ", ".join(item["evidence"]) + "]" if item.get("evidence") else ""


def plan_sections(plan: dict) -> list[str]:
    """The conversation plan written from this account's own evidence. Ids match the Evidence list on the account page."""
    out = ["", "MAIN PROBLEM", plan["problem"]["text"] + _cite(plan["problem"]),
           "", "OBJECTIVE", plan["objective"]["text"] + _cite(plan["objective"]), "", "QUESTIONS TO ASK"]
    out += [f"{i}. {q['text']}{_cite(q)}" for i, q in enumerate(plan["questions"], 1)]
    out += ["", "RETENTION OPTIONS"] + [f"- {t['text']}{_cite(t)}" for t in plan["interventions"]]
    out += ["", "FOLLOW-UP", plan["followup"]["text"] + _cite(plan["followup"])]
    return out


def play_body(play: dict, sig: dict, ctx: dict, pack: dict, email: Optional[str] = None, plan: Optional[dict] = None) -> str:
    f = lambda t: fill(t, ctx, pack)                                  # noqa: E731
    out = ["WHY NOW", why_now(sig, ctx, pack)]
    if plan:
        out += plan_sections(plan) + ["", "STEPS"]
    else:
        out += ["", "GOAL", f(play["goal"]), "", "STEPS"]
    out += [f"{i}. {f(t)}" for i, t in enumerate(play["steps"], 1)]
    if not plan:
        out += ["", "WHAT TO SAY"] + [f"- {f(t)}" for t in play["say"]]
    out += ["", "IF THEY PUSH BACK"] + [f"- {f(t)}" for t in play["pushback"]]
    out += ["", "BRING"] + [f"- {f(t)}" for t in play["bring"]]
    out += ["", "DONE WHEN", f(play["done_when"])]
    if email:
        out += ["", "DRAFT EMAIL", email]
    return "\n".join(out)


def personalize(body: str, ctx: dict, sig: dict) -> Optional[str]:
    """Optionally let the LLM tailor an email draft to the actual quote. Returns None on any failure."""
    if not llm.enabled():
        return None
    try:
        out = llm.chat_text(
            "You edit short customer emails. Keep it under 110 words, warm and direct, no subject line, no placeholders. "
            "Refer to what the customer said without quoting it word for word. Keep the greeting and the sign-off.",
            f"Customer said: \"{sig['quote']}\"\n\nDraft to improve:\n{body}", temperature=0.4)
        out = out.strip()
        return out if 40 < len(out) < 1200 and "[" not in out else None
    except Exception:  # noqa: BLE001
        return None


def draft_for(session, client_id: str, ctx: dict, pack: dict, use_llm_emails: bool = False, plan: Optional[dict] = None,
              plan_source: str = "template") -> int:
    session.execute(delete(Action).where(Action.account_id == ctx["account"]["id"], Action.status == "draft"))
    sigs = sorted([s for s in ctx["signals"] if s["feedback"] != "dismissed"],
                  key=lambda s: -pack["signals"][s["signal_type"]]["weight"] * s["confidence"])
    seen, n = set(), 0
    for s in sigs:
        if s["signal_type"] in seen or n >= MAX_PER_ACCOUNT:
            continue
        seen.add(s["signal_type"])
        pb = pack["signals"][s["signal_type"]]["playbook"]
        text, source = fill(pb["body"], ctx, pack).strip(), "template"
        if use_llm_emails and pb["kind"] == "email":
            better = personalize(text, ctx, s)
            if better:
                text, source = better, "llm"
        play = load_plays(pack["id"]).get(s["signal_type"])
        if play:
            body = play_body(play, s, ctx, pack, email=text if pb["kind"] == "email" else None, plan=plan if n == 0 else None)
            if n == 0 and plan:                      # the label says AI only when the AI wrote the plan
                source = "llm" if plan_source == "llm" else "template"
        else:
            body = text
        session.add(Action(client_id=client_id, account_id=ctx["account"]["id"], signal_type=s["signal_type"],
                           kind=pb["kind"], title=fill(pb["title"], ctx, pack), body=body, source=source))
        n += 1
    return n
