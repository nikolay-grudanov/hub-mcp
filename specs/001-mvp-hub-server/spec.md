# Feature Specification: 001 — MVP hub-mcp server

**Status**: ⚠️ **Superseded by [specs/002-skeleton-core/](../002-skeleton-core/spec.md) (ADR-006, 2026-10-10)**

> **Внимание**: этот документ сохранён для исторической трассировки. Реальная MVP-спека — [`../002-skeleton-core/spec.md`](../002-skeleton-core/spec.md).
>
> Что изменилось:
> - Убраны per-profile filtering, profile YAML schema, profile loader, profile Pydantic model — отложены в Phase 3+.
> - Убраны admin REST API + Web UI + admin auth + CSRF — отложены в Phase 4+ (отменены ADR-005).
> - Per-profile upstream → просто `enabled: true/false` в общем config.yaml.
> - Унифицирован конфиг: один `~/.harness-hub/config.yaml` со секциями `listen`, `hindsight`, `upstream`.
> - Scope сократился с 13 phase'ов (30 tasks, 6-8 дней) до 6 phase'ов (15 tasks, 3-4 дня).
>
> Ниже — оригинальный текст спеки. Не редактировать — заморожен.

---

## Context and Motivation

На harness-хосте Kolya управляет 25+ MCP-серверами в 4-5 runtime параллельно. Дублирование списков, нет контроля доступа к tools, нет централизованного audit log. Per-profile filtering решает 3 из 4 болей сразу (см. `docs/spec.md` §1).

**Что входит в MVP**:

- HTTP MCP-transport через `mcp` Python SDK (`streamable_http`).
- Profile loader: YAML → Pydantic v2.
- `include` / `exclude` filter на tools (см. `docs/profiles/schema.md`).
- Upstream MCP как HTTP-прокси через httpx.
- Audit log в Hindsight через REST (`POST /v1/{bank}/memories`).
- Тесты (schema, loader, filter, proxy, audit).
- Примеры профилей (`developer-tools`, `harness-infra`).

**Что НЕ входит** (см. `docs/roadmap.md` Phase 2+):

- stdio upstream.
- Token-based auth.
- Lazy tool loading / мета-tool.
- Circuit breaker.
- Web UI.
- Multi-host deploy.

## Compatibility

- **Wire protocol**: hub — стандартный MCP-сервер. Любой MCP-клиент (Hermes, Claude Code, GigaCode, OpenCode, Qwen) подключается без изменений.
- **Profile protocol**: `X-Profile-Id` HTTP-header (см. ADR-002). Это наше расширение, не стандарт MCP. Любой MCP-клиент, умеющий передавать `headers:` в конфиге, работает.
- **Backwards compatibility**: текущие runtime работают с N MCP-серверами напрямую. После rollout hub'а — переключаются на hub через изменение `mcp_servers`. Старые конфиги остаются валидными (просто не подключаются к hub).

## User Scenarios & Testing

### Scenario 1 — Hermes запускается с profile `harness-infra`

**Given**: Kolya отредактировал `~/.hermes/profiles/harness/config.yaml`, заменив N записей в `mcp_servers` на одну:

```yaml
mcp_servers:
  harness-hub:
    url: http://127.0.0.1:46380/mcp
    headers:
      X-Profile-Id: harness-infra
    timeout: 900
```

**When**: hub запущен через `uv run uvicorn hub_mcp.server:app`; Hermes запускается и подключается.

**Then**:

- `initialize` handshake успешен (hub читает `X-Profile-Id: harness-infra`, загружает profile, возвращает capabilities).
- `tools/list` возвращает ~80 tools (только разрешённые в profile).
- Каждый `tools/call` логируется в Hindsight под `mcp-audit-harness-infra-2026-10-10`.

### Scenario 2 — profile `developer-tools` ограничивает tools

**Given**: Kolya подключается к hub'у с `X-Profile-Id: developer-tools`.

**When**: агент делает `tools/list`.

**Then**:

