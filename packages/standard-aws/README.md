# standard-aws

`standard-aws` adds asynchronous AWS clients to the `standard` Python library.
Install it on its own or select it with the core distribution's extra:

```console
python -m pip install standard-aws
python -m pip install 'standard[aws]'
```

The public import namespace is `std.aws`. The core `standard` package stays
small; AWS SDK dependencies are installed only with this add-on.

## Credentials

Choose a credential provider explicitly when the application needs a fixed
source. The default provider delegates to the AWS SDK chain, so environment,
shared profiles, SSO, web identity, and workload roles keep their SDK behavior.

```python
from std.aws import DefaultCredentialProvider, ExplicitCredentialProvider

credentials = DefaultCredentialProvider()
# Or provide short-lived credentials supplied by an application identity system.
fixed_credentials = ExplicitCredentialProvider(
    access_key_id="access-key",
    secret_access_key="secret-key",
    session_token="session-token",
    region="us-east-1",
)
```

Credential objects hide secret values from their `repr`. Avoid logging values
returned by `to_dict()` because that method is intended for SDK integration.

## S3

```python
from std.aws import S3Client, S3ClientConfig

s3 = S3Client(S3ClientConfig(bucket_name="reports", region="us-east-1"))
await s3.put_object("daily/report.json", '{"ready": true}', content_type="application/json")
report = await s3.get_object_as_json("daily/report.json")
keys = await s3.list_objects(prefix="daily/")
```

`S3Client` also supports file and file-object upload/download, object
responses, bytes and text reads, Pydantic model validation, copy, deletion,
presigned GET/PUT/DELETE URLs, and LocalStack or S3-compatible endpoints. S3
body streams are closed after helper reads. `get_object()` returns the response
with its body buffered in memory; use `async with s3.open_object(key)` to stream
large objects while keeping the SDK client open. `list_objects()` accepts
between 1 and 1000 keys per call, matching S3's service limit.

## SQS

```python
from std.aws import SQSClient, SQSConfig

queue = SQSClient(SQSConfig(queue_url="https://sqs.us-east-1.amazonaws.com/123/tasks"))
await queue.send_message({"task_id": "task-123"})
messages = await queue.receive_message(max_number_of_messages=10, wait_time_seconds=10)
```

Mappings and Pydantic models are JSON encoded. Batch operations enforce SQS's
1–10 message limit and reject mismatched per-message attributes. `process_messages`
supports synchronous and asynchronous handlers; synchronous handlers run outside
the event loop. Successful messages are deleted only when `auto_delete=True`.
Failed JSON model parsing leaves the original body intact and adds
`_parse_error` to the message.

For a continuously polling service, use the lifecycle-aware consumer:

```python
from std.aws import SQSConsumer


async def handle(message):
    print(message["Body"])


consumer = SQSConsumer(queue_url="https://…", region="us-east-1", handler=handle)
await consumer.start()  # starts its managed worker and returns
await consumer.stop()  # signals graceful shutdown and waits for completion
```

`SQSConsumer` is a `std.service.BackgroundService`, so its state and health can
be managed alongside application services.

## DynamoDB

```python
from pydantic import BaseModel
from std.aws import DynamoDBConfig, DynamoTable


class Task(BaseModel):
    task_id: str
    title: str


tasks = DynamoTable(DynamoDBConfig(table_name="tasks"), Task)
await tasks.put_item(Task(task_id="task-123", title="Build docs"))
task = await tasks.get_item({"task_id": "task-123"})
```

The typed helper supports create/delete table, get/put/update/delete item,
query/scan pagination, and batch read/write. Batch reads and writes are split at
AWS service limits and retry unprocessed keys or writes a bounded number of
times. Number attributes deserialize as `Decimal` to preserve precision; sets,
binary values, nested mappings, lists, booleans, and `None` are supported.

## Secrets Manager settings source

`load_secret()` reads a JSON object from Secrets Manager. Its optional
`AwsSecretsManagerSettingsSource` adapts that mapping to Pydantic Settings.
Secret payloads must be JSON objects with unique keys and standard finite JSON
numbers.

## Testing

Unit tests use fake SDK clients and do not need AWS credentials. The LocalStack
end-to-end test runs through Testcontainers:

```console
make test-e2e
```

The E2E test skips when Docker is unavailable. Set `STD_REQUIRE_DOCKER=1` to
make a missing Docker daemon a test failure. See the [AWS API guide](../../docs/aws.md)
for configuration details and edge-case behavior.
