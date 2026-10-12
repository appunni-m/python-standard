"""Unit coverage for the optional HTTP client package."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from std.http import (
    ApiKeyAuth,
    AuthBase,
    AuthConfig,
    BasicAuth,
    BearerAuth,
    HttpClient,
    HttpClientError,
    RetryConfig,
)


def run(coroutine: Any) -> Any:
    """Run one async scenario in the synchronous pytest suite."""
    return asyncio.run(coroutine)


def make_client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> HttpClient:
    """Build a client that routes requests through HTTPX's in-process transport."""
    return HttpClient(transport=httpx.MockTransport(handler), **kwargs)


class User(BaseModel):
    """Response model used by model-helper tests."""

    name: str
    age: int


def test_auth_handlers_apply_headers_and_redact_secrets() -> None:
    request = httpx.Request("GET", "https://example.test")

    assert AuthBase().auth_flow(request) is request
    assert BearerAuth("bearer-secret").auth_flow(request).headers["authorization"] == (
        "Bearer bearer-secret"
    )

    basic = BasicAuth("üser", "pāss")
    basic_request = basic.auth_flow(httpx.Request("GET", "https://example.test"))
    assert base64.b64decode(basic_request.headers["authorization"][6:]).decode("utf-8") == (
        "üser:pāss"
    )

    api_key = ApiKeyAuth("key-secret", header_name="X-Custom-Key", prefix="ApiKey")
    api_request = api_key.auth_flow(httpx.Request("GET", "https://example.test"))
    assert api_request.headers["x-custom-key"] == "ApiKey key-secret"
    assert "bearer-secret" not in repr(BearerAuth("bearer-secret"))
    assert "pāss" not in repr(basic)
    assert "key-secret" not in repr(api_key)


def test_auth_handlers_reject_empty_secrets_and_invalid_headers() -> None:
    with pytest.raises(ValueError, match="bearer token"):
        BearerAuth(" ")
    with pytest.raises(ValueError, match="API key"):
        ApiKeyAuth("")
    with pytest.raises(ValueError, match="header name"):
        ApiKeyAuth("value", header_name=" ")


def test_retry_config_defaults_and_validation() -> None:
    config = RetryConfig()
    assert config.max_attempts == 3
    assert config.retry_statuses == [500, 502, 503, 504]
    assert config.retry_methods == ["GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"]
    assert config.backoff_factor == 0.5
    assert config.jitter is True
    assert config.retry_exceptions == []

    normalized = RetryConfig(retry_statuses=[503, 503, 429], retry_methods=["get", "GET", "post"])
    assert normalized.retry_statuses == [503, 429]
    assert normalized.retry_methods == ["GET", "POST"]
    with pytest.raises(ValidationError):
        RetryConfig(max_attempts=0)
    with pytest.raises(ValidationError):
        RetryConfig(retry_statuses=[99])
    with pytest.raises(ValidationError):
        RetryConfig(backoff_factor=float("inf"))
    with pytest.raises(ValidationError):
        RetryConfig(retry_methods=[""])
    with pytest.raises(ValidationError):
        RetryConfig(retry_exceptions=[ValueError()])  # type: ignore[list-item]


def test_auth_config_keeps_refresh_values_out_of_repr() -> None:
    config = AuthConfig(
        auth=BearerAuth("access-secret"),
        refresh_token="refresh-secret",
        refresh_callback=lambda: "new-secret",
    )
    assert "refresh-secret" not in repr(config)
    assert "access-secret" not in repr(config)
    assert config.refresh_callback is not None
    assert config.refresh_callback() == "new-secret"


def test_constructor_normalizes_legacy_retry_count_and_timeout() -> None:
    client = HttpClient(retries=0, timeout=2.5)
    assert client.retry_config.max_attempts == 1
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect == 2.5

    with pytest.raises(ValueError, match="negative"):
        HttpClient(retries=-1)
    with pytest.raises(TypeError, match="boolean"):
        HttpClient(retries=True)
    with pytest.raises(ValueError, match="finite and non-negative"):
        HttpClient(timeout=-0.1)
    with pytest.raises(ValueError, match="finite and non-negative"):
        HttpClient(timeout=float("inf"))


def test_client_initialization_errors_are_sanitized() -> None:
    async def scenario() -> None:
        client = HttpClient(base_url="https://host\nsecret")
        with pytest.raises(HttpClientError) as error:
            await client.get("path")
        assert "secret" not in str(error.value)

    run(scenario())


