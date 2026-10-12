# HTTP client

`standard-http` provides an asynchronous HTTPX client under `std.http`. It
keeps connection ownership, authentication, retries, and response validation
in one small API.

## Install

From this repository, install the core and HTTP projects together:

```shell
python -m pip install . packages/standard-http
```

The core project defines a `standard[http]` convenience extra. It becomes
available from PyPI after both the updated core distribution and this provider
have been published. The `standard-http` distribution owns only `std.http`.

## Make a request

```python
from std.http import HttpClient

async with HttpClient(base_url="https://api.example.com/v1/") as client:
    response = await client.get("users", params={"active": "true"})
    response.raise_for_status()
    users = response.json()
```

`HttpClient` supports `request`, `get`, `post`, `put`, `patch`, and `delete`.
Each method accepts HTTPX request options such as `params`, `json`, `data`,
`files`, and per-request `timeout`. Relative URLs are joined with `base_url`.
Per-request headers override defaults case-insensitively. A request returns
4xx and 5xx responses as-is; call `raise_for_status()` when the caller wants
HTTP status errors.

For advanced connection-pool access, `await client.client` returns the
underlying `httpx.AsyncClient`. The constructor's `transport` option accepts an
HTTPX async transport such as `httpx.MockTransport`, which is useful for
testing integrations without a network service.

## Authenticate

```python
from std.http import ApiKeyAuth, AuthConfig, BasicAuth, BearerAuth, HttpClient

client = HttpClient(
    base_url="https://api.example.com",
    auth_config=AuthConfig(auth=BearerAuth("token")),
)
```

`BearerAuth` sets `Authorization: Bearer …`. `BasicAuth` encodes username and
password as UTF-8 before Base64 encoding. `ApiKeyAuth` uses `X-API-Key` by
default and can target a custom header or add a prefix. All three redact their
secret values from `repr()` output.

Native `httpx.Auth` implementations and custom `AuthBase` subclasses are also
accepted. A custom handler implements `auth_flow(request)` and returns the
request after adding authentication.

For a refreshable bearer or API-key handler, supply a synchronous callback
that returns a new secret. It runs once after a 401 response, then the request
is retried if its method and body are replayable and the retry budget permits
it:

```python
auth = AuthConfig(
    auth=BearerAuth("expired-token"),
    refresh_token="refresh-token",
    refresh_callback=refresh_access_token,
)
```

The callback takes no arguments. It can close over `refresh_token` or another
credential source. Callback errors produce a sanitized `HttpClientError`;
the callback's exception text is not included.

## Retries and timeouts

```python
from std.http import HttpClient, RetryConfig

retries = RetryConfig(
    max_attempts=4,
    retry_statuses=[429, 500, 502, 503, 504],
    retry_methods=["GET", "HEAD"],
    backoff_factor=0.25,
    jitter=True,
)
client = HttpClient(base_url="https://api.example.com", timeout=5, retries=retries)
```

`max_attempts` counts the initial request. The integer `retries` constructor
form is retained for compatibility and also means total attempts; zero means
one attempt. By default, the client retries transport errors and the listed
server statuses for GET, HEAD, PUT, DELETE, OPTIONS, and TRACE. It does not
retry a streamed or otherwise non-replayable request body. Backoff doubles per
attempt, is capped at 60 seconds, and adds bounded jitter when enabled.
`retry_exceptions` adds exception classes on top of the default HTTPX
transport-error handling.

Timeout accepts a number of seconds, an `httpx.Timeout`, or `None` to disable
the default timeout. Per-request timeout options follow HTTPX behavior.

## Validate a response model

```python
from pydantic import BaseModel
from std.http import HttpClient


class User(BaseModel):
    name: str
    age: int


async with HttpClient(base_url="https://api.example.com") as client:
    user = await client.get_model("users/42", User)
```

The client provides `get_model`, `post_model`, `put_model`, `patch_model`, and
`delete_model`. These helpers require a successful status and valid JSON that
matches the Pydantic model. Failures raise `HttpClientError` with the status
and response attached when available.

## Errors and cleanup

`HttpClientError` exposes `status_code` and `response` when available. Its
message and retry logs omit URL, query, header, credential, and underlying
exception text so secrets are not copied into logs. Network and timeout errors
are wrapped after the configured attempts; HTTP status responses remain
ordinary responses for non-model methods.

Use `async with` for deterministic cleanup. `close()` is idempotent and closes
the connection pool; the next request can lazily create a fresh HTTPX client.

## Tests

The package tests use HTTPX `MockTransport` to exercise request construction,
auth, retries, error paths, and cleanup without depending on public services.
