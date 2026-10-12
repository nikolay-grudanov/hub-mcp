# Feature Specification: 003 — stdio upstream + hot-reload + tooling fix

**Feature Branch**: `feat/003-stdio-and-hot-reload` (to be created)
**Created**: 2026-10-10
**Status**: Draft
**Input**: «Q1 a, Q2 сделай разведку. Колya: "Вариант A"» (Kolya 2026-10-10).

**Supersedes**: Phase 2 scope in `docs/roadmap.md` (ранее перегружен — 10 пунктов). Новая версия — фокус на stdio + hot-reload + fixes.

**Decisions**:
- [ADR-006](../../docs/decisions/ADR-006-skeleton-core-no-profiles-no-ui.md) — MVP scope.
- [ADR-007](../../docs/decisions/ADR-007-upstream-via-mcp-sdk.md) — UpstreamClient через SDK; **применяется к stdio** (тот же SDK pattern).
- (NEW) ADR-008 (to write) — UpstreamClient discriminated union по типу транспорта (HTTP vs stdio).

## Context and Motivation

Phase 1 (MVP) завершён 2026-10-10 — hub-mcp проксирует HTTP upstream'ы (hindsight, qmd, deepwiki, context7). Phase 1 не покрывает stdio upstream'ы.

**Реальный стек Kolya** (из `~/.hermes/profiles/harness/config.yaml`):
- `arxiv-mcp` через `uv tool run --from arxiv-mcp-server arxiv-mcp-server`
- `mcp-fetch-server` через `npx -y @tokeniz/front@tokeniz`
- `ctx7sk` через `npx`
- `repomix-mcp` через `npx --mcp`
- `mcp-searxng` через `npx`

Минимум **5 из реального стека Kolya** — stdio. Без их поддержки hub-mcp не может заменить N записей в Hermes config — он покрывает только 4 HTTP upstream'а из ~10. Это блокирует rollout.

**Дополнительный блокер** в Phase 1:
- `OQ-hub-014` — pre-commit hook ломается с exit 250 после pyright, обход через `--no-verify`. Не блокирует, но напрягает.
- **Hot-reload конфига**: Kolya привык менять `mcp_servers` в Hermes config и сразу видеть эффект. Hub требует `kill <pid>; uv run uvicorn ...` — friction.

**Что входит в Phase 2 (минимально-жизнеспособный, «вариант a» по Kolya)**:

- **stdio upstream** (discriminated union в config + UpstreamClient расширяется). Покрывает arxiv/fetch/repomix/searxng/ctx7sk.
- **hot-reload конфига через SIGHUP** (file watcher → graceful reload in-place, без `kill`+restart).
- **fix pre-commit hook** (OQ-hub-014) — диагностировать signal-killed после pyright, починить.
- **submit upstream SDK bug** для OQ-hub-013 (cancel-scope issue с MockTransport sync raise) — upstream PR, не блокирует.

**Что НЕ входит в Phase 2** (явно отложено в Phase 3+):
- WebSocket MCP transport (OQ-hub-008) — нет upstream требующего WS.
- Audit retention policy (OQ-hub-011) — Hindsight storage cheap, нет pressure.
- Per-upstream health checker с ping loop (Phase 3+).
- Circuit breaker (Phase 3+).
- Structured logging через structlog (Phase 3+).
- Subprocess auto-restart на crash (Phase 3+).

## Compatibility

- **Config backward-compat**: существующие upstream'ы в `~/.harness-hub/config.yaml` (HTTP, `url: ...`) продолжают работать как раньше. Новый `transport: stdio` — opt-in.
- **Wire protocol**: стандартный MCP. Любой MCP-client подключается без изменений.
- **API backward-compat**: `UpstreamClient.start()/stop()/list_tools()/call_tool()` интерфейс не меняется, только внутренний `__init__` принимает `transport: TransportConfig` вместо `url: str`.

## User Scenarios & Testing

### Scenario 1 — stdio upstream listed в tools/list

