"""Retention analytics: every KPI with its definition, its period, and the customer rows behind the number.

Principles: nothing is hardcoded or forecast; every row is a real record; the numbers on the cards are computed
from the same rows the drill-downs list, so they always reconcile. A source that is not connected is reported as
unavailable, never as zero. Revenue figures are scenarios built from current contract values, not predictions."""
import datetime as dt
from collections import defaultdict
from typing import Optional

from sqlalchemy import func, select

from ..models import Conversation, FeatureUsage, Invoice, Ticket, UsageStat
from .. import service

HORIZONS = (30, 60, 90)
FEATURE_DROP = -0.25          # a feature counts as declining when its use fell by at least 25%
FEATURE_MIN = 2               # an account is "in decline" when at least two features declined
GROWTH = 0.10                 # usage up 10% (last 14 days against the earlier baseline) counts as growth
LOW_UTIL = 0.40               # below 40% of what was purchased is flagged as low adoption
CALL_DAYS = 60                # a conversation counts when it happened in the last 60 days
SOURCES = ("usage", "support", "billing", "calls")


def _eur(n: float) -> str:
    return f"€{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"€{round(n / 1000)}k" if n >= 1000 else f"€{round(n)}"


def _pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def _base(c: dict) -> dict:
    return {"account_id": c["account"]["id"], "name": c["account"]["name"], "segment": c["account"]["segment"],
            "score": c["score"]["score"], "band": c["score"]["band"], "annual_value": c["contract"]["annual_value"],
            "days_to_renewal": c["score"]["days_to_renewal"], "renewal_date": c["contract"]["renewal_date"]}


def _drivers(c: dict) -> str:
    comps = sorted((p for p in c["score"]["components"] if p["points"] > 0), key=lambda p: -p["points"])[:3]
    return ", ".join(f'{p["label"]} ({p["points"]}/{p["max"]})' for p in comps) or "No risk points"


def _kpi(id, section, name, headline, sub, period, what, why, how, rows, columns, status="ok", note="", extra=None):
    return {"id": id, "section": section, "name": name, "headline": headline, "sub": sub, "period": period,
            "what": what, "why": why, "how": how, "status": status, "note": note, "rows": rows, "columns": columns,
            **(extra or {})}


COL = {
    "score": {"key": "score", "label": "Risk", "fmt": "risk"},
    "days": {"key": "days_to_renewal", "label": "Renews in", "fmt": "days"},
    "acv": {"key": "annual_value", "label": "Contract value", "fmt": "eur"},
}


