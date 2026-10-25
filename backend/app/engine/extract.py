"""Signal extraction driven by the client's pack. Every quote must appear verbatim in a customer turn,
otherwise the flag is dropped: the product never shows a claim it can't prove."""
from typing import Optional
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select

from ..models import Conversation, Reassurance, Signal
from . import llm

LINE_RE = re.compile(r"^(?P<name>[^()\n]+?) \((?P<label>[^)\n]+)\):\s*(?P<text>.+)$")


def schema(pack: dict) -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["signals", "reassurances"],
        "properties": {"reassurances": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["speaker", "confidence", "quote"],
            "properties": {"speaker": {"type": "string"}, "confidence": {"type": "number"}, "quote": {"type": "string"}}}},
            "signals": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["signal_type", "speaker", "confidence", "quote"],
            "properties": {
                "signal_type": {"type": "string", "enum": list(pack["signals"])},
                "speaker": {"type": "string"},
                "confidence": {"type": "number"},
                "quote": {"type": "string"},
            }}}},
    }


def system_prompt(pack: dict, vendor: str) -> str:
    v = pack["vocabulary"]
    return (
        f"You review conversations between {vendor} ({v['owner_role']}) and its {v['accounts'].lower()}, "
        f"and extract signals that put the {v['renewal'].lower()} at risk.\n"
        "Signal types (use only these):\n"
        + "\n".join(f"- {k}: {s['definition']}" for k, s in pack["signals"].items())
        + "\n\nRules:\n"
        f"- Only statements by the {v['account'].lower()} count, never by {vendor}'s own staff.\n"
        "- Copy the quote verbatim from a single turn: the shortest full sentence(s) that prove the signal.\n"
        "- Only current risks. Past issues that were resolved, or decisions already made in the vendor's favour, are NOT signals.\n"
        "- confidence is 0-1. Return an empty list if there are no signals. At most one entry per signal type.\n"
        f"- Separately, list up to two reassurances: verbatim statements by the {v['account'].lower()} that show real satisfaction "
        "or an intention to stay or renew. A customer can raise a risk and be reassuring in the same call; report both. "
        "Never count politeness, or statements by the vendor's own staff."
    )


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().strip("\"'“”").lower())


def parse_turns(transcript: str, staff_marker: str):
    turns = []
    for line in transcript.splitlines():
        m = LINE_RE.match(line.strip())
        if m:
            turns.append({"name": m["name"].strip(), "label": m["label"], "text": m["text"],
                          "is_staff": staff_marker in m["label"]})
    return turns


def ground(raw: list[dict], turns: list[dict], valid_types) -> list[dict]:
    out, seen = [], set()
    for s in raw:
        stype = s.get("signal_type")
        q = norm(s.get("quote", ""))
        if stype not in valid_types or stype in seen or len(q) < 8:
            continue
        turn = next((t for t in turns if q in norm(t["text"])), None)
        if turn is None or turn["is_staff"]:
            continue
        flat = re.sub(r"\s+", " ", turn["text"].strip())
        start = flat.lower().find(q)
        exact = flat[start:start + len(q)] if start >= 0 else flat
        seen.add(stype)
        out.append({"signal_type": stype, "speaker": turn["name"],
                    "confidence": max(0.0, min(1.0, float(s.get("confidence", 0.5)))), "quote": exact})
    return out


def ground_reassurances(raw: list[dict], turns: list[dict]) -> list[dict]:
    """Same proof rule as risks: the quote must be verbatim in a customer turn. At most two per call."""
    out = []
    for r in raw:
        g = ground([{"signal_type": "reassurance", "confidence": r.get("confidence", 0.6), "quote": r.get("quote", "")}],
                   turns, {"reassurance"})
        if g and all(norm(g[0]["quote"]) != norm(o["quote"]) for o in out):
            out.append({"speaker": g[0]["speaker"], "confidence": g[0]["confidence"], "quote": g[0]["quote"]})
    return out[:2]


