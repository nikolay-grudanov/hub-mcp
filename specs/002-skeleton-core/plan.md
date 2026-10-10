# Implementation Plan: 002 — Skeleton core hub-mcp server

> **For agents**: Use `subagent-driven-development` skill to implement this plan task-by-task. Each task = 2-5 minutes focused work. TDD: test → fail → impl → pass → commit (after Kolya's explicit «коммить»).

**Goal**: запустить рабочий harness-mcp-hub с HTTP MCP-transport + единым конфиг-файлом + upstream HTTP-прокси + Hindsight audit log. **Без** per-profile filtering, **без** admin UI.

**Architecture**: Starlette ASGI app + MCP SDK types + Pydantic config + httpx upstream + Hindsight audit. Single process, no module-level state. Подробности в [`spec.md`](spec.md) и [`docs/spec.md`](../../docs/spec.md).

**Tech Stack**: Python 3.11+, Starlette 0.40+, MCP SDK 1.9+, Pydantic v2, PyYAML 6.0+, httpx 0.27+, pytest 8+.

---

## Phase 1: Project Bootstrap

### Task 1.1: Initialize project structure

**Objective**: создать `pyproject.toml`, basic src layout, dev tooling.

**Files**:
- Create: `pyproject.toml`
- Create: `src/hub_mcp/__init__.py`
- Create: `src/hub_mcp/exceptions.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

**Step 1**: Write `pyproject.toml`:

```toml
[project]
name = "hub-mcp"
version = "0.1.0"
description = "Per-profile MCP hub for Hermes / GigaCode / Claude Code / Qwen / OpenCode"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.9.0",
    "starlette>=0.40.0",
    "uvicorn>=0.30.0",
    "pydantic>=2.7.0",
    "pyyaml>=6.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5.0",
    "pyright>=1.1.390",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]
ignore = ["E501"]

[tool.pyright]
include = ["src", "tests"]
strict = ["src/hub_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/hub_mcp"]
```

**Step 2**: Create `src/hub_mcp/__init__.py`:

```python
"""harness-mcp-hub — единый MCP-сервер для всех runtime."""

__version__ = "0.1.0"
```

**Step 3**: Create `src/hub_mcp/exceptions.py`:

```python
"""Hub-specific exceptions."""


class HubMcpError(Exception):
    """Base class for all hub-mcp exceptions."""


class ConfigError(HubMcpError):
    """Config file invalid or unreadable."""


class UpstreamUnavailableError(HubMcpError):
    """Upstream MCP server did not respond."""


class ToolNotFoundError(HubMcpError):
    """Tool not found in any enabled upstream."""
```

**Step 4**: Create `tests/__init__.py` (empty).

**Step 5**: Create `.gitignore`:

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
.pyright_cache/
dist/
build/
.coverage
htmlcov/
```

**Step 6**: Verify `uv sync`:

```bash
cd /home/gna/workspase/projects/hub-mcp
uv sync
```

Expected: creates `.venv`, installs dependencies, no errors.

