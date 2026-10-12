# AWS integrations

`standard-aws` provides async AWS service clients under `std.aws`. The package
depends on `aioboto3`, while the core `standard` distribution remains usable
without AWS libraries.

## Install

```console
python -m pip install standard-aws
# or install the integration through the core extra
python -m pip install 'standard[aws]'
```

## Credential sources

Use `DefaultCredentialProvider()` for the AWS SDK credential chain. It resolves
credentials from the environment, selected profile, SSO, web identity, shared
credentials, or an AWS workload identity using the SDK's configured providers.
You may pass `profile_name="staging"` to pin a profile. If no credentials are
found, clients fall back to the SDK chain when opening their service client.

`EnvironmentCredentialProvider` requires both `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY`; it reads `AWS_SESSION_TOKEN` and `AWS_DEFAULT_REGION`
(then `AWS_REGION`) when available. `ProfileCredentialProvider` resolves a named
profile through the SDK, including profiles that use SSO or credential-process
commands. `ExplicitCredentialProvider` accepts credentials supplied by an
application identity system. Prefer short-lived session credentials over static
long-lived access keys.

```python
from std.aws import DefaultCredentialProvider, S3Client, S3ClientConfig

storage = S3Client(
    S3ClientConfig(bucket_name="reports", region="us-east-1"),
    credential_provider=DefaultCredentialProvider(profile_name="staging"),
)
```

`AWSCredentials.__repr__` hides secret key and session-token fields. Its
`to_dict()` method includes them because AWS client creation requires those
values; do not log that mapping.

## S3

`S3ClientConfig` requires a non-empty bucket name, and accepts a region (default
`us-east-1`) plus an optional `endpoint_url` for LocalStack or compatible
storage. The client offers:

- `upload_file`, `upload_fileobj`, `download_file`, and `put_object`;
- `get_object`, `get_object_body`, `get_object_as_bytes`,
  `get_object_as_string`, `get_object_as_json`, and `get_object_as_model`;
- `list_objects`, `copy_object`, `delete_object`, and `delete_objects`;
- presigned GET, PUT, and DELETE URLs.

Object keys must be non-empty. `list_objects()` accepts `max_keys` from 1 to
1000, the S3 limit for one listing response. It follows continuation tokens
when a service response is truncated and returns at most the requested number
of keys. `delete_objects()` handles any list length by splitting requests into
1000-key chunks and returns aggregate `Deleted` and `Errors` entries. An empty
list returns empty result arrays without contacting AWS.

`get_object()` returns the response with `Body` buffered in memory, so it is
suited to small objects. Use `async with client.open_object(key)` to stream a
large object while keeping the SDK client open, and read the body inside that
context. `get_object_body()` and the convenience read methods stream and close
the response even if reading fails. JSON reads may return any JSON value; model
reads validate it with Pydantic. A presigned URL expires after 1 to 604800
seconds, and an unsupported HTTP method raises `ValueError` before a request is
sent.

## SQS

`SQSConfig` contains the queue URL, region, and optional endpoint URL. The
client supports queue creation, message send/receive, batch send/delete, purge,
and one-batch processing. Python mappings and Pydantic models are encoded as
JSON; strings are sent verbatim. JSON encoding rejects non-standard `NaN` and
infinity values.

SQS service bounds are validated locally: receive and batch sizes are 1–10,
long polling is 0–20 seconds, visibility timeout is 0–43200 seconds, and
message delay is 0–900 seconds. A batch's attributes list must have exactly one
entry per message. AWS may report individual failures in batch responses; the
client returns those responses for caller handling.

`receive_message(model_class=...)` leaves `Body` unchanged and adds `_parsed`
with the validated model. If the body is invalid, it adds `_parse_error` with
the error type and retains the message for normal handling. `process_messages()`
accepts synchronous and asynchronous handlers. Synchronous handlers run in a
worker thread. Exceptions are returned on that message's result; automatic
deletion happens only after handler success and when `auto_delete=True`. If a
receipt handle is missing or deletion fails, that message is marked failed.

### Managed consumer

`SQSConsumer` extends `std.service.BackgroundService`. `await consumer.start()`
starts the managed polling task and returns. `await consumer.stop()` signals
shutdown and waits for a graceful exit. The consumer retries polling errors
after `retry_delay`; error logs include the exception type without printing
message contents or credentials. `process_batch()` runs one batch directly and
is useful for scheduled jobs and tests.

```python
from std.aws import SQSConsumer

async def handle(message):
    await persist(message["Body"])

consumer = SQSConsumer(
    queue_url="https://sqs.us-east-1.amazonaws.com/123/tasks",
    region="us-east-1",
    handler=handle,
)
await consumer.start()
# During application shutdown:
await consumer.stop()
```

## DynamoDB

`DynamoTable` maps low-level DynamoDB attribute values to a Pydantic model. It
supports table lifecycle, item CRUD, query, scan, and batch read/write. Query
and scan follow `LastEvaluatedKey` until all pages are consumed or `limit` model
instances have been collected. `limit` must be positive when supplied.

The serializer distinguishes booleans from numbers, preserves decimal
precision, and supports strings, bytes, numbers, sets, lists, nested mappings,
and `None`. DynamoDB rejects empty sets and mixed-type sets, so the helper raises
before sending those values. Unsupported Python objects and malformed
DynamoDB attribute unions raise a clear local error.

Batch reads are split into groups of 100 and writes into groups of 25. Both
helpers retry unprocessed keys or writes with bounded exponential delays; any
still-unprocessed work is returned in the corresponding `UnprocessedKeys` or
`UnprocessedItems` response field. AWS conditional, validation, authorization,
and transport errors remain visible to the caller.

```python
from pydantic import BaseModel
from std.aws import DynamoDBConfig, DynamoTable

class User(BaseModel):
    user_id: str
    email: str

users = DynamoTable(
    DynamoDBConfig(table_name="users", region="us-east-1"),
    User,
    key_schema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
    attribute_definitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
)
await users.put_item(User(user_id="u-123", email="ada@example.test"))
user = await users.get_item({"user_id": "u-123"})
```

## Secrets Manager

`load_secret(secret_id)` performs a synchronous Secrets Manager read and parses
the payload as a JSON object. It rejects duplicate object keys, non-finite
numbers, non-object JSON, and absent payloads. `AwsSecretsManagerSettingsSource`
can be installed as a Pydantic Settings source; fetch secrets at application
startup and keep the resulting settings in the application composition root.

## Verify

The unit suite uses fake clients to cover input bounds, pagination, response
cleanup, credentials, and retries. `tests/integration/test_aws_localstack.py`
uses Testcontainers to exercise S3, SQS, and DynamoDB with real service
boundaries. Run it with `make test-e2e`; it skips when Docker is unavailable
unless `STD_REQUIRE_DOCKER=1` is set.
