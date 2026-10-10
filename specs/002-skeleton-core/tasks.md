# Tasks — 002-skeleton-core

Чек-лист задач из [`plan.md`](plan.md). Обновляется по мере выполнения.

## Phase 1: Project Bootstrap

- [ ] **Task 1.1** — Initialize project structure (pyproject.toml, src layout, .gitignore, exceptions)
- [ ] **Task 1.2** — Configure git pre-commit hook (ruff + pyright + pytest)

## Phase 2: Config schema + loader

- [ ] **Task 2.1** — Define HubConfig Pydantic model (`src/hub_mcp/config.py` + `tests/test_config.py`)
- [ ] **Task 2.2** — YAML config loader with env-var overrides (`load_config()`)

## Phase 3: Upstream HTTP client

- [ ] **Task 3.1** — UpstreamClient (JSON-RPC over httpx, error handling per OQ-hub-012)

## Phase 4: Hindsight audit

- [ ] **Task 4.1** — AuditWriter (Hindsight REST, best-effort, `mcp-audit-{server}-{tool}-{date}` tag)

## Phase 5: Starlette server

- [ ] **Task 5.1** — Server bootstrap (`src/hub_mcp/server.py`)
  - [ ] `/health` endpoint
  - [ ] `/mcp` initialize handler
  - [ ] `/mcp` tools/list aggregator (parallel asyncio.gather)
  - [ ] `/mcp` tools/call router (qualified name → upstream)
  - [ ] `/mcp` notifications/pings passthrough (Phase 2; MVP — return error)

## Phase 6: Deploy + Live debug

- [ ] **Task 6.1** — Create deploy config `~/.harness-hub/config.yaml` for Kolya's setup
- [ ] **Task 6.2** — Live debug with MCP Inspector
  - [ ] Inspector connects to hub
  - [ ] tools/list returns union of enabled upstream tools
  - [ ] tools/call to fetch.fetch_html succeeds
  - [ ] Audit log written to Hindsight
  - [ ] Disabled upstream (repomix) doesn't appear in tools/list

## Final verification

- [ ] `uv run ruff check src/ tests/` → 0 errors
- [ ] `uv run ruff format --check src/ tests/` → 0 differences
- [ ] `uv run pyright src/` → 0 errors (strict mode)
- [ ] `uv run pytest tests/ -v --cov=src/hub_mcp` → all green, coverage ≥ 85%
- [ ] Live debug: Inspector + real upstream + ручной smoke

## Done when

Все задачи выше отмечены, все 4 pre-commit checks зелёные, live debug пройден. Rollout в Hermes config — отдельная задача Kolya.