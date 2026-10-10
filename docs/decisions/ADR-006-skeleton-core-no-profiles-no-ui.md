# ADR-006 — MVP упрощается до скелета + ядра: убираем profiles и admin UI

**Status**: Accepted
**Date**: 2026-10-10
**Supersedes**:
- ADR-002 (X-Profile-Id header) — откладывается в Phase 3+.
- ADR-005 (admin REST API + Web UI в MVP) — откладывается в Phase 4+.

## Context

Kolya 2026-10-10 (в чате, не на ПК):

> «Согласен, не меняем стек. Давай тогда напиши спеку для создания скелета и первого mvp пока без ui, будем через конфиг или как-то по другому добавлять доступные mcp инструменты в hub. Профили тоже уберем из списка работ. Нам надо создать хорошее ядро»

Текущее состояние (Phase 1 на паузе, Phase 0 завершён):

- ADR-002: profile-id через HTTP-header `X-Profile-Id` — Phase 1.
- ADR-005: admin REST API + Web UI в MVP — Phase 1.
- Spec-001: per-profile фильтрация + admin + UI = 13 phase'ов, ~30 bite-sized tasks.
- Roadmap: Phase 1 = 6-8 дней.

Проблема: scope распух. Мы пилим ядро, не доказав что ядро работает. Per-profile фильтрация — это уже production-grade логика, требует solid testing, schema versioning, edge cases (что если profile ссылается на несуществующий upstream, что если upstream вернул 500, что если два profile имеют одинаковое имя и т.д.). Admin UI — это полноценный фронтенд-проект с CSRF, templates, auth.

Если сначала не сделать ядро хорошо, мы не сможем валидировать базовые assumptions: держит ли протокол MCP нашу модель маршрутизации, живёт ли Hindsight audit под нагрузкой, не течёт ли память в httpx connection pool, корректно ли мы проксируем SSE streamable_http.

## Decision

**MVP (Phase 1) = скелет + ядро без профилей и без admin UI.**

### Что входит в MVP

- ASGI-приложение на Starlette + uvicorn.
- Один MCP-transport: streamable_http на `:46380/mcp`.
- **Жёстко зашитый список upstream** через единый конфиг-файл `~/.harness-hub/config.yaml` (НЕ отдельный `upstream.yaml` — единый конфиг для всего hub).
- На каждый upstream — настройка `enabled: true/false`. Hub'у видны **только enabled upstream** (`admin` секции нет, но флаг `enabled` есть).
- **Нет фильтрации**: hub проксирует `tools/list` как **union всех tools со всех enabled upstream**, с namespace `<server>.<tool>`. Агент видит всё.
- `tools/call` маршрутизирует по `<server>.<tool>` к соответствующему upstream.
- Audit log в Hindsight под тегом `mcp-audit-{server}-{tool}-{YYYY-MM-DD}` (без профиля — profile нет).
- Health endpoint `/health` (200 ok).
- Конфиг-формат — единый YAML с секциями `upstream:`, `hindsight:`, `listen:`. Перезагрузка через SIGHUP (Phase 2).
- Тесты: protocol roundtrip, upstream mock, audit write, health.
- Live debug с реальным MCP Inspector.

### Что НЕ входит в MVP (откладывается)

| Фича | ADR | Новый phase |
|---|---|---|
| Per-profile фильтрация через `X-Profile-Id` | ADR-002 | Phase 3 |
| Profile YAML schema + loader | ADR-005 (частично) | Phase 3 |
| `include` / `exclude` filter | ADR-005 (частично) | Phase 3 |
| Admin REST API | ADR-005 | Phase 4 |
| Admin Web UI (HTMX + Jinja2) | ADR-005 | Phase 4 |
| CSRF protection | ADR-005 / OQ-hub-010 | Phase 4 |
| Admin auth (X-Admin-Token) | ADR-005 | Phase 4 |
| Per-upstream health checker с ping loop | ADR-005 | Phase 2 |

### Конфиг-формат (MVP)

Один файл `~/.harness-hub/config.yaml`:

```yaml
# Listen address
listen:
  host: 127.0.0.1
  port: 46380

# Hindsight audit endpoint
hindsight:
  url: http://127.0.0.1:8888/v1
  bank_id: default
  enabled: true

# Upstream MCP servers (HTTP transport only in MVP)
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
    # stdio upstream — пока NOT supported (см. OQ-hub-001, Phase 2)
    enabled: false
```

Поле `enabled: false` = upstream зарегистрирован, но не опрашивается. Позволяет временно отключать сервер без правки конфига (через `POST /admin/upstreams/{name}/toggle` — Phase 4).

### Архитектурный эффект

