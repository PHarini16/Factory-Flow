"""Shared helpers: rounding, financial year, document numbering, audit logging, settings."""
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, InvoiceSequence, SystemSetting, User

TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


def q2(x: Decimal) -> Decimal:
    """Round money to paise using commercial rounding (half-up)."""
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def q4(x: Decimal) -> Decimal:
    return Decimal(x).quantize(FOUR, rounding=ROUND_HALF_UP)


def dec(x: Any) -> Decimal:
    """Convert API input to Decimal via string (never via float arithmetic)."""
    return Decimal(str(x))


def financial_year(d: date) -> str:
    """Indian financial year April-March, e.g. 2026-27."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


_FORMATS = {
    "INV": "FF/{fy}/{n:04d}",
    "CN": "FF/CN/{fy}/{n:04d}",
    "DSP": "DSP/{fy}/{n:04d}",
    "RCPT": "RCPT/{fy}/{n:04d}",
    "PO": "PO/{fy}/{n:04d}",
    "RUN": "RUN/{fy}/{n:04d}",
    "ORD": "ORD/{fy}/{n:05d}",
}


def next_number(db: Session, prefix: str, on_date: date) -> str:
    fy = financial_year(on_date)
    seq = db.scalar(select(InvoiceSequence).where(InvoiceSequence.prefix == prefix, InvoiceSequence.financial_year == fy))
    if seq is None:
        seq = InvoiceSequence(prefix=prefix, financial_year=fy, last_number=0)
        db.add(seq)
        db.flush()
    seq.last_number += 1
    db.flush()
    return _FORMATS[prefix].format(fy=fy, n=seq.last_number)


def jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id: int | None,
          old: dict | None = None, new: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, username=user.username if user else "system",
                    action=action, entity_type=entity_type, entity_id=entity_id,
                    old_values=jsonable(old) if old else None, new_values=jsonable(new) if new else None))


def get_setting(db: Session, key: str, default: str) -> str:
    row = db.get(SystemSetting, key)
    return row.value if row else default
