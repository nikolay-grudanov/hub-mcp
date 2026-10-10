# hub-mcp — index

**harness-mcp-hub** — единый MCP-сервер с per-profile фильтрацией инструментов и централизованным discovery для Hermes-профилей, GigaCode/OpenCode/Qwen CLI и Claude Code.

**Phase 1 MVP завершён 2026-10-10** (коммиты `e1b7f5f`, `b3d2355`, pushed на origin/master). Live verified с 4 real upstream.

## Структура

```
hub-mcp/
├── AGENT_CONTEXT.md        # контракт для агентов-исполнителей
├── README.md               # краткое описание проекта
├── pyproject.toml          # Python 3.11+, mcp/starlette/pydantic/httpx
├── uv.lock                 # pinned dependencies
├── docs/
│   ├── index.md            # этот файл
│   ├── _conventions.md     # локальные правила документации и кода
│   ├── spec.md             # живая спецификация (status: Implemented)
│   ├── roadmap.md          # фазы разработки (Phase 1 done, Phase 2 next)
│   ├── open-questions.md   # открытые вопросы (OQ-hub-001..014)
│   ├── architecture/       # архитектурные диаграммы и обзоры
│   ├── decisions/          # ADR-ы (Architecture Decision Records)
│   │   ├── ADR-001-mcp-fork-not-protocol-fork.md
│   │   ├── ADR-002-x-profile-id-header.md            (Superseded)
│   │   ├── ADR-003-starlette-not-flask.md
│   │   ├── ADR-004-no-server-side-state.md
│   │   ├── ADR-005-admin-rest-api-and-web-ui-in-mvp.md (Superseded)
│   │   ├── ADR-006-skeleton-core-no-profiles-no-ui.md  (MVP scope)
│   │   └── ADR-007-upstream-via-mcp-sdk.md              (применён в Phase 1)
│   ├── profiles/           # схемы и примеры per-profile policy (archived)
│   ├── backlog/            # отложенные задачи
│   ├── interviews/         # интервью с пользователями / записи решений
│   └── prototypes/         # прототипы, PoC, эксперименты
├── specs/
│   ├── 001-mvp-hub-server/ # Superseded (старая спека с profiles+admin)
│   │   ├── spec.md
│   │   ├── plan.md
│   │   ├── data-model.md
│   │   └── tasks.md
│   └── 002-skeleton-core/  # Завершён 2026-10-10
│       ├── spec.md         # что строили
│       ├── plan.md         # bite-sized tasks + TDD
│       ├── data-model.md   # схемы (Pydantic)
│       └── tasks.md        # чек-лист (все [x])
├── src/
│   └── hub_mcp/
│       ├── __init__.py
│       ├── exceptions.py   # HubMcpError, ConfigError, UpstreamUnavailableError, ToolNotFoundError
│       ├── config.py       # HubConfig Pydantic + load_config() + env overrides
│       ├── upstream.py     # UpstreamClient (mcp SDK wrapper, ADR-007)
│       ├── audit.py        # AuditEvent + AuditWriter (Hindsight REST)
│       └── server.py       # Starlette ASGI app + JSON-RPC dispatcher + lifespan
└── tests/
    ├── __init__.py
    ├── conftest.py         # LifespanAsyncClient helper
    ├── test_config.py      # 17 tests: Pydantic validation + env overrides
    ├── test_upstream.py    # 10+1: spec-compliant SDK lifecycle
    ├── test_audit.py       # 7 tests: best-effort Hindsight
    └── test_server.py      # 8 tests: end-to-end hub behavior
```

## Что где искать

| Хочу найти... | Идти в... |
|---|---|
| Что это за проект, что он делает | `README.md` → `docs/spec.md` |
| На каком мы этапе | `docs/roadmap.md` |
| Почему принято архитектурное решение X | `docs/decisions/ADR-NNN-<name>.md` |
| Что сейчас непонятно / висит в воздухе | `docs/open-questions.md` |
| Какой формат у profile YAML | `docs/profiles/schema.md` (archived) |
| Готовые примеры профилей | `docs/profiles/examples/` (archived) |
| Детальный план реализации MVP | `specs/002-skeleton-core/plan.md` |
| Контракт для агентов, которые будут реализовывать | `AGENT_CONTEXT.md` |
| Локальные правила (терминология, формат) | `docs/_conventions.md` |
| Конфиг Kolya's setup | `~/.harness-hub/config.yaml` |

## Ключевые ссылки на внешние ресурсы

- **llmwiki на harness-workspace**: `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md` — анализ-прообраз (Shanghai AI Lab fork MCP).
- **GitHub**: https://github.com/nikolay-grudanov/hub-mcp — public repo, 5 коммитов.

## Конвенция обновления

Этот index обновляется **вместе с любой структурной правкой** каталога (добавил документ — добавь ссылку). Проверять через `find docs specs src -type f -name '*.py' -o -name '*.md' | sort` и сверять с деревом выше.

## История изменений index

- 2026-10-10 — initial scaffold (Kolya + Hermes-harness)
- 2026-10-10 — Phase 1 завершён: добавлены ADR-005/006/007, src/, tests/, docs/_conventions.md, обновлены ссылки на Phase 1 done