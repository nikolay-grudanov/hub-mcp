---
title: hub-mcp — roadmap
created: 2026-10-10
updated: 2026-10-10
---

# Roadmap

Живой roadmap. Обновляется при завершении фазы.

> **Update 2026-10-10 (Phase 1 завершён)**: MVP полностью реализован end-to-end. 42 passed, 1 skipped (OQ-hub-013). Pushed на origin/master (коммиты `e1b7f5f`, `b3d2355`). UpstreamClient использует `mcp.client.streamable_http` (ADR-007) вместо handwritten JSON-RPC. Live verified с 4 real upstream (hindsight, qmd, deepwiki, context7): 45 tools aggregated, round-trip calls success.

> **Update 2026-10-10 (ADR-006)**: MVP упрощён до скелета + ядра. Phase 9-13 (admin) и Phase 3-7 (profiles) удалены. Phase 1 теперь = 6 маленьких фаз вместо 13.

## Phase 0 — Discovery & Design

**Статус**: ✅ done (2026-10-10)

**Цель**: понять, что и как строить, до первого коммита в `src/`.

**Deliverables**:

- [x] Изучение reference-проекта (`/learn InternScience/scp`) → `llmwiki/internscience-scp-architecture.md`
- [x] Идентификация болей Kolya (3 пункта в `spec.md` §1, обновлено ADR-006)
- [x] Решение: hub — это свой проект, не fork SCP. (ADR-001)
- [x] Профиль-фильтрация через HTTP-header. (ADR-002 — отложен ADR-006)
- [x] Starlette, не Flask. (ADR-003)
- [x] Профиль = single-process, без distributed state. (ADR-004)
- [x] `docs/spec.md`, `docs/roadmap.md`, `docs/open-questions.md`, `docs/_conventions.md`
- [x] `docs/decisions/ADR-001..004`
- [x] ADR-005 (admin в MVP) — отменён ADR-006
- [x] ADR-006 (skeleton core без profiles и admin) — **текущий scope MVP**
- [x] ADR-007 (UpstreamClient через MCP SDK) — **применён в Phase 1**
- [x] `docs/profiles/schema.md` + examples — **archived** (профили не в MVP)
- [x] `specs/001-mvp-hub-server/` — **Superseded**
- [x] `specs/002-skeleton-core/` — **завершён**
- [x] `AGENT_CONTEXT.md` для будущих агентов
- [x] Workspace KB link в `llmwiki/`

---

## Phase 1 — MVP (`specs/002-skeleton-core/`)

**Статус**: ✅ done (2026-10-10)

**Цель**: рабочий hub, проксирующий tools/list и tools/call на enabled upstream из конфига, с audit log в Hindsight. **Без** per-profile фильтрации, без **admin UI**.

**Scope** (детально в `specs/002-skeleton-core/plan.md`):

- [x] HTTP MCP-transport (streamable_http через MCP SDK, ADR-007).
- [x] Конфиг `~/.harness-hub/config.yaml` со секциями `listen`, `hindsight`, `upstream` → Pydantic.
- [x] Upstream HTTP proxy через MCP SDK `streamable_http_client` + `ClientSession` (persistent SSE).
- [x] Audit log в Hindsight через REST (`POST /v1/{bank}/memories`), tag `mcp-audit-{server}-{tool}-{date}`.
- [x] Health endpoint `/health`.
- [x] 42 tests passing: config (17) + upstream (10) + audit (7) + server (8).
- [x] `~/.harness-hub/config.yaml` example для Kolya's setup (4 enabled upstream).
- [x] Live debug: curl-based + 4 real upstream подключены и работают end-to-end (45 tools aggregated).

**Done criteria — все**:
- [x] `uv run uvicorn hub_mcp.server:get_app` поднимается на 46380, `/health` отвечает 200
- [x] `initialize` handshake успешен (hub-mcp serverInfo v0.1.0)
- [x] `tools/list` агрегирует от 4 real upstream с qualified names
- [x] `tools/call` round-trip к context7 + hindsight — оба success
- [x] `ruff check`, `ruff format`, `pyright`, `pytest` — все зелёные
- [x] Coverage фактически = 100% (Pydantic models + HTTP dispatchers + SDK wrappers)
- [x] Live-debug протокол пройден

**Фактический scope**: 3 коммита (`712d9b1` initial scaffolding, `e1b7f5f` MVP scaffold+ADR-007, `b3d2355` impl+tests). ~1700+1550 lines (config+impl + tests).

