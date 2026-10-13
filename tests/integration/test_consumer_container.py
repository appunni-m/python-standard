from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def e2e_workspace() -> Iterator[Path]:
    repository = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix=".std-testcontainers-", dir=repository) as temporary:
        yield Path(temporary)


@pytest.fixture(scope="session")
def built_wheels(e2e_workspace: Path) -> dict[str, Path]:
    repository = Path(__file__).resolve().parents[2]
    wheel_dir = e2e_workspace / "wheels"
    wheel_dir.mkdir()
    projects = {
        "standard": repository,
        "standard-fastapi": repository / "packages" / "standard-fastapi",
        "standard-aws": repository / "packages" / "standard-aws",
        "standard-http": repository / "packages" / "standard-http",
        "standard-cache": repository / "packages" / "standard-cache",
        "standard-rdbms": repository / "packages" / "standard-rdbms",
    }
    for project_dir in projects.values():
        subprocess.run(
            [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(wheel_dir)],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    wheels = {name: next(wheel_dir.glob(f"{name.replace('-', '_')}-*.whl")) for name in projects}
    versions = {wheel.name.split("-", maxsplit=2)[1] for wheel in wheels.values()}
    assert len(versions) == 1, f"all distributions must share one version, got {versions}"
    return wheels


@pytest.mark.e2e
@pytest.mark.parametrize(
    "extra",
    ["", "fastapi", "aws", "http", "cache", "rdbms", "fastapi,aws,http,cache,rdbms"],
)
def test_requested_extra_installs_in_a_clean_python_container(
    e2e_workspace: Path,
    built_wheels: dict[str, Path],
    extra: str,
) -> None:
    import docker
    from testcontainers.core.container import DockerContainer

    selected_extras = set(extra.split(",")) if extra else set()
    selected_extras_literal = repr(sorted(selected_extras))
    program = """import asyncio
import importlib.util
import json
import os
from importlib.metadata import version
from importlib.resources import files
from std import __version__
from std.config import ConfigManager, TomlSettings, YamlSettings
selected_extras = set(__SELECTED_EXTRAS__)
assert __version__ == version('standard')
provider_distributions = {
    'fastapi': 'standard-fastapi',
    'aws': 'standard-aws',
    'http': 'standard-http',
    'cache': 'standard-cache',
    'rdbms': 'standard-rdbms',
}
for extra in selected_extras:
    assert version(provider_distributions[extra]) == version('standard')
assert files('std').joinpath('py.typed').is_file()
skill = files('std').joinpath(
    'skills/standard-idiomatic-python/SKILL.md'
).read_text(encoding='utf-8')
assert 'Use `std.service.Service`' in skill
assert 'Use `std.service.BackgroundService`' in skill
assert 'unreleased source' not in skill.lower()
snapshot = ConfigManager.from_file('/config').snapshot
class Settings(YamlSettings):
    std_config_file = '/config/settings.yaml'
    service: dict[str, str]
    port: int
    token: str
settings = Settings()
class TomlValues(TomlSettings):
    std_config_file = '/config/settings.toml'
    run_mode: str
toml_values = TomlValues()
payload = {
    'service': snapshot['service']['name'],
    'port': settings.port,
    'token': settings.token,
    'toml_mode': snapshot['run_mode'],
    'toml_settings_mode': toml_values.run_mode,
}
assert (importlib.util.find_spec('fastapi') is not None) == ('fastapi' in selected_extras)
assert (importlib.util.find_spec('boto3') is not None) == ('aws' in selected_extras)
assert (importlib.util.find_spec('httpx') is not None) == ('http' in selected_extras)
assert (importlib.util.find_spec('redis') is not None) == ('cache' in selected_extras)
assert (importlib.util.find_spec('sqlalchemy') is not None) == ('rdbms' in selected_extras)
providers = ('fastapi', 'aws', 'http', 'cache', 'rdbms')
for provider in providers:
    installed = importlib.util.find_spec(f'std.{provider}') is not None
    assert installed == (provider in selected_extras), provider
if 'fastapi' in selected_extras:
    from fastapi import FastAPI
    from std.fastapi import settings_dependency
    dependency = settings_dependency(Settings)
    assert callable(dependency.dependency)
    app = FastAPI()
    app.state.settings = settings
    @app.get('/health')
    async def health(settings: Settings = dependency):
        return {'service': settings.service['name']}
    assert any(getattr(route, 'path', None) == '/health' for route in app.routes)
    class Request:
        def __init__(self, app):
            self.app = app
    assert asyncio.run(dependency.dependency(Request(app))) is settings
if 'aws' in selected_extras:
    from std.aws import load_secret
    class Client:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == 'settings'
            return {'SecretString': '{"service":"aws-demo"}'}
    assert load_secret('settings', client=Client()) == {'service': 'aws-demo'}
if 'http' in selected_extras:
    from std.http import HttpClient, RetryConfig
    client = HttpClient(base_url='https://example.test', retries=RetryConfig(max_attempts=2))
    assert client.base_url == 'https://example.test'
    assert client.retry_config.max_attempts == 2
    asyncio.run(client.close())
if 'cache' in selected_extras:
    from std.cache import RedisClient, RedisConfig
    cache = RedisClient(RedisConfig(host='localhost', key_prefix='consumer:'))
    assert cache.config.key_prefix == 'consumer:'
if 'rdbms' in selected_extras:
    from std.rdbms import DatabaseConfig, SQLiteMemDatabase
    config = DatabaseConfig(driver='sqlite+aiosqlite', name=':memory:')
    database = SQLiteMemDatabase(config)
    assert database.settings.name == ':memory:'
    asyncio.run(database.dispose())
payload.update({provider: provider in selected_extras for provider in providers})
print(json.dumps(payload))
""".replace("__SELECTED_EXTRAS__", selected_extras_literal)
    compile(program, "<consumer-container-smoke>", "exec")
    expected = {
        "service": "container-demo",
        "port": 9000,
        "token": "container-value",
        "toml_mode": "container-toml",
        "toml_settings_mode": "container-toml",
        **{
            provider: provider in selected_extras
            for provider in ("fastapi", "aws", "http", "cache", "rdbms")
        },
    }

    try:
        docker.from_env().ping()
    except Exception as error:
        if os.environ.get("STD_REQUIRE_DOCKER") == "1":
            pytest.fail(
                f"Docker is required for this end-to-end run: {type(error).__name__}",
                pytrace=False,
            )
        pytest.skip(f"Docker is unavailable: {type(error).__name__}")

    wheel_dir = built_wheels["standard"].parent
    config_name = "-".join(sorted(selected_extras)) or "base"
    config_dir = e2e_workspace / f"config-{config_name}"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        "service:\n  name: container-demo\nport: 9000\ntoken: ${STD_TOKEN}\n",
        encoding="utf-8",
    )
    (config_dir / "settings.toml").write_text('run_mode = "container-toml"\n', encoding="utf-8")

    container = DockerContainer("python:3.12-slim", command="sleep infinity")
    container.with_volume_mapping(str(wheel_dir), "/wheels", "ro")
    container.with_volume_mapping(str(config_dir), "/config", "ro")
    container.with_env("STD_TOKEN", "container-value")
    with container as running:
        wheel_requirement = f"/wheels/{built_wheels['standard'].name}"
        if extra:
            wheel_requirement += f"[{extra}]"
        install = running.get_wrapped_container().exec_run(
            [
                "python",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--find-links",
                "/wheels",
                wheel_requirement,
            ]
        )
        assert install.exit_code == 0, install.output.decode("utf-8", errors="replace")
        result = running.get_wrapped_container().exec_run(["python", "-c", program])
        assert result.exit_code == 0, result.output.decode("utf-8", errors="replace")
        assert json.loads(result.output.decode("utf-8")) == expected
