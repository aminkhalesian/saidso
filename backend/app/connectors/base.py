"""Connector interface. Each connector pulls from one source, normalizes into the canonical model,
and leaves account matching to engine.identity. Real connectors (HubSpot, Gong, Stripe...) implement
the same interface; the hackathon uses only synthetic and CSV sources."""
from abc import ABC, abstractmethod

from sqlalchemy import select

from ..engine import identity
from ..models import Account, Contract


class Connector(ABC):
    name: str = "base"

    @abstractmethod
    def sync(self, session, client, pack: dict) -> dict:
        """Load data for `client` into the session. Returns a small summary dict."""


def match_contracts(session, client_id: str) -> dict:
    """Link billing contracts to CRM accounts by name similarity."""
    accounts = {a.id: a.name for a in session.scalars(select(Account).where(Account.client_id == client_id))}
    matched = unmatched = 0
    for c in session.scalars(select(Contract).where(Contract.client_id == client_id)):
        aid, conf = identity.best_match(c.billing_name, accounts)
        c.account_id, c.match_confidence = aid, conf
        matched += aid is not None
        unmatched += aid is None
    session.commit()
    return {"matched": matched, "unmatched": unmatched}
