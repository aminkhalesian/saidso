"""Draft next steps from the pack's playbooks. Drafts only: nothing is sent or written to another
system until a person approves it (Orchera's read-only-first rule)."""
from typing import Optional
from sqlalchemy import delete

from ..models import Action
from . import llm

MAX_PER_ACCOUNT = 2


def fill(text: str, ctx: dict, pack: dict) -> str:
    a = ctx["account"]
    return text.format(account=a["name"], contact_first=a["contact_name"].split()[0], owner=a["owner"],
                       product=pack["synthetic"]["product"])


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


def draft_for(session, client_id: str, ctx: dict, pack: dict, use_llm_emails: bool = False) -> int:
    session.execute(delete(Action).where(Action.account_id == ctx["account"]["id"], Action.status == "draft"))
    sigs = sorted([s for s in ctx["signals"] if s["feedback"] != "dismissed"],
                  key=lambda s: -pack["signals"][s["signal_type"]]["weight"] * s["confidence"])
    seen, n = set(), 0
    for s in sigs:
        if s["signal_type"] in seen or n >= MAX_PER_ACCOUNT:
            continue
        seen.add(s["signal_type"])
        pb = pack["signals"][s["signal_type"]]["playbook"]
        body, source = fill(pb["body"], ctx, pack).strip(), "template"
        if use_llm_emails and pb["kind"] == "email":
            better = personalize(body, ctx, s)
            if better:
                body, source = better, "llm"
        session.add(Action(client_id=client_id, account_id=ctx["account"]["id"], signal_type=s["signal_type"],
                           kind=pb["kind"], title=fill(pb["title"], ctx, pack), body=body, source=source))
        n += 1
    return n
