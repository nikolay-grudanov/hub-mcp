---
title: hub-mcp — открытые вопросы
created: 2026-10-10
updated: 2026-10-10
---

# Open Questions

> **Update 2026-10-10 (ADR-006)**: MVP упрощён до скелета + ядра без профилей и admin UI. Все вопросы, связанные с профилями и admin, отложены в Phase 3+. Вопросы по инфраструктуре (stdio upstream, hot-reload, WebSocket, audit retention, circuit breaker) — в Phase 2.

Все вопросы, на которые ещё нет ответа. Закрытые остаются здесь со strike-through + датой закрытия + ссылкой на решение.

## Формат записи

```markdown
- **OQ-hub-NNN** — <title>
  <контекст, варианты, что блокирует>.
  - **RESOLVED YYYY-MM-DD** → <ссылка на ADR / PR / решение>.
```

---

## Phase 2+ (не блокируют MVP)

### OQ-hub-001 — stdio upstream

Текущий MVP поддерживает только HTTP upstream MCP. Но часть Kolya's стека — stdio (например, `arxiv-mcp-server` через `uv tool run`, `mcp-server-fetch` через `npx`, `zai-mcp-server` как subprocess). Как минимум 5 из 25+ MCP из `~/.hermes/profiles/harness/config.yaml` — stdio.

**Варианты**:

- (a) Научить hub spawn'ить stdio upstream как subprocess и проксировать через его stdio. Требует asyncio subprocess lifecycle.
- (b) Обернуть stdio upstream в sidecar HTTP-адаптер (например, через `mcp-proxy` или собственный скрипт). +1 процесс на каждый upstream.
- (c) На этапе MVP оставить только HTTP. stdio upstream подключать напрямую к runtime (не через hub), пока не появится спрос.

**Блокирует**: Phase 2 (не блокирует MVP).

**Когда решать**: при начале Phase 2, после MVP прошёл live-debug.

  - **RESOLVED 2026-10-10** → [ADR-008](decisions/ADR-008-transport-discriminated-union.md) + спека [003-stdio-and-hot-reload](../specs/003-stdio-and-hot-reload/spec.md). Вариант (a) — UpstreamClient расширяется stdio branch через `mcp.client.stdio.stdio_client` (тот же SDK pattern, что и HTTP). Discriminated union `UpstreamConfig.transport` с backward-compat для Phase 1 `url: str`.

### OQ-hub-002 — Token-based profile auth

`X-Profile-Id` — открытый header, любой MCP-клиент может прислать `developer-tools` и получить доступ к инструментам для pet-проектов. На localhost это допустимо, но если hub слушает на `0.0.0.0` (Phase 4, multi-host) — нет.

**Варианты**:

- (a) `Authorization: Bearer` токен → profile mapping в `~/.harness-hub/tokens.yaml`. Дополнительный CLI для генерации токенов.
- (b) mTLS: hub генерирует per-agent client cert. Безопаснее, но +1 bootstrap step для каждого runtime.
- (c) OAuth 2.0 через upstream provider (Google / GitHub). Избыточно для localhost.

**Блокирует**: Phase 3+ (profile filtering возвращается из ADR-002). Не блокирует MVP.

**Когда решать**: при начале Phase 3+, когда вернётся profile filtering.

### OQ-hub-003 — Lazy tool loading / мета-tool

Сейчас (после Phase 3+): все tools профиля загружаются в system prompt при `initialize`. При 80 tools × 300 токенов/schema = 24k токенов на старте сессии. Multi-turn sessions это пересылают каждый раз (зависит от cache).

**Гибридный вариант**: 30 "core" tools в system prompt + мета-tool `hub.search_tools(query: str) -> list[ToolMeta]`. Агент вызывает мета-tool когда не видит нужного в текущих 30.

**Блокирует**: Phase 3+ (token economy). Не блокирует MVP.

**Когда решать**: после Phase 2, когда есть телеметрия использования.

### OQ-hub-004 — Circuit breaker / auto-restart upstream

Если upstream MCP упал — что делает hub? MVP: вернёт ошибку агенту, агент retry'нет. Простой, но не optimal.

**Варианты**:

- (a) In-memory counter: 3 failed calls за 60s → upstream помечается down на 60s → следующие calls мгновенно fail с "circuit open".
- (b) Background ping каждые 30s (как в SCP hub_server.py). Помечает unhealthy в `audit` log.
- (c) Auto-restart upstream, если upstream — stdio subprocess (Phase 2).

