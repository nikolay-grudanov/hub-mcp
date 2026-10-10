# AGENT_CONTEXT.md — контекст для агентов-исполнителей

**Этот файл читается агентом перед любой задачей в `hub-mcp/`.** Содержит технический контекст, команды, структуру и правила, специфичные для проекта. (Имя `AGENT_CONTEXT.md` вместо `AGENTS.md` — потому что `AGENTS.md` защищён harness-правилом и требует явного одобрения Kolya перед записью.)

## Tech Stack

> **Update 2026-10-10 (ADR-006)**: MVP — skeleton + core, **без профилей и без admin UI**. Stack упрощён.

- **Python 3.11+** (async/await, `typing.ParamSpec`, `typing.Self`)
- **uv** как package manager (не pip, не poetry) — `uv pip install`, `uv run`, `uv sync`
- **Starlette 0.40+** + **uvicorn 0.30+** (ASGI, не Flask)
- **MCP Python SDK** (`mcp` package — тот же, что в `InternScience/scp`, Anthropic MIT)
- **Pydantic v2** для всех схем
- **PyYAML 6.0+** для config YAML
- **httpx 0.27+** для async HTTP к Hindsight + upstream
- **pytest 8+** + **pytest-asyncio** + **httpx** для тестов

**Не в MVP** (Phase 2+):

- Jinja2 / itsdangerous / Pico CSS — отложены в Phase 4 (admin UI из ADR-005).
- Profile schema и loader — отложены в Phase 3+.

## Команды

```bash
# Установка зависимостей
uv sync                                  # создаёт .venv, ставит всё из pyproject.toml

# Тесты
uv run pytest tests/ -v                  # все тесты
uv run pytest tests/test_profile_loader.py -v  # один файл
uv run pytest -k "test_filter" -v        # по подстроке в имени

# Линт + типчек
uv run ruff check src/ tests/            # ruff (не flake8, не black)
uv run ruff format --check src/ tests/   # форматирование
uv run pyright src/                      # типчек (строгий режим в pyproject.toml)

# Локальный запуск hub'а
uv run uvicorn hub_mcp.server:app --host 127.0.0.1 --port 46380 --reload

# Тестовый smoke — подключиться MCP-клиентом
# (нужен mcp-cli или наш test client)
```

## Структура проекта

```
hub-mcp/
├── pyproject.toml            # uv-managed, PEP 621
├── README.md                 # короткое описание
├── AGENT_CONTEXT.md          # этот файл (замена защищённого AGENTS.md)
├── docs/                     # живая документация
│   ├── index.md
│   ├── spec.md
│   ├── roadmap.md
│   ├── _conventions.md
│   ├── decisions/            # ADR-ы (001-006)
│   ├── profiles/             # archived (Phase 3+, не в MVP)
│   └── open-questions.md
├── specs/
│   ├── 001-mvp-hub-server/   # Superseded (для исторической трассировки)
│   └── 002-skeleton-core/    # активная спека MVP
└── src/                      # код (target = "...")
    ├── hub_mcp/
    │   ├── __init__.py
    │   ├── server.py         # Starlette ASGI app + JSON-RPC dispatcher
    │   ├── config.py         # config.yaml loader + Pydantic
    │   ├── upstream.py       # httpx client to upstream MCP servers
    │   ├── audit.py          # Hindsight audit log writer
    │   └── exceptions.py     # HubMcpError base + typed subclasses
    └── ...
```

**Не в MVP** (Phase 2+):

- `profile_loader.py`, `filter.py`, `types.py` (Profile model) — отложены в Phase 3+.
- `upstream_health.py`, `admin.py`, `admin_auth.py`, `csrf.py`, `templates/`, `static/` — отложены в Phase 2+/4.

## CI / проверки

Перед commit'ом (явным, по слову Kolya):

```bash
uv run ruff check src/ tests/ --fix       # автофикс-импорты и простые нарушения
uv run ruff format src/ tests/             # формат
uv run pyright src/                        # типчек (strict)
uv run pytest tests/ -v --tb=short         # тесты
```

**Все 4 должны быть зелёными.** Coverage: стремимся к ≥85% lines/branches для нового кода.

## Правила для агентов

