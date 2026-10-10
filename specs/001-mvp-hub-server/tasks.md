# Tasks — 001-mvp-hub-server

Чек-лист задач из [`plan.md`](plan.md). Обновляется по мере выполнения.

## Phase 1: Project Bootstrap

- [ ] **Task 1.1** — Initialize project structure (pyproject.toml, src layout, .gitignore, exceptions)
- [ ] **Task 1.2** — Configure git pre-commit hook (ruff + pyright + pytest)

## Phase 2: Pydantic types + profile schema

- [ ] **Task 2.1** — Define Profile Pydantic model (`src/hub_mcp/types.py` + `tests/test_types.py`)

## Phase 3: Profile loader

- [ ] **Task 3.1** — YAML file loading with error handling (`src/hub_mcp/profile_loader.py`)

## Phase 4: Filter

- [ ] **Task 4.1** — Tool filtering with include/exclude (`src/hub_mcp/filter.py` + `src/hub_mcp/mcp_types.py`)

## Phase 5: Upstream HTTP client

- [ ] **Task 5.1** — UpstreamClient (JSON-RPC over httpx) (`src/hub_mcp/upstream.py`)

## Phase 6: Hindsight audit

- [ ] **Task 6.1** — AuditWriter (Hindsight REST) (`src/hub_mcp/audit.py`)

## Phase 7: Starlette server

- [ ] **Task 7.1** — Server bootstrap (`src/hub_mcp/server.py` + `src/hub_mcp/config.py`)
  - [ ] `/health` endpoint returns 200
  - [ ] `/mcp` initialize with valid X-Profile-Id
  - [ ] `/mcp` initialize without X-Profile-Id → error
  - [ ] `/mcp` tools/list filters by profile
  - [ ] `/mcp` tools/call routes to upstream + audit log

## Phase 8: Deploy + Live debug

- [ ] **Task 8.1** — Create deploy configs in `~/.harness-hub/`
- [ ] **Task 8.2** — Live debug with MCP Inspector
  - [ ] Inspector connects with X-Profile-Id: developer-tools
  - [ ] tools/list returns only profile-allowed tools
  - [ ] tools/call to fetch.fetch_html succeeds
  - [ ] Audit log written to Hindsight

## Phase 9: Upstream health check (ADR-005)

- [ ] **Task 9.1** — HealthChecker + rolling-window success rate (`src/hub_mcp/upstream_health.py`)

## Phase 10: Admin auth + CSRF (ADR-005)

- [ ] **Task 10.1** — X-Admin-Token + auto-generated token (`src/hub_mcp/admin_auth.py`)
- [ ] **Task 10.2** — CSRF token via itsdangerous (`src/hub_mcp/csrf.py`)

## Phase 11: Admin REST handlers (ADR-005)

- [ ] **Task 11.1** — Profile CRUD endpoints (`src/hub_mcp/admin.py`)
- [ ] **Task 11.2** — Upstream CRUD + health endpoint (`src/hub_mcp/admin.py`)
- [ ] **Task 11.3** — Tools debug + audit listing + hub health

## Phase 12: Admin Web UI (ADR-005)

- [ ] **Task 12.1** — Jinja2 templates + base layout
- [ ] **Task 12.2** — Routes mounting

## Phase 13: Admin deploy + browser live debug

- [ ] **Task 13.1** — Browser-side live debug
  - [ ] Dashboard renders
  - [ ] Profile edit saves and hub sees changes
  - [ ] Tools debug shows filtered list
  - [ ] Audit log shows recent events
  - [ ] Upstream health indicators update

## Final verification

- [ ] `uv run ruff check src/ tests/` → 0 errors
- [ ] `uv run ruff format --check src/ tests/` → 0 differences
- [ ] `uv run pyright src/` → 0 errors (strict mode)
- [ ] `uv run pytest tests/ -v --cov=src/hub_mcp` → all green, coverage ≥ 85%
- [ ] Live debug: Inspector + real upstream + ручной smoke (Phase 8.2)
- [ ] Live debug: Browser + admin UI + CRUD profiles (Phase 13.1)

## Done when

Все задачи выше отмечены, все 4 pre-commit checks зелёные, оба live debug (MCP + browser) пройдены. Rollout в Hermes config — отдельная задача Kolya.