**Given**: `~/.harness-hub/config.yaml` содержит:
```yaml
upstream:
  - name: arxiv
    enabled: true
    timeout: 60.0
    transport:
      kind: stdio
      command: uv
      args: ["tool", "run", "--from", "arxiv-mcp-server", "arxiv-mcp-server"]
  - name: fetch
    enabled: true
    timeout: 30.0
    transport:
      kind: stdio
      command: npx
      args: ["-y", "mcp-fetch-server"]
```

**When**: hub стартует → `tools/list` через `/mcp`.

**Then**:
- arxiv subprocess spawned через `stdio_client(StdioServerParameters(...))`.
- arxiv initialize handshake успешен (или upstream excluded с warning).
- tools агрегированы: `arxiv.search_papers`, `arxiv.list_papers`, `fetch.fetch_html`, etc.
- Один упавший subprocess не блокирует остальные.

### Scenario 2 — tools/call к stdio upstream

**Given**: arxiv subprocess running, `tools/list` вернул `arxiv.search_papers`.

**When**: агент вызывает `tools/call` с `name="arxiv.search_papers"`, `arguments={"query": "MCP"}`.

**Then**:
- Hub маршрутизирует к arxiv subprocess через persistent `ClientSession`.
- Subprocess возвращает результат (или upstream error).
- Audit log в Hindsight под `mcp-audit-arxiv-search_papers-{date}`.

### Scenario 3 — hot-reload конфига через SIGHUP

**Given**: hub запущен с config.yaml содержащим arxiv (stdio) + fetch (stdio).

**When**: Kolya редактирует config.yaml — добавляет `qmd` (HTTP), и шлёт `kill -HUP $(pgrep -f 'uvicorn hub_mcp')`.

**Then**:
- Hub получает SIGHUP, перечитывает config.yaml.
- Новый upstream (qmd) подключён без рестарта процесса.
- Существующие upstream'ы (arxiv, fetch) НЕ перезапускаются (только если их config изменился).
- Invalid YAML / schema mismatch → keep old config, log error (безопаснее чем крашить процесс).

### Scenario 4 — stdio upstream с env propagation

**Given**: stdio upstream определён с `env: {FOO: "bar"}`.

**When**: hub spawns subprocess.