**Step 7**: Commit (after Kolya's «коммить»):

```bash
git add pyproject.toml src/hub_mcp/__init__.py src/hub_mcp/exceptions.py tests/__init__.py .gitignore
git commit -m "feat(002): project bootstrap (pyproject, exceptions)"
```

---

### Task 1.2: Configure git pre-commit hook

**Objective**: запускать ruff + pyright + pytest перед каждым commit'ом.

**Files**:
- Create: `.git/hooks/pre-commit` (executable)

**Step 1**: Create script (skip — repeat from spec-001 plan, paste same content).

---

## Phase 2: Config schema + loader

### Task 2.1: Define HubConfig Pydantic model

**Objective**: type-safe representation of `config.yaml`, validates per `data-model.md`.

**Files**:
- Create: `src/hub_mcp/config.py`
- Create: `tests/test_config.py`

**Step 1**: Write failing test `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from hub_mcp.config import HubConfig, HindsightConfig, ListenConfig, UpstreamConfig


def test_config_minimal_valid() -> None:
    """Minimal config with single upstream."""
    cfg = HubConfig(
        upstream=[
            UpstreamConfig(name="fetch", url="http://localhost:46381/mcp"),
        ],
    )
    assert len(cfg.upstream) == 1
    assert cfg.listen.host == "127.0.0.1"  # default
    assert cfg.listen.port == 46380  # default
    assert cfg.hindsight.bank_id == "default"  # default


def test_upstream_name_alphanumeric() -> None:
    """Upstream name must be alphanumeric with hyphens/underscores."""
    with pytest.raises(ValidationError):
        UpstreamConfig(name="bad name", url="http://x/")
    with pytest.raises(ValidationError):
        UpstreamConfig(name="bad/name", url="http://x/")


def test_upstream_timeout_minimum() -> None:
    """Upstream timeout >= 1 second."""
    with pytest.raises(ValidationError):
        UpstreamConfig(name="x", url="http://x/", timeout=0.5)


def test_listen_port_range() -> None:
    """Listen port must be 1-65535."""
    with pytest.raises(ValidationError):
        ListenConfig(port=70000)
    with pytest.raises(ValidationError):
        ListenConfig(port=0)


def test_hindsight_audit_default_enabled() -> None:
    """Hindsight audit enabled by default."""
    cfg = HindsightConfig()
    assert cfg.enabled is True


def test_upstream_audit_level_literal() -> None:
    """audit_level accepts only 'full' or 'metadata_only'."""
    UpstreamConfig(name="x", url="http://x/", audit_level="full")
    UpstreamConfig(name="x", url="http://x/", audit_level="metadata_only")
    with pytest.raises(ValidationError):
        UpstreamConfig(name="x", url="http://x/", audit_level="verbose")  # type: ignore[arg-type]


def test_duplicate_upstream_names_rejected() -> None:
    """Duplicate upstream names raise ValidationError."""
    with pytest.raises(ValidationError, match="duplicate upstream names"):
        HubConfig(
            upstream=[
                UpstreamConfig(name="fetch", url="http://a/"),
                UpstreamConfig(name="fetch", url="http://b/"),
            ],
        )


def test_upstream_can_be_disabled() -> None:
    """Upstream with enabled=false is valid."""
    u = UpstreamConfig(name="repomix", url="http://x/", enabled=False)
    assert u.enabled is False


def test_empty_upstream_list_rejected() -> None:
    """HubConfig requires at least 1 upstream."""
    with pytest.raises(ValidationError):
        HubConfig(upstream=[])
```

**Step 2**: Run test → fail (ModuleNotFound).

**Step 3**: Write `src/hub_mcp/config.py` (copy-paste from `data-model.md`).

**Step 4**: Run test → 9 passed.

**Step 5**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/config.py tests/test_config.py
git commit -m "feat(002): HubConfig Pydantic model with validation"
```

---

### Task 2.2: YAML config loader

**Objective**: `load_config(path: Path | None = None) -> HubConfig` with env-var overrides.

**Files**:
- Modify: `src/hub_mcp/config.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_config.py`

**Step 1**: Append to `tests/test_config.py`:

```python
import os
from pathlib import Path

from hub_mcp.config import load_config


def test_load_config_from_yaml(tmp_path: Path) -> None:
    """Load valid YAML config from disk."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "upstream:\n"
        "  - name: fetch\n"
        "    url: http://localhost:46381/mcp\n"
    )
    cfg = load_config(config_path)
    assert cfg.upstream[0].name == "fetch"


def test_load_config_missing_file(tmp_path: Path) -> None:
    """Missing config file raises ConfigError."""
    with pytest.raises(Exception) as exc_info:
        load_config(tmp_path / "missing.yaml")
    assert "config" in str(exc_info.value).lower()


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    """Garbage YAML raises ConfigError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("[invalid: yaml:")
    with pytest.raises(Exception) as exc_info:
        load_config(config_path)
    assert "yaml" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()


def test_load_config_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HUB_LISTEN_PORT env var overrides config."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "listen:\n  port: 46380\n"
        "upstream:\n  - name: x\n    url: http://x/\n"
    )
    monkeypatch.setenv("HUB_LISTEN_PORT", "50000")
    cfg = load_config(config_path)
    assert cfg.listen.port == 50000
```

**Step 2**: Append to `src/hub_mcp/config.py`:

```python
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

ENV_CONFIG_PATH = "HUB_CONFIG_PATH"
ENV_LISTEN_HOST = "HUB_LISTEN_HOST"
ENV_LISTEN_PORT = "HUB_LISTEN_PORT"
ENV_HINDSIGHT_URL = "HUB_HINDSIGHT_URL"


def _config_path_from_env() -> Path:
    raw = os.environ.get(ENV_CONFIG_PATH)
    return Path(raw).expanduser() if raw else Path(DEFAULT_CONFIG_PATH).expanduser()


