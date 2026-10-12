"""Local socket integration coverage for the Standard HTTP client."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from std.http import AuthConfig, BearerAuth, HttpClient, HttpClientError, RetryConfig

pytestmark = pytest.mark.integration


def test_http_client_auth_relative_url_timeout_and_server_cleanup() -> None:
    """Exercise real local TCP requests, auth headers, timeout wrapping, and shutdown."""

    async def scenario() -> None:
        received_headers: list[bytes] = []
        slow_response_finished = asyncio.Event()

        async def handle_request(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            request_line = await reader.readline()
            headers: list[bytes] = []
            while (line := await reader.readline()) not in (b"\r\n", b""):
                headers.append(line)
            received_headers.extend(headers)

            if b"/slow " in request_line:
                await asyncio.sleep(0.15)
            else:
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 11\r\n"
                    b"Connection: close\r\n\r\n"
                    b'{"ok":true}'
                )
                await writer.drain()
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            if b"/slow " in request_line:
                slow_response_finished.set()

        server = await asyncio.start_server(handle_request, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        base_url = f"http://127.0.0.1:{port}/api/"

        try:
            async with HttpClient(
                base_url=base_url,
                auth_config=AuthConfig(auth=BearerAuth("local-secret")),
            ) as client:
                response = await client.get("health")
                assert response.status_code == 200
                assert response.json() == {"ok": True}

            assert any(
                b"Authorization: Bearer local-secret" in header for header in received_headers
            )

            async with HttpClient(
                base_url=base_url,
                timeout=0.02,
                retries=RetryConfig(max_attempts=1),
            ) as client:
                with pytest.raises(HttpClientError) as error:
                    await client.get("slow")
                assert error.value.status_code is None
                assert "127.0.0.1" not in str(error.value)
            await asyncio.wait_for(slow_response_finished.wait(), timeout=1)
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
