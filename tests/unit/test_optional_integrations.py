from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType

import pytest
from pydantic_settings import BaseSettings


@pytest.mark.integration
def test_fastapi_settings_dependency_uses_settings_model() -> None:
    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("install the fastapi extra to exercise the FastAPI integration")
    from fastapi import FastAPI

    from std.fastapi import settings_dependency

    class Settings(BaseSettings):
        label: str = "standard"

    dependency = settings_dependency(Settings)
    assert callable(dependency.dependency)
    assert dependency.use_cache is True
    assert Settings().label == "standard"
    assert dependency.dependency().label == "standard"

    app = FastAPI()

    @app.get("/health")
    def health(settings: Settings = dependency) -> dict[str, str]:
        return {"label": settings.label}

    assert any(getattr(route, "path", None) == "/health" for route in app.routes)


def test_fastapi_settings_dependency_rejects_non_settings_types() -> None:
    from std.fastapi import settings_dependency

    with pytest.raises(TypeError, match="BaseSettings subclass"):
        settings_dependency(dict)  # type: ignore[arg-type]


def test_optional_integrations_explain_missing_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in tuple(sys.modules):
        if module_name == "fastapi" or module_name.startswith("fastapi."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.setitem(sys.modules, "fastapi", None)
    monkeypatch.delitem(sys.modules, "std.fastapi", raising=False)
    with pytest.raises(ImportError, match="FastAPI integration requires the fastapi extra"):
        importlib.import_module("std.fastapi")

    for module_name in tuple(sys.modules):
        if module_name == "boto3" or module_name.startswith("boto3."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.setitem(sys.modules, "boto3", None)
    monkeypatch.delitem(sys.modules, "std.aws", raising=False)
    with pytest.raises(ImportError, match="AWS integration requires the aws extra"):
        importlib.import_module("std.aws")


@pytest.mark.integration
def test_aws_secret_source_parses_json_and_redacts_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if importlib.util.find_spec("boto3") is None:
        with pytest.raises(ImportError, match="requires the aws extra"):
            importlib.import_module("std.aws")
        monkeypatch.setitem(sys.modules, "boto3", ModuleType("boto3"))

    aws = importlib.import_module("std.aws")
    AwsSecretError = aws.AwsSecretError
    AwsSecretsManagerSettingsSource = aws.AwsSecretsManagerSettingsSource
    load_secret = aws.load_secret

    class Client:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == "settings"
            return {"SecretString": '{"name":"api","enabled":true}'}

    class Settings(BaseSettings):
        name: str
        enabled: bool

    source = AwsSecretsManagerSettingsSource(Settings, "settings", client=Client())
    assert source() == {"name": "api", "enabled": True}
    assert source.get_field_value(None, "name") == (None, "name", False)
    assert load_secret("settings", client=Client()) == {"name": "api", "enabled": True}

    created_clients: list[tuple[str, str | None]] = []

    def make_client(service_name: str, *, region_name: str | None = None) -> Client:
        created_clients.append((service_name, region_name))
        return Client()

    monkeypatch.setattr(aws.boto3, "client", make_client, raising=False)
    assert load_secret("settings", region_name="eu-west-1") == {
        "name": "api",
        "enabled": True,
    }
    assert created_clients == [("secretsmanager", "eu-west-1")]

    class BinaryClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, bytes]:
            assert SecretId == "settings"
            return {"SecretBinary": b'{"name":"binary"}'}

    assert load_secret("settings", client=BinaryClient()) == {"name": "binary"}

    class NoPayloadClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {}

    with pytest.raises(AwsSecretError, match="no secret payload"):
        load_secret("settings", client=NoPayloadClient())

    class InvalidJsonClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {"SecretString": "not-json"}

    with pytest.raises(AwsSecretError, match="JSON decoding failed"):
        load_secret("settings", client=InvalidJsonClient())

    class DuplicateKeysClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {"SecretString": '{"name":"first","name":"second"}'}

    with pytest.raises(AwsSecretError, match="JSON decoding failed"):
        load_secret("settings", client=DuplicateKeysClient())

    class NonStandardJsonNumberClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {"SecretString": '{"value":NaN}'}

    with pytest.raises(AwsSecretError, match="JSON decoding failed"):
        load_secret("settings", client=NonStandardJsonNumberClient())

    class NonObjectClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {"SecretString": "[]"}

    with pytest.raises(AwsSecretError, match="must be a JSON object"):
        load_secret("settings", client=NonObjectClient())

    with pytest.raises(ValueError, match="secret_id must not be empty"):
        load_secret("", client=Client())
    with pytest.raises(ValueError, match="secret_id must not be empty"):
        load_secret(" \t\n", client=Client())

    class BrokenClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            raise RuntimeError("sensitive-response-body")

    with pytest.raises(AwsSecretError) as error:
        load_secret("private-secret-id", client=BrokenClient())
    assert "sensitive-response-body" not in str(error.value)
    assert "private-secret-id" not in str(error.value)

    def fail_to_create_client(service_name: str, *, region_name: str | None = None) -> Client:
        raise RuntimeError("sensitive-client-configuration")

    monkeypatch.setattr(aws.boto3, "client", fail_to_create_client, raising=False)
    with pytest.raises(AwsSecretError) as client_error:
        load_secret("private-secret-id")
    assert "sensitive-client-configuration" not in str(client_error.value)
    assert "private-secret-id" not in str(client_error.value)