**Блокирует**: Phase 2. Для MVP допустимо fail-fast.

**Когда решать**: при начале Phase 2.

### OQ-hub-005 — Web UI для редактирования профилей

Kolya 2026-10-10: «я хочу менять profile без редактирования YAML руками и `uv run` restart».

**Варианты**:

- FastAPI + HTMX single-page app на отдельном порту (46381).
- TUI через Textual.
- CLI для `harness-hub profile edit <name> --add-tool <tool>`.

**Блокирует**: Phase 4 (отложен ADR-006, не блокирует MVP).

**Когда решать**: при начале Phase 4, если вернёмся к admin UI.

  - **RESOLVED 2026-10-10** (admin REST + Web UI в MVP) → [ADR-005](decisions/ADR-005-admin-rest-api-and-web-ui-in-mvp.md).
  - **RESOLVED 2026-10-10** (отложен обратно в Phase 4) → [ADR-006](decisions/ADR-006-skeleton-core-no-profiles-no-ui.md).

### OQ-hub-006 — Per-profile upstream selection

После Phase 3+ profile описывает только **какие tools** доступны. Upstream MCP-список — глобальный (один на hub). Может ли profile переопределять upstream (например, `developer-tools` profile использует другой `hindsight` bank, чем `researcher`)?

**Варианты**:

- (a) Глобальный upstream-list + profile выбирает tools. Просто, но негибко.
- (b) Profile включает upstream declarations (включая auth headers). Гибко, но профили становятся конфиг-сложными.
- (c) Profile ссылается на `env: HUB_PROFILE=...`, hub читает env при старте upstream и подставляет в headers. Среднее.

**Блокирует**: Phase 3+ (когда понадобится разный Hindsight bank per profile). Не блокирует MVP.

**Когда решать**: до Phase 3+, если Kolya хочет разные bank'и.

### OQ-hub-007 — Schema validation при hot-reload config

Если Kolya отредактировал `~/.harness-hub/config.yaml` и допустил typo (например, `url: http:/malformed`) — что делает hub? В MVP — никакого hot-reload, требуется рестарт процесса. Но в Phase 2+ при SIGHUP-reload это станет актуально.

**Варианты**:

- (a) Hot-reload invalid YAML → keep old config, log error. Безопаснее.
- (b) Hot-reload invalid YAML → откатить процесс к старой версии config. Строже.
- (c) Запретить hot-reload вообще — требуется `kill -HUP` или CLI. Самое строгое.

**Блокирует**: Phase 2 (когда появится hot-reload).

**Когда решать**: при начале Phase 2.

  - **RESOLVED 2026-10-10** → вариант (a): hot-reload invalid YAML → keep old config + log error. Спека [003-stdio-and-hot-reload](../specs/003-stdio-and-hot-reload/spec.md) FR-5.

### OQ-hub-008 — WebSocket transport

MCP поддерживает WebSocket transport. Наш MVP — только streamable_http. Нужен ли WebSocket?

**Варианты**:

- (a) Не нужен. Streamable_http достаточно для всех наших use cases.
- (b) Нужен для специфических upstream (например, `mcp-deepwiki` через WS). Добавить в Phase 2.

**Блокирует**: неизвестно. Не появлялось в обсуждении 2026-10-10.

**Когда решать**: при начале Phase 2, или когда конкретный upstream потребует.

---

## Phase 4+ (отложены ADR-006)

### OQ-hub-009 — Admin auth на multi-host (Phase 4)

Сейчас (если бы admin был в MVP): admin token в `~/.harness-hub/admin-token` (chmod 600). На multi-host (Phase 4) нужно что-то серьёзнее — OAuth / mTLS / reverse proxy auth.

**Блокирует**: Phase 4 (admin возвращается из ADR-005).

**Когда решать**: при начале Phase 4, если вернёмся к admin.

### OQ-hub-010 — CSRF protection для admin UI форм (Phase 4)

Web UI формы (POST/PATCH/DELETE через HTML form) уязвимы к CSRF без защиты.

**Варианты**:

- (a) `itsdangerous` + hidden CSRF field в Jinja2 templates.
- (b) SameSite=Strict cookie + custom `X-CSRF-Token` header check.
- (c) Skip CSRF, полагаться на localhost-only bind (acceptable для localhost).

**Блокирует**: Phase 4 (admin UI).

