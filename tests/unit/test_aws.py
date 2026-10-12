"""Unit coverage for the optional AWS package without network access."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from std.aws import (
    AWSCredentials,
    DefaultCredentialProvider,
    DynamoDBConfig,
    DynamoTable,
    EnvironmentCredentialProvider,
    ExplicitCredentialProvider,
    ProfileCredentialProvider,
    S3Client,
    S3ClientConfig,
    SQSClient,
    SQSConfig,
    SQSConsumer,
)
from std.service import ServiceState


class FakeBody:
    """Asynchronous response body that records cleanup."""

    def __init__(self, value: bytes) -> None:
        self.value = value
        self.closed = False

    async def read(self) -> bytes:
        """Return configured response bytes."""
        return self.value

    async def close(self) -> None:
        """Record that response content was released."""
        self.closed = True


class FakeClient:
    """Async SDK double with overridable operation responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, Callable[..., Any]] = {}
        self.closed = False

    def __getattr__(self, name: str) -> Callable[..., Any]:
        async def call(*args: Any, **kwargs: Any) -> Any:
            recorded = dict(kwargs)
            if args:
                recorded["_args"] = args
            self.calls.append((name, recorded))
            response = self.responses.get(name)
            if response is None:
                return {}
            result = response(*args, **kwargs)
            if hasattr(result, "__await__"):
                return await result
            return result

        return call


class FakeClientContext:
    """Async context manager wrapping the fake SDK client."""

    def __init__(self, client: FakeClient) -> None:
        self.client = client

    async def __aenter__(self) -> FakeClient:
        return self.client

    async def __aexit__(self, *_: object) -> None:
        self.client.closed = True


class FakeSession:
    """SDK session double that captures service and client arguments."""

    def __init__(self, client: FakeClient) -> None:
        self.client_value = client
        self.region_name = "ca-central-1"
        self.client_calls: list[tuple[str, dict[str, Any]]] = []

    def client(self, service_name: str, **kwargs: Any) -> FakeClientContext:
        """Record client construction and return its fake context manager."""
        self.client_calls.append((service_name, kwargs))
        return FakeClientContext(self.client_value)


class FakeSDK:
    """aioboto3 module double."""

    def __init__(self, client: FakeClient) -> None:
        self.session = FakeSession(client)

    def Session(self) -> FakeSession:
        """Return the configured fake session."""
        return self.session


@pytest.fixture
def aws_client(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeClient, FakeSession]:
    """Install a fake aioboto3 SDK for one test."""
    from std.aws import _client

    sdk_client = FakeClient()
    sdk = FakeSDK(sdk_client)
    monkeypatch.setattr(_client, "import_module", lambda _: sdk)

    async def no_credentials(_: DefaultCredentialProvider) -> None:
        """Let the fake SDK exercise its own default chain."""
        return None

    monkeypatch.setattr(DefaultCredentialProvider, "get_credentials", no_credentials)
    return sdk_client, sdk.session


class User(BaseModel):
    """DynamoDB example model."""

    user_id: str
    name: str
    age: int = 0


def test_credentials_redact_secrets_and_preserve_optional_values() -> None:
    credentials = AWSCredentials(
        access_key_id=" access ",
        secret_access_key=" secret ",
        session_token=" token ",
        region=" us-east-1 ",
    )

    assert "secret" not in repr(credentials)
    assert credentials.to_dict() == {
        "aws_access_key_id": "access",
        "aws_secret_access_key": "secret",
        "aws_session_token": "token",
        "region_name": "us-east-1",
    }
    with pytest.raises(ValidationError):
        AWSCredentials(access_key_id="", secret_access_key="secret")


def test_environment_credentials_require_a_complete_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        assert await EnvironmentCredentialProvider().get_credentials() is None

        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "session")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        credentials = await EnvironmentCredentialProvider().get_credentials()
        assert credentials is not None
        assert credentials.session_token == "session"
        assert credentials.region == "eu-west-1"

    asyncio.run(scenario())


