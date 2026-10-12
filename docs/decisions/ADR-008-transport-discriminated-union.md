# ADR-008 — UpstreamConfig.transport discriminated union (HTTP | stdio)

**Date**: 2026-10-10
**Status**: Accepted
**Supersedes**: implicit decision in ADR-007 (UpstreamClient assumed HTTP-only)

## Context

Phase 1 (MVP) завершён — `UpstreamClient` обёрнут вокруг `mcp.client.streamable_http.streamable_http_client`. `UpstreamConfig` имеет `url: str` как единственный способ подключения.

Phase 2 добавляет stdio upstream (recon в `/home/gna/.hermes/profiles/harness/cache/scratch/stdio-upstream-recon-2026-10-10.md`). Реальный стек Kolya (`~/.hermes/profiles/harness/config.yaml`) использует stdio для arxiv-mcp (`uv tool run`), mcp-fetch-server (`npx`), ctx7sk, repomix-mcp, mcp-searxng. Без stdio hub-mcp покрывает только 4 HTTP upstream'а из ~10 — rollout в Hermes config блокирован.

### Архитектурные варианты

#### A. `UpstreamClient` параметризуется транспортом (рекомендуем)

`UpstreamConfig.transport` — Pydantic discriminated union по полю `kind`:
- `kind: "http"` → `HttpTransport` (url)
- `kind: "stdio"` → `StdioTransport` (command, args, env, cwd, encoding)

`UpstreamClient.start()` разветвляется по `transport.kind`:
- HTTP: `streamable_http_client(url=...)` (Phase 1 logic)
- stdio: `stdio_client(StdioServerParameters(...))` (Phase 2 new)

`list_tools()`, `call_tool()`, `stop()` — общая логика, transport-agnostic.

**Pros**: единый API, один набор тестов, upstream_map в server.py не меняется.
**Cons**: discriminated union в Pydantic — небольшой learning curve.

#### B. Отдельный `StdioUpstreamClient`

Полностью независимый класс, дублирующий ~80% `UpstreamClient`.

**Pros**: чистое разделение ответственности, легче понять в изоляции.
**Cons**: code duplication, два набора тестов, два интерфейса в server.py.

#### C. `mcp-proxy` как sidecar HTTP-adapter

Hub spawns `mcp-proxy --stdio <cmd> --listen :PORT` per upstream, коннектится к localhost:PORT как HTTP. `mcp-proxy` уже существует (sparfenyuk/mcp-proxy на GitHub).

**Pros**: zero Python subprocess code, hub использует только HTTP upstream.
**Cons**: +1 process per upstream (5 stdio → 5 extra subprocesses), нет fine-grained control над subprocess lifecycle, не подходит для hub-as-process (hub должен знать когда upstream упал чтобы log + restart).

### Backward compatibility

Phase 1 `~/.harness-hub/config.yaml` имеет:
```yaml
upstream:
  - name: hindsight
    url: http://127.0.0.1:8888/mcp/harness/
    enabled: true
```

Этот формат **должен продолжать работать** без edit'а конфига при upgrade'е до Phase 2. Решение: `@model_validator(mode="before")` на `UpstreamConfig` auto-maps `url: str` → `transport: {kind: "http", url: url}`. В Phase 3+ — deprecation warning в логах, в Phase 4+ — полное удаление shortcut'а.

## Decision

Принят **Вариант A: discriminated union в `UpstreamConfig.transport`**.

Реализация:
1. `src/hub_mcp/config.py`:
   - `HttpTransport(BaseModel)` с `kind: Literal["http"] = "http"` + `url: str`
   - `StdioTransport(BaseModel)` с `kind: Literal["stdio"] = "stdio"` + command/args/env/cwd/encoding
   - `TransportConfig = Annotated[HttpTransport | StdioTransport, Field(discriminator="kind")]`
   - `UpstreamConfig.transport: TransportConfig` (replaces `url: str`)
   - `@model_validator(mode="before") _backward_compat_url`: если нет `transport` но есть `url` → wrap в `HttpTransport`