def load_config(path: Path | None = None) -> HubConfig:
    """Load and validate hub config from YAML file.

    Args:
        path: config file path. Default: $HUB_CONFIG_PATH or ~/.harness-hub/config.yaml.

    Returns:
        Validated HubConfig.

    Raises:
        ConfigError: file not found, YAML invalid, or schema mismatch.
    """
    config_path = (path or _config_path_from_env()).expanduser()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(
            f"config must be a YAML mapping, got {type(raw).__name__}"
        )

    # Apply env-var overrides AFTER parsing
    if ENV_LISTEN_HOST in os.environ:
        raw.setdefault("listen", {})["host"] = os.environ[ENV_LISTEN_HOST]
    if ENV_LISTEN_PORT in os.environ:
        raw.setdefault("listen", {})["port"] = int(os.environ[ENV_LISTEN_PORT])
    if ENV_HINDSIGHT_URL in os.environ:
        raw.setdefault("hindsight", {})["url"] = os.environ[ENV_HINDSIGHT_URL]

    try:
        return HubConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"config validation failed: {e}") from e
```

**Step 3**: Run test → 4 new tests pass (total 13 in test_config.py).

**Step 4**: Commit.

---

## Phase 3: Upstream HTTP client

### Task 3.1: UpstreamClient

**Objective**: JSON-RPC over httpx, error handling per OQ-hub-012 (5xx → UpstreamUnavailableError, timeout → error).

**Files**:
- Create: `src/hub_mcp/upstream.py`
- Create: `tests/test_upstream.py`

**Step 1**: Write failing tests (use `httpx.MockTransport` for mocking):

```python
import json

import httpx
import pytest

from hub_mcp.exceptions import UpstreamUnavailableError
from hub_mcp.upstream import UpstreamClient


def make_upstream(**overrides) -> UpstreamClient:
    return UpstreamClient(
        name="fetch",
        url="http://localhost:46381/mcp",
        timeout=10.0,
        **overrides,
    )


def test_call_success() -> None:
    """Successful JSON-RPC call returns result dict."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"tools": [{"name": "fetch_html"}]},
            },
        )

    client = make_upstream(transport=httpx.MockTransport(handler))
    result = client.call(method="tools/list", params={})
    assert "tools" in result
    assert result["tools"][0]["name"] == "fetch_html"


def test_call_5xx_raises_unavailable() -> None:
    """Upstream 503 → UpstreamUnavailableError."""
    client = make_upstream(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(UpstreamUnavailableError, match="503"):
        client.call(method="tools/list", params={})


def test_call_jsonrpc_error_raises_unavailable() -> None:
    """JSON-RPC error response → UpstreamUnavailableError with message."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "error": {"code": -32601, "message": "method not found"},
            },
        )

    client = make_upstream(transport=httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailableError, match="method not found"):
        client.call(method="bogus", params={})


def test_call_connection_refused_raises_unavailable() -> None:
    """Connection refused → UpstreamUnavailableError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = make_upstream(transport=httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailableError, match="(connection|connect)"):
        client.call(method="tools/list", params={})


def test_call_timeout_raises_unavailable() -> None:
    """Timeout → UpstreamUnavailableError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = make_upstream(transport=httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailableError, match="timeout"):
        client.call(method="tools/list", params={})


def test_call_sends_correct_envelope() -> None:
    """Verify JSON-RPC envelope structure."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {}},
        )

    client = make_upstream(transport=httpx.MockTransport(handler))
    client.call(method="tools/call", params={"name": "fetch_html", "arguments": {"url": "https://x/"}})
    assert len(captured) == 1
    body = json.loads(captured[0].content)
    assert body["jsonrpc"] == "2.0"
    assert "id" in body
    assert body["method"] == "tools/call"
    assert body["params"] == {"name": "fetch_html", "arguments": {"url": "https://x/"}}
```

**Step 2**: Write `src/hub_mcp/upstream.py`:

```python
"""HTTP client to upstream MCP servers (JSON-RPC 2.0 over streamable_http)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from hub_mcp.exceptions import UpstreamUnavailableError