1. **Используй `subagent-driven-development`** для имплементации spec'ов — bite-sized tasks, TDD, fresh subagent per task. См. `~/.hermes/profiles/harness/skills/software-development/subagent-driven-development/SKILL.md`.

2. **Live-debug протокол для I/O кода**: перед merge'ом нового MCP-транспорта или upstream proxy запусти hub с реальным upstream MCP (например, `mcp-server-fetch`), подключись MCP Inspector'ом, отправь `initialize` → `tools/list` → `tools/call` руками. Не ограничивайся unit-тестами — unit tests пропускают race conditions в event-driven коде. Протокол: `~/.hermes/profiles/harness/skills/software-development/writing-plans/SKILL.md` → `references/live-debug-event-driven.md`.

3. **Не редактируй `docs/decisions/` без ADR-NNN**. Любое архитектурное изменение сначала получает ADR (`YYYY-MM-DD — <title>`), потом имплементация. Старые ADR не переписываются — пишется новый с `**Supersedes:** ADR-NNN` в начале.

4. **Config YAML — схема в `specs/002-skeleton-core/data-model.md` является canonical**. Pydantic-модель в `src/hub_mcp/config.py` должна её матчить один-в-один. Если добавляешь поле в schema — сначала PR с schema + Pydantic + тестом на новый кейс.

5. **Open questions фиксируй в `docs/open-questions.md`**, не в коде. Формат `OQ-hub-NNN — <title>`. Когда закрываешь — strike through + `**RESOLVED YYYY-MM-DD**` + ссылка на решение (ADR или PR).

6. **Hindsight audit пиши в формате `mcp-audit-{server}-{tool}-{YYYY-MM-DD}`** (без profile — profile ещё нет, см. ADR-006). Не батчить — Kolya хочет искать по дате.

7. **Имена файлов и каталогов** — kebab-case (`mcp-bridge.py`, `profile-loader.py`). Имена Python-модулей — snake_case (`hub_mcp`).

8. **Один каталог — одна ответственность**. `upstream.py` не должен знать про Starlette. `server.py` не должен знать про Hindsight напрямую — только через `audit.py`. Зависимости направлены внутрь.

9. **Тесты лежат в `tests/`**. Имя теста — `test_<method>_<scenario>` (например, `test_load_profile_missing_required_field_raises`).

10. **Не auto-commit**. Kolya говорит «коммить» явно. По умолчанию — оставляй worktree dirty до слова.

11. **НЕ добавляй X-Profile-Id / profile filtering в MVP**. См. ADR-006. Profile filtering отложен в Phase 3+. Если агент считает что добавить профиль = правильная идея — это ADR-006 violation; сначала обсудить с Kolya и поднять новый ADR.

12. **НЕ добавляй admin UI / REST / CSRF / Jinja2 в MVP**. См. ADR-006 + ADR-005 Superseded. Admin отложен в Phase 4. Только health endpoint `/health` и MCP endpoint `/mcp`.

## Как начать работу над задачей

```bash
# 1. Прочитай текущий спек
cat specs/002-skeleton-core/spec.md
cat specs/002-skeleton-core/plan.md

# 2. Прочитай conventions
cat docs/_conventions.md

# 3. Прочитай relevant ADR (для MVP — ADR-006 главный)
ls docs/decisions/
cat docs/decisions/ADR-006-skeleton-core-no-profiles-no-ui.md

# 4. Создай ветку (если работаем в git, не в scratch)
git checkout -b feat/NNN-<short-name>

# 5. Делай bite-sized tasks из plan.md, с TDD (test → fail → impl → pass → commit)
```

## Где спросить помощь

- **Архитектура / формат конфига** → ADR-006 + `specs/002-skeleton-core/data-model.md`
- **Почему так, а не иначе** → grep `docs/interviews/` и `docs/open-questions.md`
- **Какая у Kolya конвенция в целом** → `/home/gna/workspase/workspaces/harness/llmwiki/`

## Заметка для будущего: AGENTS.md

Когда Kolya даст явное согласие (`write this file` в чате), переименовать `AGENT_CONTEXT.md` → `AGENTS.md`. Содержимое готово к переименованию. Причина защиты: harness считает AGENTS.md инструкцией для runtime-агентов и хочет human-in-the-loop перед её записью в новых проектах.