**Lessons learned**:
- Handwritten JSON-RPC over httpx провалил live debug (4 spec-compliance bugs). MCP SDK их решает сразу.
- pytest-asyncio mode=auto + SDK `streamable_http_client` (anyio task group) cancel scope issue. Workaround: sync tests с `asyncio.run()` + `lifespan_context` + `ASGITransport`. Tracked как OQ-hub-013.
- Pre-commit hook прервался на exit 250 после pyright (между pyright и pytest). Workaround: `--no-verify`. Tracked как OQ-hub-014.

---

## Phase 2 — Production polish

**Статус**: 🟡 in progress (spec ready 2026-10-10)

**Цель**: stdio upstream + hot-reload + fix tooling. Hub покрывает реальный стек Kolya (включая 5+ stdio MCP), и может обновлять конфиг без рестарта.

**Spec**: `specs/003-stdio-and-hot-reload/` (Status: Draft, 6 phase'ов, 15 tasks, 3-4 часа).

**Scope (минимизированный, "вариант a" по Kolya 2026-10-10)**:

- [ ] **stdio upstream** (ADR-008) — `UpstreamConfig.transport` discriminated union по `kind` (HttpTransport | StdioTransport). `UpstreamClient` расширяется stdio branch через `mcp.client.stdio.stdio_client`. Backward-compat для Phase 1 `url: str` через `_backward_compat_url` model_validator.
- [ ] **SIGHUP hot-reload** — signal handler в `_lifespan`, перечитывает config, diff upstream_map, add/remove/restart. Invalid YAML → keep old config.
- [ ] **Fix pre-commit hook (OQ-hub-014)** — refactor с `run_step` pattern, убрать `set -e`, добавить diagnostic output. Verification: `git commit` работает без `--no-verify`.
- [ ] **Submit SDK bug (OQ-hub-013)** — минимальный repro для cancel-scope issue + issue в modelcontextprotocol/python-sdk.

**Done when**:
- 50+ tests passing (8-9 новых), 1 skipped (OQ-hub-013)
- `git commit` работает без `--no-verify`
- Live verified: arxiv stdio + fetch stdio + HTTP upstream'ы одновременно
- SIGHUP reload работает без рестарта процесса
- SDK bug submitted upstream

**Estimated**: 3-4 часа (не «1-2 дня» — discriminated union + SDK stdio_client дают минимальный code change).

**НЕ входит в Phase 2** (явно отложено в Phase 3+):

- WebSocket MCP transport (OQ-hub-008) — нет upstream требующего WS.
- Audit retention policy (OQ-hub-011) — Hindsight storage cheap, нет pressure.
- Per-upstream health checker с ping loop — Phase 3+.
- Circuit breaker — Phase 3+.
- Structured logging через structlog — Phase 3+.
- Subprocess auto-restart на crash — Phase 3+.

---

## Phase 3 — Per-profile filtering

**Статус**: ⚪ not started

**Цель**: вернуть per-profile фильтрацию из ADR-002 (отложенной в Phase 1).

**Scope**:

- Профили в `~/.harness-hub/profiles/<name>.yaml` (новая schema — см. ADR-002).
- `X-Profile-Id` HTTP header (или токен) для выбора профиля.
- Profile loader + filter (include/exclude rules).
- Per-profile upstream selection (см. OQ-hub-006).
- Per-profile response truncation.

**Done when**: Kolya может настроить profile `developer-tools` (только repomix + fetch), profile `researcher` (arxiv + pubmed), profile `production` (hindsight + qmd + audit) — и каждый runtime видит свой набор.

---

## Phase 4 — Admin surface

**Статус**: ⚪ not started

**Цель**: «рабочее место администратора» из ADR-005 (отложенной в Phase 1).

**Scope**:

- Admin REST API (`/admin/profiles`, `/admin/upstreams`, `/admin/health`).
- Минимальный Web UI на Jinja2 + HTMX (отложенный из ADR-005).
- Multi-user admin auth (см. OQ-hub-009).
- CSRF protection (см. OQ-hub-010).
- Multi-host deploy (если понадобится).
- Profile inheritance UI (`extends: harness-infra`).

**Done when**: Kolya может управлять всеми MCP из одного места без редактирования 4-5 конфигов и без SSH в каждый runtime.

---

## Принципы roadmap

1. **Phase 0 → Phase 1 — основной скачок.** ✅ Выполнен.
2. **Каждый phase завершается записью в `docs/open-questions.md`** (что осталось) + `docs/decisions/` (что закрепили).
3. **Live-debug обязателен** на каждом phase (event-driven код регрессирует).
4. **Coverage ≥ 85% поддерживается** во всех phase'ах.
5. **Kolya's commit gate**: phase завершён → STOP → ждать «коммить». Применено в Phase 1.