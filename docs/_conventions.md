# Conventions — hub-mcp

Этот файл — локальные правила проекта. Глобальные правила harness стека — в `/home/gna/workspase/workspaces/harness/llmwiki/` (Karpathy 5-section template, tag taxonomy, OQ lifecycle). Здесь — то, что отличается или дополняет.

## Терминология

| Термин | Значение |
|---|---|
| **hub** | Сам MCP-сервер `harness-mcp-hub`. |
| **upstream MCP** | Конкретный MCP-сервер, к которому hub проксирует (например, `mcp-server-fetch`, `mcp__hindsight`). |
| **profile** | Именованный набор правил (`developer-tools`, `harness-infra`), фильтрующий tools по `<server>.<tool>` и задающий policy (limits, redaction). |
| **policy** | Внутреннее поле profile — лимиты, redaction, audit settings. |
| **agent** | Runtime (Hermes, Claude Code, GigaCode), который подключается к hub'у. Для hub'а все они — generic MCP-клиент, различаются только по `X-Profile-Id`. |
| **skill** | Не путать с agent skill — здесь skill = tool exposed by an MCP-server. |

## Документация — формат

- **Markdown везде.** `.md` для всего, кроме генераторов (PlantUML → `.puml`, mermaid → `.mmd`).
- **YAML frontmatter** на каждом документе в `docs/`:
  ```yaml
  ---
  title: ...
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  ---
  ```
- **Имена файлов** — kebab-case (`profile-schema.md`, `x-profile-id-header.md`).
- **Имена ADR** — `ADR-NNN-kebab-case-title.md` (`ADR-001-mcp-fork-not-protocol-fork.md`). NNN сквозной, не per-folder.
- **Имена OQ** — `OQ-hub-NNN — title` в `docs/open-questions.md` (один файл, не per-folder).
- **Имена спецификаций в `specs/`** — `NNN-kebab-case-name/` (NNN сквозной). Внутри — стандартный SpecKit набор: `spec.md`, `plan.md`, `data-model.md`, `tasks.md`, `contracts/`, `checklists/`.

## ADR — формат

```markdown
# ADR-NNN — <Title>

**Status**: Proposed | Accepted | Superseded
**Date**: YYYY-MM-DD
**Supersedes**: ADR-NNN (если применимо)

## Context
Что за проблема / решение / повод.

## Decision
Что решили.

## Consequences
Что это меняет, какие trade-offs.

## Alternatives considered
Что ещё рассматривали и почему не выбрали.

## References
Ссылки на обсуждения, документы, прототипы.
```

Примеры см. в `docs/decisions/`.

## Open Questions — формат

В `docs/open-questions.md`:

```markdown
- **OQ-hub-001** — Какой HTTP header использовать для profile-id?
  `X-Profile-Id` vs `Authorization: Bearer` token? Обсуждение в ADR-002.
  - **RESOLVED 2026-10-10** → ADR-002 выбрал `X-Profile-Id` + опциональный токен.
```

Формат заимствован из harness llmwiki conventions.

## Profile YAML — формат

Canonical schema: `docs/profiles/schema.md`. Краткая сводка:

```yaml
name: developer-tools               # обязательно, kebab-case
description: "Personal dev projects"  # обязательно, ≤ 200 chars
include:                              # обязательно: явно указать, что разрешено
  - server: repomix
  - server: fetch
    tools: [fetch_html, fetch_markdown]
exclude:                              # опционально, для подстраховки
  - pattern: "*delete_*"
limits:                               # опционально
  max_calls_per_session: 500
policy:                               # опционально
  redact_tags: ["private-*"]
  max_response_tokens: 4000
```

Pydantic-модель в `src/hub_mcp/types.py::Profile` — single source of truth для парсера. Тесты на каждый edge case в `tests/test_profile_loader.py`.

## Код — формат

- **Python 3.11+**, async-first.
- **Type hints везде**, в strict mode (`pyright` в pyproject.toml).
- **Pydantic v2** для всех внешних/внутренних моделей.
- **Не использовать `from typing import List, Dict, Optional`** — встроенные generics с 3.9+.
- **Имена модулей** — snake_case (`profile_loader.py`, `mcp_bridge.py`).
- **Имена функций/методов** — snake_case.
- **Имена классов** — PascalCase.
- **Имена констант** — UPPER_SNAKE_CASE.
- **Docstrings** — Google style (см. `src/hub_mcp/profile_loader.py::load_profile` как пример).
- **Imports** — sorted by ruff (`I` rule). Никаких wildcard imports.
- **Длина строки** — 100 chars (не 88, не 79 — у Starlette/uagents экосистемы 100 это стандарт).
- **Исключения** — наследовать от `HubMcpError` (базовый класс в `src/hub_mcp/exceptions.py`). Никаких голых `raise Exception`.

## Тесты — формат

- **pytest + pytest-asyncio**.
- **Имя файла** — `test_<module>.py`.
- **Имя теста** — `test_<method>_<scenario>`:
  - `test_load_profile_missing_required_field_raises`
  - `test_filter_tools_by_include_excludes_unlisted`
  - `test_audit_log_writes_to_hindsight_with_profile_tag`
- **Arrange-Act-Assert** structure, с явными комментариями `## arrange`, `## act`, `## assert`.
- **Fixtures** — в `tests/conftest.py` или в файле теста, если используется один раз.
- **Coverage** — ≥ 85% для нового кода. Проверка через `pytest --cov=src/hub_mcp`.

## Что НЕ делать (anti-patterns)

- ❌ **Не использовать Flask** (см. ADR-003). Starlette/uvicorn — единственный ASGI стек в проекте.
- ❌ **Не использовать sync I/O** в async функциях (`requests`, `open`, `time.sleep`). Только `httpx`, `aiofiles`, `asyncio.sleep`.
- ❌ **Не хранить state в module-level globals** (см. ADR-004). Все state — через DI или closure.
- ❌ **Не использовать `subprocess.Popen` без явного lifecycle** — если нужен upstream MCP как subprocess, обернуть в context manager с timeout.
- ❌ **Не логировать credentials** в audit log. Headers вроде `Authorization` — strip перед логированием.
- ❌ **Не делать `git commit` без явной команды Kolya.** По умолчанию — оставлять worktree dirty.
- ❌ **Не дублировать profile YAML в коде.** Schema → Pydantic → loader, в этом порядке. Profile content читается только из YAML, не hard-coded.
- ❌ **Не создавать `llmwiki/` внутри проекта.** Это Kolya's workspace KB, только в `/home/gna/workspase/workspaces/harness/llmwiki/`. Внутри `hub-mcp/docs/` — локальная документация.

## Tooling

| Tool | Назначение |
|---|---|
| `uv` | package manager, venv, runner |
| `ruff` | lint + format |
| `pyright` | типчек (strict mode) |
| `pytest` | тесты |
| `pytest-asyncio` | async тесты |
| `httpx` | async HTTP клиент (Hindsight, upstream MCP) |
| `mcp` | MCP Python SDK |
| `starlette` | ASGI фреймворк |
| `uvicorn` | ASGI сервер |

## Связь с другими проектами

- `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md` — **reference-проект**, не свойство обучения. Документация и ADR-ы hub-mcp ссылаются на него как на prior art, но не копируют verbatim.
- `/home/gna/.hermes/profiles/harness/skills/mcp/` — внутренние skill-ы Hermes про MCP. Используем для проверки совместимости форматов.
- `/home/gna/.hermes/profiles/harness/config.yaml` — **где** этот hub будет подключён после MVP. Profile `harness-infra` будет соответствовать текущему набору MCP из этого конфига.