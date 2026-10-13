# Standard FastAPI consumer sample

This is a small, independently assembled order API that exercises the published
Standard `0.2.3` artifact and its FastAPI integration. It uses feature-local
routes, schemas, domain models, repositories, settings, and services. `main.py`
is the composition root; the only settings construction sites are in that
module, and each startup path constructs one `Settings` instance.

## Install and run

From this directory, create a virtual environment and install the pinned
published dependency and the sample's development tools:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
std --version
std guide
std guide --format json
std skill install
make check
make run
```

The API listens at `http://127.0.0.1:8000` by default. The sample pins
`standard[fastapi]==0.2.3`; pip resolves the published core and matching FastAPI
integration distributions from the configured package index.

## Example API

Create an order:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/orders \
  -H 'content-type: application/json' \
  -d '{"customer_reference":"customer-42","amount_cents":2500}'
```

The response contains an order ID and starts in `queued` state. The injected
`BackgroundService` marks it `processed`; fetch it at
`/api/v1/orders/{order_id}`. `GET /metadata` shows the validated application
name and environment, and `/health` uses Standard's health endpoint helper.

## Configuration

`config/settings.yaml` groups application, logging, and orders settings. It
uses Standard's `${NAME:-default}` interpolation. For example, set `APP_NAME`
and `APP_ENV` to configure the name and logging profile. Pydantic's direct
environment and dotenv sources are excluded; environment values enter through
declared YAML placeholders.

The sample uses an in-memory repository so it needs no database or container.
It is a consumer exercise, not a production persistence design. See
[EVALUATION.md](EVALUATION.md) for the tested scope, exact evidence, friction,
and current API observations.
