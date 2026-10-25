"""Canonical data model. Every row carries client_id, so clients never see each other's data.
SQLite by default; set DATABASE_URL to a Postgres URL for a real deployment."""
from typing import Optional
import datetime as dt
import os
from pathlib import Path

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parent.parent / 'engine.db'}")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Client(Base):
    """A company using the product (e.g. a SaaS vendor or an agency)."""
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    pack_id: Mapped[str] = mapped_column(String)
    user_name: Mapped[str] = mapped_column(String)      # the CSM / account manager using it


class Account(Base):
    """A customer of the client."""
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    segment: Mapped[str] = mapped_column(String)
    employees: Mapped[int] = mapped_column(Integer)
    contact_name: Mapped[str] = mapped_column(String)
    contact_role: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)


class Contract(Base):
    """Subscription, retainer, policy... whatever renews. Linked to an account by identity matching."""
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=True)
    billing_name: Mapped[str] = mapped_column(String)
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    plan: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)          # seats, retainer hours, ...
    capacity_prev: Mapped[int] = mapped_column(Integer)
    monthly_value: Mapped[float] = mapped_column(Float)
    renewal_date: Mapped[dt.date] = mapped_column(Date)


class ActivityPoint(Base):
    """Daily activity metric (active users, billable hours, ...)."""
    __tablename__ = "activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    day: Mapped[dt.date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="call")
    date: Mapped[dt.date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String)
    transcript: Mapped[str] = mapped_column(Text)


class PlantedLabel(Base):
    """Ground truth for the eval harness (synthetic data only). is_decoy = looks risky but isn't."""
    __tablename__ = "planted_labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    signal_type: Mapped[str] = mapped_column(String)
    line: Mapped[str] = mapped_column(Text)
    is_decoy: Mapped[bool] = mapped_column(Boolean, default=False)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    signal_type: Mapped[str] = mapped_column(String)
    speaker: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    quote: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String)                 # llm | rules
    feedback: Mapped[str] = mapped_column(String, default="open")  # open | confirmed | dismissed


class Brief(Base):
    __tablename__ = "briefs"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)


class Action(Base):
    """A drafted next step. Nothing leaves the system until a person approves it."""
    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    signal_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)                   # email | task | meeting
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="template")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | approved | dismissed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    decided_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


def init_db(drop: bool = False):
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
