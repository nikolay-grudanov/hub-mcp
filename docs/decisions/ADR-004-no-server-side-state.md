# ADR-004 — Hub работает без server-side state между запросами

**Status**: Accepted
**Date**: 2026-10-10

## Context

Hub должен обрабатывать MCP-запросы от множества runtime одновременно. Какие state нужны:

- **Per-session state**: результат `initialize` handshake (capabilities, server info). Активен, пока MCP-клиент держит соединение.
- **Per-request state**: profile YAML, загруженный при `initialize`. Может быть кеширован на время жизни сессии.
- **Upstream state**: connections к upstream MCP-серверам. Лучше переиспользовать через httpx connection pool.

SCP `hub_server.py` хранит **глобальный** state через module-level dict'ы: `servers: Dict[str, Server]`, `health_cache: Dict[str, tuple[datetime, bool]]`. Это создаёт проблемы:

1. **Multi-process deploy**: каждый worker имеет свой `servers` dict — рассинхрон.
2. **Тестируемость**: нельзя поднять hub in-process без загрязнения глобального state.
3. **`init_app()` на module import**: `hub_server.py:3371` вызывает `init_app()` при import → стартует daemon thread, регистрирует permission server. В multi-worker стартует N permission-серверов.

## Decision

**Hub = single-process, stateless между запросами**. Конкретно:

1. **Profiles хранятся на диске** (`~/.harness-hub/profiles/*.yaml`). Hub читает их **на каждый запрос** (или кеширует на короткий TTL, см. OQ-hub-007).
2. **Upstream list хранится на диске** (`~/.harness-hub/upstream.yaml`). То же.
3. **Audit log пишется в Hindsight** (внешний state, не in-process).
4. **In-process state** только в lifespan context Starlette:
   - httpx.AsyncClient с connection pool к upstream'ам.
   - Profile cache (TTL 60s).
   - Audit Hindsight client.

5. **Нет module-level globals для mutable state.** Константы — ок (default ports, profile dir path).

### Почему не in-memory state через Redis

- **YAGNI**: для MVP у нас 1 процесс на 1 хосте. Redis — лишняя зависимость, лишний сервис для мониторинга.
- **Phase 4 multi-host** — тогда и подумаем. Пока что `upstream.yaml` на каждом хосте + sync через git или Ansible — проще, чем Redis.

### Почему не `init_app()` на module import

- **Тестируемость**: импорт hub-модуля не должен иметь side effects (start thread, register server). Тесты импортируют модуль десятки раз.
- **Multi-worker safety**: gunicorn / uvicorn workers — каждый импортирует модуль заново. Если import = side effect, все workers стартуют лишнее.
- **Lifecycle control**: явный `lifespan` context manager Starlette — правильное место для startup/shutdown hooks. Там и httpx client, и profile cache.

## Consequences

**Плюсы**:

- Hub поднимается, обрабатывает запросы, падает — без побочных эффектов на filesystem / network.
- Тесты изолированы: каждый тест создаёт свой hub instance, не загрязняет глобальный state.
- Multi-worker deploy без сюрпризов: uvicorn `--workers 4` → каждый worker имеет свой lifespan context.
- Легко сделать `hub-mcp serve --reload` для dev: Starlette reload через uvicorn работает без проблем.

**Минусы**:

- Profile YAML парсится на каждый запрос (или из кеша с TTL). Для 1 профиля на 1 хосте это не проблема. Если профилей станет 50+ — добавим кеширование с inotify invalidation (Phase 2).
- Audit log пишется в Hindsight — если Hindsight лежит, audit теряется. Допустимо для MVP (audit — observability, не критичный path).

## Alternatives considered

**Redis backing для upstream state** (active servers, health). Слишком рано — MVP работает с in-memory lifespan state, который переживает рестарт процесса через файл `upstream.yaml`.

**Postgres backing**. Overkill для MVP. Phase 4 если multi-host.

**Module-level globals с lock**. Воспроизводит SCP проблемы (anti-pattern `init_app()` на import, рассинхрон в multi-worker).

## References

- SCP anti-pattern: `src/scp/hub/hub_server.py:2824` (`servers: Dict[str, Server]` module-level).
- SCP anti-pattern: `src/scp/hub/hub_server.py:3371` (`init_app()` at module load).
- Starlette lifespan: `https://www.starlette.io/lifespan/`
- Kolya's commit gate preference (`writing-plans/SKILL.md` Kolya's Workflow Preferences).
- ADR-003 — Starlette + uvicorn (lifespan context — стандартное место для startup/shutdown).