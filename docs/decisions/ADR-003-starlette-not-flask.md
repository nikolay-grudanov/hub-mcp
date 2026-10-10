# ADR-003 — Starlette + uvicorn, не Flask

**Status**: Accepted
**Date**: 2026-10-10

## Context

SCP `hub_server.py` использует **Flask** + `flask.run()` + `flask[async]`. Нам нужен ASGI-стек для production-ready MCP-сервера. Варианты:

- (a) **Flask** + `flask[async]` (как у SCP).
- (b) **Starlette** + uvicorn.
- (c) **FastAPI** (надстройка над Starlette).
- (d) **aiohttp** (ASGI-альтернатива, но не в тренде).

## Decision

**Starlette + uvicorn.** Без FastAPI (overhead не нужен для MCP).

### Почему не Flask

1. **ASGI vs WSGI**: MCP streamable_http использует SSE (Server-Sent Events) и долгие stream-ответы. Flask — WSGI, требует хаков (`flask[async]`, generator responses) для SSE. Starlette — native ASGI, SSE нативно.
2. **Production deploy**: `flask.run()` — это dev-server. Production требует gunicorn / uWSGI / Waitress. Starlette идёт в комплекте с uvicorn, который production-ready из коробки.
3. **Graceful shutdown**: uvicorn поддерживает SIGTERM → drain in-flight connections → close. Flask dev-server — нет.
4. **Speed**: uvicorn на uvloop быстрее, чем gunicorn + Flask в 3-5x для I/O-bound кода.
5. **MCP Python SDK построен на Starlette** — `mcp.server.fastmcp` использует Starlette внутри. Наш hub гармонично встраивается, не борется с фреймворком.

### Почему не FastAPI

- **FastAPI = Starlette + Pydantic + OpenAPI generator + dependency injection.** Первоначально мы выбрали «без FastAPI» потому, что hub — MCP-сервер (не REST API для людей). **Это решение пересмотрено ADR-005 (2026-10-10)**: admin REST API + Web UI входят в MVP, но всё равно на Starlette + Jinja2 + HTMX, без FastAPI. OpenAPI spec генерируем руками в `docs/admin-api.yaml`. **DI не нужен** (мы передаём зависимости явно через lifespan).
- Меньше зависимостей = меньше attack surface + меньше surface для breaking changes в upstream.

### Почему не aiohttp

- Не тренд в MCP / Python ecosystem. Starlette / FastAPI — стандарт.

## Consequences

**Плюсы**:

- Production-ready из коробки (`uvicorn hub_mcp.server:app`).
- Native SSE support (нужен для streamable_http MCP transport).
- Хорошо сочетается с `mcp.server.fastmcp` (если решим re-use его helper'ы).
- Меньше зависимостей, чем FastAPI.

**Минусы**:

- Надо писать руками request validation (но у нас Pydantic + dependency injection через lifespan — ок).
- ASGI middleware stack отличается от WSGI — нужно предварительно прочитать ASGI primer.

## References

- [Starlette documentation](https://www.starlette.io/)
- MCP Python SDK server: `mcp.server.fastmcp.server.FastMCP` (использует Starlette)
- SCP anti-pattern: `src/scp/hub/hub_server.py:3373` — `app.run(host=0.0.0.0, port=46380)` (Flask dev-server)
- ADR-004 — почему без server-side state (дополняет: Starlette через lifespan context хорошо поддерживает stateless pattern)