"""Eval harness: compare extracted signals with planted ground truth, plus how people rated the flags."""
from sqlalchemy import select

from ..models import PlantedLabel, Signal


def evaluate(session, client_id: str, pack: dict) -> dict:
    labels = session.scalars(select(PlantedLabel).where(PlantedLabel.client_id == client_id)).all()
    sigs = session.scalars(select(Signal).where(Signal.client_id == client_id)).all()
    truth = {(l.conversation_id, l.signal_type) for l in labels if not l.is_decoy}
    decoys = {(l.conversation_id, l.signal_type): l.line for l in labels if l.is_decoy}
    lines = {(l.conversation_id, l.signal_type): l.line for l in labels}
    pred = {(s.conversation_id, s.signal_type): s for s in sigs}
    tp, fp, fn = truth & pred.keys(), pred.keys() - truth, truth - pred.keys()
    precision = len(tp) / len(pred) if pred else 0.0
    recall = len(tp) / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    label = {k: v["label"] for k, v in pack["signals"].items()}
    per_type = []
    for t in pack["signals"]:
        tr = {x for x in truth if x[1] == t}
        pr = {x for x in pred if x[1] == t}
        per_type.append({"signal_type": t, "label": label[t], "planted": len(tr), "found": len(tr & pr),
                         "false_alarms": len(pr - tr)})
    feedback = {"confirmed": sum(s.feedback == "confirmed" for s in sigs),
                "dismissed": sum(s.feedback == "dismissed" for s in sigs),
                "open": sum(s.feedback == "open" for s in sigs)}
    source = max({s.source for s in sigs}, key=lambda src: sum(x.source == src for x in sigs)) if sigs else "none"
    return {
        "source": source, "precision": precision, "recall": recall, "f1": f1,
        "planted": len(truth), "found": len(tp), "false_alarms": len(fp),
        "decoys": len(decoys), "decoys_resisted": len(decoys.keys() - pred.keys()),
        "per_type": per_type, "feedback": feedback,
        "misses": [{"conversation_id": c, "label": label[t], "line": lines[(c, t)]} for c, t in sorted(fn)],
        "false_alarm_rows": [{"conversation_id": c, "label": label[t], "quote": pred[(c, t)].quote,
                              "was_decoy": (c, t) in decoys} for c, t in sorted(fp)],
    }
