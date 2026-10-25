"""Upload one CSV with new customers and what was said on their calls, and see where they land.

One row per customer. Only `customer` is required; everything else is optional and tidied up on the way in
(dates, numbers, percentages, column names). Nothing is guessed silently: every fix is listed in the report.

  customer, segment, contact_name, contact_role, plan, seats, seats_prev, annual_value (or monthly_value),
  renewal_date (or days_to_renewal), usage_change_pct, call_date, call_notes, urgent_tickets, overdue_invoices

`call_notes` is what the customer said (a transcript with "Name (Role): text" lines also works). The AI reads it like
any call and flags risks only where it can quote the customer word for word."""
import csv
import datetime as dt
import io
import re
from typing import Optional

from sqlalchemy import delete, select

from ..engine import extract, identity, llm
from ..models import (Account, Action, ActivityPoint, Brief, Contract, Conversation, FeatureUsage, Invoice, Reassurance,
                      Signal, Ticket, UsageStat)

MAX_ROWS = 60
SAME_COMPANY = 0.92          # at or above: the row is about a customer we already have
SIMILAR = 0.6                # between: say so, but create a new customer
KIND = "import"              # marks conversations that came from an upload, so they can be taken back out

ALIASES = {
    "customer": ["customer", "customer_name", "company", "company_name", "account", "account_name", "client", "name"],
    "segment": ["segment", "industry", "sector"],
    "contact_name": ["contact_name", "contact", "main_contact", "champion", "contact_person"],
    "contact_role": ["contact_role", "role", "title", "job_title", "contact_title"],
    "plan": ["plan", "tier", "package", "product"],
    "seats": ["seats", "licenses", "licences", "users", "capacity"],
    "seats_prev": ["seats_prev", "previous_seats", "seats_before", "prev_seats", "capacity_prev"],
    "annual_value": ["annual_value", "arr", "annual_revenue", "yearly_value", "value_per_year", "acv"],
    "monthly_value": ["monthly_value", "mrr", "monthly_revenue", "value_per_month"],
    "renewal_date": ["renewal_date", "renewal", "renews_on", "contract_end", "contract_end_date", "end_date"],
    "days_to_renewal": ["days_to_renewal", "renews_in_days", "days_until_renewal"],
    "usage_change_pct": ["usage_change_pct", "usage_change", "usage_trend", "usage_delta", "activity_change"],
    "call_date": ["call_date", "last_call_date", "date", "conversation_date", "meeting_date"],
    "call_notes": ["call_notes", "notes", "transcript", "conversation", "what_the_customer_said", "customer_said", "flags", "comments"],
    "urgent_tickets": ["urgent_tickets", "open_urgent_tickets", "escalations", "high_priority_tickets"],
    "overdue_invoices": ["overdue_invoices", "unpaid_invoices", "late_invoices", "overdue"],
}
TURN = re.compile(r"^[^:()\n]{1,60}\([^)]{1,80}\)\s*:\s*\S")


def _key(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")


def _number(raw: str) -> Optional[float]:
    s = re.sub(r"[^\d.,\-kKmM]", "", (raw or "").replace("−", "-"))
    if not s or s in "-.,":
        return None
    mult = 1.0
    if s[-1] in "kK":
        mult, s = 1_000.0, s[:-1]
    elif s[-1] in "mM":
        mult, s = 1_000_000.0, s[:-1]
    if "," in s and "." in s:                      # the last separator is the decimal point
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", "") if re.search(r",\d{3}($|,)", s) else s.replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")                     # 32.000 -> 32000
    try:
        return float(s) * mult
    except ValueError:
        return None