def extract_rules(transcript: str, pack: dict, staff_marker: str) -> list[dict]:
    turns = parse_turns(transcript, staff_marker)
    raw = [{"signal_type": k, "confidence": 0.6, "quote": t["text"]}
           for t in turns if not t["is_staff"]
           for k, sig in pack["signals"].items() if re.search(sig["keywords"], t["text"], re.I)]
    return ground(raw, turns, pack["signals"].keys())


def reassure_rules(transcript: str, pack: dict, staff_marker: str) -> list[dict]:
    pat = pack.get("reassurance_keywords")
    turns = parse_turns(transcript, staff_marker)
    raw = [{"confidence": 0.6, "quote": t["text"]} for t in turns if pat and not t["is_staff"] and re.search(pat, t["text"], re.I)]
    return ground_reassurances(raw, turns)


def extract_llm_full(transcript: str, pack: dict, vendor: str, staff_marker: str) -> tuple[list[dict], list[dict]]:
    data = llm.chat_json(system_prompt(pack, vendor), transcript, schema(pack), "risk_signals")
    turns = parse_turns(transcript, staff_marker)
    return (ground(data.get("signals", []), turns, pack["signals"].keys()),
            ground_reassurances(data.get("reassurances", []), turns))


def extract_llm(transcript: str, pack: dict, vendor: str, staff_marker: str) -> list[dict]:
    return extract_llm_full(transcript, pack, vendor, staff_marker)[0]


def analyze_full(transcript: str, pack: dict, vendor: str, staff_marker: str, use_llm: Optional[bool] = None):
    """Risks and reassurances from one call. Returns (signals, reassurances, source)."""
    use_llm = llm.enabled() if use_llm is None else use_llm
    if use_llm:
        try:
            sigs, good = extract_llm_full(transcript, pack, vendor, staff_marker)
            return sigs, good, "llm"
        except Exception as e:  # noqa: BLE001
            llm.record_failure()
            print("  AI extraction failed, using rules for this call:", str(e)[:160])
    return extract_rules(transcript, pack, staff_marker), reassure_rules(transcript, pack, staff_marker), "rules"


def analyze(transcript: str, pack: dict, vendor: str, staff_marker: str, use_llm: Optional[bool] = None):
    sigs, _, src = analyze_full(transcript, pack, vendor, staff_marker, use_llm)
    return sigs, src


def run(session, client, pack: dict, use_llm: Optional[bool] = None, workers: int = 6) -> int:
    vendor = pack["synthetic"]["product"]
    marker = staff_label(pack)
    convs = session.scalars(select(Conversation).where(Conversation.client_id == client.id)).all()
    session.execute(delete(Signal).where(Signal.client_id == client.id))
    session.execute(delete(Reassurance).where(Reassurance.client_id == client.id))
    use = llm.enabled() if use_llm is None else use_llm
    if use:
        print(f"  {client.name}: reading {len(convs)} conversations with the AI "
              f"(~{max(1, round(len(convs) / llm.RPM))} min at {llm.RPM} requests/min)…")
    done = [0]

    def work(c):
        out = (c, analyze_full(c.transcript, pack, vendor, marker, use))
        done[0] += 1
        if use and (done[0] % 10 == 0 or done[0] == len(convs)):
            print(f"    {done[0]}/{len(convs)} conversations done")
        return out

    with ThreadPoolExecutor(max_workers=min(workers, 3) if use else 1) as pool:
        results = list(pool.map(work, convs))
    n = 0
    for conv, (sigs, good, src) in results:
        for s in sigs:
            session.add(Signal(client_id=client.id, account_id=conv.account_id, conversation_id=conv.id, source=src, **s))
            n += 1
        for g in good:
            session.add(Reassurance(client_id=client.id, account_id=conv.account_id, conversation_id=conv.id, source=src, **g))
    session.commit()
    return n


def staff_label(pack: dict) -> str:
    """Staff turns are labelled '<Name> (<Product> <owner role>)' by the connectors."""
    return f"{pack['synthetic']['product']} {pack['vocabulary']['owner_role']}"