def test_request_joins_base_url_and_merges_headers_case_insensitively() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async def scenario() -> None:
        async with make_client(
            handler,
            base_url="https://example.test/api/",
            default_headers={"X-Mode": "default"},
        ) as client:
            response = await client.get("users", headers={"x-mode": "request"}, params={"q": "a"})
            assert response.status_code == 200

    run(scenario())
    assert requests[0].url.path == "/api/users"
    assert requests[0].url.params["q"] == "a"
    assert requests[0].headers["X-Mode"] == "request"


def test_bearer_auth_works_with_relative_urls_and_native_httpx_auth() -> None:
    authorization_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization_headers.append(request.headers["authorization"])
        return httpx.Response(200)

    async def scenario() -> None:
        async with make_client(
            handler,
            base_url="https://example.test/api/",
            auth_config=AuthConfig(auth=BearerAuth("secret")),
        ) as client:
            await client.get("private")
            await client.get("native", auth=httpx.BasicAuth("user", "password"))

    run(scenario())
    assert authorization_headers[0] == "Bearer secret"
    assert authorization_headers[1].startswith("Basic ")


def test_custom_auth_base_is_applied_to_httpx_request() -> None:
    class HeaderAuth(AuthBase):
        def auth_flow(self, request: httpx.Request) -> httpx.Request:
            request.headers["X-Auth"] = "custom"
            return request

    headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers["x-auth"])
        return httpx.Response(200)

    async def scenario() -> None:
        async with make_client(handler, auth_config=AuthConfig(auth=HeaderAuth())) as client:
            await client.get("https://example.test")

    run(scenario())
    assert headers == ["custom"]


def test_retries_retryable_status_once_and_return_final_response() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200)

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(max_attempts=2, backoff_factor=0, jitter=False),
        ) as client:
            response = await client.get("https://example.test")
            assert response.status_code == 200

    run(scenario())
    assert calls == 2


def test_retries_respect_method_status_and_stream_replayability() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(503)

    async def scenario() -> None:
        config = RetryConfig(max_attempts=3, backoff_factor=0, jitter=False)
        async with make_client(handler, retries=config) as client:
            await client.post("https://example.test/post")

            async def body() -> Any:
                yield b"a"
                yield b"b"

            response = await client.put("https://example.test/upload", content=body())
            assert response.status_code == 503

    run(scenario())
    assert calls == ["POST", "PUT"]


def test_not_found_is_returned_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(max_attempts=4, backoff_factor=0, jitter=False),
        ) as client:
            response = await client.request("GET", "https://example.test/missing")
            assert response.status_code == 404

    run(scenario())
    assert calls == 1


@pytest.mark.parametrize(
    ("method", "model_method"),
    [
        ("post", "post_model"),
        ("put", "put_model"),
        ("patch", "patch_model"),
        ("delete", "delete_model"),
    ],
)
def test_all_remaining_verbs_and_model_helpers(method: str, model_method: str) -> None:
    methods_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods_seen.append(request.method)
        return httpx.Response(200, json={"name": "Ada", "age": 37})

    async def scenario() -> None:
        async with make_client(handler) as client:
            response = await getattr(client, method)("https://example.test/user")
            assert response.status_code == 200
            model = await getattr(client, model_method)("https://example.test/user", User)
            assert model == User(name="Ada", age=37)

    run(scenario())
    assert methods_seen == [method.upper(), method.upper()]


def test_redirect_setting_controls_followed_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/final"})
        return httpx.Response(200, json={"path": request.url.path})

    async def scenario() -> None:
        async with make_client(handler, follow_redirects=True) as client:
            followed = await client.get("https://example.test/start")
            assert followed.status_code == 200
            assert followed.json() == {"path": "/final"}
        async with make_client(handler, follow_redirects=False) as client:
            not_followed = await client.get("https://example.test/start")
            assert not_followed.status_code == 302

    run(scenario())


def test_refresh_callback_replaces_bearer_token_once() -> None:
    seen_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"]
        seen_tokens.append(token)
        return httpx.Response(401 if token == "Bearer expired" else 200)

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(max_attempts=2, backoff_factor=0, jitter=False),
            auth_config=AuthConfig(
                auth=BearerAuth("expired"),
                refresh_token="refresh-secret",
                refresh_callback=lambda: "fresh",
            ),
        ) as client:
            response = await client.get("https://example.test")
            assert response.status_code == 200

    run(scenario())
    assert seen_tokens == ["Bearer expired", "Bearer fresh"]


