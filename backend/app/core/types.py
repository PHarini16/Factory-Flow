"""Custom SQLAlchemy types.

DecimalString stores Decimal values as exact text so that SQLite (which has no
decimal type) never converts money or quantities to binary floating point.
"""
from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalString(TypeDecorator):
    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("float is not allowed for Decimal columns; use Decimal")
        return format(Decimal(value), "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)
