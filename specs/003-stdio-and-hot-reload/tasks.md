# Tasks — 003-stdio-and-hot-reload

Чек-лист из [`plan.md`](plan.md). Обновляется по мере выполнения.

> **Estimated**: 3-4 часа (не «1-2 дня» как в roadmap — discriminated union + SDK stdio_client даёт минимальный code change).

## Phase 1: Discriminated transport в config

- [ ] **Task 1.1** — TDD discriminated union: `HttpTransport | StdioTransport` в `UpstreamConfig.transport` + backward-compat для `url: str`
  - 5 новых tests, 17 existing tests не должны регрессировать

## Phase 2: UpstreamClient stdio branch

- [ ] **Task 2.1** — TDD stdio spawn: `UpstreamClient.start()` для `StdioTransport` через `mcp.client.stdio.stdio_client`
  - 3-4 новых tests (spawn + env + timeout + stderr)

## Phase 3: SIGHUP hot-reload

- [ ] **Task 3.1** — `load_config_with_metadata()` возвращает `(HubConfig, Path, mtime)`
- [ ] **Task 3.2** — SIGHUP signal handler в `_lifespan` + diff algorithm
  - 1-2 новых tests (add/remove/change detection)
- [ ] **Task 3.3** — Invalid YAML keep old config (safe behavior)
  - 1 test

## Phase 4: Pre-commit hook fix (OQ-hub-014)

- [ ] **Task 4.1** — Refactor hook с explicit `run_step` pattern, убрать `set -e`, добавить diagnostic output
  - Verification: `git commit` работает когда gates зелёные, reject когда красные

## Phase 5: SDK bug report (OQ-hub-013)

- [ ] **Task 5.1** — Создать минимальный repro (15 строк async Python)
- [ ] **Task 5.2** — Submit issue в https://github.com/modelcontextprotocol/python-sdk/issues/new
  - Add link to OQ-hub-013 в `docs/open-questions.md`

## Phase 6: Live debug + Kolya's config update

- [ ] **Task 6.1** — Update `~/.harness-hub/config.yaml`: заменить stdio placeholder URL'ы на реальные stdio upstream'ы
  - arxiv: `uv tool run --from arxiv-mcp-server arxiv-mcp-server`
  - fetch: `npx -y mcp-fetch-server`
  - repomix: `npx ... --mcp`
- [ ] **Task 6.2** — Live test: stdio + HTTP + SIGHUP all working
  - tools/list includes arxiv (stdio) + hindsight/qmd/deepwiki/context7 (HTTP)
  - tools/call arxiv.search_papers returns real response
  - `kill -HUP` reloads config без рестарта
- [ ] **Task 6.3** — Pre-commit gates зелёные: ruff, format, pyright, pytest

## Final verification

- [ ] `uv run ruff check src/ tests/` → 0 errors
- [ ] `uv run ruff format --check src/ tests/` → 0 differences
- [ ] `uv run pyright src/` → 0 errors (strict mode)
- [ ] `uv run pytest tests/ -v` → 50+ passed, 1 skipped (OQ-hub-013)
- [ ] `git commit` работает без `--no-verify`
- [ ] Live debug: arxiv stdio + fetch stdio + HTTP upstream'ы одновременно
- [ ] SIGHUP reload: edit config + `kill -HUP` → new upstream подключён без рестарта

## Done when

Все задачи выше отмечены, 4 pre-commit checks зелёные, `git commit` работает без `--no-verify`, live debug пройден, SDK issue submitted.

**Phase 2 завершён** → Phase 3 (per-profile filtering, ADR-002) может стартовать.