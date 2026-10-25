"""Build one realistic customer from scratch in the isolated test database: usage history, contract and a call transcript.
Everything the engine then says about the customer is computed from this data; nothing about the outcome is stored here."""
import datetime as dt

from app import service
from app.engine import brief, extract
from app.models import Account, ActivityPoint, Client, Contract, Conversation, SessionLocal, init_db
from app.packs import load_pack

PACK = load_pack("saas")
STAFF = extract.staff_label(PACK)
BASE = 100.0


def transcript(*customer_turns: str) -> str:
    out = [f"Lena Vogt ({STAFF}): Thanks for making the time. How are things on your side?"]
    for t in customer_turns:
        out += [f"Mia Novak (Operations Lead, Acme): {t}", f"Lena Vogt ({STAFF}): Understood, thank you for being open about it."]
    return "\n".join(out)


def build(session, client_id: str, usage_change, turns: list[str], days_to_renewal: int = 40, usage_days: int = 90) -> int:
    """usage_change: -0.6 means the last 14 days are 60% below the earlier baseline. Returns the account id."""
    init_db()
    session.add(Client(id=client_id, name=f"Scenario {client_id}", pack_id="saas", user_name="Lena Vogt"))
    session.commit()
    acc = Account(client_id=client_id, name=f"Acme {client_id}", segment="Software", employees=120, contact_name="Mia Novak",
                  contact_role="Operations Lead", owner="Lena Vogt")
    session.add(acc)
    session.commit()
    today = dt.date.today()
    session.add(Contract(client_id=client_id, account_id=acc.id, billing_name=acc.name, match_confidence=1.0, plan="Team",
                         capacity=60, capacity_prev=60, monthly_value=2400.0, renewal_date=today + dt.timedelta(days=days_to_renewal)))
    for i in range(usage_days if usage_change is not None else 0):       # None = no usage data at all
        day = today - dt.timedelta(days=usage_days - i)
        value = BASE * (1 + usage_change) if i >= usage_days - 14 else BASE      # the last 14 days vs. everything before
        session.add(ActivityPoint(client_id=client_id, account_id=acc.id, day=day, value=value))
    session.add(Conversation(client_id=client_id, account_id=acc.id, kind="call", date=today - dt.timedelta(days=5),
                             title="Check-in call", transcript=transcript(*turns)))
    session.commit()
    extract.run(session, session.get(Client, client_id), PACK, use_llm=False)
    return acc.id


def analyse(session, client_id: str, account_id: int):
    """Score, evidence, AI brief and retention plan for one account, exactly as the pipeline builds them."""
    ctx = service.context(session, client_id, account_id)
    service.with_sources(session, client_id, ctx, PACK)
    payload, source = brief.make(ctx, PACK)
    return ctx, payload, source