def test_refresh_callback_replaces_api_key_once() -> None:
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["x-api-key"]
        seen_keys.append(key)
        return httpx.Response(401 if key == "expired" else 200)

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(max_attempts=2, backoff_factor=0),
            auth_config=AuthConfig(
                auth=ApiKeyAuth("expired"),
                refresh_callback=lambda: "fresh",
            ),
        ) as client:
            response = await client.get("https://example.test")
            assert response.status_code == 200

    run(scenario())
    assert seen_keys == ["expired", "fresh"]


def test_refresh_failure_is_sanitized_and_keeps_response_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    def fail_refresh() -> str:
        raise RuntimeError("refresh-secret leaked by provider")

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(max_attempts=2, backoff_factor=0),
            auth_config=AuthConfig(auth=BearerAuth("expired"), refresh_callback=fail_refresh),
        ) as client:
            with pytest.raises(HttpClientError) as error:
                await client.get("https://example.test")
            assert error.value.status_code == 401
            assert error.value.response is not None
            assert "refresh-secret" not in str(error.value)

    run(scenario())


def test_transport_failures_are_wrapped_without_secret_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    retry_calls = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal retry_calls
        retry_calls += 1
        if retry_calls == 1:
            raise httpx.ConnectError("access-token-secret", request=request)
        return httpx.Response(200)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("access-token-secret", request=request)

    message: list[str] = []

    async def scenario() -> None:
        async with make_client(
            retry_handler,
            retries=RetryConfig(max_attempts=2, backoff_factor=0),
        ) as client:
            response = await client.get("https://example.test/path?token=query-secret")
            assert response.status_code == 200

        async with make_client(failing_handler, retries=1) as client:
            with pytest.raises(HttpClientError) as error:
                await client.get("https://example.test/path?token=query-secret")
            assert error.value.status_code is None
            message.append(str(error.value))

    with caplog.at_level(logging.WARNING):
        run(scenario())
    assert retry_calls == 2
    assert "access-token-secret" not in message[0]
    assert "access-token-secret" not in caplog.text
    assert "query-secret" not in caplog.text


def test_configured_exception_classes_can_be_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("transient but sensitive detail")
        return httpx.Response(200)

    async def scenario() -> None:
        async with make_client(
            handler,
            retries=RetryConfig(
                max_attempts=2,
                backoff_factor=0,
                retry_exceptions=[ValueError],
            ),
        ) as client:
            response = await client.get("https://example.test")
            assert response.status_code == 200

    run(scenario())
    assert calls == 2


def test_get_model_parses_json_and_wraps_http_and_validation_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bad-status":
            return httpx.Response(502, json={"secret": "response-secret"})
        if request.url.path == "/bad-model":
            return httpx.Response(200, json={"name": "invalid"})
        if request.url.path == "/bad-json":
            return httpx.Response(200, content=b"not json")
        return httpx.Response(200, json={"name": "Ada", "age": 37})

    async def scenario() -> None:
        async with make_client(handler) as client:
            assert await client.get_model("https://example.test/user", User) == User(
                name="Ada", age=37
            )
            with pytest.raises(HttpClientError) as status_error:
                await client.get_model("https://example.test/bad-status", User)
            assert status_error.value.status_code == 502
            assert status_error.value.response is not None
            assert "response-secret" not in str(status_error.value)
            with pytest.raises(HttpClientError) as model_error:
                await client.get_model("https://example.test/bad-model", User)
            assert model_error.value.status_code == 200
            with pytest.raises(HttpClientError, match="did not match User"):
                await client.get_model("https://example.test/bad-json", User)

    run(scenario())


def test_http_client_close_is_idempotent_and_client_is_lazy() -> None:
    async def scenario() -> None:
        client = make_client(lambda request: httpx.Response(200))
        assert client._client is None
        await client.close()
        first = await client.client
        await client.close()
        await client.close()
        assert first.is_closed
        second = await client.client
        assert second is not first
        await client.close()

    run(scenario())


def test_client_cleanup_errors_are_sanitized() -> None:
    class FailingCloseTransport(httpx.AsyncBaseTransport):
        """Transport whose cleanup failure contains a value that must be hidden."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        async def aclose(self) -> None:
            raise RuntimeError("cleanup-secret")

    async def scenario() -> None:
        client = HttpClient(transport=FailingCloseTransport())
        await client.client
        with pytest.raises(HttpClientError) as error:
            await client.close()
        assert "cleanup-secret" not in str(error.value)
        await client.close()

    run(scenario())
