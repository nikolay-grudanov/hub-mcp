---
title: hub-mcp — спецификация
created: 2026-10-10
updated: 2026-10-10
status: Draft
---

# hub-mcp — спецификация

> **Update 2026-10-10**: ADR-006 упрощает MVP до скелета + ядра. Per-profile фильтрация и admin UI отложены в Phase 3+. Эта версия документа отражает новый scope.

## 1. Проблема

На harness-хосте Kolya запускает несколько runtime параллельно:

- **Hermes-профили** (`~/.hermes/profiles/harness/`, и, вероятно, `researcher`, `coder`, и т.д.) — каждый со своим `mcp_servers` конфигом.
- **OpenCode** / **GigaCode** / **Qwen CLI** в проектах — каждый со своим `opencode.jsonc` / `.gigacode/settings.json` / `.qwen/settings.json`.
- **zai-copilot** (zai-mcp-server через stdio) — для разработки.

**Боли**:

1. **Дублирование списков MCP между runtime.** Один и тот же MCP (например, `mcp-server-fetch`, `repomix`) прописан в 4-5 конфигах. Обновил endpoint в одном — забыл в другом → агенты ловят timeout.
2. **Нет централизованного audit log.** Кто что вызвал, когда — логи размазаны по runtime-specific логам.
3. **Большой tool schema в system prompt.** Сейчас `mcp_servers` config в `harness` профиле содержит 25+ MCP × ~10 tools = 250 tool descriptions. ~75k токенов только на описание tools, до старта диалога.

## 2. Цель

**harness-mcp-hub** — единый MCP-сервер с жёстко зашитым списком upstream MCP из конфига. Заменяет N записей в `mcp_servers` каждого runtime на одну (на каждый runtime). Hub проксирует все `tools/list` и `tools/call` к соответствующему upstream, логирует вызовы в Hindsight.

**MVP scope (см. ADR-006)**: skeleton + core, без per-profile фильтрации и без admin UI. Все runtime видят все upstream'ы (что в enabled=true). В дальнейшем — Phase 3+ добавляет профили, Phase 4+ — admin UI.

## 3. Архитектура (один абзац)

Hub — это **ASGI-приложение на Starlette/uvicorn**, которое:
- слушает HTTP-запросы по MCP-протоколу (JSON-RPC 2.0) на `127.0.0.1:46380/mcp`;
- при старте читает конфиг `~/.harness-hub/config.yaml` — список upstream с `enabled: true/false`;
- при `tools/list` агрегирует tools со всех enabled upstream и возвращает как union, с namespace `<server>.<tool>`;
- при `tools/call` маршрутизирует вызов к соответствующему upstream по `<server>` в имени tool'а;
- пишет audit-log в Hindsight под тегом `mcp-audit-{server}-{tool}-{YYYY-MM-DD}` (без profile — profile нет).

**Не fork протокола**: hub — стандартный MCP-сервер, который говорит со стандартными MCP-клиентами (Hermes, Claude Code, GigaCode). Никаких изменений в wire-формате. См. `docs/decisions/ADR-001-mcp-fork-not-protocol-fork.md`.

## 4. Scope MVP (Phase 1, см. ADR-006)

- HTTP MCP-transport (streamable_http).
- Единый конфиг `~/.harness-hub/config.yaml` со секциями `listen`, `hindsight`, `upstream`.
- Upstream HTTP proxy через httpx (только HTTP, не stdio).
- Audit log в Hindsight через REST (`POST /v1/{bank}/memories`).
- Health endpoint `/health`.
- Тесты на конфиг-loader, upstream-mock, audit-write, health, MCP roundtrip.
- Live debug с реальным MCP Inspector + 1+ реальный upstream.

**Не входит в MVP** (отложено в Phase 2+):

- Per-profile фильтрация через `X-Profile-Id` header (Phase 3+, см. ADR-002).
- stdio upstream (Phase 2, см. OQ-hub-001).
- Token-based auth (Phase 3+).
- Hot-reload конфига через SIGHUP (Phase 2, см. OQ-hub-007).
- Per-upstream health checker с ping loop (Phase 2).
- Lazy tool loading / мета-tool `hub.search_tools` (Phase 3+).
- Admin REST API + Web UI (Phase 4+, см. ADR-005).
- WebSocket transport (Phase 2, см. OQ-hub-008).
- Multi-host deploy (Phase 4+).

## 5. Non-goals

- **Не заменяет sub-agents**. Sub-agent (delegate_task в Hermes) — это child-процесс с собственной историей. Hub работает с MCP-серверами.
- **Не решает skill indexing**. Hub маршрутизирует **calls**; загрузка skills в agent context — отдельный механизм (Hermes skill snapshot).
- **Не multi-agent planner**. Hub — registry + router, не orchestrator с phase gates.
- **Не решает per-runtime access control в MVP** (отложено в Phase 3+). Сейчас все runtime видят все tools.

