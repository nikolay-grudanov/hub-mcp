# ADR-005 — Admin REST API + Web UI входят в MVP (Phase 1)

**Status**: Superseded (by ADR-006, 2026-10-10)
**Date**: 2026-10-10
**Superseded by**: [ADR-006](ADR-006-skeleton-core-no-profiles-no-ui.md) — admin REST API и Web UI отложены в Phase 4+, MVP работает без admin-поверхности.

> **Внимание**: ADR-005 остаётся как записанное намерение Kolya («рабочее место администратора»), но **не реализуется в MVP**. Решение Kolya 2026-10-10: «нам надо создать хорошее ядро». Admin вернётся в Phase 4, когда ядро hub'а проверено live-debug'ом и живёт в production неделю без перезапуска.

Ниже — оригинальный текст ADR-005 для исторической трассировки. Решение отменено ADR-006.
**Supersedes**: частично ADR-003 (пункт «Почему не FastAPI» — отменяется в части «OpenAPI generator не нужен»).

## Context

Kolya 2026-10-10 (в чате, не на ПК): «нам нужна будет админка чтоб человек мог создавать эти профили, добавлять или удалять mcp, смотреть состояние mcp чтоб понять кто упал а кто работает. Полноценное рабочее место администратора по настройке harness».

Текущие решения:

- **ADR-003** (Starlette, не FastAPI): «OpenAPI generator не нужен (hub — MCP-сервер, не REST API для людей)».
- **docs/spec.md §9**: «OQ-hub-005 — web UI для редактирования профилей (Phase 4)».
- **docs/roadmap.md Phase 4**: «Web UI (FastAPI + HTMX single-page app на отдельном порту 46381)» + «`/admin` endpoint для listing health всех upstream».
- **docs/open-questions.md OQ-hub-005**: «Phase 4. Для MVP ручной YAML + reload».

Все 4 должны быть пересмотрены, потому что admin surface — это **полноценное рабочее место администратора**, а не отложенная фича.

## Decision

**Admin REST API + минимальный Web UI входят в MVP (Phase 1).** Конкретно:

### Admin REST API endpoints

Все на отдельном listen-порту или path-prefix, чтобы не путать с MCP-transport (`:46380/mcp`):

- `GET    /admin/profiles` — список всех профилей с description, tools count, last-modified.
- `GET    /admin/profiles/{name}` — содержимое profile (YAML или JSON).
- `POST   /admin/profiles/{name}` — создать / перезаписать профиль. Body = YAML. Validation через Pydantic.
- `PATCH  /admin/profiles/{name}` — частичное обновление (merge в существующий profile).
- `DELETE /admin/profiles/{name}` — удалить профиль (с защитой: нельзя удалить последний / зарезервированный).
- `GET    /admin/upstreams` — список всех upstream с health-статусом (last_check, success_rate за последний час).
- `POST   /admin/upstreams` — добавить новый upstream (server name + URL).
- `DELETE /admin/upstreams/{server}` — удалить upstream (с защитой: если есть profiles, ссылающиеся на этот upstream — 409).
- `GET    /admin/tools?profile=X` — список tools, которые видит профиль (debug endpoint).
- `GET    /admin/audit?profile=X&date=YYYY-MM-DD` — последние 100 audit-записей (читает из Hindsight).
- `GET    /admin/health` — hub-level health (uptime, версия, кол-во active sessions).

### Web UI (минимальный, single-page)

**Стек**: HTMX + Jinja2 templates + небольшой CSS. **Не React, не Vue, не SPA-фреймворк.**

- Single-page на `/admin/ui/` (или `/admin/`, отдаёт HTML).
- HTMX для интерактива без JS bundle — каждый клик = HTML-запрос, сервер возвращает fragment.
- Jinja2 templates в `src/hub_mcp/templates/`.
- Static CSS в `src/hub_mcp/static/` (минимальный, можно взять Pico CSS 10KB single-file).

**Страницы**:

1. **Dashboard** (`/admin/`) — hub health, список upstream с цветным health-индикатором (🟢 ok / 🟡 degraded / 🔴 down), последние 20 audit events.
2. **Profiles list** (`/admin/profiles`) — список профилей + кнопка «New profile» → форма.
3. **Profile edit** (`/admin/profiles/{name}`) — форма с полями YAML / textarea + preview "as JSON" + save.
4. **Upstreams list** (`/admin/upstreams`) — список + форма добавления + health-check button per upstream.

### Авторизация admin API

**MVP localhost-only**. Auth через:

- `X-Admin-Token: <token>` header, где token = `harness-hub` сгенерированный random при первом запуске и записанный в `~/.harness-hub/admin-token` (chmod 600).
- Или слушать admin endpoints **только на 127.0.0.1**, отдельным ASGI-роутом (binding `admin_host = 127.0.0.1`, `admin_port = 46381`).

Multi-user admin auth — Phase 2.

### Технологический shift

- **Был**: Starlette-only, без OpenAPI.
- **Стал**: Starlette + **Jinja2** (templates) + **HTMX** (1 файл, 14KB) + **Pydantic** для request/response models. **Без FastAPI** (DI не нужен, ручные handlers проще).

OpenAPI spec генерируем **руками** в виде YAML-файла в `docs/admin-api.yaml`, не автоматически. Документация отдельно от runtime.