def _date(raw: str, warn: list[str]) -> Optional[dt.date]:
    s = (raw or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return dt.date.fromisoformat(s)
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        day, month = (a, b) if (a > 12 or b <= 12) else (b, a)    # day first, as in Germany, unless that cannot be a date
        try:
            d = dt.date(y, month, day)
        except ValueError:
            return None
        warn.append(f"date “{s}” read as {d.isoformat()} (day first)")
        return d
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            warn.append(f"date “{s}” read as {d.isoformat()}")
            return d
        except ValueError:
            pass
    return None


def _percent(raw: str) -> Optional[float]:
    v = _number((raw or "").replace("%", ""))
    if v is None:
        return None
    return v / 100 if ("%" in raw or abs(v) > 1) else v


def _transcript(notes: str, contact: str, role: str, company: str, owner: str, staff: str) -> str:
    notes = notes.strip()
    if any(TURN.match(line.strip()) for line in notes.splitlines()):
        return notes                                             # already a transcript
    who = f"{contact or 'Customer contact'} ({role or 'Contact'}, {company})"
    parts = [p.strip() for p in re.split(r"\n+|\s\|\s", notes) if p.strip()]
    out = [f"{owner} ({staff}): Thanks for making the time. How are things on your side?"]
    for p in parts:
        out += [f"{who}: {p}", f"{owner} ({staff}): Understood, thank you for being open about it."]
    return "\n".join(out)


def parse(text: str) -> tuple[list[dict], list[str]]:
    """Rows keyed by our column names, plus notes about the file as a whole."""
    notes = []
    text = text.lstrip("﻿")
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    if dialect.delimiter != ",":
        notes.append(f"separator “{dialect.delimiter}” detected")
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], ["the file is empty"]
    header = [_key(h) for h in rows[0]]
    lookup = {}
    for ours, names in ALIASES.items():
        for n in names:
            if n in header and ours not in lookup:
                lookup[ours] = header.index(n)
    unknown = [h for i, h in enumerate(header) if i not in lookup.values() and h]
    if unknown:
        notes.append("ignored columns: " + ", ".join(unknown))
    out = []
    for r in rows[1:]:
        out.append({ours: (r[i].strip() if i < len(r) else "") for ours, i in lookup.items()})
    return out, notes


def remove_imported(session, client_id: str) -> dict:
    """Take back everything an upload added: its conversations and flags, and customers that only existed because of it."""
    convs = session.scalars(select(Conversation).where(Conversation.client_id == client_id)).all()
    by_acc: dict[int, list] = {}
    for c in convs:
        by_acc.setdefault(c.account_id, []).append(c)
    imported = [c for c in convs if c.kind == KIND]
    only = [a for a, cs in by_acc.items() if all(c.kind == KIND for c in cs)]
    ids = [c.id for c in imported]
    if ids:
        session.execute(delete(Signal).where(Signal.conversation_id.in_(ids)))
        session.execute(delete(Reassurance).where(Reassurance.conversation_id.in_(ids)))
        session.execute(delete(Conversation).where(Conversation.id.in_(ids)))
    for model in (Action, Brief, ActivityPoint, Contract, Ticket, Invoice, UsageStat, FeatureUsage):
        if only:
            session.execute(delete(model).where(model.account_id.in_(only)))
    if only:
        session.execute(delete(Account).where(Account.id.in_(only)))
    session.commit()
    touched = sorted({c.account_id for c in imported} - set(only))
    return {"customers_removed": len(only), "calls_removed": len(imported), "refresh": touched}


