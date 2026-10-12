"""Unit tests for the example health service."""

from example_app.modules.health.models import HealthStatus
from example_app.modules.health.service import HealthService


def test_health_service_reports_application_name() -> None:
    service = HealthService(application_name="Example API")

    assert service.check() == HealthStatus(status="ok", application="Example API")