### Что остаётся вне MVP

- Multi-user auth (OQ-hub-009 ниже).
- Profile inheritance UI (`extends:` поле — пока через YAML).
- Audit retention / cleanup policies.
- WebSocket для live-updating dashboard.

### Изменения в Phase boundaries

| Что | Было | Стало |
|---|---|---|
| Admin REST API | Phase 4 | **Phase 1** |
| Web UI | Phase 4 | **Phase 1 (минимальный)** |
| `/admin/health` per-upstream listing | Phase 4 | **Phase 1** |
| Multi-user auth для admin | Phase 4 | Phase 2 |
| Profile inheritance UI | Phase 2 | Phase 2 (без изменений) |

## Consequences

**Плюсы**:

- **Kolya может администрировать hub без редактирования YAML руками** — это было ключевое требование, и оно в MVP.
- **Visibility «кто упал»** — health-check listing через `/admin/upstreams` сразу даёт операционную картину.
- **Меньше Phase 1 → меньше Phase 4**: Phase 4 теперь только про multi-host / profile inheritance UI / advanced features. Больше scope в Phase 1 = быстрее получим ценный инструмент.
- **Jinja2 + HTMX** — small surface, легко тестировать (Starlette TestClient + Jinja2 loader), не нужен JS-build pipeline.

**Минусы**:

- **Phase 1 становится больше**: добавляется ~5 новых endpoint'ов + 4 страницы UI. Трудоёмкость MVP растёт с 4-5 дней до 6-8 дней.
- **Дополнительные зависимости**: `jinja2`, `httpx` (уже есть), `python-multipart` (для form encoding), возможно `itsdangerous` для CSRF-токенов.
- **CSRF protection**: формы в Web UI требуют CSRF-токенов. Starlette не даёт из коробки — нужно либо itsdangerous, либо SameSite cookie + custom header.
- **UI tests**: нужно тестировать HTML rendering, не только API. Дополнительный test surface.

### Не сломает ли это другие решения

- **ADR-001** (не fork протокола): REST API для admin — это не MCP, не конфликтует. Hub по-прежнему стандартный MCP-сервер с точки зрения MCP-клиентов.
- **ADR-002** (`X-Profile-Id` header): admin API использует другой механизм (`X-Admin-Token` или localhost-bind). Не конфликтует.
- **ADR-003** (Starlette, не Flask): **сохраняется**. Starlette + Jinja2 templates отлично работает. Меняется только обоснование «не нужен FastAPI» — оно было про OpenAPI generator, и мы заменяем автогенерацию на ручной `docs/admin-api.yaml`.
- **ADR-004** (без server-side state): admin API мутирует state (CRUD на YAML-файлах). Это **write** операции, не in-process state. Не конфликтует — state по-прежнему на диске, in-process только httpx clients в lifespan.

## Alternatives considered

**Phase 4 как было (отдельный FastAPI + HTMX)**. Минус: Kolya ждёт 4 фаз до admin-инструмента, на практике может не дойти до Phase 4 или admin окажется нужен раньше.

**CLI вместо Web UI** (`hub-mcp profile create <name>`). Минус: Kolya явно сказал «рабочее место администратора», что подразумевает UI. CLI можно добавить потом как alias для тех же REST endpoints.

**Только REST API, без Web UI** (UI = отдельный React SPA). Минус: ещё одна зависимость (npm toolchain, build step, deploy pipeline). HTMX даёт 90% ценности за 10% стоимости.

**Только Web UI, без REST API** (UI = server-rendered формы сразу мутируют файлы). Минус: нельзя автоматизировать (curl, scripts). REST + UI — стандарт для admin-инструментов.

**Web UI на FastAPI, не Starlette + Jinja2**. Минус: FastAPI добавляет DI и OpenAPI generator, которые для нашего admin UI не нужны. Starlette + Jinja2 = проще, меньше зависимостей.

## New Open Questions (создаются этим ADR)

### OQ-hub-009 — Admin auth на multi-host

Сейчас (MVP, localhost): admin token в `~/.harness-hub/admin-token` (chmod 600). На multi-host (Phase 4) нужно что-то серьёзнее.

**Когда решать**: при начале Phase 4.

### OQ-hub-010 — CSRF protection для Web UI форм

Без CSRF admin UI уязвим к cross-site form submission.

**Варианты**: (a) `itsdangerous` + hidden field в Jinja2 templates. (b) SameSite=Strict cookie + custom header check. (c) Skip CSRF, полагаться на localhost-only bind.

**Когда решать**: при имплементации Phase 1 admin UI.

### OQ-hub-011 — Audit retention policy

Сейчас Hindsight audit log пишется без cleanup. Через год — миллионы записей, замедление query.

**Когда решать**: при начале Phase 2 (когда появится хоть какая-то телеметрия по объёму).

## References

- ADR-003 (Starlette, не Flask) — обоснование stack сохраняется, но OpenAPI-пункт отменяется этим ADR.
- ADR-004 (без server-side state) — admin API мутирует файлы на диске, не in-process state.
- [HTMX documentation](https://htmx.org/) — single-page без JS bundle.
- [Jinja2 templates](https://jinja.palletsprojects.com/) — server-side rendering для Starlette.
- SCP anti-pattern: `src/scp/hub/hub_server.py` НЕ имеет admin UI — это gap в их дизайне.