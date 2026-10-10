# Data Model — 001-mvp-hub-server

Pydantic v2 models, copy-paste ready. Source of truth = `src/hub_mcp/types.py` (создаётся в Phase 2 плана) + `src/hub_mcp/mcp_types.py`.

## Profile (`src/hub_mcp/types.py`)

```python
"""Pydantic models for hub-mcp. Mirrors docs/profiles/schema.md exactly."""

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

## UpstreamTool / FilteredTool (`src/hub_mcp/mcp_types.py`)

```python
"""Minimal tool representation (decoupled from MCP SDK types)."""

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

## AuditEvent (`src/hub_mcp/audit.py`)

```python
class AuditEvent(BaseModel):
    """One tool call event. Written to Hindsight under mcp-audit-{profile}-{date}."""

    timestamp: str  # ISO 8601 with Z
    profile: str
    server: str
    tool: str
    success: bool
    response_size: int = 0
    error_message: str | None = None
    duration_ms: int | None = None

    def tag(self, on_date: date | None = None) -> str:
        d = on_date or datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).date()
        return f"mcp-audit-{self.profile}-{d.isoformat()}"
```

## upstream.yaml format (NOT in code — config file)

```yaml
# ~/.harness-hub/upstream.yaml
# Format: {server-name: upstream-URL}. Loaded by server.py on startup.
# Stdio MCP servers — НЕ включаются в MVP (см. OQ-hub-001).

fetch: http://127.0.0.1:46381/mcp          # if you run mcp-server-fetch as HTTP locally
jina-rester: http://127.0.0.1:46382/mcp
context7: https://mcp.context7.com/mcp     # or http://localhost:...
deepwiki: https://mcp.deepwiki.com/mcp
qmd: http://127.0.0.1:8181/mcp             # see ~/.hermes/profiles/harness/config.yaml
hindsight: http://127.0.0.1:8888/mcp/harness/
searxng: http://127.0.0.1:8080/mcp
```

**Note**: реальные upstream URLs Kolya должен извлечь из `~/.hermes/profiles/harness/config.yaml` сам. Этот файл — config, не source.

## Что НЕ моделируется в MVP

| Не моделируется | Почему | Когда добавим |
|---|---|---|
| Profile inheritance (`extends: harness-infra`) | Усложняет loader | Phase 2 |
| Per-upstream выбор | Profile не знает про upstream config | Phase 2 |
| Session state object | Сейчас session = request-scoped; state в Hindsight | Phase 2 |
| Tool invocation result cache | Не критично для MVP | Phase 3 |
| Profile version / hash | Не нужно пока нет hot reload | Phase 2 |

## Migrations

Нет. Это новый проект, схема с нуля. Изменения schema = новый ADR + новый release.