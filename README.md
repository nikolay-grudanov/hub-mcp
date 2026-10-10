# hub-mcp

**harness-mcp-hub** — единый MCP-сервер с per-profile фильтрацией инструментов и централизованным discovery.

Заменяет N записей в `mcp_servers` каждого runtime (Hermes, GigaCode, OpenCode, Qwen, Claude Code) на одну. Агент подключается к hub'у и через HTTP-header `X-Profile-Id` (или `Authorization: Bearer` токен) получает только разрешённые в его профиле tools.

## Документация

Вся живая документация — в [`docs/`](docs/index.md). Ключевые точки входа:

- [`docs/spec.md`](docs/spec.md) — что строим и почему
- [`docs/roadmap.md`](docs/roadmap.md) — фазы и текущий статус
- [`docs/decisions/`](docs/decisions/) — архитектурные решения (ADR-ы)
- [`docs/open-questions.md`](docs/open-questions.md) — что ещё не решено
- [`docs/profiles/`](docs/profiles/schema.md) — схема per-profile policy
- [`specs/001-mvp-hub-server/`](specs/001-mvp-hub-server/spec.md) — детальный план MVP

## Контекст

Возник из обсуждения 2026-10-10 в `/learn InternScience/scp` → изучения Shanghai AI Lab MCP-fork → выявления боли с дублированием MCP между Hermes-профилями / OpenCode / Qwen / zai-copilot. Подробный trace — в `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md` и в `docs/interviews/2026-10-10-discovery.md` (планируется).

## Технологии

- **Python 3.11+** (как и весь остальной harness стек)
- **Starlette + uvicorn** (не Flask — см. ADR-003)
- **MCP Python SDK** (`mcp` пакет от Anthropic) — wire-protocol реализация
- **Pydantic v2** для валидации profile YAML
- **PyYAML** для парсинга профилей
- **Hindsight** (через REST) для audit log
- **Тесты**: pytest + httpx async client

## Статус

В работе. Текущая фаза — **Phase 0: discovery + design** (см. `docs/roadmap.md`).