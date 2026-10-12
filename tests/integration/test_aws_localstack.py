"""Real AWS service-boundary coverage against a Testcontainers LocalStack."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from uuid import uuid4

import pytest
from pydantic import BaseModel

from std.aws import (
    DynamoDBConfig,
    DynamoTable,
    ExplicitCredentialProvider,
    S3Client,
    S3ClientConfig,
    SQSClient,
    SQSConfig,
)


@pytest.fixture(scope="module")
def localstack_endpoint() -> Iterator[str]:
    """Start LocalStack with the AWS services exercised by this module."""
    import docker
    from testcontainers.core.container import DockerContainer

    try:
        docker.from_env().ping()
    except Exception as error:
        if os.environ.get("STD_REQUIRE_DOCKER") == "1":
            pytest.fail(f"Docker is required for AWS E2E: {type(error).__name__}", pytrace=False)
        pytest.skip(f"Docker is unavailable: {type(error).__name__}")

    container = DockerContainer("localstack/localstack:3.8")
    container.with_exposed_ports(4566)
    container.with_env("SERVICES", "s3,sqs,dynamodb")
    container.with_env("AWS_DEFAULT_REGION", "us-east-1")
    container.with_env("EAGER_SERVICE_LOADING", "1")
    with container as running:
        host = running.get_container_host_ip()
        port = running.get_exposed_port(4566)
        endpoint = f"http://{host}:{port}"
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{endpoint}/_localstack/health", timeout=2
                ) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.5)
        else:
            pytest.fail("LocalStack did not become healthy within 90 seconds", pytrace=False)
        yield endpoint


class Record(BaseModel):
    """DynamoDB model used to check typed round-trips."""

    record_id: str
    message: str


@pytest.mark.e2e
@pytest.mark.integration
def test_s3_sqs_and_dynamodb_round_trip_with_localstack(localstack_endpoint: str) -> None:
    async def scenario() -> None:
        endpoint = localstack_endpoint
        credentials = ExplicitCredentialProvider("test-key", "test-secret")
        suffix = uuid4().hex[:10]

        bucket = f"std-aws-{suffix}"
        s3 = S3Client(S3ClientConfig(bucket_name=bucket, endpoint_url=endpoint), credentials)
        async with s3.get_client() as raw_s3:
            await raw_s3.create_bucket(Bucket=bucket)
        await s3.put_object("payload.json", json.dumps({"ready": True}))
        assert await s3.get_object_as_json("payload.json") == {"ready": True}

        queue_name = f"std-aws-{suffix}"
        queue_admin = SQSClient(
            SQSConfig(queue_url=f"{endpoint}/000000000000/{queue_name}", endpoint_url=endpoint),
            credentials,
        )
        raw_queue_url = await queue_admin.create_queue(queue_name)
        queue_path = "/" + raw_queue_url.split("/", 3)[3]
        queue_url = endpoint + queue_path
        sqs = SQSClient(SQSConfig(queue_url=queue_url, endpoint_url=endpoint), credentials)
        await sqs.send_message({"task": "round-trip"})
        messages = await sqs.receive_message(max_number_of_messages=1, wait_time_seconds=1)
        assert messages and json.loads(messages[0]["Body"]) == {"task": "round-trip"}
        await sqs.delete_message(messages[0]["ReceiptHandle"])

        table_name = f"std-aws-{suffix}"
        table = DynamoTable(
            DynamoDBConfig(table_name=table_name, endpoint_url=endpoint),
            Record,
            credentials,
            key_schema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
            attribute_definitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
            provisioned_throughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
        await table.create_table()
        record = Record(record_id="one", message="hello")
        await table.put_item(record)
        restored = await table.get_item({"record_id": "one"})
        assert restored == record

    asyncio.run(scenario())
