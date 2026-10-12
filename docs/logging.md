# Application logging

`std.logging` configures Python's standard logging pipeline once from the
application composition root. It provides environment defaults, a readable
console formatter, newline-delimited JSON, and a typed custom-format path. It
does not add a logging dependency.

## Environment presets

Pass the application's environment to `configure_logging`. `format: auto` and
an unset `level` select these defaults:

| Environment | Default level | Default format | Color |
| --- | --- | --- | --- |
| `development` (`dev`, `local`) | `DEBUG` | Human-readable console | Automatically on for a terminal |
| `test` | `WARNING` | Human-readable console | Off unless explicitly enabled |
| `staging` (`stage`) | `INFO` | JSON | Off |
| `production` (`prod`) | `INFO` | JSON | Off |

Staging uses the production JSON shape so deployments can exercise the same
log collection path before production. Set `level` or `format` to override a
profile independently. `LoggingEnvironment` validates canonical environment
names and accepts the aliases shown above.

## Configure from YAML

Keep settings in the application's single YAML file and let
`std.config` resolve the environment placeholders:

```yaml
application:
  name: ${APP_NAME:-Example API}
  environment: ${APP_ENV:-development}

logging:
  level: ${LOG_LEVEL:-null}
  format: ${LOG_FORMAT:-auto}
  stream: ${LOG_STREAM:-stdout}
  color: ${LOG_COLOR:-auto}
  include_source: ${LOG_INCLUDE_SOURCE:-false}
  date_format: ${LOG_DATE_FORMAT:-null}
  custom_format: ${LOG_CUSTOM_FORMAT:-null}
  custom_style: ${LOG_CUSTOM_STYLE:-%}
  logger_levels: {}
```

The application settings aggregate references `LoggingConfig`; `main.py` is
the only place that creates settings and configures logging:

```python
from app.core.settings import Settings
from std.logging import configure_logging


def main() -> None:
    settings = Settings()
    configure_logging(
        settings.logging,
        environment=settings.application.environment,
        service_name=settings.application.name,
    )
    # Construct services and inject dependencies after logging starts.


if __name__ == "__main__":
    main()
```

The [FastAPI app template](https://github.com/appunni-m/python-standard/tree/main/templates/fastapi-app) demonstrates this startup path with injected services and a managed lifespan.

## Formats and overrides

`LoggingConfig.format` accepts:

| Value | Behavior |
| --- | --- |
| `auto` | Select console for development/tests and JSON for staging/production. |
| `console` | Human-readable UTC timestamp, level, logger, and message. |
| `json` | One JSON object per line, with UTC timestamp, level, logger, message, environment, optional service/source, exception details, and `extra` fields. |
| `custom` | Use `custom_format` with the `%`, `{`, or `$` style supported by `logging.Formatter`. |

Other options are:

| Field | Purpose |
| --- | --- |
| `level` | Override the environment's default with `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. `None` keeps the profile default. |
| `stream` | Write to `stdout` (default) or `stderr`. |
| `color` | `auto`, `always`, or `never`; applies to console output. |
| `include_source` | Add filename and line to console output, or file, line, and function fields to JSON. |
| `date_format` | Override the console/custom timestamp format. Without it, timestamps use ISO 8601 UTC. |
| `custom_format` | Required for `format: custom`; supports the standard formatter fields. |
| `custom_style` | The formatter style: `%`, `{`, or `$`. |
| `logger_levels` | Optional mapping of named logger paths to severity levels. It does not disable other loggers. |

JSON records include arbitrary logging `extra` values as top-level fields.
Exception records use `exception.type`, `exception.message`, and
`exception.stacktrace`; source fields are opt-in. Keep passwords, tokens,
personal data, and other secrets out of messages, exception text, and `extra`
values. This formatter does not attempt to infer or redact secrets.

The default destination is stdout so a hosting runtime can collect and route
the event stream. Set `stream: stderr` when the application uses stdout for
another protocol. Configure file rotation or external transport in the
deployment's log collector rather than adding hidden file writes to application
startup, following the [Twelve-Factor logs guidance](https://12factor.net/logs).

## Direct use

```python
from std.logging import LoggingConfig, configure_logging

configure_logging(
    LoggingConfig(level="INFO", format="json", include_source=True),
    environment="production",
    service_name="billing-api",
)
```

Application modules should use `logging.getLogger(__name__)` and log with
standard levels. Add request or trace correlation fields with `extra`, for
example `logger.info("request complete", extra={"request_id": request_id})`.
JSON keeps those fields structured so a collector can index them. The field
shape follows common logging concepts and can be mapped to the
[OpenTelemetry log data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).

Python's [`logging` API](https://docs.python.org/3/howto/logging.html) provides
the levels, logger hierarchy, handlers, and formatters used here. Django's
[logging guide](https://docs.djangoproject.com/en/5.2/howto/logging/) is another
example of keeping logging policy in application configuration. This module
uses a validated subset so YAML remains declarative and cannot load arbitrary
formatter factories.
