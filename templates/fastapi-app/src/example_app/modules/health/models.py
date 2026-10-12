"""Health-module domain data structures."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Process health data returned by the health service.

    This is an in-memory domain model, not a database model. Add persistence
    models inside the owning module only when the application gains a database.
    """

    status: Literal["ok"]
    application: str
