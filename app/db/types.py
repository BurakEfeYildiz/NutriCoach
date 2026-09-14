"""Exact two-decimal values and a UTC timestamp contract across DB backends."""
from datetime import timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric
from sqlalchemy.types import TypeDecorator


class Amount(TypeDecorator):
    """SQLite stores integer hundredths; PostgreSQL stores NUMERIC(12, 2)."""
    impl = Numeric(12, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(BigInteger() if dialect.name == 'sqlite' else Numeric(12, 2))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = Decimal(str(value))
        if not value.is_finite() or abs(value) >= Decimal('10000000000') or value != value.quantize(Decimal('.01')):
            raise ValueError('Sonlu ve en fazla iki ondalıklı değer gerekli.')
        return int(value * 100) if dialect.name == 'sqlite' else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100 if dialect.name == 'sqlite' else Decimal(value)).quantize(Decimal('.01'))


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Saat dilimi zorunlu.')
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == 'sqlite' else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