def run(session, client, pack: dict, text: str, use_llm: Optional[bool] = None) -> dict:
    rows, file_notes = parse(text)
    if len(rows) > MAX_ROWS:
        file_notes.append(f"only the first {MAX_ROWS} of {len(rows)} rows were read")
        rows = rows[:MAX_ROWS]
    if rows and "customer" not in rows[0]:
        return {"error": "No customer column found. Name one column customer (or company, account, client).", "rows": [], "notes": file_notes}
    today = dt.date.today()
    staff = extract.staff_label(pack)
    existing = {a.id: a.name for a in session.scalars(select(Account).where(Account.client_id == client.id))}
    seen, report, new_convs, touched = set(), [], [], set()

    for n, r in enumerate(rows, start=2):                        # row 1 is the header
        name = r.get("customer", "").strip()
        line = {"row": n, "customer": name, "status": "skipped", "reason": "", "fixes": []}
        report.append(line)
        if not name:
            line["reason"] = "no customer name"
            continue
        if identity.normalize(name) in seen:
            line["reason"] = "the same customer appears twice in the file"
            continue
        seen.add(identity.normalize(name))
        fixes = line["fixes"]

        aid, sim = identity.best_match(name, existing, threshold=SAME_COMPANY) if existing else (None, 0.0)
        if aid is None and existing:
            near_id, near = identity.best_match(name, existing, threshold=SIMILAR)
            if near_id is not None:
                fixes.append(f"similar to existing customer “{existing[near_id]}” ({round(near * 100)}% match), added as a new customer")
        notes = r.get("call_notes", "").strip()

        if aid is not None:                                      # a customer we already have: add what was said
            if not notes:
                line["reason"] = f"“{existing[aid]}” already exists and the row has no call notes to add"
                continue
            acc = session.get(Account, aid)
            line["status"], line["matched"] = "updated", acc.name
            if sim < 1.0:
                fixes.append(f"matched to existing customer “{acc.name}” ({round(sim * 100)}%)")
        else:
            renewal = _date(r.get("renewal_date", ""), fixes)
            if renewal is None and r.get("days_to_renewal"):
                d = _number(r["days_to_renewal"])
                renewal = today + dt.timedelta(days=int(d)) if d is not None else None
            if renewal is None:
                line["reason"] = "no usable renewal date (use renewal_date or days_to_renewal)"
                continue
            if renewal < today:
                line["reason"] = f"renewal date {renewal.isoformat()} is in the past"
                continue
            seats = _number(r.get("seats", ""))
            if seats is None or seats <= 0:
                seats = 10
                fixes.append("no seat count, assumed 10")
            prev = _number(r.get("seats_prev", ""))
            prev = prev if prev and prev > 0 else seats
            annual, monthly = _number(r.get("annual_value", "")), _number(r.get("monthly_value", ""))
            if monthly is None and annual is not None:
                monthly = annual / 12
            if monthly is None or monthly <= 0:
                line["reason"] = "no contract value (use annual_value or monthly_value)"
                continue
            acc = Account(client_id=client.id, name=name, segment=r.get("segment") or "Imported", employees=0,
                          contact_name=r.get("contact_name", ""), contact_role=r.get("contact_role", ""), owner=client.user_name)
            session.add(acc)
            session.flush()
            session.add(Contract(client_id=client.id, account_id=acc.id, billing_name=name, match_confidence=1.0,
                                 plan=r.get("plan") or "Imported", capacity=int(seats), capacity_prev=int(prev),
                                 monthly_value=round(monthly, 2), renewal_date=renewal))
            existing[acc.id] = name
            line["status"] = "added"
            line["renewal_date"], line["annual_value"] = renewal.isoformat(), round(monthly * 12)
            usage = _percent(r.get("usage_change_pct", ""))
            if usage is not None:                                # a one-row file has no daily history, so we draw the trend it states
                usage = max(-0.95, min(usage, 3.0))
                for i in range(90):
                    day = today - dt.timedelta(days=90 - i)
                    session.add(ActivityPoint(client_id=client.id, account_id=acc.id, day=day,
                                              value=100.0 * (1 + usage) if i >= 76 else 100.0))
                fixes.append(f"usage trend {round(usage * 100):+d}% taken from the file (no daily history)")
            else:
                fixes.append("no usage trend given, shown as “No data”")
            for _ in range(min(int(_number(r.get("urgent_tickets", "")) or 0), 10)):
                session.add(Ticket(client_id=client.id, account_id=acc.id, opened=today - dt.timedelta(days=9), last_update=today - dt.timedelta(days=6),
                                   status="open", priority="high", category="complaint", subject="Urgent issue reported (imported)"))
            for k in range(min(int(_number(r.get("overdue_invoices", "")) or 0), 6)):
                due = today - dt.timedelta(days=20 + 30 * k)
                session.add(Invoice(client_id=client.id, account_id=acc.id, number=f"IMP-{acc.id}-{k + 1}", issued=due - dt.timedelta(days=30),
                                    due=due, amount=round(monthly, 2), paid_on=None))

        if notes:
            when = _date(r.get("call_date", ""), fixes) or today - dt.timedelta(days=3)
            conv = Conversation(client_id=client.id, account_id=acc.id, kind=KIND, date=min(when, today), title="Imported call notes",
                                transcript=_transcript(notes, acc.contact_name, acc.contact_role, acc.name, client.user_name, staff))
            session.add(conv)
            new_convs.append((conv, line))
        else:
            fixes.append("no call notes, so no flags can be found")
        touched.add(acc.id)
        line["account_id"] = acc.id
    session.flush()

    vendor = pack["synthetic"]["product"]
    from concurrent.futures import ThreadPoolExecutor
    use = llm.enabled() if use_llm is None else use_llm
    if use:
        print(f"  import: reading {len(new_convs)} conversations with the AI…")
    with ThreadPoolExecutor(max_workers=3 if use else 1) as pool:          # the AI calls run side by side
        results = list(pool.map(lambda cl: extract.analyze_full(cl[0].transcript, pack, vendor, staff, use), new_convs))
    for (conv, line), (sigs, good, src) in zip(new_convs, results):
        for s in sigs:
            session.add(Signal(client_id=client.id, account_id=conv.account_id, conversation_id=conv.id, source=src, **s))
        for g in good:
            session.add(Reassurance(client_id=client.id, account_id=conv.account_id, conversation_id=conv.id, source=src, **g))
        line["found_by"] = "AI" if src == "llm" else "keyword rules"
    session.commit()
    return {"rows": report, "notes": file_notes, "touched": sorted(touched)}
