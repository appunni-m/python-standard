"""Timezone helpers for database-backed model properties."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps


def ensure_utc(function: Callable[..., datetime | None]) -> property:
    """Decorate a property getter so returned datetimes are UTC-aware.

    Naive values are interpreted as UTC, matching the historical helper
    contract. Aware values are converted to UTC. ``None`` passes through.
    """

    @wraps(function)
    def getter(instance: object) -> datetime | None:
        value = function(instance)
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("ensure_utc property getter must return datetime or None")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    return property(getter)
