"""Shared pytest fixtures for hub-mcp tests.

Why no TestClient: Starlette TestClient uses anyio.from_thread.start_blocking_portal
to run the ASGI app in a separate task. With UpstreamClient.start() which uses
mcp.client.streamable_http.streamable_http_client (creates anyio task_group),
the cancel-scope-exited-in-different-task RuntimeError fires at teardown.
Verified manually: /tmp/direct_test.py works fine against real context7.

So we use httpx.AsyncClient with ASGITransport and run lifespan in the same
task via app.router.lifespan_context(app).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from hub_mcp.server import create_app

VALID_CONFIG_YAML = """
listen:
  host: 127.0.0.1
  port: 46380
hindsight:
  url: http://127.0.0.1:8888/v1
  bank_id: default
  enabled: false
upstream:
  - name: fetch
    url: http://localhost:46381/mcp
    enabled: true
    timeout: 5.0
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Write a valid config.yaml to tmp dir."""
    path = tmp_path / "config.yaml"
    path.write_text(VALID_CONFIG_YAML)
    return path


class LifespanAsyncClient:
    """Async HTTPX client that runs Starlette lifespan in the same async task.

    Usage:
        async with LifespanAsyncClient(app) as client:
            r = await client.get("/health")
    """

    def __init__(
        self,
        app: Any,
        **client_kwargs: Any,
    ) -> None:
        self._app = app
        self._lifespan_cm: Any = None
        self._client: httpx.AsyncClient | None = None
        self._client_kwargs = client_kwargs

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan_cm = self._app.router.lifespan_context(self._app)
        await self._lifespan_cm.__aenter__()
        transport = httpx.ASGITransport(app=self._app)
        self._client = httpx.AsyncClient(
            transport=transport, base_url="http://test", **self._client_kwargs
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)
        if self._lifespan_cm is not None:
            await self._lifespan_cm.__aexit__(*exc)


@pytest.fixture
async def http_client(config_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Yields an AsyncClient with full lifespan (upstream_map, audit) populated."""
    app = create_app(config_path=config_path)
    async with LifespanAsyncClient(app) as client:
        yield client
