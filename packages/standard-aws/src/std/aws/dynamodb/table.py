"""Typed asynchronous DynamoDB operations and attribute-value conversion."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence, Set
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from .._client import open_client
from ..auth.credentials import CredentialProvider, DefaultCredentialProvider

T = TypeVar("T", bound=BaseModel)
_NUMBER_TYPES = (int, float, Decimal)


class DynamoDBConfig(BaseModel):
    """Table name, region, and optional DynamoDB-compatible endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    table_name: str = Field(min_length=1)
    region: str | None = Field(default=None, min_length=1)
    endpoint_url: str | None = None


class DynamoTable(Generic[T]):
    """Async low-level DynamoDB table client with Pydantic model conversion."""

    def __init__(
        self,
        config: DynamoDBConfig,
        model_class: type[T],
        credential_provider: CredentialProvider | None = None,
        key_schema: Sequence[Mapping[str, str]] | None = None,
        attribute_definitions: Sequence[Mapping[str, str]] | None = None,
        provisioned_throughput: Mapping[str, int] | None = None,
    ) -> None:
        """Configure a table facade and optional settings for ``create_table``."""
        if not issubclass(model_class, BaseModel):
            raise TypeError("model_class must be a Pydantic BaseModel subclass")
        self.config = config
        self.model_class = model_class
        self.credential_provider = credential_provider or DefaultCredentialProvider()
        self.key_schema = [dict(item) for item in key_schema] if key_schema is not None else None
        self.attribute_definitions = (
            [dict(item) for item in attribute_definitions]
            if attribute_definitions is not None
            else None
        )
        self.provisioned_throughput = dict(
            provisioned_throughput or {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        )

    @asynccontextmanager
    async def get_client(self) -> Any:
        """Yield an aioboto3 DynamoDB client and close it at context exit."""
        async with open_client(
            "dynamodb",
            region=self.config.region,
            endpoint_url=self.config.endpoint_url,
            credential_provider=self.credential_provider,
        ) as client:
            yield client

    async def create_table(self) -> dict[str, Any]:
        """Create a provisioned table using the configured key definitions."""
        if not self.key_schema or not self.attribute_definitions:
            raise ValueError("key_schema and attribute_definitions are required to create a table")
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.create_table(
                    TableName=self.config.table_name,
                    KeySchema=self.key_schema,
                    AttributeDefinitions=self.attribute_definitions,
                    ProvisionedThroughput=self.provisioned_throughput,
                ),
            )

    async def delete_table(self) -> dict[str, Any]:
        """Delete the configured table."""
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.delete_table(TableName=self.config.table_name))

    async def put_item(self, item: T | Mapping[str, Any]) -> dict[str, Any]:
        """Write a Pydantic model or mapping as a DynamoDB item."""
        values = item.model_dump(mode="python") if isinstance(item, BaseModel) else dict(item)
        if not values:
            raise ValueError("item must contain at least one attribute")
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.put_item(
                    TableName=self.config.table_name,
                    Item=self._serialize_item(values),
                ),
            )

    async def get_item(self, key: Mapping[str, Any], *, consistent_read: bool = False) -> T | None:
        """Return a validated model, or ``None`` when the primary key is absent."""
        if not key:
            raise ValueError("key must contain at least one attribute")
        async with self.get_client() as client:
            response = await client.get_item(
                TableName=self.config.table_name,
                Key=self._serialize_item(key),
                ConsistentRead=consistent_read,
            )
        item = response.get("Item")
        return self.model_class.model_validate(self._deserialize_item(item)) if item else None

    async def delete_item(self, key: Mapping[str, Any]) -> dict[str, Any]:
        """Delete the item matching a primary-key mapping."""
        if not key:
            raise ValueError("key must contain at least one attribute")
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.delete_item(
                    TableName=self.config.table_name,
                    Key=self._serialize_item(key),
                ),
            )

    async def query(
        self,
        key_condition_expression: str,
        expression_attribute_values: Mapping[str, Any] | None = None,
        expression_attribute_names: Mapping[str, str] | None = None,
        filter_expression: str | None = None,
        index_name: str | None = None,
        limit: int | None = None,
        scan_index_forward: bool = True,
    ) -> list[T]:
        """Query all result pages and return validated models, respecting ``limit``."""
        if not key_condition_expression.strip():
            raise ValueError("key_condition_expression must not be empty")
        self._validate_limit(limit)
        kwargs: dict[str, Any] = {
            "TableName": self.config.table_name,
            "KeyConditionExpression": key_condition_expression,
            "ScanIndexForward": scan_index_forward,
        }
        self._add_expression_options(
            kwargs,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            filter_expression=filter_expression,
            index_name=index_name,
        )
        async with self.get_client() as client:
            return await self._read_pages(client.query, kwargs, limit)

    async def scan(
        self,
        filter_expression: str | None = None,
        expression_attribute_values: Mapping[str, Any] | None = None,
        expression_attribute_names: Mapping[str, str] | None = None,
        index_name: str | None = None,
        limit: int | None = None,
    ) -> list[T]:
        """Scan all result pages and return validated models, respecting ``limit``."""
        self._validate_limit(limit)
        kwargs: dict[str, Any] = {"TableName": self.config.table_name}
        self._add_expression_options(
            kwargs,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            filter_expression=filter_expression,
            index_name=index_name,
        )
        async with self.get_client() as client:
            return await self._read_pages(client.scan, kwargs, limit)

    async def update_item(
        self,
        key: Mapping[str, Any],
        update_expression: str,
        expression_attribute_values: Mapping[str, Any] | None = None,
        expression_attribute_names: Mapping[str, str] | None = None,
        condition_expression: str | None = None,
        return_values: str = "UPDATED_NEW",
    ) -> dict[str, Any]:
        """Update one item using DynamoDB's expression syntax."""
        if not key:
            raise ValueError("key must contain at least one attribute")
        if not update_expression.strip():
            raise ValueError("update_expression must not be empty")
        if return_values not in {"NONE", "ALL_OLD", "UPDATED_OLD", "ALL_NEW", "UPDATED_NEW"}:
            raise ValueError("return_values is not a valid DynamoDB ReturnValues option")
        kwargs: dict[str, Any] = {
            "TableName": self.config.table_name,
            "Key": self._serialize_item(key),
            "UpdateExpression": update_expression,
            "ReturnValues": return_values,
        }
        self._add_expression_options(
            kwargs,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            condition_expression=condition_expression,
        )
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.update_item(**kwargs))

    async def batch_get_items(
        self,
        keys: Sequence[Mapping[str, Any]],
        consistent_read: bool = False,
        projection_expression: str | None = None,
    ) -> dict[str, Any]:
        """Fetch keys in DynamoDB's 100-key batches and retry unprocessed keys."""
        if not keys:
            return {"Responses": {self.config.table_name: []}, "UnprocessedKeys": {}}
        if any(not key for key in keys):
            raise ValueError("keys must not contain empty mappings")
        wire_keys = [self._serialize_item(key) for key in keys]
        responses: list[dict[str, Any]] = []
        unprocessed: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        async with self.get_client() as client:
            for start in range(0, len(wire_keys), 100):
                pending = wire_keys[start : start + 100]
                for attempt in range(6):
                    table_request: dict[str, Any] = {
                        "Keys": pending,
                        "ConsistentRead": consistent_read,
                    }
                    if projection_expression is not None:
                        table_request["ProjectionExpression"] = projection_expression
                    response = await client.batch_get_item(
                        RequestItems={self.config.table_name: table_request}
                    )
                    responses.extend(response.get("Responses", {}).get(self.config.table_name, []))
                    metadata = response.get("ResponseMetadata", metadata)
                    pending = (
                        response.get("UnprocessedKeys", {})
                        .get(self.config.table_name, {})
                        .get("Keys", [])
                    )
                    if not pending:
                        break
                    if attempt < 5:
                        await asyncio.sleep(min(0.05 * (2**attempt), 1.0))
                unprocessed.extend(pending)
        result: dict[str, Any] = {
            "Responses": {self.config.table_name: responses},
            "UnprocessedKeys": {},
        }
        if unprocessed:
            request: dict[str, Any] = {
                "Keys": unprocessed,
                "ConsistentRead": consistent_read,
            }
            if projection_expression is not None:
                request["ProjectionExpression"] = projection_expression
            result["UnprocessedKeys"] = {self.config.table_name: request}
        if metadata:
            result["ResponseMetadata"] = metadata
        return result

    async def batch_write_items(
        self,
        items_to_put: Sequence[Mapping[str, Any]] | None = None,
        items_to_delete: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Write and delete items in 25-operation batches with bounded retries."""
        requests: list[dict[str, Any]] = []
        for item in items_to_put or []:
            if not item:
                raise ValueError("items_to_put must not contain empty mappings")
            requests.append({"PutRequest": {"Item": self._serialize_item(item)}})
        for key in items_to_delete or []:
            if not key:
                raise ValueError("items_to_delete must not contain empty mappings")
            requests.append({"DeleteRequest": {"Key": self._serialize_item(key)}})
        if not requests:
            return {"UnprocessedItems": {}}

        unprocessed: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        async with self.get_client() as client:
            for start in range(0, len(requests), 25):
                pending = requests[start : start + 25]
                for attempt in range(6):
                    response = await client.batch_write_item(
                        RequestItems={self.config.table_name: pending}
                    )
                    metadata = response.get("ResponseMetadata", metadata)
                    pending = response.get("UnprocessedItems", {}).get(self.config.table_name, [])
                    if not pending:
                        break
                    if attempt < 5:
                        await asyncio.sleep(min(0.05 * (2**attempt), 1.0))
                unprocessed.extend(pending)
        result: dict[str, Any] = {"UnprocessedItems": {}}
        if unprocessed:
            result["UnprocessedItems"] = {self.config.table_name: unprocessed}
        if metadata:
            result["ResponseMetadata"] = metadata
        return result

    async def batch_write_items_to_table(
        self, items: Sequence[T | Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Write Pydantic models or mappings using the bounded batch writer."""
        values = [
            item.model_dump(mode="python") if isinstance(item, BaseModel) else item
            for item in items
        ]
        return await self.batch_write_items(items_to_put=values)

    async def batch_get_items_from_table(
        self,
        keys: Sequence[Mapping[str, Any]],
        consistent_read: bool = False,
    ) -> list[T]:
        """Return model instances for all successfully fetched keys."""
        response = await self.batch_get_items(keys, consistent_read=consistent_read)
        wire_items = response.get("Responses", {}).get(self.config.table_name, [])
        return [
            self.model_class.model_validate(self._deserialize_item(item)) for item in wire_items
        ]

    async def _read_pages(
        self, operation: Any, kwargs: dict[str, Any], limit: int | None
    ) -> list[T]:
        items: list[T] = []
        request = dict(kwargs)
        while True:
            if limit is not None:
                remaining = limit - len(items)
                if remaining <= 0:
                    break
                request["Limit"] = remaining
            response = await operation(**request)
            items.extend(
                self.model_class.model_validate(self._deserialize_item(item))
                for item in response.get("Items", [])
            )
            next_key = response.get("LastEvaluatedKey")
            if not next_key or (limit is not None and len(items) >= limit):
                break
            request["ExclusiveStartKey"] = next_key
        return items[:limit] if limit is not None else items

    @staticmethod
    def _validate_limit(limit: int | None) -> None:
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")

    def _add_expression_options(
        self,
        kwargs: dict[str, Any],
        *,
        expression_attribute_values: Mapping[str, Any] | None = None,
        expression_attribute_names: Mapping[str, str] | None = None,
        filter_expression: str | None = None,
        index_name: str | None = None,
        condition_expression: str | None = None,
    ) -> None:
        if expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = {
                key: self._serialize_value(value)
                for key, value in expression_attribute_values.items()
            }
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = dict(expression_attribute_names)
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        if index_name is not None:
            kwargs["IndexName"] = index_name
        if condition_expression is not None:
            kwargs["ConditionExpression"] = condition_expression

    def _serialize_item(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """Convert Python attributes to DynamoDB low-level attribute values."""
        return {key: self._serialize_value(value) for key, value in item.items()}

    def _serialize_value(self, value: Any) -> dict[str, Any]:
        """Serialize nested values while preserving numeric precision and rejecting ambiguity."""
        if value is None:
            return {"NULL": True}
        if isinstance(value, bool):
            return {"BOOL": value}
        if isinstance(value, str):
            return {"S": value}
        if isinstance(value, (bytes, bytearray, memoryview)):
            return {"B": bytes(value)}
        if isinstance(value, _NUMBER_TYPES):
            return {"N": self._number_to_string(value)}
        if isinstance(value, Mapping):
            return {"M": self._serialize_item(value)}
        if isinstance(value, (list, tuple)):
            return {"L": [self._serialize_value(item) for item in value]}
        if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
            return self._serialize_set(value)
        raise TypeError(f"unsupported DynamoDB value type: {type(value).__name__}")

    def _serialize_set(self, value: Set[Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("DynamoDB does not support empty sets")
        if all(isinstance(item, str) for item in value):
            return {"SS": sorted(value)}
        if all(isinstance(item, (bytes, bytearray, memoryview)) for item in value):
            return {"BS": [bytes(item) for item in value]}
        if all(isinstance(item, _NUMBER_TYPES) and not isinstance(item, bool) for item in value):
            return {"NS": sorted(self._number_to_string(item) for item in value)}
        raise TypeError("DynamoDB sets must contain only strings, bytes, or numbers of one kind")

    @staticmethod
    def _number_to_string(value: int | float | Decimal) -> str:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("DynamoDB numbers must be finite values") from error
        if not number.is_finite():
            raise ValueError("DynamoDB numbers must be finite values")
        return str(number)

    def _deserialize_item(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """Convert DynamoDB attribute values into Python values."""
        return {key: self._deserialize_value(value) for key, value in item.items()}

    def _deserialize_value(self, value: Mapping[str, Any]) -> Any:
        """Decode one low-level DynamoDB attribute, rejecting malformed unions."""
        if len(value) != 1:
            raise ValueError("DynamoDB attribute values must contain exactly one type")
        kind, payload = next(iter(value.items()))
        if kind == "S":
            return payload
        if kind == "N":
            try:
                number = Decimal(payload)
            except (InvalidOperation, TypeError) as error:
                raise ValueError("invalid DynamoDB number") from error
            if not number.is_finite():
                raise ValueError("DynamoDB numbers must be finite values")
            return number
        if kind == "B":
            return bytes(payload)
        if kind == "BOOL":
            if not isinstance(payload, bool):
                raise ValueError("DynamoDB BOOL must contain a boolean")
            return payload
        if kind == "NULL":
            if payload is not True:
                raise ValueError("DynamoDB NULL must be true")
            return None
        if kind == "SS":
            return set(payload)
        if kind == "NS":
            return {Decimal(number) for number in payload}
        if kind == "BS":
            return {bytes(binary) for binary in payload}
        if kind == "L":
            return [self._deserialize_value(item) for item in payload]
        if kind == "M":
            return self._deserialize_item(payload)
        raise ValueError(f"unsupported DynamoDB attribute type: {kind}")


__all__ = ["DynamoDBConfig", "DynamoTable"]