- Возвращаются только tools из `docs/profiles/examples/developer-tools.yaml` (repomix + fetch + context7 + deepwiki).
- Tools типа `hindsight` НЕ возвращаются (не в `include`).
- `tools/call` для не-разрешённого tool возвращает MCP error «tool not found in profile».

### Scenario 3 — upstream MCP возвращает ошибку

**Given**: profile разрешает `fetch.fetch_html`, upstream `mcp-server-fetch` лежит.

**When**: агент вызывает `fetch.fetch_html`.

**Then**:

- Hub возвращает MCP error с оригинальным сообщением от upstream (или «upstream unavailable» если timeout).
- Audit log пишется с `success=false` и error message.

## Functional Requirements

### FR-1 — Profile loading

- Hub читает `~/.harness-hub/profiles/<name>.yaml` при `initialize`.
- YAML валидируется через Pydantic v2 модель `Profile`.
- Невалидный YAML / несуществующий файл → MCP error `«profile not found»` (initialize всё равно отвечает, но capabilities пустые).

### FR-2 — Tool filtering

- `tools/list` возвращает только tools, прошедшие `include` + `exclude` фильтр.
- Имя tool'а в response — `<server>.<tool>` (с namespace, чтобы избежать коллизий между upstream).
- Если фильтр пустой (profile без `include` или все `include`-server'ы недоступны) — возвращается пустой массив.

### FR-3 — Tool routing

- `tools/call` маршрутизирует к upstream'у из `upstream.yaml` по `<server>` в имени tool'а.
- Upstream вызывается через httpx (HTTP MCP-transport, JSON-RPC 2.0).
- Request включает `arguments` и `meta.progressToken` если есть.
- Response проксируется агенту as-is (с audit log).

### FR-4 — Audit log

- Каждый `tools/call` пишет в Hindsight под тегом `mcp-audit-{profile}-{YYYY-MM-DD}` (per `AGENT_CONTEXT.md` п.6).
- Audit record содержит: timestamp, profile, server, tool, args (без secrets), response_size, success, error_message (если failed).
- Hindsight недоступен → audit drop (не блокирует tool call).

### FR-5 — Limits enforcement

- `max_calls_per_session` проверяется перед каждым `tools/call`. Превышение → MCP error `«session limit reached»`.
- `max_calls_per_tool` — per-tool счётчик, аналогично.
- `max_session_duration_seconds` — TTL сессии, проверяется при каждом call.

## Non-Functional Requirements

### NFR-1 — Performance

- `tools/list` ответ ≤ 100ms при 100 tools в profile.
- `tools/call` proxy добавляет ≤ 5ms overhead (без учёта upstream latency).

### NFR-2 — Reliability

- Hub переживает падение одного upstream'а — остальные продолжают работать.
- Hub переживает недоступность Hindsight — tool calls работают, audit log теряется (с warning в лог).

### NFR-3 — Security

- `Authorization`-headers из upstream responses **не проксируются** агенту (только `data` payload).
- Audit log не содержит values из `Authorization` headers (только profile-name).
- `X-Profile-Id` НЕ используется для авторизации в MVP — это identification, не authentication (см. ADR-002). Для localhost допустимо; для multi-host — Phase 2.

### NFR-4 — Observability

- Structured JSON logging через `structlog` или `logging` с JSON formatter.
- Каждый request логируется с profile, server, tool, duration_ms, success.
- Audit log в Hindsight — для долгосрочного анализа (per-day/per-profile queries).

## Files to Create/Modify

| File | Action | Priority |
|---|---|---|
| `pyproject.toml` | Create | P0 |
| `src/hub_mcp/__init__.py` | Create | P0 |
| `src/hub_mcp/server.py` | Create | P0 |
| `src/hub_mcp/types.py` | Create (Profile, ToolRef, etc.) | P0 |
| `src/hub_mcp/profile_loader.py` | Create | P0 |
| `src/hub_mcp/filter.py` | Create (include/exclude logic) | P0 |
| `src/hub_mcp/upstream.py` | Create (httpx client to upstream) | P0 |
| `src/hub_mcp/audit.py` | Create (Hindsight REST client) | P0 |
| `src/hub_mcp/exceptions.py` | Create (HubMcpError base) | P0 |
| `src/hub_mcp/config.py` | Create (paths from env) | P1 |
| `src/hub_mcp/admin.py` | Create (admin REST API handlers) | **P0 (ADR-005)** |
| `src/hub_mcp/admin_auth.py` | Create (X-Admin-Token + localhost bind) | **P0 (ADR-005)** |
| `src/hub_mcp/csrf.py` | Create (CSRF token via itsdangerous) | **P0 (ADR-005)** |
| `src/hub_mcp/upstream_health.py` | Create (per-upstream health cache + ping) | **P0 (ADR-005)** |
| `src/hub_mcp/templates/` | Create (Jinja2 templates for /admin/ui/) | **P0 (ADR-005)** |
| `src/hub_mcp/static/` | Create (minimal CSS, Pico single-file) | **P1 (ADR-005)** |
| `docs/admin-api.yaml` | Create (OpenAPI spec, manually authored) | **P1 (ADR-005)** |
| `tests/conftest.py` | Create (fixtures) | P0 |
| `tests/test_types.py` | Create (Pydantic validation) | P0 |
| `tests/test_profile_loader.py` | Create | P0 |
| `tests/test_filter.py` | Create | P0 |
| `tests/test_upstream.py` | Create (mock httpx) | P0 |
| `tests/test_audit.py` | Create (mock Hindsight) | P0 |
| `tests/test_server.py` | Create (Starlette TestClient) | P0 |
| `tests/test_admin.py` | Create (admin REST + UI smoke) | **P0 (ADR-005)** |
| `tests/test_admin_auth.py` | Create (token check, localhost bind) | **P0 (ADR-005)** |
| `tests/test_csrf.py` | Create (CSRF token validation) | **P0 (ADR-005)** |
| `~/.harness-hub/profiles/developer-tools.yaml` | Create (deploy) | P0 |
| `~/.harness-hub/profiles/harness-infra.yaml` | Create (deploy) | P0 |
| `~/.harness-hub/upstream.yaml` | Create (deploy, с явным списком upstream) | P0 |
| `~/.harness-hub/admin-token` | Create on first run (chmod 600, generated random) | **P0 (ADR-005)** |

## Testing Strategy

- **Unit tests**: `pytest tests/ -v`, ≥ 85% coverage.
- **Integration test**: live MCP Inspector подключается к hub'у, делает `initialize` + `tools/list` + `tools/call` руками. Live debug протокол (см. `AGENT_CONTEXT.md` п.2).
- **Smoke test**: `uv run uvicorn hub_mcp.server:app --reload`, MCP Inspector connect → list tools → call tool. Если 2 из 2 успешны — MVP готов.

## Open Questions (blockers)

См. `docs/open-questions.md`. Для MVP:

- OQ-hub-001 (stdio upstream) — не блокирует, откладываем в Phase 2.
- OQ-hub-002 (token auth) — не блокирует, localhost-only MVP.
- OQ-hub-007 (hot-reload) — не блокирует, ручной restart для MVP.

## Related Specifications

- [`spec.md`](../../docs/spec.md) — верхнеуровневая спецификация проекта.
- [`roadmap.md`](../../docs/roadmap.md) — Phase 1 = этот spec.
- [`profile-schema.md`](../../docs/profiles/schema.md) — schema для profile YAML.
- `decisions/ADR-001..004` — архитектурные решения, влияющие на MVP.

## References

- MCP Python SDK: `https://github.com/modelcontextprotocol/python-sdk`
- MCP spec: `https://modelcontextprotocol.io/`
- Hindsight REST API: `http://localhost:8888/docs` (локально)
- Starlette: `https://www.starlette.io/`
- uvicorn: `https://www.uvicorn.org/`