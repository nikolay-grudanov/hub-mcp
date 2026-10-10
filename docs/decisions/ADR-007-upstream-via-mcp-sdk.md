# ADR-007 — UpstreamClient поверх mcp.client.streamable_http.streamable_http_client

**Status**: Accepted
**Date**: 2026-10-10
**Supersedes**: MVP-1 `UpstreamClient` (handwritten HTTP+JSON-RPC). Логика полностью заменяется.

## Context

Kolya 2026-10-10 (live debug): 4 из 4 modern remote upstream'ов (`hindsight`, `qmd`, `context7`, `deepwiki`) вернули `-32000 Not Acceptable` или `-32600 Bad Request: Missing session ID` в ответ на первый `tools/list` через MVP. Cause: мой UpstreamClient не реализует MCP spec 2025-06-18 streamable_http транспорт:

1. **Не отправляет `Accept: application/json, text/event-stream`** — обязательно по spec §2.1.2.
2. **Не обрабатывает SSE-streamed responses** — server может вернуть `Content-Type: text/event-stream` с `event: message\ndata: {...}` форматом.
3. **Не поддерживает session management** — после `initialize` server отдаёт `Mcp-Session-Id` header, который нужно передавать во всех subsequent requests (spec §2.2.2). Без него — `-32600 Missing session ID`.
4. **Не отправляет `MCP-Protocol-Version`** header на subsequent requests (spec §2.1.5).

Handwritten request-response подход фундаментально неправилен для streamable_http — это **persistent bidirectional connection** (открыл GET-stream на старте, шлёшь POST для запросов, читаешь responses через stream).

Все 8 unit-тестов `test_upstream.py` проходят потому что `httpx.MockTransport` принимает любые headers и любое тело ответа без валидации. Тесты бесполезны — они не покрывают реальное поведение upstream'а.

## Decision

**UpstreamClient переписывается как тонкая обёртка над `mcp.client.streamable_http.streamable_http_client`** из MCP Python SDK. Используем SDK'шный persistent SSE transport для всей работы с upstream'ом.

### Архитектура

```
Hub (our process)
├── Per enabled upstream: UpstreamClient
│   ├── owns: httpx.AsyncClient (shared per upstream)
│   ├── owns: streamable_http_client transport (per upstream, persistent)
│   │   ├── read_stream: anyio stream of SessionMessage from upstream
│   │   └── write_stream: anyio stream for sending SessionMessage to upstream
│   ├── session_id: str | None (set after initialize, propagated to subsequent calls)
│   └── protocol_version: str (set after initialize)
├── On startup (lifespan): for each enabled upstream:
│   1. open streamable_http_client (GET-stream established)
│   2. send initialize → store session_id, protocol_version, capabilities
│   3. send notifications/initialized
└── On tools/list (asyncio.gather across upstream):
    send tools/list request via write_stream → wait for matching response in read_stream
On tools/call:
    send tools/call via write_stream → wait for matching response in read_stream
On shutdown (lifespan):
    terminate_session (DELETE) → close streams
```

### Key SDK API surface

```python
from mcp.client.streamable_http import streamable_http_client

@asynccontextmanager
async def streamable_http_client(
    url: str, *,
    http_client: httpx.AsyncClient | None = None,
    terminate_on_close: bool = True,
) -> AsyncGenerator[TransportStreams, None]:
    """Yields (read_stream, write_stream)."""

# For sending:
session_message = SessionMessage(
    message=JSONRPCMessage(jsonrpc_request_or_notification_or_response)
)
await write_stream.send(session_message)

# For receiving:
async for message in read_stream:
    if isinstance(message, Exception):
        # transport-level error
    else:
        # message.message.root is JSONRPCRequest | Notification | Response
        if isinstance(message.message.root, JSONRPCResponse):
            response_id = message.message.root.id
            # match with pending request
```

### Конкретные классы

