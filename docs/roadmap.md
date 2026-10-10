---
title: hub-mcp — roadmap
created: 2026-10-10
updated: 2026-10-10
---

# Roadmap

Живой roadmap. Обновляется при завершении фазы.

> **Update 2026-10-10 (ADR-006)**: MVP упрощён до скелета + ядра. Phase 9-13 (admin) и Phase 3-7 (profiles) удалены. Phase 1 теперь = 6 маленьких фаз вместо 13.

## Phase 0 — Discovery & Design

**Статус**: 🟡 in progress (2026-10-10)

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
- [x] `docs/profiles/schema.md` + examples — **archived** (профили не в MVP)
- [x] `specs/001-mvp-hub-server/` — **Superseded**
- [x] `specs/002-skeleton-core/` — **активная спека**
- [x] `AGENT_CONTEXT.md` для будущих агентов
- [x] Workspace KB link в `llmwiki/`

**Следующий шаг**: показать Kolya, дождаться «коммить», перейти к Phase 1.

---

## Phase 1 — MVP (`specs/002-skeleton-core/`)

**Статус**: ⚪ not started

**Цель**: рабочий hub, проксирующий tools/list и tools/call на enabled upstream из конфига, с audit log в Hindsight. **Без** per-profile фильтрации, без **admin UI**.

**Scope** (детально в `specs/002-skeleton-core/plan.md`):

- HTTP MCP-transport (streamable_http через MCP SDK).
- Конфиг `~/.harness-hub/config.yaml` со секциями `listen`, `hindsight`, `upstream` → Pydantic.
- Upstream HTTP proxy через httpx (только HTTP, не stdio).
- Audit log в Hindsight через REST (`POST /v1/{bank}/memories`), tag `mcp-audit-{server}-{tool}-{date}`.
- Health endpoint `/health`.
- Тесты: config loader, upstream mock, audit mock, MCP roundtrip, health.
- `~/.harness-hub/config.yaml` example для Kolya's setup (5 upstream'ов из harness config).
- Live debug с MCP Inspector + 1+ реальный upstream.

**Done when**: все 4 pre-commit checks зелёные, coverage ≥ 85%, live-debug с реальным upstream и Inspector.

**Estimated**: 3-4 дня (1 разработчик + 1 ревью). В 2 раза меньше, чем было до ADR-006.

---

## Phase 2 — Production polish

**Статус**: ⚪ not started

**Цель**: устранить оставшиеся rough edges после MVP живёт неделю в production без ручного перезапуска.

**Scope**:

- stdio upstream (через `asyncio.create_subprocess_exec` + lifecycle).
- Hot-reload конфига через SIGHUP (file watcher + graceful reload).
- Per-upstream health checker с background ping loop (rolling window).
- Structured logging через `structlog` (JSON output).
- Graceful shutdown (SIGTERM → drain in-flight calls → close upstream).
- WebSocket MCP transport (см. OQ-hub-008).
- Audit retention policy (см. OQ-hub-011).
- Circuit breaker на upstream (3 failed calls → 60s cooldown → retry) — отложено из старого Phase 2.

**Done when**: hub работает 24/7 в течение недели без ручного перезапуска.

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

1. **Phase 0 → Phase 1 — основной скачок.** Дальше — incremental improvements на основе реального использования.
2. **Каждый phase завершается записью в `docs/open-questions.md`** (что осталось) + `docs/decisions/` (что закрепили).
3. **Live-debug обязателен** на каждом phase (event-driven код регрессирует).
4. **Coverage ≥ 85% поддерживается** во всех phase'ах.
5. **Kolya's commit gate**: phase завершён → STOP → ждать «коммить».