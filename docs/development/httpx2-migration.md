# HTTPX2 migration

## Client injection and stability

The main branch uses `httpx2>=2.16.2,<3` and requires Python >=3.14.
`Bot(..., client=...)` and `HTTPTransport(..., client=...)` accept an
`httpx2.AsyncClient`. Passing a client from another HTTP library raises `TypeError`.
HTTPX clients, responses, exceptions, URLs and transports are separate types and must
be replaced at this boundary. There is no dual-library adapter or process-wide alias.

```python
import ssl

import httpx2

from python_vk_bot import Bot


async def use_bot(token: str, user_id: int) -> None:
    context = ssl.create_default_context(cafile="/path/to/organization-ca.pem")
    async with httpx2.AsyncClient(verify=context, trust_env=False) as client:
        async with Bot(token, client=client) as bot:
            await bot.get_user_info(user_id)
```

The CA path above is a deployment-specific example. Omit `verify=context` and the
context creation to use the default system trust store. TLS verification remains on.
Configure proxies with `proxy=` on the injected client. `limits=`, event hooks, custom
transports and optional HTTP/2 likewise belong to that client. HTTP/2 and SOCKS require
HTTPX2's respective `http2` and `socks` extras; the library does not enable them itself.
Use `httpx2.MockTransport` and `httpx2.ASGITransport` for local synthetic responses.

The caller closes injected clients. Internally created clients are reused until
shutdown, closed by the transport, and recreated on reinitialization. Reinitializing
with a closed injected client raises `LifecycleError`. No ownership transfer occurs.
The `client` keyword and other method signatures remain stable apart from the new
HTTP library types. This is a breaking dependency-boundary change in the alpha API;
there is no compatibility guarantee for HTTPX objects.

## Request and security behavior

VK API requests still use POST with per-request Bearer authorization. Polling uses
GET with the Long Poll key in the query; uploads use buffered multipart bytes without
the community token. Credentials never become client defaults. Default Authorization
headers and credential query parameters are rejected, as before. Upload clients also
reject default query parameters and Content-Type headers.

HTTPS URL validation rejects user information and fragments, and Long Poll also
rejects query parameters. Invalid Long Poll URLs become a sanitized
`InvalidResponseError`, without including the input URL. Redirects remain disabled
per request, including when an injected client enables them. URL validation does not
provide a DNS/IP allowlist: deployment network policies still apply.

Request timeouts remain the configured scalar timeout for connect/read/write/pool;
Long Poll uses at least `wait + 10` seconds. Injecting a client does not override these
per-request timeouts. Network `httpx2.RequestError` exceptions become `NetworkError`
without the original exception text. HTTP status errors expose status and parsed
`Retry-After`; no automatic retry is added. Polling retains its existing recovery
policy. Cancellation propagates and file-reading cleanup is unchanged.

The `_RedactQuery` filter now targets `httpx2` and removes URL query strings from its
standard request records process-wide. This includes unrelated HTTPX2 requests.
The filter does not sanitize user hooks, custom transports, arbitrary messages or
third-party telemetry. Never log authorization headers, request bodies, or full
message/event payloads. Low-level logging uses `httpcore2.*`; avoid enabling detailed
wire diagnostics in production, as response headers and exception details may contain
server-controlled data. No direct `httpcore2` dependency or tracing hook is added.

## Observable dependency changes

HTTPX2 verifies against the operating system trust store through `truststore` instead
of the former certifi default. `SSL_CERT_FILE` and `SSL_CERT_DIR` remain supported;
use an explicit `ssl.SSLContext` for controlled custom CA configuration. Default
clients retain environment proxy/CA handling; `trust_env=False` on an injected client
opts out. Review HTTPX2's expanded `NO_PROXY` matching for wildcards, CIDR and IPv6.
The default User-Agent is `python-httpx2/<version>`. Deprecation warnings may now be
visible. Configure `httpx2` and `httpcore2.*` logger names in application logging.

## Dependency selection and compatibility branch

Verified on 2026-11-26: stable HTTPX2 is 2.16.2, requiring Python >=3.11.
The lower bound includes the restored runtime type aliases in 2.16.2, invalid redirect
handling in 2.16.1, and the recent proxy/URL fixes. `<3` excludes a future major API
change; the lock file fixes the resolved version. New 2.x behavior still requires
regression checks when updating the lock.

The approved strategy for `compat/py39` is HTTPX on every Python version supported by
that branch. It avoids environment-dependent exception/type identities, two test
matrices and conditional imports. Transfer only applicable behavior/security fixes,
adapting imports and logger names to HTTPX; preserve branch-specific metadata and
Python 3.9 syntax. This describes the strategy, not a completed branch transfer.

## References

Reviewed on 2026-11-26:

- [HTTPX2 migration guide](https://pydantic.dev/docs/httpx2/get-started/migration/)
- [HTTPX2 release and Python requirements](https://pypi.org/project/httpx2/)
- [HTTPX2 changelog](https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md)
- [TLS configuration](https://pydantic.dev/docs/httpx2/advanced/ssl/)
- [Logging](https://pydantic.dev/docs/httpx2/guides/logging/)
- [PTB design reference](../architecture/python-telegram-bot-compatibility.md#httpx2-transport)