```python
# src/hub_mcp/upstream.py — НОВЫЙ
from mcp import ClientSession, types as mcp_types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.session import RequestResponder

class UpstreamClient:
    """Persistent MCP client to one upstream. Owns its own transport + session."""
    
    def __init__(self, *, name: str, url: str, timeout: float, ...):
        self._name = name
        self._url = url
        self._timeout = timeout
        self._session: ClientSession | None = None
        self._task_group: TaskGroup | None = None
        self._send_stream: MemoryObjectSendStream | None = None
        self._ready: asyncio.Event
        self._lock: asyncio.Lock
    
    async def start(self) -> None:
        """Open transport, send initialize, send notifications/initialized."""
        async with streamable_http_client(self._url, ...) as (read, write):
            self._session = ClientSession(read, write)
            await self._session.initialize()
            await self._session.send_notification(...)
    
    async def stop(self) -> None:
        """Send DELETE, close streams."""
    
    async def list_tools(self) -> list[Tool]:
        """Send tools/list via session, wait for response."""
        result = await self._session.list_tools()
        return result.tools
    
    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Send tools/call via session, wait for response."""
        result = await self._session.call_tool(name, arguments)
        return result.model_dump()
```

### Что НЕ меняется

- Hub это **прокси**, не клиент. Agent → hub → upstream. Hub хранит сессии к upstream'ам, не агент к hub.
- Profile architecture (Phase 3+) — отдельный layer, не задет.
- Config schema, audit log, health endpoint — без изменений.
- Per-profile filtering — отсутствует в MVP (Phase 3+).

### Почему MCP SDK, а не ручной SSE-handling

| Аспект | MCP SDK | Ручная |
|---|---|---|
| Session lifecycle | ✅ встроен (initialize → initialized notification → terminate) | ❌ писать самому (~100 LOC) |
| Accept header | ✅ автоматически | ❌ легко забыть |
| SSE stream parsing | ✅ anyio + httpx + event-stream | ❌ писать руками, edge cases (keep-alive, multi-line data) |
| Mcp-Session-Id propagation | ✅ встроен | ❌ ручное управление state'ом |
| Protocol-Version header | ✅ через ClientSession | ❌ ручное |
| Backwards compat (HTTP+SSE старый) | ✅ SDK поддерживает оба | ❌ если нужна совместимость |
| Кода у нас | ~80 LOC (тонкая обёртка) | ~300+ LOC (reimplement) |

## Consequences

**Плюсы**:

- **MVP работает с реальными upstream'ами** (включая context7, deepwiki, Hindsight).
- **Spec-compliance** гарантирована upstream, без возможности забыть header.
- **Persistent connection** — только один TCP handshake на upstream за всю сессию hub'а, не на каждый tool call.
- **Session affinity** — `Mcp-Session-Id` хранится один раз на startup.

**Минусы**:

- **Зависимость на MCP SDK API surface** — если SDK breaking change в streamable_http_client, наш код требует обновления. SDK 1.x → 2.x breaking changes возможны.
- **Persistent state** — каждый upstream = long-lived connection. Упавший upstream требует reconnect (Phase 2 — circuit breaker).
- **Тесты сложнее** — нужен mock, проверяющий Accept header и SSE response format. Без этого тесты снова будут бесполезны.

### Делаем тесты настоящими

Все тесты `UpstreamClient` будут:
- Проверять что `Accept` header отправляется.
- Проверять `Mcp-Session-Id` header на subsequent requests.
- Проверять SSE response parsing (mock returns `text/event-stream`).
- Проверять `MCP-Protocol-Version` header.

Если mock не проверяет — тест бесполезен, как сейчас.

### Альтернатива для тестов — реальный upstream

Добавляем **integration test** против публичного context7 (`https://mcp.context7.com/mcp`):
- Skipped by default (requires network).
- Marked `pytest.mark.integration`.
- Можно прогнать локально: `uv run pytest -m integration`.

Это **golden test** — единственный способ гарантировать что мы реально spec-compliant.

## Alternatives considered

**B. Handwritten SSE consumer с anyio** — больше кода, выше риск регрессии, нет advantage'а.

**C. Откатить MVP к stateless Accept: application/json** — не работает с modern remote MCP (context7, deepwiki требуют SSE). MVP бесполезен для главных upstream'ов Kolya's setup.

**D. Fork MCP SDK** — антипаттерн ADR-001 (не форкаем upstream).

## References

- MCP spec 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports (см. §2.1.2 Accept header, §2.1.5 Protocol Version, §2.2 Session Management).
- MCP Python SDK source: `mcp.client.streamable_http.streamable_http_client`, `mcp.ClientSession`.
- Live debug log 2026-10-10 (4 upstream'ов failed в первом request).
- ADR-006 — упрощённый MVP scope (skeleton + core, без admin UI).
- OQ-hub-008 — WebSocket transport (Phase 2).
- OQ-hub-012 — Behavior при upstream failure (resolved: fail-fast, лучшее в Phase 2).