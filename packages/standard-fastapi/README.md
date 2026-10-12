# standard-fastapi

FastAPI integration for the [`standard`](https://pypi.org/project/standard/)
Python library. After publication, install it directly with
`python -m pip install standard-fastapi` or use the `standard[fastapi]` extra.

Define the application's settings model in `core/settings.py`:

```python
from std.config import YamlSettings


class Settings(YamlSettings):
    std_config_file = "settings.yaml"
    service_name: str
```

In `main.py`, create the app and inject that settings instance once:

```python
from fastapi import Depends, FastAPI
from app.core.settings import Settings
from std.fastapi import settings_dependency


def create_app() -> FastAPI:
    settings = Settings()  # Create once in the application composition root.
    app = FastAPI()
    app.state.settings = settings
    settings_dep = settings_dependency(Settings)

    @app.get("/health")
    async def health(settings: Settings = Depends(settings_dep)) -> dict[str, str]:
        return {"service": settings.service_name}

    return app
```

Create `Settings()` once in `main.py` and assign the instance to
`app.state.settings`. The dependency returns that injected instance and never
constructs or reloads settings.

The integration includes `APIConfig` and `FastAPISetup` for app construction,
`LifecycleManager` for injected background services, `AppTokenAuth` and
`TokenAuthMiddleware`, health-check endpoints, request logging middleware, and
the Pydantic Settings dependency helper. Core service lifecycle types remain
available as `std.service` from `standard`.

The core library and this package are versioned independently. The `std`
command and core modules remain in the `standard` distribution. See the
[API reference](https://appunni-m.github.io/python-standard/api/) for public
signatures, behavior, and examples.