2. `src/hub_mcp/upstream.py`:
   - `__init__` принимает `transport: TransportConfig` вместо `url: str, transport=...`
   - `start()`: `if transport.kind == "http":` → `streamable_http_client(url=transport.url)`, `else: stdio_client(StdioServerParameters(command=transport.command, args=transport.args, env=transport.env, cwd=transport.cwd, encoding=transport.encoding, encoding_error_handler=transport.encoding_error_handler))`
   - Остальные методы (`stop()`, `list_tools()`, `call_tool()`) — общая логика
3. `tests/test_config.py` + `tests/test_upstream.py` — обновить существующие 42 теста + добавить 8-9 новых

## Consequences

### Positive

- **Один интерфейс, два транспорта** — `UpstreamClient` остаётся единственным классом для всех upstream'ов. server.py / tests / docs не нуждаются в разделении.
- **Spec-compliant** — используем официальный SDK pattern из `examples/snippets/clients/stdio_client.py`. Никаких custom subprocess code.
- **Backward compatible** — Phase 1 конфиги работают без изменений благодаря `_backward_compat_url` валидатору.
- **Extensible** — Phase 3+ может добавить `WebsocketTransport(kind="websocket", url, headers)` без breaking change (просто union member).
- **Testable** — stdio upstream тестируется через fake Python script (см. `tests/test_upstream.py` Phase 2). HTTP upstream тесты не меняются.

### Negative

- **Discriminated union complexity** — Pydantic feature требует `Annotated[Union, Field(discriminator=...)]` pattern. Менее очевидно для новичков.
- **Backward-compat layer** — `_backward_compat_url` валидатор добавляет runtime overhead (мизерный) и complexity. Должен быть удалён в Phase 4 когда все конфиги мигрированы.
- **Парные сигнатуры** — `UpstreamClient.__init__` принимает discriminated object вместо primitive (`url`). Тесты/документация должны использовать `transport: TransportConfig`, не raw string.

### Risks

- **Pydantic version compatibility**: `Annotated[..., Field(discriminator=...)]` pattern работает в Pydantic 2.5+. У нас 2.14+ — OK.
- **Stdio subprocess isolation**: stdio upstream'ы запускаются как child processes. Если hub упадёт — subprocess'ы могут остаться. Решается через `process group kill` на SIGTERM (SDK делает автоматически).
- **env var interpolation**: Pydantic не делает `${VAR}` substitution в `env: dict`. Если Kolya захочет reference env vars в config, добавим в Phase 3 как мини-feature (одна regex-функция).

## Alternatives considered

**Вариант B (отдельный StdioUpstreamClient)** отклонён потому что:
- ~80% кода дублируется (start/stop/list_tools/call_tool)
- `server.py` должен знать про два класса (при `tools/list` агрегации, при `tools/call` routing)
- Тесты пишутся дважды

**Вариант C (mcp-proxy sidecar)** отклонён потому что:
- 5+ extra subprocess'ов (overhead, особенно на CPU-constrained машинах)
- Нет visibility в crash detection — mcp-proxy молча умирает, hub не знает
- Дополнительная dependency (npm install mcp-proxy), не Python-native
- Logging раскидан по 5 файлам mcp-proxy + hub

## References

- Recon: `/home/gna/.hermes/profiles/harness/cache/scratch/stdio-upstream-recon-2026-10-10.md`
- Spec: `specs/003-stdio-and-hot-reload/spec.md`
- Data model: `specs/003-stdio-and-hot-reload/data-model.md`
- Plan: `specs/003-stdio-and-hot-reload/plan.md`
- MCP SDK stdio example: https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/clients/stdio_client.py
- mcp-proxy (отклонён): https://github.com/sparfenyuk/mcp-proxy
- Pydantic discriminated unions: https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions
- Phase 1 ADR: `ADR-007-upstream-via-mcp-sdk.md`
- Kolya's реальный stdio список: `~/.hermes/profiles/harness/config.yaml`