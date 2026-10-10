# Feature Specification: 002 — Skeleton core hub-mcp server

**Feature Branch**: `feat/002-skeleton-core` (merged to master)
**Created**: 2026-10-10
**Completed**: 2026-10-10
**Status**: Implemented
**Input**: «Согласен, не меняем стек. Давай тогда напиши спеку для создания скелета и первого mvp пока без ui, будем через конфиг или как-то по другому добавлять доступные mcp инструменты в hub. Профили тоже уберем из списка работ. Нам надо создать хорошее ядро» (Kolya 2026-10-10).

**Supersedes**: [`specs/001-mvp-hub-server/`](../001-mvp-hub-server/spec.md) — старая спека с per-profile filtering + admin UI, отменена ADR-006.
**Decisions**:
- [ADR-001](../docs/decisions/ADR-001-mcp-fork-not-protocol-fork.md) — hub-mcp ≠ fork MCP протокола.
- [ADR-003](../docs/decisions/ADR-003-starlette-not-flask.md) — Starlette + uvicorn, не Flask, не FastAPI.
- [ADR-004](../docs/decisions/ADR-004-no-server-side-state.md) — без server-side state между запросами.
- [ADR-006](../docs/decisions/ADR-006-skeleton-core-no-profiles-no-ui.md) — **MVP = skeleton + core, без профилей и admin**.
- [ADR-007](../docs/decisions/ADR-007-upstream-via-mcp-sdk.md) — **UpstreamClient через `mcp.client.streamable_http` (применён в Phase 1)**.

## Context and Motivation

На harness-хосте Kolya управляет 25+ MCP-серверами в 4-5 runtime параллельно (Hermes-профили, OpenCode/GigaCode/Qwen CLI в проектах, zai-copilot). Дублирование списков, отсутствие централизованного audit log, расход контекенов на tool schema — три боли, которые решает hub (см. `docs/spec.md` §1).

**Что входит в MVP (по ADR-006)**:

- ASGI-приложение на Starlette + uvicorn, слушает `streamable_http` MCP-transport на `:46380`.
- Один конфиг-файл `~/.harness-hub/config.yaml` со секциями `listen`, `hindsight`, `upstream`.
- Upstream MCP как HTTP-прокси через httpx (только HTTP, не stdio в MVP).
- Audit log в Hindsight через REST под тегом `mcp-audit-{server}-{tool}-{YYYY-MM-DD}`.
- Health endpoint `/health`.
- `tools/list` = union tools со всех enabled upstream с namespace `<server>.<tool>`.
- `tools/call` маршрутизирует по `<server>` в имени tool'а.
- Тесты: config loader, upstream mock, audit write, MCP roundtrip, health.
- Live debug с реальным MCP Inspector + 1+ реальный upstream.

**Что НЕ входит в MVP** (отложено):

- Per-profile фильтрация через `X-Profile-Id` (Phase 3+, см. ADR-002).
- Profile YAML schema + loader (Phase 3+).
- Admin REST API + Web UI (Phase 4+, см. ADR-005 Superseded).
- stdio upstream (Phase 2, см. OQ-hub-001).
- Token-based auth (Phase 3+).
- Hot-reload конфига через SIGHUP (Phase 2).
- Per-upstream health checker с ping loop (Phase 2).
- Lazy tool loading / мета-tool `hub.search_tools` (Phase 3+).
- WebSocket transport (Phase 2).
- Multi-host deploy (Phase 4+).

## Compatibility

- **Wire protocol**: hub — стандартный MCP-сервер. Любой MCP-клиент (Hermes, Claude Code, GigaCode, OpenCode, Qwen) подключается без изменений.
- **Config-driven**: Колya редактирует `~/.harness-hub/config.yaml` руками, рестартует hub процесс. Никаких dynamic API для редактирования в MVP.
- **Backwards compatibility**: существующие runtime работают с N MCP-серверами напрямую. После rollout hub'а — переключаются на hub через изменение `mcp_servers` (одна запись вместо N).

## User Scenarios & Testing

### Scenario 1 — MCP Inspector подключается и видит все tools

**Given**: hub запущен через `uv run uvicorn hub_mcp.server:app`; `~/.harness-hub/config.yaml` содержит 3 enabled upstream (hindsight, fetch, qmd).

**When**: MCP Inspector подключается к `http://127.0.0.1:46380/mcp` и делает `tools/list`.

**Then**:

- `initialize` handshake успешен, hub возвращает capabilities `{tools: {listChanged: false}}` и serverInfo `{name: "hub-mcp", version: "0.1.0"}`.
- `tools/list` возвращает union tools со всех 3 upstream, каждый с префиксом `<server>.`. Например: `hindsight.recall`, `hindsight.retain`, `fetch.fetch_html`, `fetch.fetch_markdown`, `qmd.query`, `qmd.get`.
- Каждый tool имеет `name` (qualified), `description` (от upstream), `inputSchema` (JSON Schema от upstream).