def retention(session, client_id: str, pack: dict, window: int = 90) -> dict:
    window = window if window in HORIZONS else 90
    today = dt.date.today()
    ctxs = service.contexts(session, client_id, window=window)
    n = len(ctxs)
    ids = {c["account"]["id"] for c in ctxs}
    total = sum(c["contract"]["annual_value"] for c in ctxs)
    count = lambda model: session.scalar(select(func.count()).select_from(model).where(model.client_id == client_id)) or 0   # noqa: E731
    has = {"usage": count(UsageStat) > 0, "support": count(Ticket) > 0, "billing": count(Invoice) > 0, "calls": count(Conversation) > 0}
    hours = pack["id"] == "agency"
    vocab = pack["vocabulary"]
    horizon = f"renewals in the next {window} days"
    out = []

    # ---------------------------------------------------------------- leadership
    high = sorted((c for c in ctxs if c["score"]["band"] == "high"), key=lambda c: (-c["score"]["score"], c["score"]["days_to_renewal"]))
    exposed = sum(c["contract"]["annual_value"] for c in high)
    rows = [{**_base(c), "share": round(c["contract"]["annual_value"] / exposed, 3) if exposed else 0} for c in high]
    retained = total - exposed
    out.append(_kpi(
        "exposure", "leadership", "Revenue exposure scenario",
        _pct(retained / total) if total else "–", f"{_eur(exposed)} of {_eur(total)} exposed" if total else "No renewals in this period",
        horizon,
        "A what-if: the share of recurring revenue that would remain if every High-risk renewal in this period were lost.",
        "Shows how concentrated the revenue at stake is, and which few accounts carry most of it.",
        f"(contract value of all renewals − contract value of High-risk renewals) ÷ contract value of all renewals = ({_eur(total)} − {_eur(exposed)}) ÷ {_eur(total)}. "
        "It is not a churn prediction and not Gross Revenue Retention; those need last year's revenue.",
        rows, [{"key": "share", "label": "Share of exposure", "fmt": "pct"}, COL["acv"], COL["score"], COL["days"]],
        status="ok" if total else "none", extra={"n": retained / total if total else None}))

    out.append(_kpi(
        "at_risk", "leadership", "Customers at risk",
        f"{len(high)} of {n}", f"{_eur(exposed)} annual contract value", horizon,
        "Customers whose risk score is 50 or above (High risk), and the yearly contract value attached to them.",
        "These are the renewals most likely to need action before they come up.",
        f"Count of renewals in the next {window} days with a risk score ≥ 50, out of all {n} renewals in that period. Value = sum of their yearly contract values.",
        [{**_base(c), "drivers": _drivers(c), "flags": ", ".join(dict.fromkeys(pack["signals"][s["signal_type"]]["label"] for s in c["signals"] if s["feedback"] != "dismissed")) or "–"} for c in high],
        [COL["score"], COL["acv"], COL["days"], {"key": "drivers", "label": "Main risk drivers", "fmt": "text"}],
        status="ok" if n else "none"))

    avg_health = round(100 - sum(c["score"]["score"] for c in ctxs) / n, 1) if n else None
    bands = {b: sum(1 for c in ctxs if c["score"]["band"] == b) for b in ("low", "medium", "high")}
    out.append(_kpi(
        "health", "leadership", "Average health score",
        f"{avg_health}" if n else "–", f'{bands["low"]} healthy · {bands["medium"]} watch · {bands["high"]} high risk' if n else "No renewals in this period",
        horizon,
        "100 minus the risk score, averaged over the customers renewing in this period. 100 is best, 0 is worst.",
        "Gives one number for the state of the book. It moves whenever any customer's evidence changes.",
        "Health = 100 − risk score, where the risk score (0–100) adds up usage trend, seat cuts, call signals, support, payments and renewal urgency, minus reassuring evidence. "
        "It is a transparent rules-based score, not a validated predictive model.",
        [{**_base(c), "health": 100 - c["score"]["score"]} for c in sorted(ctxs, key=lambda c: -c["score"]["score"])],
        [{"key": "health", "label": "Health", "fmt": "num"}, COL["score"], COL["acv"], COL["days"]],
        status="ok" if n else "none"))

    cut = []
    for c in ctxs:
        k = c["contract"]
        if k["capacity"] and k["capacity"] < k["capacity_prev"]:
            per_seat = k["annual_value"] / k["capacity"]
            cut.append({**_base(c), "seats_prev": k["capacity_prev"], "seats": k["capacity"], "per_seat": round(per_seat),
                        "reduction": round(per_seat * (k["capacity_prev"] - k["capacity"]))})
    cut.sort(key=lambda r: -r["reduction"])
    est = sum(r["reduction"] for r in cut)
    out.append(_kpi(
        "contraction", "leadership", "Estimated revenue reduction from seat cuts",
        _eur(est) if n else "–", f"{len(cut)} of {n} customers cut {vocab['capacity'].lower()}" if n else "No renewals in this period", horizon,
        f"An estimate of the yearly revenue these customers already reduced by cutting {vocab['capacity'].lower()} before renewal.",
        "Seat cuts are an early sign of shrinking value, even before the renewal call.",
        f"For each customer: (previous {vocab['capacity'].lower()} − current) × current yearly value per unit. The current contract value already reflects the cut, "
        "so this amount is not subtracted from any other figure. It is an estimate, not revenue confirmed as lost: we have no billing history to confirm it.",
        cut, [{"key": "seats_prev", "label": f"{vocab['capacity']} before", "fmt": "num"}, {"key": "seats", "label": "Now", "fmt": "num"},
              {"key": "reduction", "label": "Estimated reduction", "fmt": "eur"}, COL["acv"], COL["score"], COL["days"]],
        status="ok" if n else "none", note="Confirmed revenue lost: data unavailable (no billing history)."))

    exp_rows = []
    for c in ctxs:
        if c["score"]["band"] == "high":
            continue
        k, why = c["contract"], []
        if k["capacity"] > k["capacity_prev"]:
            why.append(f'{vocab["capacity"]} grew {k["capacity_prev"]} → {k["capacity"]}')
        if c["score"].get("usage_known", True) and c["score"]["activity_pct"] >= GROWTH:
            why.append(f'{vocab["activity"].lower()} up {_pct(c["score"]["activity_pct"])}')
        if why:
            exp_rows.append({**_base(c), "why": "; ".join(why), "positives": len(c["positives"])})
    exp_rows.sort(key=lambda r: (r["days_to_renewal"], r["score"]))
    out.append(_kpi(
        "expansion", "leadership", "Expansion candidates",
        f"{len(exp_rows)}", f'{_eur(sum(r["annual_value"] for r in exp_rows))} existing contract value (not expansion revenue)', horizon,
        "Customers who are not High risk and show growth: more seats than before, or usage up at least 10%.",
        "These are the accounts to approach about upgrades, once the renewal is secure.",
        f"Not High risk, and either {vocab['capacity'].lower()} above the previous count, or {vocab['activity'].lower()} up ≥ 10% (last 14 days against the earlier baseline). "
        "The value shown is what they pay today. Potential extra revenue is not estimated: we have no pricing or upsell data.",
        exp_rows, [{"key": "why", "label": "Why it qualifies", "fmt": "text"}, COL["acv"], COL["score"], COL["days"]],
        status="ok" if n else "none", note="Potential incremental revenue: not estimated."))

    # ---------------------------------------------------------------- CSM
    util_rows, no_usage = [], 0
    usage = {u.account_id: u for u in session.scalars(select(UsageStat).where(UsageStat.client_id == client_id))}
    for c in ctxs:
        u = usage.get(c["account"]["id"])
        if u is None:
            no_usage += 1
            continue
        util_rows.append({**_base(c), "utilisation": u.utilization, "used": round(u.metric, 1), "capacity": c["contract"]["capacity"],
                          "low": u.utilization < LOW_UTIL})
    util_rows.sort(key=lambda r: r["utilisation"])
    avg_util = sum(r["utilisation"] for r in util_rows) / len(util_rows) if util_rows else None
    what_util = ("Hours logged (monthly pace) divided by retainer hours bought." if hours else
                 f"Average daily active users (last 14 days) divided by {vocab['capacity'].lower()} purchased.")
    out.append(_kpi(
        "utilisation", "csm", "Capacity utilisation",
        _pct(avg_util) if avg_util is not None else "Data unavailable",
        f'{sum(1 for r in util_rows if r["low"])} of {len(util_rows)} below {_pct(LOW_UTIL)}' if util_rows else "No usage source connected",
        f"last 14 days · {horizon}",
        what_util + " It measures how much of what was bought is in use; it is not a count of licensed users who logged in.",
        "Customers using little of what they pay for are the first to question the renewal.",
        f"Simple average across the {len(util_rows)} customers with usage data in this period ({no_usage} without). Accounts below {_pct(LOW_UTIL)} are highlighted.",
        util_rows, [{"key": "utilisation", "label": "Utilisation", "fmt": "pct"}, {"key": "used", "label": "Used (daily avg)" if not hours else "Hours logged", "fmt": "num"},
                    {"key": "capacity", "label": "Purchased", "fmt": "num"}, COL["score"], COL["acv"], COL["days"]],
        status="ok" if util_rows else "none"))

    feats = defaultdict(list)
    for f in session.scalars(select(FeatureUsage).where(FeatureUsage.client_id == client_id)):
        if f.account_id in ids:
            feats[f.account_id].append(f)
    dec_rows = []
    for c in ctxs:
        fl = feats.get(c["account"]["id"], [])
        down = [f for f in fl if f.value_prev > 0 and (f.value - f.value_prev) / f.value_prev <= FEATURE_DROP]
        if len(down) >= FEATURE_MIN:
            down.sort(key=lambda f: (f.value - f.value_prev) / f.value_prev)
            dec_rows.append({**_base(c), "features": "; ".join(f'{f.feature} {f.value_prev:g} → {f.value:g} ({_pct((f.value - f.value_prev) / f.value_prev)})' for f in down),
                             "adoption": f'{sum(1 for f in fl if f.value > 0)} of {len(fl)} features in use', "n_down": len(down)})
    dec_rows.sort(key=lambda r: (-r["n_down"], r["days_to_renewal"]))
    out.append(_kpi(
        "features", "csm", "Customers with falling feature use",
        f"{len(dec_rows)} of {n}" if feats else "Data unavailable", f"at least {FEATURE_MIN} features down ≥ {_pct(-FEATURE_DROP)}" if feats else "No feature data connected",
        f"last 30 days vs the 30 before · {horizon}",
        f"Customers where at least {FEATURE_MIN} features are used at least {_pct(-FEATURE_DROP)} less than in the previous 30 days.",
        "Falling use of core features usually comes before a customer questions the value of the product.",
        f"For each feature: (use in the last 30 days − use in the 30 days before) ÷ use before ≤ −25%. A customer is listed when {FEATURE_MIN} or more features cross that line.",
        dec_rows, [{"key": "features", "label": "Declining features", "fmt": "text"}, {"key": "adoption", "label": "Adoption", "fmt": "text"}, COL["score"], COL["acv"], COL["days"]],
        status="ok" if feats else "none"))

    last_call = {}
    for cv in session.scalars(select(Conversation).where(Conversation.client_id == client_id)):
        if cv.kind != "import_pending" and (cv.account_id not in last_call or cv.date > last_call[cv.account_id]):
            last_call[cv.account_id] = cv.date
    call_rows = []
    for c in ctxs:
        d = last_call.get(c["account"]["id"])
        ago = (today - d).days if d else None
        call_rows.append({**_base(c), "last_call": d.isoformat() if d else None, "days_since": ago, "covered": ago is not None and ago <= CALL_DAYS})
    call_rows.sort(key=lambda r: (r["covered"], -(r["days_since"] if r["days_since"] is not None else 10_000)))
    covered = sum(1 for r in call_rows if r["covered"])
    out.append(_kpi(
        "calls", "csm", "Recent conversation coverage",
        _pct(covered / n) if n and has["calls"] else "Data unavailable" if not has["calls"] else "–",
        f"{covered} of {n} customers spoken to in the last {CALL_DAYS} days" if has["calls"] else "No call source connected",
        f"last {CALL_DAYS} days · {horizon}",
        f"Share of renewing customers with at least one recorded conversation (any call transcript) in the last {CALL_DAYS} days.",
        "A customer nobody has spoken to is a customer whose risks nobody has heard.",
        f"Customers renewing in the next {window} days with a conversation dated within {CALL_DAYS} days, divided by all renewals in that period. "
        "Every kind of recorded conversation counts; the data does not label QBRs separately.",
        call_rows, [{"key": "last_call", "label": "Last conversation", "fmt": "date"}, {"key": "days_since", "label": "Days ago", "fmt": "num"},
                    COL["score"], COL["acv"], COL["days"]],
        status="ok" if has["calls"] and n else "none"))

    tix = []
    if has["support"]:
        for t in session.scalars(select(Ticket).where(Ticket.client_id == client_id, Ticket.status.in_(("open", "pending")), Ticket.priority == "high")):
            if t.account_id in ids:
                tix.append((t.account_id, t))
    by_id = {c["account"]["id"]: c for c in ctxs}
    tix_rows = [{**_base(by_id[a]), "subject": t.subject, "status": t.status, "severity": t.priority, "category": t.category.replace("_", " "),
                 "age_days": (today - t.opened).days} for a, t in tix]
    tix_rows.sort(key=lambda r: (-r["age_days"], r["days_to_renewal"]))
    out.append(_kpi(
        "tickets", "csm", "Urgent open tickets",
        f"{len(tix_rows)}" if has["support"] else "Data unavailable",
        f'across {len({r["account_id"] for r in tix_rows})} customers' if has["support"] else "No support source connected",
        f"currently open · customers renewing in the next {window} days",
        "Support tickets with high priority that are still open or pending.",
        "An unresolved urgent problem during renewal talks erodes trust faster than almost anything else.",
        f"Count of tickets with priority high and status open or pending, for customers renewing in the next {window} days. Age = days since the ticket was opened.",
        tix_rows, [{"key": "subject", "label": "Ticket", "fmt": "text"}, {"key": "status", "label": "Status", "fmt": "text"},
                   {"key": "age_days", "label": "Open for (days)", "fmt": "num"}, COL["score"], COL["acv"], COL["days"]],
        status="ok" if has["support"] else "none"))

    inv_rows = []
    if has["billing"]:
        for i in session.scalars(select(Invoice).where(Invoice.client_id == client_id, Invoice.paid_on.is_(None), Invoice.due < today)):
            if i.account_id in ids:
                inv_rows.append({**_base(by_id[i.account_id]), "number": i.number, "amount": i.amount, "days_overdue": (today - i.due).days})
    inv_rows.sort(key=lambda r: -r["days_overdue"])
    out.append(_kpi(
        "invoices", "csm", "Overdue invoices",
        f"{len(inv_rows)}" if has["billing"] else "Data unavailable",
        f'{_eur(sum(r["amount"] for r in inv_rows))} unpaid across {len({r["account_id"] for r in inv_rows})} customers' if has["billing"] else "No billing records connected",
        f"as of today · customers renewing in the next {window} days",
        "Invoices past their due date and not yet paid.",
        "Late payment is an early sign of a customer pulling back, and a topic to raise before the renewal call.",
        f"Invoices with no payment date and a due date before today, for customers renewing in the next {window} days.",
        inv_rows, [{"key": "number", "label": "Invoice", "fmt": "text"}, {"key": "amount", "label": "Amount", "fmt": "eur"},
                   {"key": "days_overdue", "label": "Days overdue", "fmt": "num"}, COL["score"], COL["days"]],
        status="ok" if has["billing"] else "none"))

    return {"window": window, "horizons": list(HORIZONS), "renewals": n, "total_value": total,
            "sources": {"usage": has["usage"], "support": has["support"], "billing": has["billing"], "calls": has["calls"]},
            "kpis": out}
