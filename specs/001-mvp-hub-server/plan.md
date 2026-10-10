# Implementation Plan: 001 — MVP hub-mcp server

**Status**: ⚠️ **Superseded** by [`../002-skeleton-core/plan.md`](../002-skeleton-core/plan.md) per ADR-006 (2026-10-10).

> **Внимание**: этот план сохранён для исторической трассировки. Реальный план MVP — [`../002-skeleton-core/plan.md`](../002-skeleton-core/plan.md).
>
> Что изменилось:
> - Phase 9-13 (admin поверх MVP) удалены.
> - Phase 3 (Profile loader) → больше не отдельный phase; profile loading отложен в Phase 3+ (см. ADR-006).
> - Phase 4 (Filter) → удалён полностью (нет profiles в MVP).
> - Phase 7 (Starlette server) упрощён: dispatch только для `initialize` + `tools/list` + `tools/call`, без profile resolution.
>
> Не редактировать — заморожен.

---

> **For Hermes:** Use `subagent-driven-development` skill to implement this plan task-by-task. Each task = 2-5 minutes focused work. TDD: test → fail → impl → pass → commit (after Kolya's explicit «коммить»).

**Goal**: запустить рабочий harness-mcp-hub с HTTP MCP-transport + per-profile filtering + HTTP upstream proxy + Hindsight audit log.

**Architecture**: Starlette ASGI app + MCP SDK + Pydantic profiles + httpx upstream + Hindsight audit. Single process, no module-level state. Подробности в [`spec.md`](spec.md) и [`docs/spec.md`](../../docs/spec.md).

**Tech Stack**: Python 3.11+, Starlette 0.40+, MCP SDK 1.9+, Pydantic v2, httpx 0.27+, pytest 8+.

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
"""harness-mcp-hub — per-profile MCP hub."""

__version__ = "0.1.0"
```

**Step 3**: Create `src/hub_mcp/exceptions.py`:

```python
"""Hub-specific exceptions."""


class HubMcpError(Exception):
    """Base class for all hub-mcp exceptions."""


class ProfileNotFoundError(HubMcpError):
    """Profile YAML file not found or invalid."""


class ProfileValidationError(HubMcpError):
    """Profile YAML does not match Pydantic schema."""


class UpstreamUnavailableError(HubMcpError):
    """Upstream MCP server did not respond."""
```

**Step 4**: Create `tests/__init__.py` (empty file).

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

**Step 6**: Verify `uv sync` works:

```bash
cd /home/gna/workspase/projects/hub-mcp
uv sync
```

Expected: creates `.venv`, installs dependencies, no errors.

**Step 7**: Commit (after Kolya's explicit «коммить»):

```bash
git add pyproject.toml src/hub_mcp/__init__.py src/hub_mcp/exceptions.py tests/__init__.py .gitignore
git commit -m "feat(001): project bootstrap (pyproject, exceptions)"
```

---

### Task 1.2: Configure git pre-commit hook (optional)

**Objective**: запускать ruff + pyright + pytest перед каждым commit'ом.

**Files**:
- Create: `.git/hooks/pre-commit` (executable)

**Step 1**: Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e
cd /home/gna/workspase/projects/hub-mcp
echo "=== ruff check ==="
uv run ruff check src/ tests/
echo "=== ruff format check ==="
uv run ruff format --check src/ tests/
echo "=== pyright ==="
uv run pyright src/
echo "=== pytest ==="
uv run pytest tests/ -v --tb=short
echo "=== all green ==="
```

**Step 2**: Make executable:

```bash
chmod +x .git/hooks/pre-commit
```

**Step 3**: Verify hook fires (after first commit):

```bash
touch src/hub_mcp/__init__.py
git add src/hub_mcp/__init__.py
git commit -m "test: pre-commit hook"
# Expected: hook runs, all 4 checks pass
```

---

## Phase 2: Pydantic types + profile schema

### Task 2.1: Define Profile Pydantic model

**Objective**: type-safe representation of profile YAML, matching [`docs/profiles/schema.md`](../../docs/profiles/schema.md).

**Files**:
- Create: `src/hub_mcp/types.py`
- Create: `tests/test_types.py`

**Step 1**: Write failing test `tests/test_types.py`:

```python
import pytest
from pydantic import ValidationError

from hub_mcp.types import (
    ExcludeRule,
    IncludeRule,
    Limits,
    Policy,
    Profile,
)


def test_profile_minimal_valid():
    """Minimal profile with single server include."""
    p = Profile(
        name="test-profile",
        description="A test profile",
        include=[IncludeRule(server="fetch")],
    )
    assert p.name == "test-profile"
    assert len(p.include) == 1
    assert p.include[0].tools is None  # all tools


def test_profile_name_kebab_case():
    """Profile name must be kebab-case."""
    with pytest.raises(ValidationError):
        Profile(name="TestProfile", description="x", include=[IncludeRule(server="fetch")])
    with pytest.raises(ValidationError):
        Profile(name="test profile", description="x", include=[IncludeRule(server="fetch")])


def test_profile_description_too_long():
    """Description > 200 chars rejected."""
    with pytest.raises(ValidationError):
        Profile(
            name="ok-name",
            description="x" * 201,
            include=[IncludeRule(server="fetch")],
        )


def test_include_with_specific_tools():
    """Include can specify subset of tools."""
    rule = IncludeRule(
        server="fetch",
        tools=["fetch_html", "fetch_markdown"],
    )
    assert rule.tools == ["fetch_html", "fetch_markdown"]


def test_exclude_with_pattern():
    """Exclude can use glob pattern."""
    rule = ExcludeRule(pattern="*delete*")
    assert rule.pattern == "*delete*"


def test_exclude_with_specific_tool():
    """Exclude can target server.tool combination."""
    rule = ExcludeRule(server="fetch", tool="fetch_txt")
    assert rule.server == "fetch"
    assert rule.tool == "fetch_txt"


def test_limits_defaults():
    """Limits have sensible defaults."""
    p = Profile(name="x", description="x", include=[IncludeRule(server="x")])
    assert p.limits.max_calls_per_session == 1000
    assert p.limits.max_calls_per_tool == 200
    assert p.limits.max_session_duration_seconds == 7200


def test_policy_audit_level():
    """Policy audit_level accepts only known values."""
    Policy(audit_level="full")
    Policy(audit_level="metadata_only")
    Policy(audit_level="none")
    with pytest.raises(ValidationError):
        Policy(audit_level="verbose")  # type: ignore[arg-type]
```

**Step 2**: Run test to verify failure:

```bash
uv run pytest tests/test_types.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hub_mcp.types'`.

**Step 3**: Write `src/hub_mcp/types.py`:

```python
"""Pydantic models for hub-mcp."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 200
MAX_INCLUDE_RULES = 1000


class IncludeRule(BaseModel):
    """Rule that allows a server (optionally with specific tools)."""

    server: str = Field(min_length=1, max_length=128)
    tools: list[str] | None = None
    policy: Policy | None = None


class ExcludeRule(BaseModel):
    """Rule that denies a tool (either by glob pattern or by exact match)."""

    pattern: str | None = None
    server: str | None = None
    tool: str | None = None

    def model_post_init(self, __context) -> None:
        """At least one of pattern / server+tool must be set."""
        if self.pattern is None and (self.server is None or self.tool is None):
            raise ValueError("ExcludeRule must have either pattern or (server AND tool)")


class Limits(BaseModel):
    """Per-session rate limits."""

    max_calls_per_session: int = Field(default=1000, ge=1)
    max_calls_per_tool: int = Field(default=200, ge=1)
    max_session_duration_seconds: int = Field(default=7200, ge=60)


class Policy(BaseModel):
    """Policy overrides (audit, response truncation)."""

    redact_tags: list[str] = Field(default_factory=list)
    max_response_tokens: int | None = Field(default=None, ge=100)
    audit_level: Literal["full", "metadata_only", "none"] = "full"


class Profile(BaseModel):
    """Per-profile policy: which tools are exposed, with what limits."""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    include: list[IncludeRule] = Field(min_length=1, max_length=MAX_INCLUDE_RULES)
    exclude: list[ExcludeRule] = Field(default_factory=list, max_length=MAX_INCLUDE_RULES)
    limits: Limits = Field(default_factory=Limits)
    policy: Policy = Field(default_factory=Policy)

    @field_validator("name")
    @classmethod
    def _validate_name_kebab_case(cls, v: str) -> str:
        if not KEBAB_CASE_RE.match(v):
            raise ValueError(
                f"name must be kebab-case (lowercase, hyphens, no leading/trailing hyphen): {v!r}"
            )
        return v
```

**Step 4**: Run test to verify pass:

```bash
uv run pytest tests/test_types.py -v
```

Expected: 9 passed.

**Step 5**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/types.py tests/test_types.py
git commit -m "feat(001): Profile Pydantic model with include/exclude/limits/policy"
```

---

## Phase 3: Profile loader (YAML → Profile)

### Task 3.1: YAML file loading with error handling

**Objective**: `load_profile(name: str, profiles_dir: Path) -> Profile` with clear errors.

**Files**:
- Create: `src/hub_mcp/profile_loader.py`
- Create: `tests/test_profile_loader.py`
- Create: `tests/conftest.py` (shared fixture: tmp profiles dir)

**Step 1**: Write `tests/conftest.py`:

```python
"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    """Return a tmp dir where profiles live."""
    d = tmp_path / "profiles"
    d.mkdir()
    return d
```

**Step 2**: Write failing test `tests/test_profile_loader.py`:

```python
from pathlib import Path

import pytest

from hub_mcp.exceptions import ProfileNotFoundError, ProfileValidationError
from hub_mcp.profile_loader import load_profile
from hub_mcp.types import Profile

VALID_YAML = """
name: my-profile
description: A test profile
include:
  - server: fetch
    tools: [fetch_html]
limits:
  max_calls_per_session: 100
"""

INVALID_NAME_YAML = """
name: InvalidName
description: x
include:
  - server: fetch
"""

MISSING_REQUIRED_YAML = """
name: my-profile
description: x
"""  # no include


def test_load_profile_success(profiles_dir: Path) -> None:
    """Load a valid profile from disk."""
    (profiles_dir / "my-profile.yaml").write_text(VALID_YAML)
    profile = load_profile("my-profile", profiles_dir)
    assert isinstance(profile, Profile)
    assert profile.name == "my-profile"
    assert profile.limits.max_calls_per_session == 100


def test_load_profile_not_found(profiles_dir: Path) -> None:
    """Missing file raises ProfileNotFoundError."""
    with pytest.raises(ProfileNotFoundError):
        load_profile("nonexistent", profiles_dir)


def test_load_profile_invalid_name_format(profiles_dir: Path) -> None:
    """Profile with invalid name raises ProfileValidationError."""
    (profiles_dir / "InvalidName.yaml").write_text(INVALID_NAME_YAML)
    with pytest.raises(ProfileValidationError):
        load_profile("InvalidName", profiles_dir)


def test_load_profile_missing_required_field(profiles_dir: Path) -> None:
    """Profile missing include raises ProfileValidationError."""
    (profiles_dir / "my-profile.yaml").write_text(MISSING_REQUIRED_YAML)
    with pytest.raises(ProfileValidationError):
        load_profile("my-profile", profiles_dir)


def test_load_profile_empty_file(profiles_dir: Path) -> None:
    """Empty YAML file raises ProfileValidationError."""
    (profiles_dir / "empty.yaml").write_text("")
    with pytest.raises(ProfileValidationError):
        load_profile("empty", profiles_dir)


def test_load_profile_garbage_yaml(profiles_dir: Path) -> None:
    """Garbage YAML raises ProfileValidationError (not raw YAMLError)."""
    (profiles_dir / "garbage.yaml").write_text("[invalid: yaml: :")
    with pytest.raises(ProfileValidationError):
        load_profile("garbage", profiles_dir)
```

**Step 3**: Run test to verify failure:

```bash
uv run pytest tests/test_profile_loader.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hub_mcp.profile_loader'`.

**Step 4**: Write `src/hub_mcp/profile_loader.py`:

```python
"""Load Profile from YAML file on disk."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from hub_mcp.exceptions import ProfileNotFoundError, ProfileValidationError
from hub_mcp.types import Profile

_PROFILE_FILENAME_SUFFIX = ".yaml"


def load_profile(name: str, profiles_dir: Path) -> Profile:
    """Load and validate profile by name.

    Args:
        name: profile name (kebab-case, e.g. "developer-tools").
        profiles_dir: directory containing <name>.yaml files.

    Returns:
        Validated Profile object.

    Raises:
        ProfileNotFoundError: file does not exist.
        ProfileValidationError: YAML is invalid or does not match Profile schema.
    """
    path = profiles_dir / f"{name}{_PROFILE_FILENAME_SUFFIX}"
    if not path.exists():
        raise ProfileNotFoundError(f"profile {name!r} not found at {path}")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ProfileValidationError(f"profile {name!r} has invalid YAML: {e}") from e

    if not isinstance(raw, dict):
        raise ProfileValidationError(
            f"profile {name!r} must be a YAML mapping, got {type(raw).__name__}"
        )

    try:
        return Profile.model_validate(raw)
    except ValidationError as e:
        raise ProfileValidationError(f"profile {name!r} validation failed: {e}") from e
```

**Step 5**: Run test to verify pass:

```bash
uv run pytest tests/test_profile_loader.py -v
```

Expected: 6 passed.

**Step 6**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/profile_loader.py tests/test_profile_loader.py tests/conftest.py
git commit -m "feat(001): YAML profile loader with clear error handling"
```

---

## Phase 4: Filter (include/exclude logic)

### Task 4.1: Tool filtering

**Objective**: `filter_tools(tools: list[Tool], profile: Profile) -> list[FilteredTool]` applies include+exclude.

**Files**:
- Create: `src/hub_mcp/filter.py`
- Create: `src/hub_mcp/mcp_types.py` — minimal Tool representation (or reuse MCP SDK types)
- Create: `tests/test_filter.py`

**Step 1**: Write failing test `tests/test_filter.py`:

```python
import pytest

from hub_mcp.filter import filter_tools
from hub_mcp.mcp_types import UpstreamTool
from hub_mcp.types import ExcludeRule, IncludeRule, Profile


def make_profile(
    include: list[IncludeRule] | None = None,
    exclude: list[ExcludeRule] | None = None,
) -> Profile:
    return Profile(
        name="test",
        description="t",
        include=include or [IncludeRule(server="fetch")],
        exclude=exclude or [],
    )


def make_tools(*pairs: tuple[str, str]) -> list[UpstreamTool]:
    return [
        UpstreamTool(server=server, name=name)
        for server, name in pairs
    ]


def test_filter_include_all_tools_from_server() -> None:
    """Server in include without tools list → all tools from that server pass."""
    tools = make_tools(("fetch", "fetch_html"), ("fetch", "fetch_txt"))
    profile = make_profile(include=[IncludeRule(server="fetch")])
    result = filter_tools(tools, profile)
    assert len(result) == 2
    assert {t.qualified_name for t in result} == {"fetch.fetch_html", "fetch.fetch_txt"}


def test_filter_include_specific_tools_only() -> None:
    """Server in include with tools=[a, b] → only those tools pass."""
    tools = make_tools(("fetch", "fetch_html"), ("fetch", "fetch_txt"), ("fetch", "fetch_json"))
    profile = make_profile(include=[IncludeRule(server="fetch", tools=["fetch_html"])])
    result = filter_tools(tools, profile)
    assert len(result) == 1
    assert result[0].qualified_name == "fetch.fetch_html"


def test_filter_exclude_pattern() -> None:
    """Exclude with pattern *delete* removes matching tools."""
    tools = make_tools(
        ("admin", "delete_user"),
        ("admin", "list_users"),
    )
    profile = make_profile(
        include=[IncludeRule(server="admin")],
        exclude=[ExcludeRule(pattern="*delete*")],
    )
    result = filter_tools(tools, profile)
    assert {t.qualified_name for t in result} == {"admin.list_users"}


def test_filter_exclude_specific_tool() -> None:
    """Exclude with server+tool removes that exact tool."""
    tools = make_tools(("fetch", "fetch_html"), ("fetch", "fetch_txt"))
    profile = make_profile(
        include=[IncludeRule(server="fetch")],
        exclude=[ExcludeRule(server="fetch", tool="fetch_txt")],
    )
    result = filter_tools(tools, profile)
    assert {t.qualified_name for t in result} == {"fetch.fetch_html"}


def test_filter_exclude_wins_over_include() -> None:
    """Tool in include AND exclude → not exposed."""
    tools = make_tools(("admin", "delete_user"))
    profile = make_profile(
        include=[IncludeRule(server="admin")],
        exclude=[ExcludeRule(pattern="*delete*")],
    )
    result = filter_tools(tools, profile)
    assert len(result) == 0


def test_filter_tools_from_unlisted_server_dropped() -> None:
    """Tools from servers not in include are dropped entirely."""
    tools = make_tools(("fetch", "fetch_html"), ("secrets", "get_key"))
    profile = make_profile(include=[IncludeRule(server="fetch")])
    result = filter_tools(tools, profile)
    assert {t.qualified_name for t in result} == {"fetch.fetch_html"}


def test_filter_qualifies_name_with_server_prefix() -> None:
    """Qualified name is <server>.<tool>."""
    tools = make_tools(("fetch", "fetch_html"))
    profile = make_profile()
    result = filter_tools(tools, profile)
    assert result[0].qualified_name == "fetch.fetch_html"
```

**Step 2**: Run test to verify failure:

```bash
uv run pytest tests/test_filter.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

**Step 3**: Write `src/hub_mcp/mcp_types.py`:

```python
"""Minimal tool representation used by hub (decoupled from MCP SDK types)."""

from __future__ import annotations

from pydantic import BaseModel


class UpstreamTool(BaseModel):
    """A tool exposed by an upstream MCP server (before filtering)."""

    server: str
    name: str


class FilteredTool(BaseModel):
    """A tool after filtering: ready to be advertised to the agent."""

    qualified_name: str  # e.g. "fetch.fetch_html"
    server: str
    name: str
```

**Step 4**: Write `src/hub_mcp/filter.py`:

```python
"""Apply include/exclude rules from a Profile to a list of upstream tools."""

from __future__ import annotations

import fnmatch

from hub_mcp.mcp_types import FilteredTool, UpstreamTool
from hub_mcp.types import ExcludeRule, IncludeRule, Profile


def _is_excluded(qualified_name: str, exclude_rules: list[ExcludeRule]) -> bool:
    """Check if a tool (qualified name) matches any exclude rule."""
    for rule in exclude_rules:
        if rule.pattern is not None:
            if fnmatch.fnmatch(qualified_name, rule.pattern):
                return True
        elif rule.server is not None and rule.tool is not None:
            if qualified_name == f"{rule.server}.{rule.tool}":
                return True
    return False


def _in_include(qualified_name: str, include_rules: list[IncludeRule]) -> bool:
    """Check if a tool (qualified name) matches any include rule."""
    for rule in include_rules:
        if rule.tools is None:
            # all tools from this server
            if qualified_name.startswith(f"{rule.server}."):
                return True
        else:
            if qualified_name in {f"{rule.server}.{t}" for t in rule.tools}:
                return True
    return False


def filter_tools(
    tools: list[UpstreamTool],
    profile: Profile,
) -> list[FilteredTool]:
    """Apply include+exclude rules.

    Order: include check first, then exclude. Tools not in include are dropped.
    Tools in include but also in exclude are dropped (deny wins).
    """
    result: list[FilteredTool] = []
    for tool in tools:
        qualified_name = f"{tool.server}.{tool.name}"
        if not _in_include(qualified_name, profile.include):
            continue
        if _is_excluded(qualified_name, profile.exclude):
            continue
        result.append(
            FilteredTool(
                qualified_name=qualified_name,
                server=tool.server,
                name=tool.name,
            )
        )
    return result
```

**Step 5**: Run test to verify pass:

```bash
uv run pytest tests/test_filter.py -v
```

Expected: 7 passed.

**Step 6**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/filter.py src/hub_mcp/mcp_types.py tests/test_filter.py
git commit -m "feat(001): tool filter with include+exclude (deny wins)"
```

---

## Phase 5: Upstream HTTP client

### Task 5.1: Upstream MCP HTTP proxy

**Objective**: `UpstreamClient.call(server, method, params) -> dict` — JSON-RPC over HTTP to upstream.

**Files**:
- Create: `src/hub_mcp/upstream.py`
- Create: `tests/test_upstream.py`

**Step 1**: Write failing test `tests/test_upstream.py`:

```python
import json

import httpx
import pytest

from hub_mcp.upstream import UpstreamClient, UpstreamUnavailableError


@pytest.fixture
def mock_upstream() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/mcp/fetch":
            body = json.loads(request.content)
            assert body["method"] == "tools/list"
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"tools": [{"name": "fetch_html", "description": "x"}]},
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_call_success(mock_upstream: httpx.MockTransport) -> None:
    """Successful JSON-RPC call returns result."""
    client = UpstreamClient(
        upstream={"fetch": "http://test/mcp/fetch"},
        transport=mock_upstream,
    )
    result = client.call(server="fetch", method="tools/list", params={})
    assert "tools" in result
    assert result["tools"][0]["name"] == "fetch_html"


def test_call_unknown_server_raises() -> None:
    """Calling on unregistered server raises ValueError."""
    client = UpstreamClient(upstream={"fetch": "http://test/mcp/fetch"})
    with pytest.raises(ValueError, match="unknown upstream"):
        client.call(server="nonexistent", method="tools/list", params={})


def test_call_upstream_5xx_raises_unavailable() -> None:
    """Upstream 503 → UpstreamUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = UpstreamClient(
        upstream={"fetch": "http://test/mcp/fetch"},
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(UpstreamUnavailableError):
        client.call(server="fetch", method="tools/list", params={})


def test_call_upstream_jsonrpc_error_returns_error() -> None:
    """JSON-RPC error response raises UpstreamUnavailableError."""

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

    client = UpstreamClient(
        upstream={"fetch": "http://test/mcp/fetch"},
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(UpstreamUnavailableError, match="method not found"):
        client.call(server="fetch", method="bogus", params={})
```

**Step 2**: Run test to verify failure:

```bash
uv run pytest tests/test_upstream.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

**Step 3**: Write `src/hub_mcp/upstream.py`:

```python
"""HTTP client to upstream MCP servers (JSON-RPC 2.0 over streamable_http)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from hub_mcp.exceptions import UpstreamUnavailableError


class UpstreamClient:
    """Proxy JSON-RPC calls to a fixed set of upstream MCP servers.

    Args:
        upstream: dict mapping server-name → upstream URL.
        transport: optional httpx.MockTransport (for tests). Production uses real httpx.
        timeout: per-request timeout in seconds.
    """

    def __init__(
        self,
        upstream: dict[str, str],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not upstream:
            raise ValueError("upstream dict must not be empty")
        self._upstream = dict(upstream)
        self._timeout = timeout
        if transport is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self) -> UpstreamClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def call(
        self,
        *,
        server: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Send JSON-RPC request to upstream MCP server.

        Args:
            server: upstream server name (key in upstream dict).
            method: JSON-RPC method (e.g. "tools/list", "tools/call").
            params: JSON-RPC params.

        Returns:
            JSON-RPC result dict.

        Raises:
            ValueError: unknown server.
            UpstreamUnavailableError: HTTP error or JSON-RPC error response.
        """
        if server not in self._upstream:
            raise ValueError(f"unknown upstream server: {server!r}")
        url = self._upstream[server]
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise UpstreamUnavailableError(f"upstream {server!r} HTTP error: {e}") from e

        if response.status_code >= 500:
            raise UpstreamUnavailableError(
                f"upstream {server!r} returned {response.status_code}: {response.text}"
            )

        body = response.json()
        if "error" in body:
            err = body["error"]
            raise UpstreamUnavailableError(
                f"upstream {server!r} JSON-RPC error {err.get('code')}: {err.get('message')}"
            )
        return body.get("result", {})
```

**Step 4**: Run test to verify pass:

```bash
uv run pytest tests/test_upstream.py -v
```

Expected: 4 passed.

**Step 5**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/upstream.py tests/test_upstream.py
git commit -m "feat(001): upstream HTTP client with httpx + error handling"
```

---

## Phase 6: Hindsight audit client

### Task 6.1: Audit log writer

**Objective**: `AuditWriter.log_event(...)` writes to Hindsight REST under `mcp-audit-{profile}-{YYYY-MM-DD}` tag.

**Files**:
- Create: `src/hub_mcp/audit.py`
- Create: `tests/test_audit.py`

**Step 1**: Write failing test `tests/test_audit.py`:

```python
from datetime import date

import httpx
import pytest

from hub_mcp.audit import AuditEvent, AuditWriter


@pytest.fixture
def mock_hindsight() -> httpx.MockTransport:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/memories" in request.url.path:
            captured.append(request)
            return httpx.Response(200, json={"id": "mem_abc123"})
        return httpx.Response(404)

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
        profile="developer-tools",
        server="fetch",
        tool="fetch_html",
        success=True,
        response_size=1234,
    )
    writer.log_event(event)

    assert len(mock_hindsight.captured) == 1  # type: ignore[attr-defined]
    body = mock_hindsight.captured[0]  # type: ignore[attr-defined]
    assert "mcp-audit-developer-tools-2026-10-10" in str(body.content)


def test_log_event_hindsight_down_does_not_raise(mock_hindsight: httpx.MockTransport) -> None:
    """Hindsight 503 → AuditWriter swallows error (does not propagate)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(handler),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        profile="x",
        server="y",
        tool="z",
        success=False,
    )
    # Should not raise
    writer.log_event(event)


def test_audit_event_serializes_correctly() -> None:
    """AuditEvent.model_dump_json produces valid JSON."""
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        profile="dev",
        server="fetch",
        tool="fetch_html",
        success=True,
        response_size=100,
    )
    payload = event.model_dump_json()
    assert '"profile":"dev"' in payload
    assert '"tool":"fetch_html"' in payload


def test_audit_tag_format() -> None:
    """Tag is mcp-audit-{profile}-{date} per AGENT_CONTEXT.md."""
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        profile="dev",
        server="fetch",
        tool="fetch_html",
        success=True,
    )
    today = date(2026, 10, 10)
    assert event.tag(today) == "mcp-audit-dev-2026-10-10"
```

**Step 2**: Run test to verify failure:

```bash
uv run pytest tests/test_audit.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

**Step 3**: Write `src/hub_mcp/audit.py`:

```python
"""Hindsight audit log writer for hub-mcp tool calls.

Tag format: mcp-audit-{profile}-{YYYY-MM-DD} (see AGENT_CONTEXT.md §6).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditEvent(BaseModel):
    """One tool call event."""

    timestamp: str  # ISO 8601 with Z
    profile: str
    server: str
    tool: str
    success: bool
    response_size: int = 0
    error_message: str | None = None
    duration_ms: int | None = None

    def tag(self, on_date: date | None = None) -> str:
        """Generate Hindsight tag for this event."""
        d = on_date or datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).date()
        return f"mcp-audit-{self.profile}-{d.isoformat()}"


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
    ) -> None:
        self._bank_id = bank_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
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

**Step 4**: Run test to verify pass:

```bash
uv run pytest tests/test_audit.py -v
```

Expected: 4 passed.

**Step 5**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/audit.py tests/test_audit.py
git commit -m "feat(001): Hindsight audit writer (mcp-audit-{profile}-{date} tag)"
```

---

## Phase 7: Starlette server + integration test

### Task 7.1: Server bootstrap

**Objective**: `uv run uvicorn hub_mcp.server:app` запускается, healthcheck `/health` отвечает.

**Files**:
- Create: `src/hub_mcp/config.py`
- Create: `src/hub_mcp/server.py`
- Create: `tests/test_server.py`

**Step 1**: Write `src/hub_mcp/config.py`:

```python
"""Runtime configuration (paths from env)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PROFILES_DIR = Path.home() / ".harness-hub" / "profiles"
DEFAULT_UPSTREAM_PATH = Path.home() / ".harness-hub" / "upstream.yaml"
DEFAULT_HINDSIGHT_URL = "http://127.0.0.1:8888/v1"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 46380


def profiles_dir() -> Path:
    """Profiles YAML directory (default ~/.harness-hub/profiles)."""
    raw = os.environ.get("HUB_PROFILES_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_PROFILES_DIR


def upstream_path() -> Path:
    """Path to upstream.yaml (default ~/.harness-hub/upstream.yaml)."""
    raw = os.environ.get("HUB_UPSTREAM_PATH")
    return Path(raw).expanduser() if raw else DEFAULT_UPSTREAM_PATH


def hindsight_url() -> str:
    """Hindsight REST base URL (default http://127.0.0.1:8888/v1)."""
    return os.environ.get("HUB_HINDSIGHT_URL", DEFAULT_HINDSIGHT_URL)


def listen_host() -> str:
    return os.environ.get("HUB_LISTEN_HOST", DEFAULT_LISTEN_HOST)


def listen_port() -> int:
    raw = os.environ.get("HUB_LISTEN_PORT", str(DEFAULT_LISTEN_PORT))
    return int(raw)
```

**Step 2**: Write failing test `tests/test_server.py`:

```python
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from hub_mcp.server import create_app

VALID_PROFILE = """
name: test-profile
description: Test
include:
  - server: fetch
"""


@pytest.fixture
def app_with_profiles(tmp_path: Path) -> tuple[TestClient, Path]:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "test-profile.yaml").write_text(VALID_PROFILE)
    upstream = tmp_path / "upstream.yaml"
    upstream.write_text("fetch: http://test/mcp/fetch\n")
    app = create_app(profiles_dir=profiles, upstream_path=upstream)
    return TestClient(app), profiles


def test_health_endpoint(app_with_profiles: tuple[TestClient, Path]) -> None:
    """GET /health returns 200 OK."""
    client, _ = app_with_profiles
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_initialize_without_profile_header(app_with_profiles: tuple[TestClient, Path]) -> None:
    """MCP initialize without X-Profile-Id returns error."""
    client, _ = app_with_profiles
    response = client.post(
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
    assert response.status_code == 200
    body = response.json()
    assert "error" in body


def test_mcp_initialize_with_profile_header(app_with_profiles: tuple[TestClient, Path]) -> None:
    """MCP initialize with valid X-Profile-Id succeeds."""
    client, _ = app_with_profiles
    response = client.post(
        "/mcp",
        headers={"X-Profile-Id": "test-profile"},
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
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert "capabilities" in body["result"]
```

**Step 3**: Run test to verify failure:

```bash
uv run pytest tests/test_server.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hub_mcp.server'`.

**Step 4**: Write `src/hub_mcp/server.py`:

```python
"""Starlette ASGI app for hub-mcp.

Endpoints:
- GET /health → 200 OK (liveness)
- POST /mcp → MCP JSON-RPC 2.0 (initialize, tools/list, tools/call, ...)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hub_mcp.audit import AuditWriter
from hub_mcp.config import hindsight_url as default_hindsight_url
from hub_mcp.config import profiles_dir as default_profiles_dir
from hub_mcp.config import upstream_path as default_upstream_path
from hub_mcp.exceptions import ProfileNotFoundError, ProfileValidationError, UpstreamUnavailableError
from hub_mcp.filter import filter_tools
from hub_mcp.mcp_types import UpstreamTool
from hub_mcp.profile_loader import load_profile
from hub_mcp.types import Profile
from hub_mcp.upstream import UpstreamClient

logger = logging.getLogger(__name__)

PROFILE_HEADER = "x-profile-id"


def _load_upstream(path: Path) -> dict[str, str]:
    """Load upstream.yaml: {server_name: url}."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _resolve_profile_from_request(request: Request) -> Profile | None:
    """Load profile from X-Profile-Id header (None if missing/invalid)."""
    name = request.headers.get(PROFILE_HEADER)
    if not name:
        return None
    profiles_path = default_profiles_dir()
    try:
        return load_profile(name, profiles_path)
    except (ProfileNotFoundError, ProfileValidationError) as e:
        logger.warning("profile load failed: %s", e)
        return None


@asynccontextmanager
async def _lifespan(app: Starlette):
    """Start/stop httpx clients."""
    upstream_dict = _load_upstream(app.state.upstream_path)
    upstream = UpstreamClient(upstream=upstream_dict)
    audit = AuditWriter(bank_id="default", base_url=app.state.hindsight_url)
    app.state.upstream = upstream
    app.state.audit = audit
    try:
        yield
    finally:
        await upstream.__aexit__(None, None, None)
        await audit.__aexit__(None, None, None)


def _jsonrpc_error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _jsonrpc_result(result: dict[str, Any], request_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def _handle_initialize(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    return _jsonrpc_result(
        result={
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hub-mcp", "version": "0.1.0"},
        },
        request_id=request_id,
    )


async def _handle_tools_list(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    profile = _resolve_profile_from_request(request)
    if profile is None:
        return _jsonrpc_error(
            code=-32001,
            message="profile not loaded (missing or invalid X-Profile-Id header)",
            request_id=request_id,
        )

    # Aggregate tools from all upstream (Phase 1: just one tool list per upstream).
    upstream: UpstreamClient = request.app.state.upstream
    aggregated: list[UpstreamTool] = []
    for server_name in {inc.server for inc in profile.include}:
        try:
            result = await upstream.call(
                server=server_name,
                method="tools/list",
                params={},
            )
        except (ValueError, UpstreamUnavailableError) as e:
            logger.warning("upstream %s tools/list failed: %s", server_name, e)
            continue
        for tool in result.get("tools", []):
            aggregated.append(UpstreamTool(server=server_name, name=tool["name"]))

    filtered = filter_tools(aggregated, profile)
    tools_payload = [
        {
            "name": ft.qualified_name,
            "description": "",  # Phase 1: no upstream-provided description; Phase 3
            "inputSchema": {"type": "object", "properties": {}},
        }
        for ft in filtered
    ]
    return _jsonrpc_result(result={"tools": tools_payload}, request_id=request_id)


async def _handle_tools_call(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    params = body.get("params", {})
    qualified_name = params.get("name", "")
    if "." not in qualified_name:
        return _jsonrpc_error(
            code=-32602,
            message=f"tool name must be '<server>.<tool>': got {qualified_name!r}",
            request_id=request_id,
        )
    server_name, tool_name = qualified_name.split(".", 1)

    profile = _resolve_profile_from_request(request)
    if profile is None:
        return _jsonrpc_error(
            code=-32001,
            message="profile not loaded",
            request_id=request_id,
        )

    # Verify tool is in profile (filter again — defense in depth)
    filtered = filter_tools(
        [UpstreamTool(server=server_name, name=tool_name)],
        profile,
    )
    if not filtered:
        return _jsonrpc_error(
            code=-32601,
            message=f"tool {qualified_name!r} not in profile {profile.name!r}",
            request_id=request_id,
        )

    upstream: UpstreamClient = request.app.state.upstream
    audit: AuditWriter = request.app.state.audit

    try:
        result = await upstream.call(
            server=server_name,
            method="tools/call",
            params={"name": tool_name, "arguments": params.get("arguments", {})},
        )
        await audit.log_event(_make_audit_event(profile, server_name, tool_name, True))
        return _jsonrpc_result(result=result, request_id=request_id)
    except UpstreamUnavailableError as e:
        await audit.log_event(_make_audit_event(profile, server_name, tool_name, False, str(e)))
        return _jsonrpc_error(
            code=-32002,
            message=f"upstream {server_name!r} unavailable: {e}",
            request_id=request_id,
        )


def _make_audit_event(
    profile: Profile,
    server: str,
    tool: str,
    success: bool,
    error: str | None = None,
) -> "AuditEventLike":  # type: ignore[name-defined]
    from datetime import datetime, timezone
    from hub_mcp.audit import AuditEvent
    return AuditEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        profile=profile.name,
        server=server,
        tool=tool,
        success=success,
        error_message=error,
    )


async def mcp_endpoint(request: Request) -> Response:
    """POST /mcp — JSON-RPC 2.0 dispatcher."""
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(_jsonrpc_error(code=-32700, message=f"invalid JSON: {e}"))

    method = body.get("method")
    if method == "initialize":
        result = await _handle_initialize(request)
    elif method == "tools/list":
        result = await _handle_tools_list(request)
    elif method == "tools/call":
        result = await _handle_tools_call(request)
    else:
        result = _jsonrpc_error(
            code=-32601,
            message=f"method not found: {method!r}",
            request_id=body.get("id"),
        )
    return JSONResponse(result)


async def health_endpoint(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


def create_app(
    *,
    profiles_dir: Path | None = None,
    upstream_path: Path | None = None,
    hindsight_url: str | None = None,
) -> Starlette:
    """Build the Starlette app with injected paths (for testing)."""
    app = Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/mcp", mcp_endpoint, methods=["POST"]),
        ],
        lifespan=_lifespan,
    )
    app.state.profiles_dir = profiles_dir or default_profiles_dir()
    app.state.upstream_path = upstream_path or default_upstream_path()
    app.state.hindsight_url = hindsight_url or default_hindsight_url()
    return app


app = create_app()
```

**Step 5**: Run test to verify pass:

```bash
uv run pytest tests/test_server.py -v
```

Expected: 3 passed.

**Step 6**: Run full test suite:

```bash
uv run pytest tests/ -v --tb=short
```

Expected: ~32 tests passing (across test_types, test_profile_loader, test_filter, test_upstream, test_audit, test_server).

**Step 7**: Verify health endpoint with real uvicorn:

```bash
uv run uvicorn hub_mcp.server:app --host 127.0.0.1 --port 46380 &
sleep 2
curl http://127.0.0.1:46380/health
# Expected: {"status":"ok"}
kill %1
```

**Step 8**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/config.py src/hub_mcp/server.py tests/test_server.py
git commit -m "feat(001): Starlette server with /health and /mcp endpoints"
```

---

## Phase 8: Deploy + Live debug

### Task 8.1: Create deploy configs

**Objective**: `~/.harness-hub/profiles/*.yaml` + `~/.harness-hub/upstream.yaml` ready for Kolya's setup.

**Files** (deployed, not in repo):
- `~/.harness-hub/profiles/developer-tools.yaml`
- `~/.harness-hub/profiles/harness-infra.yaml`
- `~/.harness-hub/upstream.yaml`

**Step 1**: Copy example profiles:

```bash
mkdir -p ~/.harness-hub/profiles
cp /home/gna/workspase/projects/hub-mcp/docs/profiles/examples/developer-tools.yaml \
   ~/.harness-hub/profiles/
cp /home/gna/workspase/projects/hub-mcp/docs/profiles/examples/harness-infra.yaml \
   ~/.harness-hub/profiles/
```

**Step 2**: Create `~/.harness-hub/upstream.yaml` based on Kolya's current `~/.hermes/profiles/harness/config.yaml`. Extract every MCP that has `url:` (HTTP transport) into `server-name: url` format. Stdio MCP — оставить за рамками MVP (см. OQ-hub-001).

**Step 3**: Verify hub starts and loads profiles:

```bash
cd /path/to/hub-mcp
uv run uvicorn hub_mcp.server:app --host 127.0.0.1 --port 46380 &
sleep 2
curl -s -X POST http://127.0.0.1:46380/mcp \
  -H "X-Profile-Id: developer-tools" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
# Expected: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"hub-mcp","version":"0.1.0"}}}
kill %1
```

### Task 8.2: Live debug with MCP Inspector

**Objective**: real MCP Inspector подключается к hub, делает `initialize` → `tools/list` → `tools/call`, всё работает.

**Step 1**: Запустить hub:

```bash
uv run uvicorn hub_mcp.server:app --host 127.0.0.1 --port 46380 --log-level debug
```

**Step 2**: В другом терминале — запустить MCP Inspector:

```bash
npx -y @modelcontextprotocol/inspector
```

**Step 3**: В Inspector UI:
- Transport: `Streamable HTTP`
- URL: `http://127.0.0.1:46380/mcp`
- Headers: `X-Profile-Id: developer-tools`

**Step 4**: Нажать Connect, потом List Tools, потом Call Tool (например, `fetch.fetch_html`).

**Step 5**: Если 2 из 2 (List + Call) работают — MVP готов. Закоммить деплой-configs (после явного «коммить» от Kolya).

---

## Summary

После Phase 8 hub-mcp MVP готов к использованию Kolya. Общее количество задач: ~20 (Phase 1-8). Каждая = 2-5 минут. Coverage target ≥ 85%. Live debug обязателен (Phase 8.2).

**Update 2026-10-10**: ADR-005 добавляет admin REST API + Web UI в MVP. Следующие 4 phase'а (9-12) — новая работа. Phase 9 — upstream health check (блокирует admin UI), Phase 10 — admin auth + CSRF, Phase 11 — admin REST handlers, Phase 12 — admin UI templates + deploy. С live debug протоколом в Phase 13.

После MVP — Phase 2 (production polish) per `docs/roadmap.md`.

---

## Phase 9: Upstream health check (ADR-005)

Должна быть до admin UI — без health check'а `/admin/upstreams` нечего показывать.

### Task 9.1: Health cache + ping loop

**Objective**: in-memory health state per upstream (last_check, success_rate).

**Files**:
- Create: `src/hub_mcp/upstream_health.py`
- Create: `tests/test_upstream_health.py`

**Step 1**: Write failing test `tests/test_upstream_health.py`:

```python
import asyncio
import time

import httpx
import pytest

from hub_mcp.upstream_health import HealthChecker, HealthState


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "ok" in request.url.host:
            return httpx.Response(200, json={"result": "ok"})
        return httpx.Response(503)

    return httpx.MockTransport(handler)


def test_health_state_initial_unknown() -> None:
    """Brand-new checker has state=unknown for all upstream."""
    checker = HealthChecker(
        upstream={"ok-server": "http://ok-server/mcp", "bad-server": "http://bad-server/mcp"},
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    state = checker.snapshot()
    assert state["ok-server"].last_status == "unknown"
    assert state["bad-server"].last_status == "unknown"


def test_health_check_updates_state(mock_transport: httpx.MockTransport) -> None:
    """Single check updates snapshot."""
    checker = HealthChecker(
        upstream={"ok-server": "http://ok-server/mcp", "bad-server": "http://bad-server/mcp"},
        transport=mock_transport,
    )
    asyncio.run(checker.check_all())
    state = checker.snapshot()
    assert state["ok-server"].last_status == "healthy"
    assert state["bad-server"].last_status == "unhealthy"


def test_health_success_rate_calculation(mock_transport: httpx.MockTransport) -> None:
    """Success rate computed over rolling window."""
    checker = HealthChecker(
        upstream={"ok-server": "http://ok-server/mcp"},
        transport=mock_transport,
    )
    for _ in range(5):
        asyncio.run(checker.check_all())
    state = checker.snapshot()
    assert state["ok-server"].success_rate_5min == 1.0
```

**Step 2**: Run test → fail (ModuleNotFound).

**Step 3**: Write `src/hub_mcp/upstream_health.py`:

```python
"""Per-upstream health cache + background ping loop."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class HealthState:
    """Snapshot of one upstream's health."""

    last_status: str = "unknown"  # unknown | healthy | unhealthy
    last_check_at: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    recent_results: deque[bool] = field(default_factory=lambda: deque(maxlen=300))

    @property
    def success_rate_5min(self) -> float:
        if not self.recent_results:
            return 0.0
        return sum(self.recent_results) / len(self.recent_results)


class HealthChecker:
    """Track per-upstream health via periodic MCP `initialize` pings."""

    def __init__(
        self,
        *,
        upstream: dict[str, str],
        transport: httpx.AsyncBaseTransport | None = None,
        ping_interval_seconds: float = 30.0,
    ) -> None:
        self._upstream = dict(upstream)
        self._ping_interval = ping_interval_seconds
        if transport is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=10.0)
        self._state: dict[str, HealthState] = {name: HealthState() for name in upstream}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def check_all(self) -> None:
        """Ping all upstream once and update state."""
        for name, url in self._upstream.items():
            await self._check_one(name, url)

    async def _check_one(self, name: str, url: str) -> None:
        state = self._state[name]
        try:
            response = await self._client.post(
                url,
                json={
                    "jsonrpc": "2.0",
                    "id": "health",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "hub-health", "version": "0.1"},
                    },
                },
            )
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False

        state.last_check_at = time.time()
        if ok:
            state.last_status = "healthy"
            state.success_count += 1
        else:
            state.last_status = "unhealthy"
            state.failure_count += 1
        state.recent_results.append(ok)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.check_all()
            except Exception:
                logger.exception("health check loop error")
            await asyncio.sleep(self._ping_interval)

    def snapshot(self) -> dict[str, HealthState]:
        """Return current health state for all upstream."""
        return dict(self._state)
```

**Step 4**: Run test → pass (3 tests).

**Step 5**: Commit (after Kolya's «коммить»):

```bash
git add src/hub_mcp/upstream_health.py tests/test_upstream_health.py
git commit -m "feat(001): upstream health checker with rolling-window success rate"
```

---

## Phase 10: Admin auth + CSRF

### Task 10.1: X-Admin-Token middleware + auto-generated token

**Objective**: middleware rejects `/admin/*` без правильного `X-Admin-Token`. Token = `secrets.token_urlsafe(32)`, generated on first start, persisted in `~/.harness-hub/admin-token` (chmod 600).

**Files**:
- Create: `src/hub_mcp/admin_auth.py`
- Create: `tests/test_admin_auth.py`

**Step 1**: Write failing test `tests/test_admin_auth.py`:

```python
import os
from pathlib import Path

import pytest

from hub_mcp.admin_auth import AdminAuthenticator, AdminAuthError


@pytest.fixture
def auth_dir(tmp_path: Path) -> Path:
    d = tmp_path / "auth"
    d.mkdir()
    return d


def test_admin_token_generated_on_first_use(auth_dir: Path) -> None:
    """First call generates and persists a random token."""
    auth = AdminAuthenticator(token_path=auth_dir / "admin-token")
    token = auth.token()
    assert len(token) >= 32
    assert (auth_dir / "admin-token").exists()
    assert oct((auth_dir / "admin-token").stat().st_mode)[-3:] == "600"


def test_admin_token_persisted_across_instances(auth_dir: Path) -> None:
    """Second instance reads same token from disk."""
    auth1 = AdminAuthenticator(token_path=auth_dir / "admin-token")
    token1 = auth1.token()
    auth2 = AdminAuthenticator(token_path=auth_dir / "admin-token")
    token2 = auth2.token()
    assert token1 == token2


def test_admin_authenticate_correct_token(auth_dir: Path) -> None:
    """Correct token authenticates."""
    auth = AdminAuthenticator(token_path=auth_dir / "admin-token")
    token = auth.token()
    auth.authenticate(f"Bearer {token}")  # no exception


def test_admin_authenticate_wrong_token_raises(auth_dir: Path) -> None:
    """Wrong token raises AdminAuthError."""
    auth = AdminAuthenticator(token_path=auth_dir / "admin-token")
    auth.token()  # ensure token exists
    with pytest.raises(AdminAuthError):
        auth.authenticate("Bearer wrong-token")


def test_admin_authenticate_missing_raises(auth_dir: Path) -> None:
    """Missing Authorization header raises AdminAuthError."""
    auth = AdminAuthenticator(token_path=auth_dir / "admin-token")
    auth.token()
    with pytest.raises(AdminAuthError):
        auth.authenticate("")
```

**Step 2-5**: standard TDD flow → create `src/hub_mcp/admin_auth.py`:

```python
"""Admin authentication via X-Admin-Token header (auto-generated on first use)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from hub_mcp.exceptions import HubMcpError


class AdminAuthError(HubMcpError):
    """Raised when admin authentication fails."""


class AdminAuthenticator:
    """Manages admin token (generate on first use, persist in chmod 600 file)."""

    def __init__(self, *, token_path: Path) -> None:
        self._token_path = token_path

    def token(self) -> str:
        """Return admin token. Generate and persist if not exists."""
        if self._token_path.exists():
            return self._token_path.read_text().strip()
        token = secrets.token_urlsafe(32)
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(token)
        os.chmod(self._token_path, 0o600)
        return token

    def authenticate(self, authorization_header: str | None) -> None:
        """Validate Authorization header. Raises AdminAuthError on failure."""
        expected = self.token()
        if not authorization_header:
            raise AdminAuthError("missing Authorization header")
        scheme, _, value = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not value:
            raise AdminAuthError("invalid Authorization scheme (expected 'Bearer <token>')")
        if not secrets.compare_digest(value.encode(), expected.encode()):
            raise AdminAuthError("invalid admin token")
```

**Step 6**: Commit (after Kolya's «коммить»).

### Task 10.2: CSRF token via itsdangerous

**Objective**: signed CSRF token в cookie + hidden form field. itsdangerous.URLSafeTimedSerializer.

**Files**:
- Create: `src/hub_mcp/csrf.py`
- Create: `tests/test_csrf.py`
- Modify: `pyproject.toml` (add `itsdangerous` dep)

**Step 1-5**: standard TDD. Key tests:

- `generate_csrf(secret) -> str` produces URL-safe string.
- `validate_csrf(token, secret, max_age=3600) -> bool` accepts valid token, rejects expired, rejects wrong signature.
- Constant-time comparison via `hmac.compare_digest`.

**Step 6**: Commit.

---

## Phase 11: Admin REST handlers

### Task 11.1: Profile CRUD endpoints

**Objective**: `GET/POST/PATCH/DELETE /admin/profiles[/{name}]`.

**Files**:
- Create: `src/hub_mcp/admin.py`
- Create: `tests/test_admin.py`

**Step 1**: Failing tests cover:

- `GET /admin/profiles` → list of profile names + descriptions.
- `GET /admin/profiles/{name}` → YAML content + parsed Profile JSON.
- `POST /admin/profiles/{name}` with body=YAML → write file, return 201.
- `POST with invalid YAML → 400`.
- `PATCH /admin/profiles/{name}` with body=JSON → merge, write, return 200.
- `DELETE /admin/profiles/{name}` → remove file, return 204.
- All endpoints require `X-Admin-Token` (else 401).

**Step 2-5**: TDD. Key implementation details:

- Use Starlette `Route` + `Request`.
- Re-use `load_profile()` from `src/hub_mcp/profile_loader.py` for GET.
- For PATCH, use `Profile.model_validate(existing.model_dump() | patch_dict)` — Pydantic handles merge validation.
- Atomic write via `tempfile + os.replace()`.

**Step 6**: Commit.

### Task 11.2: Upstream CRUD + health endpoint

**Objective**: `GET/POST/DELETE /admin/upstreams[/{server}]` + `GET /admin/upstreams/{server}/health` (force ping).

**Files**:
- Modify: `src/hub_mcp/admin.py`
- Modify: `tests/test_admin.py`

**Step 1**: Tests:
- `GET /admin/upstreams` → list with `health` (last_status, success_rate).
- `POST /admin/upstreams/{server}` with body=`{"url": "..."}` → add to upstream.yaml.
- `DELETE /admin/upstreams/{server}` → remove.
- `POST /admin/upstreams/{server}/health` → force ping, return HealthState.
- `DELETE` returns 409 if profile includes this server.

**Step 2-5**: TDD.

**Step 6**: Commit.

### Task 11.3: Tools debug + audit listing + hub health

**Objective**: `GET /admin/tools?profile=X`, `GET /admin/audit?profile=X&date=Y`, `GET /admin/health`.

**Step 1**: Tests:
- `/admin/tools?profile=developer-tools` → list of tools in profile (after filter).
- `/admin/audit?profile=X&date=Y` → read Hindsight, filter by tag, return last 100.
- `/admin/health` → `{"status": "ok", "version": "0.1.0", "uptime_seconds": N, "active_sessions": N}`.

**Step 2-5**: TDD.

**Step 6**: Commit.

---

## Phase 12: Admin Web UI (HTMX + Jinja2)

### Task 12.1: Jinja2 templates + base layout

**Objective**: 4 страницы: dashboard, profiles list, profile edit, upstreams list. Pico CSS для стилей.

**Files**:
- Create: `src/hub_mcp/templates/base.html` (layout + nav)
- Create: `src/hub_mcp/templates/dashboard.html`
- Create: `src/hub_mcp/templates/profiles.html`
- Create: `src/hub_mcp/templates/profile_edit.html`
- Create: `src/hub_mcp/templates/upstreams.html`
- Create: `src/hub_mcp/static/pico.min.css` (vendored, 10KB)

**Step 1**: руками templates с минимальной логикой (loop over profiles, форма с CSRF field, HTMX `hx-post` для save).

**Step 2**: mount в Starlette через `Starlette(templates=Jinja2Templates(directory=...))`.

**Step 3**: Commit.

### Task 12.2: Routes mounting

**Objective**: `/admin/ui/` → HTML pages; `/admin/*` → REST endpoints.

**Files**:
- Modify: `src/hub_mcp/server.py`

Mount routes из `admin.py` на prefix `/admin`. UI routes — отдельный list в `admin.py`. CSRF middleware applied to all admin routes.

**Step 2**: Smoke test через `TestClient`: GET `/admin/ui/profiles` рендерит HTML, POST `/admin/profiles/X` работает через curl.

**Step 3**: Commit.

---

## Phase 13: Admin deploy + live debug (browser)

### Task 13.1: Browser-side live debug

**Objective**: открыть `http://127.0.0.1:46381/admin/` в браузере, проверить:

- Dashboard показывает upstream со health-индикаторами.
- Profile list показывает загруженные профили.
- Edit form сохраняет профиль, hub видит изменения.
- Tools debug показывает корректный filtered list.
- Audit log показывает последние events.

**Step 1**: запустить hub.

**Step 2**: открыть в Firefox/Chrome: `http://127.0.0.1:46381/admin/`.

**Step 3**: ввести `X-Admin-Token` (читаем из `~/.harness-hub/admin-token`).

**Step 4**: проверить все 5 use cases. Записать результаты в `docs/interviews/2026-10-13-admin-ui-live-debug.md`.

**Step 5**: Commit.