### Scenario 2 — tools/call маршрутизирует к правильному upstream

**Given**: hub подключён к upstream `fetch` на `http://localhost:46381/mcp`.

**When**: агент вызывает `tools/call` с `name="fetch.fetch_html"` и `arguments={"url": "https://example.com"}`.

**Then**:

- Hub маршрутизирует вызов к `fetch` upstream с методом `tools/call`, `name="fetch_html"`, `arguments={"url": "https://example.com"}`.
- Upstream возвращает HTML content.
- Hub проксирует ответ агенту as-is.
- Audit log в Hindsight под тегом `mcp-audit-fetch-fetch_html-2026-10-10`.

### Scenario 3 — upstream с `enabled: false` не виден

**Given**: конфиг содержит `upstream.repomix.enabled: false`.

**When**: агент делает `tools/list`.

**Then**:

- Tools с repomix upstream **не** появляются в ответе.
- При попытке `tools/call` с `name="repomix.pack_codebase"` — hub возвращает MCP error «tool not found».

### Scenario 4 — upstream недоступен, hub возвращает ошибку

**Given**: конфиг содержит `upstream.fetch.url: http://localhost:9999/mcp` (порт не слушается).

**When**: агент делает `tools/call` с `name="fetch.fetch_html"`.

**Then**:

- Hub пытается подключиться, получает `ConnectionRefusedError`.
- Hub возвращает агенту MCP error `-32002 Service unavailable: upstream 'fetch' unavailable`.
- Audit log в Hindsight с `success: false`, `error_message: connection refused`.

## Functional Requirements

### FR-1 — Config loading

- Hub читает `~/.harness-hub/config.yaml` при старте через `_lifespan` Starlette context.
- YAML валидируется через Pydantic v2 модель `HubConfig` (см. `data-model.md`).
- Невалидный YAML / отсутствующий файл → процесс падает с понятным error message (не молча).
- Переменные окружения `HUB_CONFIG_PATH` (default `~/.harness-hub/config.yaml`), `HUB_LISTEN_HOST` (default `127.0.0.1`), `HUB_LISTEN_PORT` (default `46380`), `HUB_HINDSIGHT_URL` (default `http://127.0.0.1:8888/v1`) переопределяют конфиг.

### FR-2 — Upstream discovery

- При старте hub читает `config.upstream:`, фильтрует `enabled: true`.
- Upstream с `enabled: false` существуют в конфиге, но не опрашиваются (ни в `tools/list`, ни в `tools/call`).
- Уникальность `name` среди upstream валидируется Pydantic (дубликаты → startup error).

### FR-3 — Tool aggregation

- `tools/list` MCP-handshake параллельно вызывает `tools/list` на всех enabled upstream (через `asyncio.gather`).
- Таймаут на upstream = `config.upstream[i].timeout` (default 60s).
- Upstream с ошибкой (5xx, timeout, connection refused) исключаются из ответа, **не блокируют** остальные.
- Tools квалифицируются как `<upstream.name>.<tool.name>`.

### FR-4 — Tool routing

- `tools/call` парсит `<server>.<tool>` из `params.name`.
- Если `<server>` не в upstream → MCP error `-32601 Method not found: tool '<name>' not found`.
- Если `<server>` в upstream, но `<tool>` нет в этом upstream → MCP error `-32601 Tool not found on server '<server>'`.
- Если `<server>` в upstream, но upstream с `enabled: false` → MCP error `-32601 Tool not available (upstream disabled)`.
- Если `<server>` и `<tool>` найдены, но upstream возвращает error → MCP error `-32002 Upstream '<server>' unavailable: <details>`.

### FR-5 — Audit log

- Каждый `tools/call` пишет в Hindsight под тегом `mcp-audit-{server}-{tool}-{YYYY-MM-DD}` (см. `AGENT_CONTEXT.md` п.6).
- Audit record содержит: `timestamp`, `server`, `tool`, `qualified_name`, `success`, `response_size`, `duration_ms`, `error_message` (если failed).
- Hindsight недоступен → audit drop с warning в логи (не блокирует tool call).
- `audit_level: metadata_only` (если указан в upstream config) → пишет только metadata, не arguments.

### FR-6 — Health endpoint

- `GET /health` → 200 OK с `{"status": "ok", "version": "0.1.0", "uptime_seconds": N}`.
- Health endpoint не зависит от upstream state — всегда отвечает 200 если процесс жив.

### FR-7 — Graceful shutdown (минимальный)

