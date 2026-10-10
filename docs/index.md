# hub-mcp — index

**harness-mcp-hub** — единый MCP-сервер с per-profile фильтрацией инструментов и централизованным discovery для Hermes-профилей, GigaCode/OpenCode/Qwen CLI и Claude Code.

## Структура

```
hub-mcp/
├── AGENTS.md                   # контракт для агентов-исполнителей
├── README.md                   # краткое описание проекта
├── docs/
│   ├── index.md                # этот файл
│   ├── _conventions.md         # локальные правила документации и кода
│   ├── spec.md                 # живая спецификация проекта
│   ├── roadmap.md              # фазы разработки
│   ├── open-questions.md       # открытые вопросы (OQ-hub-NNN)
│   ├── architecture/           # архитектурные диаграммы и обзоры
│   ├── decisions/              # ADR-ы (Architecture Decision Records)
│   │   ├── ADR-001-mcp-fork-not-protocol-fork.md
│   │   ├── ADR-002-x-profile-id-header.md
│   │   ├── ADR-003-starlette-not-flask.md
│   │   └── ADR-004-no-server-side-state.md
│   ├── profiles/               # схемы и примеры per-profile policy
│   │   ├── schema.md
│   │   └── examples/
│   │       ├── developer-tools.yaml
│   │       └── harness-infra.yaml
│   ├── backlog/                # отложенные задачи
│   ├── interviews/             # интервью с пользователями / записи решений
│   └── prototypes/             # прототипы, PoC, эксперименты
└── specs/
    └── 001-mvp-hub-server/     # SpecKit-style спека на MVP
        ├── spec.md             # что строим
        ├── plan.md             # bite-sized tasks + TDD
        ├── data-model.md       # схемы (Pydantic / TypedDict)
        └── tasks.md            # чек-лист задач
```

## Что где искать

| Хочу найти... | Идти в... |
|---|---|
| Что это за проект, что он делает | `README.md` → `docs/spec.md` |
| На каком мы этапе | `docs/roadmap.md` |
| Почему принято архитектурное решение X | `docs/decisions/ADR-NNN-<name>.md` |
| Что сейчас непонятно / висит в воздухе | `docs/open-questions.md` |
| Какой формат у profile YAML | `docs/profiles/schema.md` |
| Готовые примеры профилей | `docs/profiles/examples/` |
| Детальный план реализации MVP | `specs/001-mvp-hub-server/plan.md` |
| Контракт для агентов, которые будут реализовывать | `AGENTS.md` |
| Локальные правила (терминология, формат) | `docs/_conventions.md` |

## Ключевые ссылки на внешние ресурсы

- **llmwiki на harness-workspace**: `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md` — анализ-прообраз (Shanghai AI Lab fork MCP).
- **Песочница для экспериментов**: `prototypes/` — пусто, будет наполняться PoC-кодом.

## Конвенция обновления

Этот index обновляется **вместе с любой структурной правкой** каталога (добавил документ — добавь ссылку). Проверять через `find docs specs -type f -name '*.md' | sort` и сверять с деревом выше.

## История изменений index

- 2026-10-10 — initial scaffold (Kolya + Hermes-harness)