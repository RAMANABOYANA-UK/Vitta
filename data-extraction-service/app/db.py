"""PostgreSQL persistence layer (Neon/Supabase-compatible).

Stores validated ParsedBill results. Uses SQLAlchemy with a JSONB column for
the full ParsedBill payload, plus indexed columns for common query fields.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class ParsedBillRecord(Base):
    """Database record for a validated ParsedBill."""

    __tablename__ = "parsed_bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(128), unique=True, nullable=False, index=True)
    document_type = Column(String(16), nullable=False, index=True)
    provider_name = Column(String(256), nullable=True)
    provider_npi = Column(String(16), nullable=True, index=True)
    payer_name = Column(String(256), nullable=True)
    patient_account_ref = Column(String(64), nullable=True, index=True)
    service_date_start = Column(DateTime, nullable=True)
    service_date_end = Column(DateTime, nullable=True)
    statement_date = Column(DateTime, nullable=True)

    # Totals
    billed_total = Column(Float, nullable=True)
    allowed_total = Column(Float, nullable=True)
    paid_total = Column(Float, nullable=True)
    patient_responsibility_total = Column(Float, nullable=True)

    # Scoring
    anomaly_score = Column(Float, nullable=True)
    anomaly_is_anomalous = Column(Boolean, nullable=True)
    appeal_score = Column(Float, nullable=True)
    appeal_recommendation = Column(String(32), nullable=True)

    # Full payload
    payload = Column(JSONB, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Database:
    """Thin wrapper around SQLAlchemy for the service."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.database_url
        self.engine = None
        self.SessionLocal = None
        self.connected = False

    def connect(self) -> "Database":
        """Create the engine and session factory. No-op if no URL configured."""
        if not self.url:
            logger.warning("No DATABASE_URL configured — persistence disabled")
            return self
        try:
            self.engine = create_engine(self.url, echo=settings.db_echo)
            self.SessionLocal = sessionmaker(
                bind=self.engine, autoflush=False, autocommit=False
            )
            Base.metadata.create_all(self.engine)
            self.connected = True
            logger.info("Connected to PostgreSQL database")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to connect to database: %s", exc)
            self.connected = False
        return self

    def save_parsed_bill(self, bill: Any) -> Optional[int]:
        """Persist a ParsedBill. Returns the record id, or None if not connected."""
        if not self.connected or self.SessionLocal is None:
            return None

        payload = bill.model_dump(mode="json")
        meta = bill.metadata
        totals = bill.totals
        anomaly = bill.pricing_anomaly
        appeal = bill.appeal_success

        record = ParsedBillRecord(
            document_id=bill.document_id,
            document_type=meta.document_type.value if meta.document_type else None,
            provider_name=meta.provider_name,
            provider_npi=meta.provider_npi,
            payer_name=meta.payer_name,
            patient_account_ref=meta.patient_account_ref,
            service_date_start=(
                datetime.combine(meta.service_date_start, datetime.min.time())
                if meta.service_date_start
                else None
            ),
            service_date_end=(
                datetime.combine(meta.service_date_end, datetime.min.time())
                if meta.service_date_end
                else None
            ),
            statement_date=(
                datetime.combine(meta.statement_date, datetime.min.time())
                if meta.statement_date
                else None
            ),
            billed_total=totals.billed_total if totals else None,
            allowed_total=totals.allowed_total if totals else None,
            paid_total=totals.paid_total if totals else None,
            patient_responsibility_total=(
                totals.patient_responsibility_total if totals else None
            ),
            anomaly_score=anomaly.score if anomaly else None,
            anomaly_is_anomalous=anomaly.is_anomalous if anomaly else None,
            appeal_score=appeal.score if appeal else None,
            appeal_recommendation=appeal.recommendation if appeal else None,
            payload=payload,
        )

        try:
            with self.SessionLocal() as session:
                # Upsert on document_id
                existing = (
                    session.query(ParsedBillRecord)
                    .filter(ParsedBillRecord.document_id == bill.document_id)
                    .first()
                )
                if existing:
                    # Update fields
                    for key, value in record.__dict__.items():
                        if key.startswith("_") or key in ("id", "created_at"):
                            continue
                        setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                    session.commit()
                    return existing.id
                session.add(record)
                session.commit()
                return record.id
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to save ParsedBill %s: %s", bill.document_id, exc)
            return None

    def get_parsed_bill(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a ParsedBill by document_id. Returns the payload dict."""
        if not self.connected or self.SessionLocal is None:
            return None
        try:
            with self.SessionLocal() as session:
                record = (
                    session.query(ParsedBillRecord)
                    .filter(ParsedBillRecord.document_id == document_id)
                    .first()
                )
                if record:
                    return record.payload
                return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to fetch ParsedBill %s: %s", document_id, exc)
            return None


_db: Optional[Database] = None


def get_db() -> Database:
    """Singleton database instance."""
    global _db
    if _db is None:
        _db = Database().connect()
    return _db