def test_explicit_credentials_and_profile_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        credentials = await ExplicitCredentialProvider("key", "secret").get_credentials()
        assert credentials.access_key_id == "key"

        class Frozen:
            access_key = "profile-key"
            secret_key = "profile-secret"
            token = "profile-token"

        class Credentials:
            def get_frozen_credentials(self) -> Frozen:
                """Return static profile values from the fake AWS SDK."""
                return Frozen()

        class Session:
            region_name = "us-west-2"

            def __init__(self, **kwargs: Any) -> None:
                assert kwargs == {"profile_name": "development"}

            def get_credentials(self) -> Credentials:
                return Credentials()

        import std.aws.auth.credentials as credentials_module

        offloaded_calls: list[str] = []

        async def run_inline(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            """Run blocking SDK doubles inline because sandbox threads are unavailable."""
            offloaded_calls.append(function.__name__)
            return function(*args, **kwargs)

        monkeypatch.setattr(credentials_module.asyncio, "to_thread", run_inline)

        monkeypatch.setattr(
            credentials_module,
            "import_module",
            lambda name: SimpleNamespace(Session=Session) if name == "boto3" else None,
        )
        profile = await ProfileCredentialProvider("development").get_credentials()
        assert profile is not None
        assert profile.access_key_id == "profile-key"
        assert profile.session_token == "profile-token"
        assert profile.region == "us-west-2"
        assert offloaded_calls == ["_resolve_credentials"]

    asyncio.run(scenario())


def test_default_provider_uses_sdk_chain_and_returns_no_credentials_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        class Session:
            region_name = "us-east-2"

            def __init__(self, **kwargs: Any) -> None:
                assert kwargs == {}

            def get_credentials(self) -> None:
                return None

        import std.aws.auth.credentials as credentials_module

        offloaded_calls: list[str] = []

        async def run_inline(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            """Run blocking SDK doubles inline because sandbox threads are unavailable."""
            offloaded_calls.append(function.__name__)
            return function(*args, **kwargs)

        monkeypatch.setattr(credentials_module.asyncio, "to_thread", run_inline)

        monkeypatch.setattr(
            credentials_module,
            "import_module",
            lambda name: SimpleNamespace(Session=Session) if name == "boto3" else None,
        )
        assert await DefaultCredentialProvider().get_credentials() is None
        assert offloaded_calls == ["_resolve_credentials"]

    asyncio.run(scenario())


def test_s3_passes_region_credentials_and_endpoint_and_closes_client(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, session = aws_client
        s3 = S3Client(
            S3ClientConfig(bucket_name="assets", region="eu-west-1", endpoint_url="http://local"),
            ExplicitCredentialProvider("key", "secret", session_token="token", region="ignored"),
        )
        response = await s3.put_object("items/a.txt", "hello")
        assert response == {}
        assert session.client_calls == [
            (
                "s3",
                {
                    "region_name": "eu-west-1",
                    "endpoint_url": "http://local",
                    "aws_access_key_id": "key",
                    "aws_secret_access_key": "secret",
                    "aws_session_token": "token",
                },
            )
        ]
        assert client.calls[0] == (
            "put_object",
            {"Bucket": "assets", "Key": "items/a.txt", "Body": b"hello"},
        )
        assert client.closed

        regional = S3Client(
            S3ClientConfig(bucket_name="assets"),
            ExplicitCredentialProvider("key", "secret", region="ap-south-1"),
        )
        await regional.put_object("regional.txt", "body")
        assert session.client_calls[-1][1]["region_name"] == "ap-south-1"

        inherited = S3Client(S3ClientConfig(bucket_name="assets"))
        await inherited.put_object("inherited.txt", "body")
        assert session.client_calls[-1][1]["region_name"] == "ca-central-1"

    asyncio.run(scenario())


def test_s3_reads_and_closes_body_and_paginates_listing(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        body = FakeBody(b'{"name":"Ada"}')
        client.responses["get_object"] = lambda **_: {"Body": body}
        pages = iter(
            [
                {
                    "Contents": [{"Key": "one"}],
                    "IsTruncated": True,
                    "NextContinuationToken": "next",
                },
                {"Contents": [{"Key": "two"}], "IsTruncated": False},
            ]
        )
        client.responses["list_objects_v2"] = lambda **_: next(pages)
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        assert await s3.get_object_as_json("ada.json") == {"name": "Ada"}
        assert body.closed
        assert await s3.list_objects(max_keys=2) == ["one", "two"]
        list_calls = [kwargs for name, kwargs in client.calls if name == "list_objects_v2"]
        assert list_calls[1]["ContinuationToken"] == "next"

    asyncio.run(scenario())


def test_s3_raw_response_keeps_a_readable_body_after_client_closes(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        body = FakeBody(b"detached")
        client.responses["get_object"] = lambda **_: {"Body": body, "ContentLength": 8}
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        response = await s3.get_object("small.txt")
        assert client.closed
        assert body.closed
        assert response["ContentLength"] == 8
        assert await response["Body"].read() == b"detached"

    asyncio.run(scenario())


def test_s3_rejects_invalid_limits_and_http_methods() -> None:
    async def scenario() -> None:
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        with pytest.raises(ValueError, match="max_keys"):
            await s3.list_objects(max_keys=1001)
        with pytest.raises(ValueError, match="http_method"):
            await s3.get_presigned_url("object", http_method="PATCH")
        with pytest.raises(ValueError, match="metadata"):
            await s3.copy_object("source", "target", metadata={"owner": "team"})

    asyncio.run(scenario())


def test_sqs_serializes_messages_and_rejects_invalid_batch_sizes(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        sqs = SQSClient(SQSConfig(queue_url="http://local/queue"))
        await sqs.send_message({"text": "snowman ☃"})
        assert client.calls[0][1]["MessageBody"] == '{"text": "snowman ☃"}'
        with pytest.raises(ValueError, match="between 1 and 10"):
            await sqs.send_message_batch([])
        with pytest.raises(ValueError, match="one entry per message"):
            await sqs.send_message_batch(["a", "b"], [{}])
        with pytest.raises(ValueError, match="delay_seconds"):
            await sqs.send_message("a", delay_seconds=901)

    asyncio.run(scenario())


def test_sqs_parses_models_and_preserves_parse_failures(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        client.responses["receive_message"] = lambda **_: {
            "Messages": [
                {"Body": '{"user_id":"1","name":"Ada"}', "ReceiptHandle": "one"},
                {"Body": "not-json", "ReceiptHandle": "two"},
            ]
        }
        messages = await SQSClient(SQSConfig(queue_url="http://local/queue")).receive_message(
            max_number_of_messages=2,
            model_class=User,
        )
        assert messages[0]["_parsed"].name == "Ada"
        assert messages[1]["_parse_error"] == "ValidationError"

    asyncio.run(scenario())


def test_sqs_offloads_sync_handler_and_deletes_only_successes(
    aws_client: tuple[FakeClient, FakeSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        client.responses["receive_message"] = lambda **_: {
            "Messages": [
                {"Body": "ok", "ReceiptHandle": "ok"},
                {"Body": "bad", "ReceiptHandle": "bad"},
            ]
        }
        offloaded: list[str] = []

        async def run_inline(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            """Record the intended offload while avoiding forbidden sandbox threads."""
            offloaded.append("handler")
            return function(*args, **kwargs)

        import std.aws.sqs.client as sqs_module

        monkeypatch.setattr(sqs_module.asyncio, "to_thread", run_inline)

        def handler(message: Mapping[str, Any]) -> None:
            if message["Body"] == "bad":
                raise RuntimeError("handler failed")

        sqs = SQSClient(SQSConfig(queue_url="http://local/queue"))
        results = await sqs.process_messages(handler, auto_delete=True)
        assert offloaded == ["handler", "handler"]
        assert results[0]["success"] is True and results[0]["deleted"] is True
        assert results[1]["success"] is False and results[1]["deleted"] is False
        assert len([name for name, _ in client.calls if name == "delete_message"]) == 1

    asyncio.run(scenario())


def test_sqs_consumer_is_a_managed_background_service() -> None:
    async def scenario() -> None:
        processed = asyncio.Event()
        consumer = SQSConsumer(
            "http://local/queue",
            "us-east-1",
            lambda _: processed.set(),
            wait_time=0,
            retry_delay=0.01,
        )

        async def one_batch(batch_size: int) -> list[dict[str, Any]]:
            processed.set()
            consumer.stop_event.set()
            return []

        consumer.process_batch = one_batch  # type: ignore[method-assign]
        await consumer.start()
        await asyncio.wait_for(processed.wait(), timeout=1)
        await consumer.stop()
        assert consumer.state is ServiceState.STOPPED

    asyncio.run(scenario())


def test_dynamodb_serialization_is_precise_and_rejects_invalid_values() -> None:
    table = DynamoTable(DynamoDBConfig(table_name="users"), User)
    wire = table._serialize_item(
        {
            "active": True,
            "age": 34,
            "score": 1.25,
            "precision": Decimal("12345678901234567890.123"),
            "labels": {"admin", "user"},
            "payload": b"bytes",
            "nested": {"items": [None, "value"]},
        }
    )
    assert wire["active"] == {"BOOL": True}
    assert wire["age"] == {"N": "34"}
    assert wire["score"] == {"N": "1.25"}
    assert wire["precision"] == {"N": "12345678901234567890.123"}
    assert wire["labels"] == {"SS": ["admin", "user"]}
    restored = table._deserialize_item(wire)
    assert restored["active"] is True
    assert restored["age"] == Decimal("34")
    assert restored["labels"] == {"admin", "user"}
    with pytest.raises(ValueError, match="empty sets"):
        table._serialize_value(set())
    with pytest.raises(ValueError, match="finite"):
        table._serialize_value(float("nan"))
    with pytest.raises(TypeError, match="unsupported"):
        table._serialize_value(object())


def test_dynamodb_rejects_malformed_attribute_union() -> None:
    table = DynamoTable(DynamoDBConfig(table_name="users"), User)
    with pytest.raises(ValueError, match="exactly one"):
        table._deserialize_value({"S": "value", "N": "2"})
    with pytest.raises(ValueError, match="unsupported"):
        table._deserialize_value({"UNKNOWN": "value"})


def test_dynamodb_query_follows_pages_and_validates_models(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        pages = iter(
            [
                {
                    "Items": [{"user_id": {"S": "1"}, "name": {"S": "Ada"}, "age": {"N": "37"}}],
                    "LastEvaluatedKey": {"user_id": {"S": "1"}},
                },
                {"Items": [{"user_id": {"S": "2"}, "name": {"S": "Lin"}, "age": {"N": "32"}}]},
            ]
        )
        client.responses["query"] = lambda **_: next(pages)
        table = DynamoTable(DynamoDBConfig(table_name="users"), User)
        users = await table.query("user_id = :id", {":id": "1"})
        assert [user.user_id for user in users] == ["1", "2"]
        assert client.calls[0][1]["ExpressionAttributeValues"] == {":id": {"S": "1"}}
        assert client.calls[1][1]["ExclusiveStartKey"] == {"user_id": {"S": "1"}}
        with pytest.raises(ValueError, match="greater than zero"):
            await table.scan(limit=0)

    asyncio.run(scenario())


def test_dynamodb_batch_get_retries_unprocessed_keys(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        responses = iter(
            [
                {
                    "Responses": {"users": [{"user_id": {"S": "1"}, "name": {"S": "Ada"}}]},
                    "UnprocessedKeys": {
                        "users": {"Keys": [{"user_id": {"S": "2"}}], "ConsistentRead": False}
                    },
                },
                {
                    "Responses": {"users": [{"user_id": {"S": "2"}, "name": {"S": "Lin"}}]},
                    "UnprocessedKeys": {},
                },
            ]
        )
        client.responses["batch_get_item"] = lambda **_: next(responses)
        table = DynamoTable(DynamoDBConfig(table_name="users"), User)
        result = await table.batch_get_items_from_table([{"user_id": "1"}, {"user_id": "2"}])
        assert [user.user_id for user in result] == ["1", "2"]
        assert len([name for name, _ in client.calls if name == "batch_get_item"]) == 2

    asyncio.run(scenario())


def test_dynamodb_batch_write_chunks_at_service_limit(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        table = DynamoTable(DynamoDBConfig(table_name="users"), User)
        items = [{"user_id": str(index), "name": "User"} for index in range(26)]
        await table.batch_write_items_to_table(items)
        sizes = [
            len(kwargs["RequestItems"]["users"])
            for name, kwargs in client.calls
            if name == "batch_write_item"
        ]
        assert sizes == [25, 1]

    asyncio.run(scenario())


def test_credentials_handle_environment_fallback_and_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
        monkeypatch.setenv("AWS_REGION", "eu-central-1")
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        credentials = await EnvironmentCredentialProvider().get_credentials()
        assert credentials is not None
        assert credentials.region == "eu-central-1"
        assert await EnvironmentCredentialProvider().get_credentials() == credentials

        import std.aws.auth.credentials as credentials_module

        async def run_inline(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return function(*args, **kwargs)

        monkeypatch.setattr(credentials_module.asyncio, "to_thread", run_inline)

        class ProfileNotFound(Exception):
            pass

        class MissingProfileSession:
            region_name = None

            def __init__(self, **_: Any) -> None:
                pass

            def get_credentials(self) -> None:
                raise ProfileNotFound("missing")

        monkeypatch.setattr(
            credentials_module,
            "import_module",
            lambda _: SimpleNamespace(Session=MissingProfileSession),
        )
        assert await ProfileCredentialProvider("missing").get_credentials() is None
        assert await DefaultCredentialProvider(" missing ").get_credentials() is None
        assert DefaultCredentialProvider(" missing ").profile_name == "missing"

        class BrokenSession(MissingProfileSession):
            def get_credentials(self) -> None:
                raise RuntimeError("credential backend unavailable")

        monkeypatch.setattr(
            credentials_module,
            "import_module",
            lambda _: SimpleNamespace(Session=BrokenSession),
        )
        with pytest.raises(RuntimeError, match="credential backend unavailable"):
            await ProfileCredentialProvider().get_credentials()

        with pytest.raises(ValueError, match="profile_name"):
            ProfileCredentialProvider("  ")
        with pytest.raises(ValueError, match="profile_name"):
            DefaultCredentialProvider("  ")

    asyncio.run(scenario())


def test_dynamodb_crud_table_setup_and_expression_options(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        key_schema = [{"AttributeName": "user_id", "KeyType": "HASH"}]
        definitions = [{"AttributeName": "user_id", "AttributeType": "S"}]
        table = DynamoTable(
            DynamoDBConfig(table_name="users", endpoint_url="http://dynamo.local"),
            User,
            key_schema=key_schema,
            attribute_definitions=definitions,
            provisioned_throughput={"ReadCapacityUnits": 2, "WriteCapacityUnits": 3},
        )
        key_schema[0]["KeyType"] = "RANGE"
        definitions.clear()
        assert (await table.create_table()) == {}
        assert client.calls[-1] == (
            "create_table",
            {
                "TableName": "users",
                "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                "AttributeDefinitions": [{"AttributeName": "user_id", "AttributeType": "S"}],
                "ProvisionedThroughput": {"ReadCapacityUnits": 2, "WriteCapacityUnits": 3},
            },
        )
        assert await table.delete_table() == {}

        model = User(user_id="1", name="Ada", age=37)
        await table.put_item(model)
        assert client.calls[-1][1]["Item"]["age"] == {"N": "37"}
        with pytest.raises(ValueError, match="at least one"):
            await table.put_item({})

        client.responses["get_item"] = lambda **_: {
            "Item": {"user_id": {"S": "1"}, "name": {"S": "Ada"}, "age": {"N": "37"}}
        }
        assert await table.get_item({"user_id": "1"}, consistent_read=True) == model
        assert client.calls[-1][1]["ConsistentRead"] is True
        client.responses["get_item"] = lambda **_: {}
        assert await table.get_item({"user_id": "absent"}) is None
        await table.delete_item({"user_id": "1"})
        assert client.calls[-1][1]["Key"] == {"user_id": {"S": "1"}}
        with pytest.raises(ValueError, match="at least one"):
            await table.get_item({})
        with pytest.raises(ValueError, match="at least one"):
            await table.delete_item({})

        client.responses["update_item"] = lambda **kwargs: kwargs
        updated = await table.update_item(
            {"user_id": "1"},
            "SET #name = :name",
            expression_attribute_values={":name": "Lin"},
            expression_attribute_names={"#name": "name"},
            condition_expression="attribute_exists(user_id)",
            return_values="ALL_NEW",
        )
        assert updated["ExpressionAttributeValues"] == {":name": {"S": "Lin"}}
        assert updated["ExpressionAttributeNames"] == {"#name": "name"}
        assert updated["ConditionExpression"] == "attribute_exists(user_id)"
        assert updated["ReturnValues"] == "ALL_NEW"
        with pytest.raises(ValueError, match="update_expression"):
            await table.update_item({"user_id": "1"}, " ")
        with pytest.raises(ValueError, match="ReturnValues"):
            await table.update_item({"user_id": "1"}, "SET age = :age", return_values="BAD")
        with pytest.raises(ValueError, match="at least one"):
            await table.update_item({}, "SET age = :age")

        with pytest.raises(ValueError, match="required"):
            await DynamoTable(DynamoDBConfig(table_name="users"), User).create_table()
        with pytest.raises(TypeError, match="Pydantic"):
            DynamoTable(DynamoDBConfig(table_name="users"), dict)  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_dynamodb_query_scan_limits_and_model_conversion(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        wire_users = [
            {"user_id": {"S": "1"}, "name": {"S": "Ada"}, "age": {"N": "37"}},
            {"user_id": {"S": "2"}, "name": {"S": "Lin"}, "age": {"N": "32"}},
        ]
        pages = iter(
            [
                {"Items": wire_users, "LastEvaluatedKey": {"user_id": {"S": "2"}}},
                {"Items": [wire_users[0]]},
            ]
        )
        client.responses["query"] = lambda **_: next(pages)
        table = DynamoTable(DynamoDBConfig(table_name="users"), User)
        result = await table.query(
            "user_id = :id",
            expression_attribute_values={":id": "1"},
            expression_attribute_names={"#name": "name"},
            filter_expression="#name <> :empty",
            index_name="by-name",
            limit=1,
            scan_index_forward=False,
        )
        assert [user.user_id for user in result] == ["1"]
        request = client.calls[-1][1]
        assert request["Limit"] == 1
        assert request["ScanIndexForward"] is False
        assert request["IndexName"] == "by-name"
        assert request["FilterExpression"] == "#name <> :empty"
        assert "ExclusiveStartKey" not in request

        scan_pages = iter(
            [
                {"Items": wire_users, "LastEvaluatedKey": {"user_id": {"S": "2"}}},
                {"Items": []},
            ]
        )
        client.responses["scan"] = lambda **_: next(scan_pages)
        scanned = await table.scan(
            filter_expression="age > :age",
            expression_attribute_values={":age": 30},
            expression_attribute_names={"#age": "age"},
            index_name="by-age",
            limit=5,
        )
        assert len(scanned) == 2
        scan_calls = [kwargs for name, kwargs in client.calls if name == "scan"]
        assert [kwargs["Limit"] for kwargs in scan_calls] == [5, 3]
        assert scan_calls[0]["ExpressionAttributeNames"] == {"#age": "age"}
        client.responses["scan"] = lambda **_: {"Items": wire_users}
        assert len(await table.scan(limit=None)) == 2
        with pytest.raises(ValueError, match="key_condition_expression"):
            await table.query("   ")

    asyncio.run(scenario())


def test_dynamodb_batch_operations_retry_report_residuals_and_chunk_requests(
    aws_client: tuple[FakeClient, FakeSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        import std.aws.dynamodb.table as table_module

        sleeps: list[float] = []

        async def no_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr(table_module.asyncio, "sleep", no_sleep)
        client, _ = aws_client
        table = DynamoTable(DynamoDBConfig(table_name="users"), User)
        assert await table.batch_get_items([]) == {
            "Responses": {"users": []},
            "UnprocessedKeys": {},
        }
        with pytest.raises(ValueError, match="empty mappings"):
            await table.batch_get_items([{}])

        response_calls: list[dict[str, Any]] = []

        def always_unprocessed(**kwargs: Any) -> dict[str, Any]:
            response_calls.append(kwargs)
            return {
                "Responses": {"users": []},
                "UnprocessedKeys": {"users": {"Keys": kwargs["RequestItems"]["users"]["Keys"]}},
                "ResponseMetadata": {"attempt": len(response_calls)},
            }

        client.responses["batch_get_item"] = always_unprocessed
        result = await table.batch_get_items(
            [{"user_id": str(index)} for index in range(101)],
            consistent_read=True,
            projection_expression="user_id",
        )
        assert len(response_calls) == 12
        assert len(sleeps) == 10
        assert len(result["UnprocessedKeys"]["users"]["Keys"]) == 101
        assert result["UnprocessedKeys"]["users"]["ProjectionExpression"] == "user_id"
        assert result["ResponseMetadata"] == {"attempt": 12}
        assert [len(call["RequestItems"]["users"]["Keys"]) for call in response_calls[::6]] == [
            100,
            1,
        ]

        client.responses["batch_get_item"] = lambda **_: {
            "Responses": {"users": [{"user_id": {"S": "1"}, "name": {"S": "Ada"}}]},
            "ResponseMetadata": {"status": 200},
        }
        records = await table.batch_get_items_from_table([{"user_id": "1"}], consistent_read=True)
        assert records == [User(user_id="1", name="Ada")]
        assert await table.batch_write_items() == {"UnprocessedItems": {}}
        with pytest.raises(ValueError, match="items_to_put"):
            await table.batch_write_items(items_to_put=[{}])
        with pytest.raises(ValueError, match="items_to_delete"):
            await table.batch_write_items(items_to_delete=[{}])

        write_calls: list[dict[str, Any]] = []

        def always_unprocessed_write(**kwargs: Any) -> dict[str, Any]:
            write_calls.append(kwargs)
            return {
                "UnprocessedItems": {"users": kwargs["RequestItems"]["users"]},
                "ResponseMetadata": {"attempt": len(write_calls)},
            }

        client.responses["batch_write_item"] = always_unprocessed_write
        put_result = await table.batch_write_items(
            items_to_put=[{"user_id": "1", "name": "Ada"}],
            items_to_delete=[{"user_id": "2"}],
        )
        assert len(write_calls) == 6
        assert len(sleeps) == 15
        assert len(put_result["UnprocessedItems"]["users"]) == 2
        assert put_result["ResponseMetadata"] == {"attempt": 6}

        client.responses["batch_write_item"] = lambda **_: {"UnprocessedItems": {}}
        models_result = await table.batch_write_items_to_table([User(user_id="3", name="Grace")])
        assert models_result == {"UnprocessedItems": {}}

    asyncio.run(scenario())


def test_dynamodb_serialization_supports_binary_and_nested_types() -> None:
    table = DynamoTable(DynamoDBConfig(table_name="users"), User)
    wire = table._serialize_item(
        {
            "none": None,
            "binary": bytearray(b"bin"),
            "view": memoryview(b"view"),
            "numbers": {3, 1, Decimal("2.5")},
            "binary_set": {b"b", memoryview(b"a")},
            "nested": {"values": (None, b"x")},
        }
    )
    assert wire == {
        "none": {"NULL": True},
        "binary": {"B": b"bin"},
        "view": {"B": b"view"},
        "numbers": {"NS": ["1", "2.5", "3"]},
        "binary_set": {"BS": list(wire["binary_set"]["BS"])},
        "nested": {"M": {"values": {"L": [{"NULL": True}, {"B": b"x"}]}}},
    }
    assert set(wire["binary_set"]["BS"]) == {b"a", b"b"}
    decoded = table._deserialize_item(
        {
            "binary": {"B": bytearray(b"bin")},
            "bool": {"BOOL": True},
            "nil": {"NULL": True},
            "strings": {"SS": ["one", "two"]},
            "numbers": {"NS": ["1", "2.5"]},
            "binaries": {"BS": [b"a", bytearray(b"b")]},
            "nested": {"M": {"items": {"L": [{"N": "2"}, {"S": "ok"}]}}},
        }
    )
    assert decoded == {
        "binary": b"bin",
        "bool": True,
        "nil": None,
        "strings": {"one", "two"},
        "numbers": {Decimal("1"), Decimal("2.5")},
        "binaries": {b"a", b"b"},
        "nested": {"items": [Decimal("2"), "ok"]},
    }
    with pytest.raises(TypeError, match="one kind"):
        table._serialize_value({1, "one"})
    with pytest.raises(TypeError, match="one kind"):
        table._serialize_value({True, False})
    with pytest.raises(ValueError, match="finite"):
        table._serialize_value(float("inf"))
    with pytest.raises(ValueError, match="invalid DynamoDB number"):
        table._deserialize_value({"N": "not-a-number"})
    with pytest.raises(ValueError, match="finite"):
        table._deserialize_value({"N": "NaN"})
    with pytest.raises(ValueError, match="BOOL"):
        table._deserialize_value({"BOOL": 1})
    with pytest.raises(ValueError, match="NULL"):
        table._deserialize_value({"NULL": False})


def test_s3_file_lifecycle_json_model_and_object_operations(
    aws_client: tuple[FakeClient, FakeSession], tmp_path: Path
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        local = tmp_path / "upload.txt"
        local.write_text("payload", encoding="utf-8")
        assert await s3.upload_file(local, "upload.txt", {"ContentType": "text/plain"}) is True
        assert client.calls[-1] == (
            "upload_file",
            {
                "_args": (str(local), "assets", "upload.txt"),
                "ExtraArgs": {"ContentType": "text/plain"},
            },
        )
        file_object = BytesIO(b"from memory")
        assert await s3.upload_fileobj(file_object, "memory.bin") is True
        assert not file_object.closed
        assert client.calls[-1][1]["_args"] == (file_object, "assets", "memory.bin")
        assert await s3.download_file("upload.txt", tmp_path / "download.txt") is True
        assert client.calls[-1][1]["_args"] == (
            "assets",
            "upload.txt",
            str(tmp_path / "download.txt"),
        )

        client.responses["get_object"] = lambda **_: {
            "Body": FakeBody(b'{"user_id":"9","name":"Lin","age":31}'),
            "ContentType": "application/json",
        }
        model = await s3.get_object_as_model("user.json", User)
        assert model == User(user_id="9", name="Lin", age=31)
        assert await s3.get_object_as_bytes("user.json") == b'{"user_id":"9","name":"Lin","age":31}'
        assert await s3.get_object_as_string("user.json") == '{"user_id":"9","name":"Lin","age":31}'

        await s3.put_object(
            "plain.txt", b"bytes", content_type="text/plain", metadata={"owner": "ops"}
        )
        assert client.calls[-1][1] == {
            "Bucket": "assets",
            "Key": "plain.txt",
            "Body": b"bytes",
            "ContentType": "text/plain",
            "Metadata": {"owner": "ops"},
        }
        await s3.delete_object("plain.txt")
        assert client.calls[-1][0] == "delete_object"

        client.responses["generate_presigned_url"] = (
            lambda *_args, **kwargs: f"https://example.test/{kwargs['HttpMethod']}"
        )
        assert (
            await s3.get_presigned_url("plain.txt", http_method="put") == "https://example.test/PUT"
        )
        assert client.calls[-1][1]["_args"] == ("put_object",)
        with pytest.raises(ValueError, match="expires_in"):
            await s3.get_presigned_url("x", expires_in=0)

        await s3.copy_object("source.txt", "copy.txt", source_bucket="source-bucket")
        assert client.calls[-1][1]["CopySource"] == {"Bucket": "source-bucket", "Key": "source.txt"}
        await s3.copy_object(
            "source.txt", "copy.txt", metadata={"copied": "yes"}, metadata_directive="replace"
        )
        assert client.calls[-1][1]["MetadataDirective"] == "REPLACE"
        assert client.calls[-1][1]["Metadata"] == {"copied": "yes"}

        with pytest.raises(ValueError, match="s3_key"):
            await s3.upload_file(local, "")
        with pytest.raises(ValueError, match="s3_key"):
            await s3.upload_fileobj(file_object, "")
        with pytest.raises(TypeError, match="read"):
            await s3.upload_fileobj(object(), "x")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="s3_key"):
            await s3.download_file("", local)
        with pytest.raises(ValueError, match="s3_key"):
            await s3.get_object("")
        with pytest.raises(ValueError, match="s3_key"):
            await s3.put_object("", "body")
        with pytest.raises(ValueError, match="s3_key"):
            await s3.delete_object("")
        with pytest.raises(ValueError, match="s3_key"):
            await s3.get_presigned_url("")
        with pytest.raises(ValueError, match="source_key"):
            await s3.copy_object("", "target")

    asyncio.run(scenario())


def test_s3_object_context_closes_sync_and_async_streams_on_failure(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    class SyncBody:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    async def scenario() -> None:
        client, _ = aws_client
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        sync_body = SyncBody()
        client.responses["get_object"] = lambda **_: {"Body": sync_body}
        with pytest.raises(RuntimeError, match="consumer failed"):
            async with s3.open_object("sync-close"):
                raise RuntimeError("consumer failed")
        assert sync_body.closed

        async_body = FakeBody(b"\xff")
        client.responses["get_object"] = lambda **_: {"Body": async_body}
        with pytest.raises(UnicodeDecodeError):
            await s3.get_object_as_string("invalid-utf8", encoding="ascii")
        assert async_body.closed

        client.responses["get_object"] = lambda **_: {"Body": FakeBody(b'{"ok":true}')}
        detached = await s3.get_object("small")
        async with detached["Body"] as detached_body:
            assert await detached_body.read(2) == b'{"'

    asyncio.run(scenario())


def test_s3_listing_bulk_delete_presigning_and_copy_validation(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        s3 = S3Client(S3ClientConfig(bucket_name="assets"))
        pages = iter(
            [
                {"Contents": [{"Key": "a"}], "IsTruncated": True, "NextContinuationToken": "t"},
                {"Contents": [{"Key": "b"}, {"Key": "c"}], "IsTruncated": False},
            ]
        )
        client.responses["list_objects_v2"] = lambda **_: next(pages)
        assert await s3.list_objects(prefix="docs/", delimiter="/", max_keys=2) == ["a", "b"]
        calls = [kwargs for name, kwargs in client.calls if name == "list_objects_v2"]
        assert calls[0]["Delimiter"] == "/"
        assert calls[1]["ContinuationToken"] == "t"
        assert calls[1]["MaxKeys"] == 1
        with pytest.raises(ValueError, match="max_keys"):
            await s3.list_objects(max_keys=0)

        client.responses["delete_objects"] = lambda **kwargs: {
            "Deleted": [{"Key": kwargs["Delete"]["Objects"][0]["Key"]}],
            "Errors": [{"Key": "bad", "Code": "AccessDenied"}],
        }
        assert await s3.delete_objects([]) == {"Deleted": [], "Errors": []}
        with pytest.raises(ValueError, match="empty keys"):
            await s3.delete_objects(["ok", ""])
        result = await s3.delete_objects([f"key-{index}" for index in range(1001)])
        assert len(result["Deleted"]) == 2
        assert len(result["Errors"]) == 2
        delete_calls = [kwargs for name, kwargs in client.calls if name == "delete_objects"]
        assert [len(kwargs["Delete"]["Objects"]) for kwargs in delete_calls] == [1000, 1]

        async def presign(*_args: Any, **kwargs: Any) -> str:
            return kwargs["HttpMethod"]

        client.responses["generate_presigned_url"] = presign
        assert await s3.get_presigned_url("k", http_method="DELETE") == "DELETE"
        assert await s3.get_presigned_url("k") == "GET"
        with pytest.raises(ValueError, match="http_method"):
            await s3.get_presigned_url("k", http_method="PATCH")
        with pytest.raises(ValueError, match="expires_in"):
            await s3.get_presigned_url("k", expires_in=604801)

        with pytest.raises(ValueError, match="metadata_directive"):
            await s3.copy_object("source", "target", metadata_directive="MERGE")
        with pytest.raises(ValueError, match="only when"):
            await s3.copy_object("source", "target", metadata={"owner": "ops"})

    asyncio.run(scenario())


def test_sqs_queue_send_receive_delete_and_validation(
    aws_client: tuple[FakeClient, FakeSession],
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        sqs = SQSClient(SQSConfig(queue_url="http://local/queue"))
        client.responses["create_queue"] = lambda **kwargs: {
            "QueueUrl": f"http://local/{kwargs['QueueName']}"
        }
        assert (
            await sqs.create_queue("  jobs  ", {"VisibilityTimeout": "10"}) == "http://local/jobs"
        )
        assert client.calls[-1][1] == {
            "QueueName": "jobs",
            "Attributes": {"VisibilityTimeout": "10"},
        }
        with pytest.raises(ValueError, match="queue_name"):
            await sqs.create_queue(" ")
        with pytest.raises(ValueError, match="queue_name"):
            await sqs.create_queue("x" * 81)

        await sqs.send_message(
            User(user_id="4", name="Ada"),
            message_attributes={"source": {"StringValue": "test", "DataType": "String"}},
            delay_seconds=3,
        )
        assert client.calls[-1][1]["MessageBody"] == '{"user_id":"4","name":"Ada","age":0}'
        assert client.calls[-1][1]["DelaySeconds"] == 3
        assert client.calls[-1][1]["MessageAttributes"]["source"]["StringValue"] == "test"
        with pytest.raises(TypeError, match="message must"):
            await sqs.send_message(object())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="delay_seconds"):
            await sqs.send_message("x", delay_seconds=True)  # type: ignore[arg-type]

        await sqs.send_message_batch(
            ["one", {"value": 2}],
            message_attributes=[{"kind": {"StringValue": "text"}}, {}],
            delay_seconds=4,
        )
        entries = client.calls[-1][1]["Entries"]
        assert entries[0]["Id"] == "0" and entries[1]["Id"] == "1"
        assert entries[1]["MessageBody"] == '{"value": 2}'
        assert all(entry["DelaySeconds"] == 4 for entry in entries)

        client.responses["receive_message"] = lambda **_: {
            "Messages": [{"Body": '{"user_id":"7","name":"Lin"}', "ReceiptHandle": "r"}]
        }
        received = await sqs.receive_message(
            max_number_of_messages=2,
            wait_time_seconds=5,
            visibility_timeout=20,
            model_class=User,
        )
        assert received[0]["_parsed"] == User(user_id="7", name="Lin")
        assert client.calls[-1][1]["WaitTimeSeconds"] == 5
        assert client.calls[-1][1]["VisibilityTimeout"] == 20
        await sqs.delete_message("r")
        await sqs.delete_message_batch([{"Id": "one", "ReceiptHandle": "r1"}])
        assert client.calls[-1][1]["Entries"] == [{"Id": "one", "ReceiptHandle": "r1"}]
        await sqs.purge_queue()
        assert client.calls[-1][0] == "purge_queue"

        for invalid in (0, 11):
            with pytest.raises(ValueError, match="max_number_of_messages"):
                await sqs.receive_message(max_number_of_messages=invalid)
        for invalid in (-1, 21):
            with pytest.raises(ValueError, match="wait_time_seconds"):
                await sqs.receive_message(wait_time_seconds=invalid)
        for invalid in (-1, 43201):
            with pytest.raises(ValueError, match="visibility_timeout"):
                await sqs.receive_message(visibility_timeout=invalid)
        with pytest.raises(ValueError, match="receipt_handle"):
            await sqs.delete_message("")
        with pytest.raises(ValueError, match="between 1 and 10"):
            await sqs.delete_message_batch([])
        with pytest.raises(ValueError, match="Id and ReceiptHandle"):
            await sqs.delete_message_batch([{"Id": "one"}])
        with pytest.raises(ValueError, match="unique"):
            await sqs.delete_message_batch(
                [{"Id": "one", "ReceiptHandle": "r1"}, {"Id": "one", "ReceiptHandle": "r2"}]
            )

    asyncio.run(scenario())


def test_sqs_receive_parse_errors_batch_send_validation_and_async_handlers(
    aws_client: tuple[FakeClient, FakeSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        client, _ = aws_client
        sqs = SQSClient(SQSConfig(queue_url="http://local/queue"))
        client.responses["receive_message"] = lambda **_: {
            "Messages": [{"Body": "{}"}, {"ReceiptHandle": "missing-body"}]
        }
        messages = await sqs.receive_message(model_class=User)
        assert messages[0]["_parse_error"] == "ValidationError"
        assert messages[1]["_parse_error"] == "KeyError"

        await sqs.send_message_batch(["one", "two"])
        assert client.calls[-1][1]["Entries"] == [
            {"Id": "0", "MessageBody": "one"},
            {"Id": "1", "MessageBody": "two"},
        ]
        with pytest.raises(ValueError, match="between 1 and 10"):
            await sqs.send_message_batch([])
        with pytest.raises(ValueError, match="one entry per message"):
            await sqs.send_message_batch(["one"], [{}, {}])
        with pytest.raises(ValueError, match="delay_seconds"):
            await sqs.send_message_batch(["one"], delay_seconds=-1)
        with pytest.raises(ValueError, match="between 0 and 900"):
            await sqs.send_message("one", delay_seconds=901)
        with pytest.raises(ValueError, match="between 0 and 900"):
            await sqs.send_message_batch(["one"], delay_seconds=901)
        with pytest.raises(ValueError, match="between 0 and 900"):
            sqs._validate_delay(True)  # type: ignore[arg-type]

        client.responses["receive_message"] = lambda **_: {
            "Messages": [
                {"Body": "one", "ReceiptHandle": "r1"},
                {"Body": "two"},
            ]
        }

        async def async_handler(_: Mapping[str, Any]) -> None:
            return None

        results = await sqs.process_messages(async_handler, auto_delete=False)
        assert [result["success"] for result in results] == [True, True]
        assert [result["deleted"] for result in results] == [False, False]

        client.responses["receive_message"] = lambda **_: {"Messages": [{"Body": "missing-handle"}]}
        missing_handle = await sqs.process_messages(async_handler, auto_delete=True)
        assert missing_handle[0]["success"] is False
        assert missing_handle[0]["error"] == "received message has no ReceiptHandle"

        class AsyncCallable:
            async def __call__(self, _: Mapping[str, Any]) -> None:
                return None

        client.responses["receive_message"] = lambda **_: {
            "Messages": [{"Body": "async-callable", "ReceiptHandle": "r"}]
        }
        callable_result = await sqs.process_messages(AsyncCallable(), auto_delete=False)
        assert callable_result[0]["success"] is True

    asyncio.run(scenario())


def test_sqs_consumer_recovers_from_errors_and_propagates_cancellation() -> None:
    async def scenario() -> None:
        consumer = SQSConsumer(
            "http://local/queue",
            "us-east-1",
            lambda _: None,
            polling_interval=0,
            retry_delay=0,
        )
        with pytest.raises(ValueError, match="batch_size"):
            await consumer.process_batch(0)

        calls = 0

        async def fail_once(batch_size: int) -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            consumer.stop_event.set()
            raise RuntimeError("temporary queue failure")

        consumer.process_batch = fail_once  # type: ignore[method-assign]
        await consumer.run()
        assert calls == 1

        async def cancelled(_: int) -> list[dict[str, Any]]:
            raise asyncio.CancelledError

        consumer.stop_event.clear()
        consumer.process_batch = cancelled  # type: ignore[method-assign]
        with pytest.raises(asyncio.CancelledError):
            await consumer.run()

        for kwargs in (
            {"max_messages": 0},
            {"max_messages": 11},
            {"wait_time": 21},
            {"visibility_timeout": 43201},
            {"polling_interval": -1},
            {"retry_delay": -1},
        ):
            with pytest.raises(ValueError):
                SQSConsumer("http://local/queue", "us-east-1", lambda _: None, **kwargs)

    asyncio.run(scenario())