- **Меньше Pydantic моделей** в MVP. `Upstream` (Pydantic модель), `HindsightConfig`, `ListenConfig` — это всё. Нет `Profile`, `IncludeRule`, `ExcludeRule`, `Limits`, `Policy`.
- **Нет filter.py** в MVP. Phase 3 добавит.
- **Нет admin.py / admin_auth.py / csrf.py / templates/** в MVP.
- **Нет upstream_health.py** в MVP. Phase 2 добавит.
- **Тесты проще**: нет profile edge cases, нет admin auth, нет CSRF.

### Phase 1 (новый MVP): scope

- Phase 1: Project Bootstrap (Task 1.1 — pyproject, src layout, exceptions).
- Phase 2: Config schema + loader (Pydantic для конфига).
- Phase 3: Upstream HTTP client (httpx-based, JSON-RPC proxy).
- Phase 4: Audit log в Hindsight (best-effort writer).
- Phase 5: Starlette ASGI server (`/health` + `/mcp` JSON-RPC dispatcher).
- Phase 6: Deploy + Live debug с MCP Inspector.

**6 phase'ов вместо 13**. **~15 bite-sized tasks вместо ~30**. **Estimated: 3-4 дня вместо 6-8**.

## Consequences

**Плюсы**:

- **Фокус на качестве ядра**: protocol correctness, connection management, error handling, SSE proxying.
- **Быстрый feedback loop**: за 3-4 дня — рабочий hub с 5 upstream'ами, без профилей. Доказываем концепцию.
- **Меньше moving parts**: 5 модулей в `src/hub_mcp/` вместо 13. Меньше мест, где может быть баг.
- **Лучше live debug**: без профилей и admin — debugging только protocol layer. Легче понять, что работает, что нет.
- **Можно отказаться позже**: если per-profile фильтрация не нужна, мы сэкономили 2-3 недели. Если нужна — добавляем как Phase 3.

**Минусы**:

- **Per-profile фильтрация отложена**: Kolya хотел «разные tools для разных runtime». Это всё ещё нужно, но позже. На MVP-этапе все runtime видят все tools.
- **Admin откладывается**: «рабочее место администратора» (Kolya's запрос) — Phase 4. Колya пока редактирует YAML руками и `kill -HUP`.
- **Audit log менее полезный без profile-id**: тег `mcp-audit-{server}-{tool}-{date}` вместо `mcp-audit-{profile}-{date}`. Меньше аналитики по runtime (но `server` уже даёт достаточно контекста для MVP).
- **SIGHUP reload ещё не реализован**: на MVP нужно `kill <pid>; uv run uvicorn ...` для reload. Phase 2.

### Что НЕ теряем

- ADR-001 (не fork протокола) — сохранён.
- ADR-003 (Starlette, не Flask, не FastAPI) — сохранён, Kolya явно подтвердил «не меняем стек» в чате 2026-10-10.
- ADR-004 (без server-side state между запросами) — сохранён, даже упрощается (нет profile cache).
- Live debug протокол из `AGENT_CONTEXT.md` п.2 — сохранён, теперь чётче: только протокол-уровень.

### Что де-факто отменяется

- ADR-002 (X-Profile-Id) — откладывается. Header больше не читается в MVP. Если Phase 3 его восстановит — вернёмся, иначе ADR останется «отложен, не реализован».
- ADR-005 (admin REST + UI) — откладывается. Web UI не делаем. Если Phase 4 вернётся к этому — будет новый ADR (вероятно ADR-007 «admin поверх post-MVP hub»).

## Alternatives considered

**Делать всё сразу (per-profile + admin + UI)** — отвергнуто Kolya 2026-10-10 («нам надо создать хорошее ядро»).

**Делать только skeleton без upstream проксирования** (только health endpoint) — отвергнуто. Не имеет ценности, нельзя live-debug'ить с MCP Inspector.

**Делать скелет + admin, без профилей** — отвергнуто. Admin без per-profile filtering = управление списком из YAML, который без профилей бесполезен. Admin имеет смысл только вместе с профилями.

**Делать скелет + profile filtering + audit, без admin** — рассмотрено как альтернатива, но profile filtering — это тоже production-grade логика, Kolya явно сказал «уберём профили из списка работ».

## References

- ADR-001 (не fork протокола) — сохранён.
- ADR-003 (Starlette) — сохранён.
- ADR-004 (без server-side state) — сохранён, упрощается.
- ADR-002 (X-Profile-Id) — отложен этим ADR.
- ADR-005 (admin + UI) — отложен этим ADR.
- `specs/002-skeleton-core/` — новая спека.
- `docs/roadmap.md` — обновлён этим ADR.
- `docs/open-questions.md` — OQ-hub-005, 009, 010, 011 откладываются.
- `llmwiki/hub-mcp-project.md` — обновлён этим ADR.

## Новые Open Questions (не блокируют MVP)

(Все из ADR-002/005 откладываются в Phase 3+; перечислены здесь для трекинга.)

- OQ-hub-001 — stdio upstream (Phase 2, не блокирует MVP)
- OQ-hub-002 — token-based profile auth (Phase 3+, не блокирует MVP)
- OQ-hub-005 — admin Web UI (Phase 4, отложен ADR-006)
- OQ-hub-006 — per-profile upstream (Phase 3+, не блокирует MVP)
- OQ-hub-007 — hot-reload behavior (Phase 2, после MVP)
- OQ-hub-008 — WebSocket transport (Phase 2, не блокирует MVP)
- OQ-hub-009 — admin auth multi-host (Phase 4, отложен ADR-006)
- OQ-hub-010 — CSRF (Phase 4, отложен ADR-006)
- OQ-hub-011 — audit retention (Phase 2, не блокирует MVP)