## 6. Архитектурный обзор (текстовая диаграмма)

```
┌──────────────────────────────────────────────────────────┐
│  Hermes / Claude Code / GigaCode / Qwen / OpenCode      │
│  (MCP-клиент)                                            │
└────────────────────┬─────────────────────────────────────┘
                     │ HTTP, streamable_http
                     ▼
┌──────────────────────────────────────────────────────────┐
│  harness-mcp-hub (Starlette :46380)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ config.py    │  │ bridge.py    │  │ audit.py     │  │
│  │ (YAML loader │→ │ (proxy call  │→ │ (Hindsight   │  │
│  │ + Pydantic)  │  │ to upstream) │  │  best-effort)│  │
│  └──────────────┘  └──────┬───────┘  └──────────────┘  │
│                           │                              │
│                  ┌────────┴────────┐                     │
│                  │ upstream.py    │                     │
│                  │ (httpx client, │                     │
│                  │  JSON-RPC 2.0) │                     │
│                  └────────┬───────┘                     │
└───────────────────────────┼─────────────────────────────┘
                            │ HTTP
                            ▼
   ┌────────────────────────────────────────────────────┐
   │ enabled upstream MCP servers                       │
   │  - http://localhost:46381/mcp (fetch)              │
   │  - http://localhost:8888/mcp/harness/ (hindsight)  │
   │  - http://localhost:8181/mcp (qmd)                 │
   │  - https://mcp.context7.com/mcp                     │
   │  - ...                                              │
   └────────────────────────────────────────────────────┘
```

## 7. Конфигурация

Единый файл `~/.harness-hub/config.yaml` (формат в ADR-006). Валидируется через Pydantic. В MVP — никакого hot-reload, требуется рестарт процесса.

## 8. Acceptance

Hub считается готовым к MVP, когда:

- [ ] `uv run uvicorn hub_mcp.server:app` поднимается на 46380, `/health` отвечает 200.
- [ ] MCP Inspector успешно подключается, делает `tools/list` → видит union tools со всех enabled upstream с namespace `<server>.<tool>`.
- [ ] Inspector делает `tools/call` для tool'а с любого upstream → hub маршрутизирует и возвращает результат.
- [ ] Каждый tool call пишется в Hindsight под `mcp-audit-{server}-{tool}-{date}`.
- [ ] Все 4 pre-commit checks зелёные: `ruff check`, `ruff format`, `pyright`, `pytest --cov`.
- [ ] Coverage ≥ 85% для `src/hub_mcp/`.
- [ ] Live-debug протокол пройден (см. `AGENT_CONTEXT.md` п.2): реальный upstream + реальный MCP-клиент + ручной smoke через Inspector.

## 9. Открытые вопросы

См. `docs/open-questions.md`. Все отложены ADR-006 в Phase 2+.

- OQ-hub-001 — stdio upstream (Phase 2)
- OQ-hub-007 — hot-reload behavior (Phase 2)
- OQ-hub-008 — WebSocket transport (Phase 2)
- OQ-hub-011 — audit retention policy (Phase 2)
- OQ-hub-002 — token-based profile auth (Phase 3+, после ADR-002)
- OQ-hub-006 — per-profile upstream selection (Phase 3+)
- OQ-hub-005 — admin Web UI (Phase 4+, отложен ADR-006)
- OQ-hub-009 — admin auth multi-host (Phase 4+, отложен ADR-006)
- OQ-hub-010 — CSRF (Phase 4+, отложен ADR-006)

## 10. Ссылки

- [InternScience/scp analysis в llmwiki](../../../workspaces/harness/llmwiki/internscience-scp-architecture.md) — reference-проект, не свойство обучения.
- [ADR-001 — MCP-fork, не protocol-fork](decisions/ADR-001-mcp-fork-not-protocol-fork.md)
- [ADR-002 — X-Profile-Id header (Superseded)](decisions/ADR-002-x-profile-id-header.md) — отложен ADR-006
- [ADR-003 — Starlette, не Flask](decisions/ADR-003-starlette-not-flask.md)
- [ADR-004 — без server-side state](decisions/ADR-004-no-server-side-state.md)
- [ADR-005 — Admin REST API + Web UI (Superseded)](decisions/ADR-005-admin-rest-api-and-web-ui-in-mvp.md) — отложен ADR-006
- [ADR-006 — Skeleton core, без профилей и admin](decisions/ADR-006-skeleton-core-no-profiles-no-ui.md) — **текущий scope MVP**
- [MVP-2 спека — Skeleton core](specs/002-skeleton-core/spec.md)
- [Старая MVP-1 спека — Superseded](specs/001-mvp-hub-server/spec.md) — для исторической трассировки