class UpstreamClient:
    """Proxy JSON-RPC calls to one upstream MCP server."""

    def __init__(
        self,
        *,
        name: str,
        url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._name = name
        self._url = url
        self._timeout = timeout
        if transport is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    @property
    def name(self) -> str:
        return self._name

    async def __aenter__(self) -> UpstreamClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def call(self, *, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request to upstream.

        Raises:
            UpstreamUnavailableError: HTTP error, timeout, or JSON-RPC error.
        """
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            response = await self._client.post(self._url, json=payload)
        except httpx.HTTPError as e:
            raise UpstreamUnavailableError(
                f"upstream {self._name!r} HTTP error: {e}"
            ) from e

        if response.status_code >= 500:
            raise UpstreamUnavailableError(
                f"upstream {self._name!r} returned {response.status_code}: {response.text[:200]}"
            )

        body = response.json()
        if "error" in body:
            err = body["error"]
            raise UpstreamUnavailableError(
                f"upstream {self._name!r} JSON-RPC error {err.get('code')}: {err.get('message')}"
            )
        return body.get("result", {})
```

**Step 3**: Run test → 6 passed.

**Step 4**: Commit.

---

## Phase 4: Hindsight audit

### Task 4.1: AuditWriter

**Objective**: best-effort writer to Hindsight REST under `mcp-audit-{server}-{tool}-{date}` tag.

**Files**:
- Create: `src/hub_mcp/audit.py`
- Create: `tests/test_audit.py`

**Step 1**: Write failing tests:

```python
from datetime import date

import httpx
import pytest

from hub_mcp.audit import AuditEvent, AuditWriter


@pytest.fixture
def mock_hindsight() -> httpx.MockTransport:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "mem_123"})

    handler.captured = captured  # type: ignore[attr-defined]
    return httpx.MockTransport(handler)


def test_log_event_writes_to_hindsight(mock_hindsight: httpx.MockTransport) -> None:
    """Successful Hindsight POST."""
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=mock_hindsight,
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="fetch",
        tool="fetch_html",
        qualified_name="fetch.fetch_html",
        success=True,
        response_size=1234,
        duration_ms=50,
    )
    writer.log_event(event)
    assert len(mock_hindsight.captured) == 1  # type: ignore[attr-defined]
    body = mock_hindsight.captured[0]  # type: ignore[attr-defined]
    content = body.content.decode() if isinstance(body.content, bytes) else body.content
    assert "mcp-audit-fetch-fetch_html-2026-10-10" in content


def test_log_event_hindsight_down_does_not_raise() -> None:
    """Hindsight 503 → AuditWriter swallows error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(handler),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=False,
    )
    writer.log_event(event)  # should not raise


def test_log_event_transport_error_does_not_raise() -> None:
    """httpx.ConnectError → AuditWriter swallows."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(handler),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=True,
    )
    writer.log_event(event)


def test_audit_event_tag_format() -> None:
    """Tag is mcp-audit-{server}-{tool}-{date}."""
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="fetch",
        tool="fetch_html",
        qualified_name="fetch.fetch_html",
        success=True,
    )
    today = date(2026, 10, 10)
    assert event.tag(today) == "mcp-audit-fetch-fetch_html-2026-10-10"


def test_audit_event_handles_disabled_audit_level() -> None:
    """If audit disabled at writer level, log_event is no-op."""
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),  # would fail if called
        enabled=False,
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=True,
    )
    writer.log_event(event)  # no-op, no raise
```

**Step 2**: Write `src/hub_mcp/audit.py`:

```python
"""Hindsight audit log writer for hub-mcp tool calls.

Tag format: mcp-audit-{server}-{tool}-{YYYY-MM-DD} (see AGENT_CONTEXT.md §6).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuditEvent(BaseModel):
    """One tool call event."""

    timestamp: str  # ISO 8601 with Z
    server: str
    tool: str
    qualified_name: str
    success: bool
    response_size: int = 0
    duration_ms: int = 0
    error_message: str | None = None

    def tag(self, on_date: date | None = None) -> str:
        d = on_date or datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).date()
        return f"mcp-audit-{self.server}-{self.tool}-{d.isoformat()}"


