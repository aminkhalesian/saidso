"""Retention outlook: executive and CSM KPIs worked out from the data we already hold.

Everything here is a snapshot of the renewals in the window. True GRR, NRR and logo churn need last year's
revenue, which no connector provides yet, so the revenue figures are labelled as an outlook, never as GRR/NRR.
"""
import datetime as dt

GRR_MEDIAN, GRR_GOOD, GRR_BEST = 84, 85, 90          # 2025 SaaS benchmarks (Aleph), shown for context only
CALL_WINDOW_DAYS = 60
GROWTH = 0.10                                         # usage growth that counts as an expansion signal


def compute(ctxs: list[dict]) -> dict:
    n = len(ctxs)
    total = sum(c["contract"]["annual_value"] for c in ctxs)
    high = [c for c in ctxs if c["score"]["band"] == "high"]
    at_risk = sum(c["contract"]["annual_value"] for c in high)
    today = dt.date.today()

    # revenue outlook: what survives if every high-risk renewal is lost
    grr = round(100 * (total - at_risk) / total, 1) if total else None

    # contraction: seats already cut; the lost value is estimated from the price per seat after the cut
    contraction, cut_logos = 0.0, 0
    for c in ctxs:
        k = c["contract"]
        if k["capacity"] and k["capacity"] < k["capacity_prev"]:
            contraction += k["annual_value"] * (k["capacity_prev"] - k["capacity"]) / k["capacity"]
            cut_logos += 1

    # expansion candidates: seats up, or usage clearly growing, and not high-risk
    exp = [c for c in ctxs if c["score"]["band"] != "high" and (
        c["contract"]["capacity"] > c["contract"]["capacity_prev"]
        or (c["score"].get("usage_known", True) and c["score"]["activity_pct"] >= GROWTH))]

    util = [c["sources"]["usage"]["utilization"] for c in ctxs if c.get("sources", {}).get("usage")]
    decline = [c for c in ctxs if c.get("sources", {}).get("usage") and
               sum(1 for f in c["sources"]["usage"]["features"] if f["pct"] is not None and f["pct"] <= -0.25) >= 2]
    covered = [c for c in ctxs if (c["sources"]["conversations"]["last"] or "") >=
               (today - dt.timedelta(days=CALL_WINDOW_DAYS)).isoformat()]
    support = [c["sources"]["support"] for c in ctxs if c["sources"]["support"]]
    comm = [c["sources"]["commercial"] for c in ctxs]

    return {
        "health": {"average": round(100 - sum(c["score"]["score"] for c in ctxs) / n, 1) if n else None,
                   "bands": {b: sum(1 for c in ctxs if c["score"]["band"] == b) for b in ("high", "medium", "low")}},
        "grr_outlook": {"pct": grr, "renewing": total, "at_risk": at_risk,
                        "benchmark": {"median": GRR_MEDIAN, "good": GRR_GOOD, "best": GRR_BEST}},
        "logos_at_risk": {"count": len(high), "of": n, "pct": round(100 * len(high) / n, 1) if n else None, "value": at_risk},
        "contraction": {"value": round(contraction), "logos": cut_logos},
        "expansion": {"count": len(exp), "value": sum(c["contract"]["annual_value"] for c in exp)},
        "utilization": {"avg_pct": round(100 * sum(util) / len(util)) if util else None},
        "features": {"accounts_declining": len(decline), "of": n},
        "call_coverage": {"covered": len(covered), "of": n, "pct": round(100 * len(covered) / n) if n else None,
                          "window_days": CALL_WINDOW_DAYS},
        "support": {"high_priority_open": sum(s["high_priority"] for s in support),
                    "accounts_with_open": sum(1 for s in support if s["unresolved"])},
        "payments": {"overdue_invoices": sum(c["overdue"] for c in comm),
                     "overdue_amount": round(sum(c["overdue_amount"] for c in comm)),
                     "accounts": sum(1 for c in comm if c["overdue"])},
    }
