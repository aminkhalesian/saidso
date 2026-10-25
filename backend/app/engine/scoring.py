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


def reassurance_points(activity_pct: float, tickets: list, invoices: list, today: dt.date, cfg: dict, positives: int = 0) -> float:
    """Good news counts too: growing usage, invoices paid on time and no unresolved complaints lower the score."""
    cap = cfg.get("reassure_max", 0)
    if not cap:
        return 0
    pts = clamp(activity_pct / 0.15 * 5, 0, 5)
    if invoices and not any((i.paid_on is None and i.due < today) or (i.paid_on and i.paid_on > i.due) for i in invoices):
        pts += 3
    if tickets and not any(t.status in ("open", "pending") and (t.category == "complaint" or t.priority == "high") for t in tickets):
        pts += 2
    if positives:                                     # the customer said something reassuring on a call
        pts += 3
    return clamp(pts, 0, cap)


MIN_USAGE_POINTS = 28      # 14 recent days plus at least 14 earlier days; with less we do not know the trend


def score(contract, activity: list[float], signals: list, pack: dict, today: Optional[dt.date] = None,
          tickets: Optional[list] = None, invoices: Optional[list] = None, positives: int = 0) -> dict:
    cfg = pack["score"]
    today = today or dt.date.today()
    days = (contract.renewal_date - today).days
    usage_known = len(activity) >= MIN_USAGE_POINTS
    if usage_known:
        recent = mean(activity[-14:])
        baseline = (mean(activity[:45]) if len(activity) >= 45 else mean(activity[:-14])) or 1
        activity_pct = (recent - baseline) / baseline
    else:                                           # no or too little usage data: unknown, never "zero usage"
        activity_pct = 0.0
    cap_pct = (contract.capacity_prev - contract.capacity) / contract.capacity_prev if contract.capacity_prev else 0

    act_pts = clamp(-activity_pct * 100 * cfg["activity_drop_max"] / 30, 0, cfg["activity_drop_max"])
    cap_pts = clamp(cap_pct * 100 * cfg["capacity_cut_max"] / 15, 0, cfg["capacity_cut_max"])
    sig_pts = clamp(sum(pack["signals"][s.signal_type]["weight"] * s.confidence
                        for s in signals if s.feedback != "dismissed"), 0, cfg["signals_max"])
    sup_pts = support_points(tickets or [], cfg)
    pay_pts = payment_points(invoices or [], today, cfg)
    good_pts = reassurance_points(activity_pct, tickets or [], invoices or [], today, cfg, positives)
    base = max(0.0, act_pts + cap_pts + sig_pts + sup_pts + pay_pts - good_pts)
    max_base = (cfg["activity_drop_max"] + cfg["capacity_cut_max"] + cfg["signals_max"]
                + cfg.get("support_max", 0) + cfg.get("payment_max", 0))
    urg = cfg["urgency_max"]
    urgency = min(urg, base / max_base * urg * 2.5) if days <= 30 else min(urg / 2, base / max_base * urg) if days <= 60 else 0
    total = round(clamp(base + urgency, 0, 100))
    v = pack["vocabulary"]
    return {
        "score": total, "band": band(total, pack), "days_to_renewal": days, "usage_known": usage_known,
        "activity_pct": round(activity_pct, 4), "capacity_pct": round(cap_pct, 4),
        "components": [
            {"label": f"{v['activity']} trend", "points": round(act_pts), "max": cfg["activity_drop_max"]},
            {"label": f"{v['capacity']} cut", "points": round(cap_pts), "max": cfg["capacity_cut_max"]},
            {"label": "Conversation signals", "points": round(sig_pts), "max": cfg["signals_max"]},
            *([{"label": "Unresolved support", "points": round(sup_pts), "max": cfg["support_max"]}] if cfg.get("support_max") else []),
            *([{"label": "Payment issues", "points": round(pay_pts), "max": cfg["payment_max"]}] if cfg.get("payment_max") else []),
            *([{"label": "Reassuring evidence", "points": -round(good_pts), "max": cfg["reassure_max"]}] if cfg.get("reassure_max") else []),
            {"label": "Renewal is close", "points": round(urgency), "max": urg},
        ],
    }
