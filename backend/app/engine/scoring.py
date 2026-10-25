"""Transparent 0-100 risk score. Weights come from the pack; every point is traceable to a component."""
from typing import Optional
import datetime as dt
from statistics import mean


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def band(score: int, pack: dict) -> str:
    b = pack["score"]["bands"]
    return "high" if score >= b["high"] else "medium" if score >= b["medium"] else "low"


def support_points(tickets: list, cfg: dict) -> float:
    """Unresolved complaints weigh most, then unresolved high-priority tickets, then any other unresolved ticket."""
    raw = 0
    for t in tickets:
        if t.status not in ("open", "pending"):
            continue
        raw += 4 if t.category == "complaint" else 3 if t.priority == "high" else 1
    return clamp(raw, 0, cfg.get("support_max", 0))


def payment_points(invoices: list, today: dt.date, cfg: dict) -> float:
    """An unpaid invoice past its due date is a strong signal; a late payment is a mild one."""
    raw = 0
    for i in invoices:
        if i.paid_on is None and i.due < today:
            raw += 5
        elif i.paid_on is not None and i.paid_on > i.due:
            raw += 2
    return clamp(raw, 0, cfg.get("payment_max", 0))


def score(contract, activity: list[float], signals: list, pack: dict, today: Optional[dt.date] = None,
          tickets: Optional[list] = None, invoices: Optional[list] = None) -> dict:
    cfg = pack["score"]
    today = today or dt.date.today()
    days = (contract.renewal_date - today).days
    recent = mean(activity[-14:]) if activity else 0
    baseline = (mean(activity[:45]) if len(activity) >= 45 else mean(activity) if activity else 0) or 1
    activity_pct = (recent - baseline) / baseline
    cap_pct = (contract.capacity_prev - contract.capacity) / contract.capacity_prev if contract.capacity_prev else 0

    act_pts = clamp(-activity_pct * 100 * cfg["activity_drop_max"] / 30, 0, cfg["activity_drop_max"])
    cap_pts = clamp(cap_pct * 100 * cfg["capacity_cut_max"] / 15, 0, cfg["capacity_cut_max"])
    sig_pts = clamp(sum(pack["signals"][s.signal_type]["weight"] * s.confidence
                        for s in signals if s.feedback != "dismissed"), 0, cfg["signals_max"])
    sup_pts = support_points(tickets or [], cfg)
    pay_pts = payment_points(invoices or [], today, cfg)
    base = act_pts + cap_pts + sig_pts + sup_pts + pay_pts
    max_base = (cfg["activity_drop_max"] + cfg["capacity_cut_max"] + cfg["signals_max"]
                + cfg.get("support_max", 0) + cfg.get("payment_max", 0))
    urg = cfg["urgency_max"]
    urgency = min(urg, base / max_base * urg * 2.5) if days <= 30 else min(urg / 2, base / max_base * urg) if days <= 60 else 0
    total = round(clamp(base + urgency, 0, 100))
    v = pack["vocabulary"]
    return {
        "score": total, "band": band(total, pack), "days_to_renewal": days,
        "activity_pct": round(activity_pct, 4), "capacity_pct": round(cap_pct, 4),
        "components": [
            {"label": f"{v['activity']} trend", "points": round(act_pts), "max": cfg["activity_drop_max"]},
            {"label": f"{v['capacity']} cut", "points": round(cap_pts), "max": cfg["capacity_cut_max"]},
            {"label": "Conversation signals", "points": round(sig_pts), "max": cfg["signals_max"]},
            *([{"label": "Unresolved support", "points": round(sup_pts), "max": cfg["support_max"]}] if cfg.get("support_max") else []),
            *([{"label": "Payment issues", "points": round(pay_pts), "max": cfg["payment_max"]}] if cfg.get("payment_max") else []),
            {"label": "Renewal is close", "points": round(urgency), "max": urg},
        ],
    }
