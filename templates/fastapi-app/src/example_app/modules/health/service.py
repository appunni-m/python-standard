"""Health-status application service."""

from example_app.modules.health.models import HealthStatus


class HealthService:
    """Build the application's small health response."""

    def __init__(self, application_name: str) -> None:
        """Create the service with the application identity it reports."""
        self._application_name = application_name

    def check(self) -> HealthStatus:
        """Return a process-level health status and application name."""
        return HealthStatus(status="ok", application=self._application_name)
