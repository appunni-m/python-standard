"""Optional AWS Secrets Manager settings source."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import import_module
from typing import Any, NoReturn

try:
    # The optional type environment intentionally omits third-party boto3 stubs.
    boto3: Any = import_module("boto3")
except ImportError as error:  # pragma: no cover - depends on installation extra
    raise ImportError(
        "AWS integration requires the aws extra; from a checkout run `pip install -e '.[aws]'`"
    ) from error

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class AwsSecretError(RuntimeError):
    """A secret could not be retrieved or did not contain a JSON object."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting ambiguous duplicate keys."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> NoReturn:
    """Reject Python's non-standard JSON NaN and Infinity extensions."""
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def load_secret(
    secret_id: str,
    *,
    region_name: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Load a JSON object from AWS Secrets Manager without exposing secret data."""
    if not secret_id.strip():
        raise ValueError("secret_id must not be empty")
    try:
        secrets_client = (
            client
            if client is not None
            else boto3.client("secretsmanager", region_name=region_name)
        )
        response = secrets_client.get_secret_value(SecretId=secret_id)
        if "SecretString" in response:
            raw = response["SecretString"]
        elif "SecretBinary" in response:
            binary = response["SecretBinary"]
            raw = (
                binary.decode("utf-8")
                if isinstance(binary, bytes)
                else bytes(binary).decode("utf-8")
            )
        else:
            raise AwsSecretError("AWS Secrets Manager returned no secret payload")
        value = json.loads(
            raw,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_non_finite_number,
        )
    except AwsSecretError:
        raise
    except Exception:
        raise AwsSecretError("AWS Secrets Manager request or JSON decoding failed") from None
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise AwsSecretError("AWS secret payload must be a JSON object with string keys")
    return dict(value)


class AwsSecretsManagerSettingsSource(PydanticBaseSettingsSource):
    """Pydantic source that maps an AWS Secrets Manager JSON object to fields."""

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        secret_id: str,
        *,
        region_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Configure the source with a Settings model and secret identifier."""
        super().__init__(settings_cls)
        self.secret_id = secret_id
        self.region_name = region_name
        self.client = client

    def __call__(self) -> dict[str, object]:
        """Return the secret object as a mapping of Settings field values."""
        return load_secret(self.secret_id, region_name=self.region_name, client=self.client)

    def get_field_value(self, field: object, field_name: str) -> tuple[object, str, bool]:
        """Satisfy the Pydantic source protocol; this source returns a full mapping."""
        return None, field_name, False


__all__ = ["AwsSecretError", "AwsSecretsManagerSettingsSource", "load_secret"]
