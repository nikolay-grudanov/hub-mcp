# Data Model — 002-skeleton-core

Pydantic v2 models, copy-paste ready. Source of truth = `src/hub_mcp/config.py` (создаётся в Phase 1.1 плана).

## HubConfig (`src/hub_mcp/config.py`)

```python
"""Pydantic models for hub-mcp config. Mirrors specs/002-skeleton-core/data-model.md exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Default paths (overridden by env vars)
DEFAULT_CONFIG_PATH = "~/.harness-hub/config.yaml"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 46380
DEFAULT_HINDSIGHT_URL = "http://127.0.0.1:8888/v1"
DEFAULT_UPSTREAM_TIMEOUT = 60.0
MIN_UPSTREAM_TIMEOUT = 1.0
MAX_UPSTREAM_NAME_LENGTH = 64
MIN_PORT = 1
MAX_PORT = 65535


class ListenConfig(BaseModel):
    """TCP listen address."""

    host: str = DEFAULT_LISTEN_HOST
    port: int = Field(default=DEFAULT_LISTEN_PORT, ge=MIN_PORT, le=MAX_PORT)


class HindsightConfig(BaseModel):
    """Hindsight audit endpoint."""

    url: str = DEFAULT_HINDSIGHT_URL
    bank_id: str = "default"
    enabled: bool = True


class UpstreamConfig(BaseModel):
    """Single upstream MCP server (HTTP transport only in MVP)."""

    name: str = Field(min_length=1, max_length=MAX_UPSTREAM_NAME_LENGTH)
    url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True
    timeout: float = Field(default=DEFAULT_UPSTREAM_TIMEOUT, ge=MIN_UPSTREAM_TIMEOUT)
    audit_level: Literal["full", "metadata_only"] = "full"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"upstream name must be alphanumeric with hyphens/underscores: {v!r}"
            )
        return v


class HubConfig(BaseModel):
    """Top-level hub configuration."""

    listen: ListenConfig = Field(default_factory=ListenConfig)
    hindsight: HindsightConfig = Field(default_factory=HindsightConfig)
    upstream: list[UpstreamConfig] = Field(min_length=1)

    @field_validator("upstream")
    @classmethod
    def _validate_unique_upstream_names(cls, v: list[UpstreamConfig]) -> list[UpstreamConfig]:
        names = [u.name for u in v]
        if len(names) != len(set(names)):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate upstream names: {duplicates}")
        return v
```

## AuditEvent (`src/hub_mcp/audit.py`)

```python
class AuditEvent(BaseModel):
    """One tool call event. Written to Hindsight under mcp-audit-{server}-{tool}-{date}."""

    timestamp: str  # ISO 8601 with Z
    server: str
    tool: str
    qualified_name: str  # e.g. "fetch.fetch_html"
    success: bool
    response_size: int = 0
    duration_ms: int = 0
    error_message: str | None = None

    def tag(self, on_date: date | None = None) -> str:
        """Generate Hindsight tag for this event."""
        d = on_date or datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).date()
        return f"mcp-audit-{self.server}-{self.tool}-{d.isoformat()}"
```

## config.yaml format (NOT in code — config file)

```yaml
# ~/.harness-hub/config.yaml
# Format: YAML, validated by Pydantic HubConfig.

listen:
  host: 127.0.0.1       # default
  port: 46380          # default

hindsight:
  url: http://127.0.0.1:8888/v1   # default
  bank_id: default                # default
  enabled: true                   # default

upstream:
  - name: fetch
    url: http://127.0.0.1:46381/mcp
    enabled: true
    timeout: 60.0

  - name: hindsight
    url: http://127.0.0.1:8888/mcp/harness/
    enabled: true
    timeout: 30.0

  - name: qmd
    url: http://127.0.0.1:8181/mcp
    enabled: true
    timeout: 60.0

  - name: context7
    url: https://mcp.context7.com/mcp
    enabled: true
    timeout: 30.0

  - name: repomix
    # stdio upstream — NOT supported в MVP, см. OQ-hub-001
    enabled: false
    timeout: 60.0
```

**Замечание**: Kolya должен извлечь HTTP upstream из `~/.hermes/profiles/harness/config.yaml` (строки с `url:`) и вставить сюда как `name`/`url`. Stdio upstream — `enabled: false` в MVP.

## Что НЕ моделируется в MVP

| Не моделируется | Почему | Когда добавим |
|---|---|---|
| Profile model и schema | Per-profile filtering отложен в Phase 3+ | Phase 3+ |
| Profile include/exclude rules | То же | Phase 3+ |
| Session state object | Session = request-scoped | Phase 2+ |
| Tool invocation result cache | Не критично для MVP | Phase 3+ |
| Config version / hash | Не нужно пока нет hot reload | Phase 2 |
| Multi-host routing | MVP = single-host | Phase 4+ |
| Profile inheritance | Отложен | Phase 4+ |

## Migrations

Нет. Это новый проект, схема с нуля. Изменения schema = новый ADR + новый release.