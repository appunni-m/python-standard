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
def built_wheel(e2e_workspace: Path) -> tuple[Path, Path]:
    repository = Path(__file__).resolve().parents[2]
    wheel_dir = e2e_workspace / "wheels"
    wheel_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(wheel_dir)],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return repository, next(wheel_dir.glob("standard-*.whl"))


@pytest.mark.e2e
@pytest.mark.parametrize("extra", ["", "fastapi", "aws", "fastapi,aws"])
def test_requested_extra_installs_in_a_clean_python_container(
    e2e_workspace: Path,
    built_wheel: tuple[Path, Path],
    extra: str,
) -> None:
    import docker
    from testcontainers.core.container import DockerContainer

    selected_extras = set(extra.split(",")) if extra else set()
    selected_extras_literal = repr(sorted(selected_extras))
    program = """import importlib.util
import json
import os
from importlib.resources import files
from std.config import ConfigManager, TomlSettings, YamlSettings
selected_extras = set(__SELECTED_EXTRAS__)
assert files('std').joinpath('py.typed').is_file()
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
if 'fastapi' in selected_extras:
    from fastapi import FastAPI
    from std.fastapi import settings_dependency
    dependency = settings_dependency(Settings)
    assert callable(dependency.dependency)
    assert dependency.dependency().model_dump() == settings.model_dump()
    app = FastAPI()
    @app.get('/health')
    def health(settings: Settings = dependency):
        return {'service': settings.service['name']}
    assert any(getattr(route, 'path', None) == '/health' for route in app.routes)
if 'aws' in selected_extras:
    from std.aws import load_secret
    class Client:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == 'settings'
            return {'SecretString': '{"service":"aws-demo"}'}
    assert load_secret('settings', client=Client()) == {'service': 'aws-demo'}
payload.update({'fastapi': 'fastapi' in selected_extras, 'aws': 'aws' in selected_extras})
print(json.dumps(payload))
""".replace("__SELECTED_EXTRAS__", selected_extras_literal)
    compile(program, "<consumer-container-smoke>", "exec")
    expected = {
        "service": "container-demo",
        "port": 9000,
        "token": "container-value",
        "toml_mode": "container-toml",
        "toml_settings_mode": "container-toml",
        "fastapi": "fastapi" in selected_extras,
        "aws": "aws" in selected_extras,
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

    _, wheel_path = built_wheel
    wheel_dir = wheel_path.parent
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
        wheel_requirement = f"/wheels/{wheel_path.name}"
        if extra:
            wheel_requirement += f"[{extra}]"
        install = running.get_wrapped_container().exec_run(
            ["python", "-m", "pip", "install", "--disable-pip-version-check", wheel_requirement]
        )
        assert install.exit_code == 0, install.output.decode("utf-8", errors="replace")
        result = running.get_wrapped_container().exec_run(["python", "-c", program])
        assert result.exit_code == 0, result.output.decode("utf-8", errors="replace")
        assert json.loads(result.output.decode("utf-8")) == expected