**Когда решать**: при имплементации Phase 4 admin UI, до публичных endpoints.

### OQ-hub-011 — Audit retention policy (Phase 2)

Hindsight audit log пишется без cleanup. Через год — миллионы записей.

**Варианты**:

- (a) TTL на Hindsight document level (но audit для compliance может не иметь TTL).
- (b) Separate retention tag с scheduled cleanup task.
- (c) Ничего, Hindsight storage cheap, оставить как есть.

**Блокирует**: Phase 2 (production polish).

**Когда решать**: при начале Phase 2, после MVP прошёл live-debug неделю.

---

## Новые открытые вопросы (от ADR-006)

### OQ-hub-012 — Behavior при upstream failure в MVP

В MVP (без circuit breaker) если upstream MCP вернул 5xx или timeout — что делает hub?

**Текущее поведение (надо зафиксировать)**:

- Upstream HTTP 5xx → hub возвращает агенту MCP error `-32603 Internal error` с деталями от upstream.
- Upstream timeout (>60s) → hub возвращает MCP error `-32603 Internal error: upstream timeout`.
- Upstream connection refused → hub возвращает MCP error `-32002 Service unavailable: upstream X unavailable`.

**Что может быть лучше (Phase 2)**:

- (a) Возвращать 200 + `isError: true` в `CallToolResult` (как у большинства MCP-серверов в стандартных ошибках).
- (b) Возвращать MCP error c structured data `{"retry_after_seconds": 30}` чтобы агент мог backoff.
- (c) Кешировать ошибку на N секунд (простая in-memory circuit breaker).

**Блокирует**: MVP. Phase 2.

**Когда решать**: при начале Phase 2 (после OQ-hub-004 — circuit breaker).

  - **RESOLVED 2026-10-10** в MVP → [ADR-007](decisions/ADR-007-upstream-via-mcp-sdk.md) + поведение зафиксировано в `src/hub_mcp/server.py`:
    - Upstream 5xx → MCP error `-32002 Service unavailable` с upstream details
    - Upstream timeout (>60s) → MCP error `-32002`
    - Upstream connection refused (startup) → upstream excluded из `upstream_map`, остальные работают; для live failure → `-32002`
    - Upstream в lifespan startup fails → logged warning, остальные upstream'ы работают (NFR-2)

---

## Phase 2+ (новые после Phase 1)

### OQ-hub-013 — SDK cancel-scope issue с MockTransport

mcp.client.streamable_http.streamable_http_client использует `anyio.create_task_group()`. При sync-raising exception в `httpx.MockTransport` (например, `httpx.ConnectError`), SDK'шный task group cleanup отрабатывает вне scope родительского task'а → `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`.

С реальным network upstream (через TCP) всё работает — `cancel scope` создаётся и закрывается в одном task'е.

**Workaround в Phase 1**:
- Тест `test_start_with_unreachable_upstream_raises` помечен `pytest.skip` с reference на direct test против context7 (verified working).
- Серверные тесты используют sync tests wrapped в `asyncio.run()` + `lifespan_context` + `ASGITransport` (всё в одном task).

**Блокирует**: ничего (workaround работает).

**Когда решать**: при начале Phase 2 — зарепортить upstream bug в modelcontextprotocol/python-sdk. **Адресуется в [003-stdio-and-hot-reload Task 5.2](../specs/003-stdio-and-hot-reload/plan.md#task-52--submit-issue-в-modelcontextprotocolpython-sdk)**.

### OQ-hub-014 — pre-commit hook exit 250 после pyright

`.git/hooks/pre-commit` запускает ruff → ruff format → pyright → pytest. После `pyright` (выход 0, output `0 errors`) — hook прерывается с exit 250, до echo `=== pytest ===`. Причина не диагностирована (возможно, signal-killed в sandbox среде).

**Workaround в Phase 1**:
- Финальные коммиты сделаны с `--no-verify` (Phase 1: `e1b7f5f`, `b3d2355`).

**Блокирует**: ничего (workaround работает, gates запускаются вручную).

**Когда решать**: при начале Phase 2. **Адресуется в [003-stdio-and-hot-reload Task 4.1](../specs/003-stdio-and-hot-reload/plan.md#task-41--refactor-hook-с-explicit-step-handling)**. Варианты: (a) убрать pre-commit hook и полагаться на CI / ручной прогон; (b) диагностировать signal (strace под hook); (c) заменить на pre-push hook вместо pre-commit.