- SIGTERM → завершить in-flight requests → закрыть httpx connections → exit 0.
- Не реализуем SIGHUP-reload в MVP — рестарт через `kill <pid>; uv run uvicorn ...`.

## Non-Functional Requirements

### NFR-1 — Performance

- `tools/list` ответ ≤ 200ms при 5 enabled upstream (10 tools каждый).
- `tools/call` proxy добавляет ≤ 10ms overhead (без учёта upstream latency).

### NFR-2 — Reliability

- Hub переживает падение одного upstream'а — остальные продолжают работать.
- Hub переживает недоступность Hindsight — tool calls работают, audit log теряется (с warning).

### NFR-3 — Security

- Hub слушает на `127.0.0.1` по умолчанию (не `0.0.0.0`). Multi-host в Phase 4+.
- Audit log не содержит values из `Authorization` headers (только server + tool name).
- Нет auth в MVP — localhost-only. Multi-user auth в Phase 4+.

### NFR-4 — Observability

- Structured JSON logging через `logging` + `python-json-logger` (или stdlib `logging` с JSON formatter).
- Каждый request логируется с profile-less identifier (по server + tool), duration_ms, success.
- Audit log в Hindsight — для долгосрочного анализа (per-day/per-upstream queries).

## Files to Create/Modify

| File | Action | Priority |
|---|---|---|
| `pyproject.toml` | Create | P0 |
| `src/hub_mcp/__init__.py` | Create | P0 |
| `src/hub_mcp/exceptions.py` | Create | P0 |
| `src/hub_mcp/config.py` | Create (HubConfig Pydantic + load_config) | P0 |
| `src/hub_mcp/upstream.py` | Create (UpstreamClient, JSON-RPC over httpx) | P0 |
| `src/hub_mcp/audit.py` | Create (AuditEvent + AuditWriter) | P0 |
| `src/hub_mcp/server.py` | Create (Starlette ASGI app + JSON-RPC dispatcher) | P0 |
| `tests/conftest.py` | Create (fixtures) | P0 |
| `tests/test_config.py` | Create (Pydantic validation) | P0 |
| `tests/test_upstream.py` | Create (mock httpx) | P0 |
| `tests/test_audit.py` | Create (mock Hindsight) | P0 |
| `tests/test_server.py` | Create (Starlette TestClient) | P0 |
| `~/.harness-hub/config.yaml` | Create (deploy example) | P0 |

**Не в MVP** (отложено в Phase 2+/3+/4):

- `src/hub_mcp/profile_loader.py`, `src/hub_mcp/filter.py`, `src/hub_mcp/types.py` (Profile model) — отложены в Phase 3+.
- `src/hub_mcp/admin*.py`, `src/hub_mcp/csrf.py`, `src/hub_mcp/templates/`, `src/hub_mcp/static/` — отложены в Phase 4.
- `src/hub_mcp/upstream_health.py` — отложен в Phase 2.

## Testing Strategy

- **Unit tests**: `pytest tests/ -v`, ≥ 85% coverage.
- **Integration test** (live debug): реальный upstream MCP (например, `mcp-server-fetch` через `npx`) + MCP Inspector через `npx @modelcontextprotocol/inspector`. Протокол в `AGENT_CONTEXT.md` п.2.
- **Smoke test**: `uv run uvicorn hub_mcp.server:app`, MCP Inspector connect → list tools → call tool. Если 2 из 2 успешны — MVP готов.

## Open Questions (blockers)

См. `docs/open-questions.md`. Для MVP ничего не блокирует (все OQ — Phase 2+).

- OQ-hub-001 (stdio) — Phase 2.
- OQ-hub-002 (token auth) — Phase 3+.
- OQ-hub-007 (hot-reload validation) — Phase 2.
- OQ-hub-008 (WebSocket) — Phase 2.
- OQ-hub-011 (audit retention) — Phase 2.
- OQ-hub-012 (upstream failure behavior) — фиксируется в MVP через OQ-hub-012 RESOLVED в `plan.md` Task 3.1.

## Related Specifications

- [`docs/spec.md`](../../docs/spec.md) — верхнеуровневая спецификация проекта.
- [`docs/roadmap.md`](../../docs/roadmap.md) — Phase 1 = этот спек.
- Старая [spec-001 — Superseded](../001-mvp-hub-server/spec.md) — для исторической трассировки.

## References

- MCP Python SDK: `https://github.com/modelcontextprotocol/python-sdk`
- MCP spec: `https://modelcontextprotocol.io/`
- Hindsight REST API: `http://localhost:8888/docs` (локально)
- Starlette: `https://www.starlette.io/`
- uvicorn: `https://www.uvicorn.org/`