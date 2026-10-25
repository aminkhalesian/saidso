"""Demo data for the other sources a real customer would connect: product usage, support tickets and invoices.
It is generated from what the engine already knows about each account (risk band, signals, activity), so the story
stays consistent: an account that says it will pay late has overdue invoices, one that says nobody logs in has
fewer logins and collapsed features. It does NOT change any score, signal or quote."""
from functools import lru_cache
from pathlib import Path
from statistics import mean
import datetime as dt
import random

import yaml
from sqlalchemy import delete, select

from ..models import ActivityPoint, FeatureUsage, Invoice, Ticket, UsageStat

DIR = Path(__file__).resolve().parents[1] / "demo_sources"
UNRESOLVED = ("open", "pending")


@lru_cache
def load_cfg(pack_id: str) -> dict:
    return yaml.safe_load((DIR / f"{pack_id}.yaml").read_text(encoding="utf-8"))


def clear(session, client_id: str):
    for model in (Ticket, Invoice, UsageStat, FeatureUsage):
        session.execute(delete(model).where(model.client_id == client_id))


def usage_numbers(series: list[float], capacity: int, mode: str) -> tuple[float, float, float]:
    """(daily average now, daily average before, utilization against what was purchased).
    Same windows as the risk score (last 14 days against the earlier baseline), so the percentages agree on screen."""
    now = mean(series[-14:]) if series else 0.0
    before = (mean(series[:45]) if len(series) >= 45 else mean(series)) if series else 0.0
    pace = now * 30 if mode == "hours" else now                  # hours: monthly pace against the retainer hours
    return round(now, 2), round(before, 2), round(pace / capacity, 3) if capacity else 0.0


def add_sources(session, client, pack: dict, seed: int = 7) -> dict:
    from .. import service                                   # late import: service imports the engine
    cfg = load_cfg(pack["id"])
    rng = random.Random(f"{seed}-{client.id}-sources")
    today = dt.date.today()
    clear(session, client.id)
    counts = {"tickets": 0, "invoices": 0, "usage": 0, "features": 0}
    for ctx in service.contexts(session, client.id):
        aid, band = ctx["account"]["id"], ctx["score"]["band"]
        types = {s["signal_type"] for s in ctx["signals"] if s["feedback"] != "dismissed"}
        cap = ctx["contract"]["capacity"]
        series = [p.value for p in session.scalars(
            select(ActivityPoint).where(ActivityPoint.account_id == aid).order_by(ActivityPoint.day))]

        # ---- product usage
        cur, prev, util = usage_numbers(series, cap, cfg["mode"])
        prev = prev or 1.0
        raw_cur, raw_prev = sum(series[-30:]), sum(series[-60:-30] or series[-30:])
        k = rng.uniform(1.15, 1.6) if cfg["mode"] == "users" else 1 / rng.uniform(5, 9)
        last_login = today - dt.timedelta(days={"low": rng.randint(0, 1), "medium": rng.randint(1, 4),
                                                 "high": rng.randint(3, 13)}[band])
        session.add(UsageStat(account_id=aid, client_id=client.id, metric=cur, metric_prev=prev, utilization=util,
                              logins=max(1, round(raw_cur * k)), logins_prev=max(1, round(raw_prev * k)),
                              last_login=last_login))
        counts["usage"] += 1
        trend = min(1.5, max(0.2, cur / prev)) if prev else 1.0
        scale = 30 if cfg["mode"] == "hours" else 1        # hours per day -> hours per 30 days for the workstreams
        collapse = set(rng.sample(range(len(cfg["features"])), 2)) if (band == "high" or "low_adoption" in types) else set()
        for i, f in enumerate(cfg["features"]):
            before = round(prev * scale * f["share"] * rng.uniform(0.85, 1.15))
            now = round(before * trend * rng.uniform(0.85, 1.15))
            if i in collapse:
                now = round(before * rng.uniform(0.1, 0.4))
            session.add(FeatureUsage(client_id=client.id, account_id=aid, feature=f["name"], value=now, value_prev=before))
            counts["features"] += 1

        # ---- support tickets
        pool, used = cfg["tickets"], set()

        def ticket(category, status, opened_ago, stale_days, priority=None):
            subject = rng.choice([t for t in pool[category] if t not in used] or pool[category])
            used.add(subject)
            opened = today - dt.timedelta(days=opened_ago)
            last = min(today, opened + dt.timedelta(days=rng.randint(1, 7))) if status == "solved" \
                else max(opened, today - dt.timedelta(days=stale_days))
            prio = priority or {"complaint": "high", "bug": rng.choice(["normal", "high"]), "billing": "normal"}.get(category, "low")
            session.add(Ticket(client_id=client.id, account_id=aid, opened=opened, last_update=last, status=status,
                               priority=prio, category=category, subject=subject))
            counts["tickets"] += 1

        for _ in range({"low": rng.randint(1, 3), "medium": rng.randint(2, 4), "high": rng.randint(2, 5)}[band]):
            ticket(rng.choice(["how_to", "feature_request", "bug"]), "solved", rng.randint(8, 80), 0)
        if band == "low":
            if rng.random() < 0.3:
                ticket(rng.choice(["how_to", "feature_request"]), "open", rng.randint(1, 5), rng.randint(0, 2))
        elif band == "medium":
            for _ in range(rng.choice([1, 1, 2])):
                ticket(rng.choice(["bug", "bug", "billing"]), rng.choice(["open", "pending"]), rng.randint(4, 25), rng.randint(2, 9))
        else:
            ticket("complaint", "pending", rng.randint(12, 50), rng.randint(6, 20), "high")
            for _ in range(rng.choice([1, 2, 3])):
                ticket(rng.choice(["complaint", "bug", "bug"]), rng.choice(["open", "pending"]), rng.randint(8, 45), rng.randint(3, 15))
        if "low_adoption" in types:
            ticket("how_to", "open", rng.randint(10, 30), rng.randint(5, 14), "normal")
        if "pricing_complaint" in types:
            ticket("billing", "open", rng.randint(5, 20), rng.randint(2, 8), "normal")

        # ---- invoices (newest first); unpaid and past due is the payment issue
        net = cfg["invoice"]["net_days"]
        overdue = 2 if "payment_delays" in types else (rng.choice([0, 0, 1]) if band == "high" else 0)
        late_k = 2 if band == "medium" and rng.random() < 0.4 else None
        for k_ in range(4):
            issued = today - dt.timedelta(days=net + 6 + 30 * k_)
            due = issued + dt.timedelta(days=net)
            if k_ < overdue:
                paid = None
            elif k_ == late_k:
                paid = due + dt.timedelta(days=rng.randint(4, 12))
            else:
                paid = due - dt.timedelta(days=rng.randint(0, 6))
            session.add(Invoice(client_id=client.id, account_id=aid, number=f"{cfg['invoice']['prefix']}-{issued:%y%m}-{aid:03d}",
                                issued=issued, due=due, amount=round(ctx["contract"]["monthly_value"], 2), paid_on=min(paid, today) if paid else None))
            counts["invoices"] += 1
    session.commit()
    return counts