**Then**:
- Subprocess получает merged env: `os.environ` ∪ `{FOO: "bar"}`.
- Например, `ANTHROPIC_API_KEY` из shell прокинут автоматически (для upstream'ов которые его требуют).

### Scenario 5 — pre-commit hook работает

**Given**: разработчик делает `git commit`.

**Then**:
- ruff check, ruff format, pyright, pytest запускаются последовательно.
- Если все зелёные — commit проходит. Если хоть один красный — commit отклонён с понятным output.

## Functional Requirements

### FR-1 — Discriminated transport в config

- `UpstreamConfig` расширяется полем `transport: TransportConfig` (вместо `url: str`).
- `TransportConfig` — Pydantic discriminated union по полю `kind`:
  - `kind: "http"` → `HttpTransport` (поля: `url`)
  - `kind: "stdio"` → `StdioTransport` (поля: `command`, `args`, `env`, `cwd`, `encoding`, `encoding_error_handler`)
- Backward-compat: если `transport` отсутствует, `url: str` treated as `HttpTransport(url=url)`. Депрекация `url` в Phase 3+.
- Pydantic validation: `command` required, `args` default `[]`, `env` default `{}`, `cwd` default `None`.

### FR-2 — UpstreamClient оба транспорта

- `UpstreamClient.__init__` принимает `transport: TransportConfig`, не `url: str`.
- `start()`:
  - `kind == "http"` → `streamable_http_client(url=...)` как раньше.
  - `kind == "stdio"` → `stdio_client(StdioServerParameters(command=..., args=..., env=..., cwd=...))`.
  - После успешного transport open: `ClientSession(read, write)` + `initialize()` + `notifications/initialized` (общая логика).
- `stop()`, `list_tools()`, `call_tool()` — общая логика, transport-agnostic.
- Exception hierarchy: `UpstreamUnavailableError` для обоих транспортов.

### FR-3 — spawn timeout на startup

- `asyncio.wait_for(self._spawn(), timeout=10.0)` для stdio upstream'ов.
- Если timeout — upstream excluded из `upstream_map`, log warning (consistent с HTTP upstream failure в lifespan).

### FR-4 — stderr capture в hub logger

- stdio upstream'ы получают `errlog=subprocess_logger` где `subprocess_logger` пишет в `logging.getLogger("hub_mcp.upstream.{name}.stderr")` с префиксом `[{name} stderr]`.
- По умолчанию уровень INFO (видно в dev), в production можно поднять до WARNING через logging config.

### FR-5 — SIGHUP hot-reload

- Hub устанавливает signal handler для `SIGHUP` в lifespan startup.
- При SIGHUP:
  1. Прочитать `~/.harness-hub/config.yaml` заново.
  2. Validate через Pydantic. Если invalid → log error, keep old config, no-op.
  3. Diff с `app.state.config.upstream`:
     - Новые upstream'ы → start() + add в `upstream_map`.
     - Удалённые upstream'ы → stop() + remove из `upstream_map`.
     - Изменённые upstream'ы (url, command, args) → stop() + start() с новыми параметрами.
  4. Log diff summary: "config reloaded: +qmd -repomix ~arxiv (timeout changed)".
- Hot-reload НЕ трогает audit writer config (Hindsight url/bank_id) — это требует рестарта.
- Concurrency: signal handler scheduling через `asyncio.get_event_loop().call_soon_threadsafe()`, чтобы reload запустился в event loop без race с in-flight requests.

### FR-6 — pre-commit hook fix (OQ-hub-014)

- Диагностика root cause: hook прерывается с exit 250 после pyright. Гипотезы:
  1. **process group kill**: `bash` под `set -e` запускает `uv run pyright` как child process; если SIGTERM/SIGKILL идёт на parent group, child умирает.
  2. **signal handler в sandbox среде**: shell tool может слать signal после определённого timeout/output limit.
  3. **pyright внутренний OOM/signal**: при strict-режиме pyright может exit через signal.
- Решение: добавить `trap '' SIGTERM` в hook, чтобы ignore сигналы от parent, И заменить `set -e` на `set -eo pipefail` с явной проверкой exit codes (`cmd1 && cmd2 && cmd3 ...`).
- Альтернатива: перенести hook в `pre-push` (где output/time limit другой).

### FR-7 — SDK bug report для OQ-hub-013

- Создать минимальный repro (10-20 строк async Python) — `httpx.MockTransport` raising sync `httpx.ConnectError` + `mcp.client.streamable_http.streamable_http_client` → `RuntimeError: cancel scope in different task`.
- Submit issue в https://github.com/modelcontextprotocol/python-sdk с repro + expected behavior.
- Track: добавить OQ-hub-013 в `docs/open-questions.md` со ссылкой на issue.

## Non-Functional Requirements

### NFR-1 — Performance

- stdio upstream spawn + initialize ≤ 10s timeout (FR-3). Total hub startup с 5 stdio upstream'ами ≤ 60s.
- Hot-reload diff: ≤ 5s для 10 upstream'ов (mostly local filesystem read + validate).

### NFR-2 — Reliability

- Один упавший stdio upstream (exit code != 0) → log warning, exclude из upstream_map. Остальные работают (NFR-2 уже было в Phase 1).
- Hot-reload с invalid YAML → keep old config, no crash (consistent с "safe than sorry").
- Subprocess auto-restart — НЕ в Phase 2 (Phase 3+).

### NFR-3 — Security

- stdio subprocess inherits shell env (через `get_default_environment()`). Kolya управляет env в config.yaml. Нет privilege escalation если config.yaml под контролем.
- stdio env var propagation documented в config schema (`env: dict[str, str] | None`).

### NFR-4 — Observability

- Subprocess stderr логируется в `hub_mcp.upstream.{name}.stderr` (FR-4).
- Hot-reload events логируются: "config reloaded" с diff details.
- Audit log не меняется (HTTP и stdio upstream'ы пишут одинаково).

## Files to Create/Modify

| File | Action | Priority |
|---|---|---|
| `src/hub_mcp/config.py` | Modify — replace `url: str` с `transport: TransportConfig` discriminated union; добавить `HttpTransport`, `StdioTransport` | P0 |
| `src/hub_mcp/upstream.py` | Modify — UpstreamClient принимает `transport: TransportConfig`; добавить stdio branch | P0 |
| `src/hub_mcp/server.py` | Modify — добавить SIGHUP signal handler в lifespan | P0 |
| `.git/hooks/pre-commit` | Modify — fix OQ-hub-014 | P0 |
| `~/.harness-hub/config.yaml` | Modify — добавить stdio upstream'ы (arxiv, fetch, repomix) | P0 |
| `tests/test_config.py` | Modify — тесты для discriminated union + backward-compat | P0 |
| `tests/test_upstream.py` | Modify — добавить stdio-specific тесты (env, cwd, timeout) | P0 |
| `tests/test_server.py` | Modify — добавить тест hot-reload через SIGHUP | P0 |
| `docs/decisions/ADR-008-transport-discriminated-union.md` | Create | P0 |
| `docs/open-questions.md` | Modify — link SDK bug report для OQ-hub-013 | P0 |

**Не входит в Phase 2**:
- `src/hub_mcp/upstream_health.py` — Phase 3+.
- `src/hub_mcp/circuit_breaker.py` — Phase 3+.

## Testing Strategy

- **Unit tests**: `pytest tests/ -v`, coverage ≥ 85%.
  - `test_config.py`: HttpTransport + StdioTransport validation, backward-compat (existing `url: str` config десериализуется в HttpTransport), invalid combinations.
  - `test_upstream.py`: stdio mock (subprocess через `subprocess.Popen` + fake MCP server), env propagation, spawn timeout, stderr capture.
  - `test_server.py`: hot-reload через SIGHUP, invalid YAML keep old config, diff logic.
- **Integration test** (live debug): реальный stdio upstream (arxiv-mcp-server) + curl, real fetch server (через `npx`).
- **Smoke test**: hub стартует, `tools/list` включает tools от arxiv (stdio) + fetch (stdio) + hindsight (HTTP) + qmd (HTTP).

## Open Questions (blockers)

См. `docs/open-questions.md`. Для Phase 2 ничего не блокирует.

- OQ-hub-001 (stdio) → RESOLVED в Phase 2 (этот спек).
- OQ-hub-007 (hot-reload validation) → RESOLVED в Phase 2.
- OQ-hub-013 (SDK cancel-scope) → upstream issue submitted.
- OQ-hub-014 (pre-commit hook) → RESOLVED в Phase 2.

**Возможные новые OQ (из разведки)**:
- stdio subprocess re-spawn на runtime crash (Phase 3+).
- Hot-reload audit config (Hindsight bank_id change) — требует рестарта или extended reload.
- Hot-reload `listen` config (port change) — почти всегда требует рестарта.

## Related Specifications

- [`docs/spec.md`](../../docs/spec.md) — верхнеуровневая спецификация.
- [`docs/roadmap.md`](../../docs/roadmap.md) — Phase 2 (этот спек).
- [`specs/002-skeleton-core/`](../../specs/002-skeleton-core/) — Phase 1 (завершён).
- Recon: `/home/gna/.hermes/profiles/harness/cache/scratch/stdio-upstream-recon-2026-10-10.md`.

## References

- MCP Python SDK stdio: `https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/clients/stdio_client.py`
- MCP stdio source: `mcp/client/stdio.py` (in SDK, см. `StdioServerParameters` + `stdio_client`)
- SIGHUP signal handling in asyncio: `asyncio.get_event_loop().add_signal_handler()`
- Hot-reload patterns: SIGHUP в Flask (`werkzeug.serving.run_with_reloader`), но для production не годится — мы реализуем свой.
- Kolya's Hermes config: `~/.hermes/profiles/harness/config.yaml` (реальный stdio список).
- Kolya's hub config: `~/.harness-hub/config.yaml` (текущий, с placeholder URL'ами).