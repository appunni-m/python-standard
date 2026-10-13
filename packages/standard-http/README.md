# standard-http

`standard-http` adds an asynchronous HTTP client and authentication helpers to
the `standard` Python library. Install the package to use the `std.http`
import namespace:

From this repository, install the core and HTTP projects together:

```shell
python -m pip install . packages/standard-http
```

For an application, install the provider with
`python -m pip install 'standard[http]'` or install `standard-http` directly.

```python
from std.http import AuthConfig, BearerAuth, HttpClient, RetryConfig

client = HttpClient(
    base_url="https://api.example.com/v1/",
    auth_config=AuthConfig(auth=BearerAuth("your-token")),
    retries=RetryConfig(max_attempts=3),
)

async with client:
    response = await client.get("users", params={"active": "true"})
    response.raise_for_status()
    print(response.json())
```

The package also provides `BasicAuth`, `ApiKeyAuth`, `AuthBase`, `AuthConfig`,
and Pydantic response helpers such as `get_model`. See the [HTTP guide](../../docs/http.md)
for retry, timeout, token refresh, error, transport injection, and lifecycle
behavior.

The wheel contains only `std.http`; it does not bundle FastAPI, AWS, or other
integration modules.