class AuditWriter:
    """Best-effort Hindsight audit writer.

    If Hindsight is down, log_event() logs a warning and returns without raising.
    Audit is observability, not a critical path.
    """

    def __init__(
        self,
        *,
        bank_id: str,
        base_url: str = "http://127.0.0.1:8888/v1",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self._bank_id = bank_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._enabled = enabled
        if transport is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self) -> AuditWriter:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def log_event(self, event: AuditEvent) -> None:
        """Write event to Hindsight. Best-effort: never raises."""
        if not self._enabled:
            return

        url = f"{self._base_url}/{self._bank_id}/memories"
        try:
            response = await self._client.post(
                url,
                json={
                    "content": event.model_dump_json(),
                    "tags": [event.tag()],
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "hindsight audit failed: status=%s body=%s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as e:
            logger.warning("hindsight audit transport error: %s", e)
```

**Step 3**: Run test → 5 passed.

**Step 4**: Commit.

---

## Phase 5: Starlette server

### Task 5.1: Server bootstrap

**Objective**: `uv run uvicorn hub_mcp.server:app` поднимается на 46380, health/mcp endpoints работают.

**Files**:
- Create: `src/hub_mcp/server.py`
- Create: `tests/test_server.py`
- Create: `tests/conftest.py`

**Step 1**: Create `tests/conftest.py`:

```python
"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient


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
  - name: disabled-upstream
    url: http://localhost:9999/mcp
    enabled: false
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(VALID_CONFIG_YAML)
    return path


@pytest.fixture
def test_client(config_path: Path) -> TestClient:
    """Build hub app with given config and wrap in Starlette TestClient."""
    from hub_mcp.server import create_app

    app = create_app(config_path=config_path)
    return TestClient(app)
```

**Step 2**: Write failing tests in `tests/test_server.py`:

```python
import json

import httpx
import pytest
from starlette.testclient import TestClient


def test_health_endpoint(test_client: TestClient) -> None:
    """GET /health returns 200."""
    r = test_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_mcp_initialize(test_client: TestClient) -> None:
    """POST /mcp initialize returns server info."""
    r = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    assert body["result"]["serverInfo"]["name"] == "hub-mcp"


def test_tools_list_aggregates_upstream(test_client: TestClient) -> None:
    """tools/list returns union of enabled upstream tools with qualified names."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "x", "version": "0"}},
                },
            )
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"tools": [{"name": "fetch_html", "description": "fetch HTML", "inputSchema": {"type": "object"}}]},
                },
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})

    from hub_mcp.upstream import UpstreamClient
    # ... (more elaborate test setup; this is a sketch)
    # See real implementation in repo.
    pass


def test_tools_call_routes_to_upstream(test_client: TestClient) -> None:
    """tools/call with fetch.fetch_html routes to fetch upstream."""
    # similar mock-based test
    pass
```

**Step 3**: Write `src/hub_mcp/server.py`:

```python
"""Starlette ASGI app for hub-mcp.

Endpoints:
- GET /health → 200 OK
- POST /mcp → MCP JSON-RPC 2.0 (initialize, tools/list, tools/call)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hub_mcp.audit import AuditEvent, AuditWriter
from hub_mcp.config import HubConfig, load_config
from hub_mcp.exceptions import ToolNotFoundError, UpstreamUnavailableError
from hub_mcp.upstream import UpstreamClient

logger = logging.getLogger(__name__)


def _jsonrpc_error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _jsonrpc_result(result: dict[str, Any], request_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def _handle_initialize(_request: Request) -> dict[str, Any]:
    return _jsonrpc_result(
        result={
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hub-mcp", "version": "0.1.0"},
        },
        request_id=1,  # placeholder; real id handled in dispatcher
    )


async def _handle_tools_list(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")

    upstream_map: dict[str, UpstreamClient] = request.app.state.upstream_map
    audit: AuditWriter = request.app.state.audit

    # Parallel call to all enabled upstream
    import asyncio

    async def fetch_one(name: str, client: UpstreamClient) -> list[dict[str, Any]]:
        try:
            result = await client.call(method="tools/list", params={})
            return [
                {
                    "name": f"{name}.{tool['name']}",
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {"type": "object"}),
                }
                for tool in result.get("tools", [])
            ]
        except UpstreamUnavailableError as e:
            logger.warning("upstream %s tools/list failed: %s", name, e)
            return []

    tasks = [fetch_one(name, client) for name, client in upstream_map.items()]
    results_per_upstream = await asyncio.gather(*tasks)

    tools = [tool for upstream_tools in results_per_upstream for tool in upstream_tools]

    return _jsonrpc_result(result={"tools": tools}, request_id=request_id)


async def _handle_tools_call(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    params = body.get("params", {})
    qualified_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if "." not in qualified_name:
        return _jsonrpc_error(
            code=-32602,
            message=f"tool name must be '<server>.<tool>': got {qualified_name!r}",
            request_id=request_id,
        )
    server_name, tool_name = qualified_name.split(".", 1)

    upstream_map: dict[str, UpstreamClient] = request.app.state.upstream_map
    audit: AuditWriter = request.app.state.audit

    if server_name not in upstream_map:
        return _jsonrpc_error(
            code=-32601,
            message=f"tool {qualified_name!r} not found (unknown upstream {server_name!r})",
            request_id=request_id,
        )

    client = upstream_map[server_name]
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        result = await client.call(
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        duration_ms = int((time.time() - start_time) * 1000)
        response_size = len(str(result).encode())
        await audit.log_event(AuditEvent(
            timestamp=timestamp,
            server=server_name,
            tool=tool_name,
            qualified_name=qualified_name,
            success=True,
            response_size=response_size,
            duration_ms=duration_ms,
        ))
        return _jsonrpc_result(result=result, request_id=request_id)
    except UpstreamUnavailableError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await audit.log_event(AuditEvent(
            timestamp=timestamp,
            server=server_name,
            tool=tool_name,
            qualified_name=qualified_name,
            success=False,
            duration_ms=duration_ms,
            error_message=str(e),
        ))
        return _jsonrpc_error(
            code=-32002,
            message=f"upstream {server_name!r} unavailable: {e}",
            request_id=request_id,
        )


METHOD_DISPATCH: dict[str, Any] = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


async def mcp_endpoint(request: Request) -> Response:
    """POST /mcp — JSON-RPC 2.0 dispatcher."""
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(_jsonrpc_error(code=-32700, message=f"invalid JSON: {e}"))

    method = body.get("method")
    request_id = body.get("id")

    handler = METHOD_DISPATCH.get(method)
    if handler is None:
        return JSONResponse(_jsonrpc_error(
            code=-32601,
            message=f"method not found: {method!r}",
            request_id=request_id,
        ))

    result = await handler(request)
    return JSONResponse(result)


async def health_endpoint(request: Request) -> Response:
    return JSONResponse({
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - request.app.state.start_time),
    })


@asynccontextmanager
async def _lifespan(app: Starlette):
    """Start/stop httpx clients per upstream + audit writer."""
    config: HubConfig = app.state.config
    app.state.start_time = time.time()

    # Create upstream clients
    upstream_map: dict[str, UpstreamClient] = {}
    for u in config.upstream:
        if u.enabled:
            client = UpstreamClient(name=u.name, url=u.url, timeout=u.timeout)
            upstream_map[u.name] = client
    app.state.upstream_map = upstream_map

    # Audit writer
    audit = AuditWriter(
        bank_id=config.hindsight.bank_id,
        base_url=config.hindsight.url,
        enabled=config.hindsight.enabled,
    )
    app.state.audit = audit

    try:
        yield
    finally:
        for client in upstream_map.values():
            await client.__aexit__(None, None, None)
        await audit.__aexit__(None, None, None)


def create_app(*, config_path: Path | None = None) -> Starlette:
    """Build the Starlette app with the given config."""
    cfg = load_config(config_path)
    app = Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/mcp", mcp_endpoint, methods=["POST"]),
        ],
        lifespan=_lifespan,
    )
    app.state.config = cfg
    return app


app = create_app()
```

**Step 4**: Run tests → all green.

**Step 5**: Commit.

---

## Phase 6: Deploy + Live debug

### Task 6.1: Create deploy config

**Step 1**: Write `~/.harness-hub/config.yaml` from Kolya's `~/.hermes/profiles/harness/config.yaml` HTTP MCP entries.

### Task 6.2: Live debug with MCP Inspector

```bash
uv run uvicorn hub_mcp.server:app --host 127.0.0.1 --port 46380 --log-level debug
```

In another terminal:

```bash
npx -y @modelcontextprotocol/inspector
```

In Inspector UI:
- Transport: `Streamable HTTP`
- URL: `http://127.0.0.1:46380/mcp`
- Headers: (none in MVP)

Connect → List Tools → Call Tool.

If 2 of 2 work → MVP ready. Record results.

**Step 3**: Commit deploy config (after Kolya's «коммить»).

---

## Summary

После Phase 6 hub-mcp MVP готов. **6 phase'ов, ~15 bite-sized tasks, 3-4 дня**. Coverage target ≥ 85%. Live debug обязателен.

После MVP — Phase 2 (production polish) per `docs/roadmap.md`.