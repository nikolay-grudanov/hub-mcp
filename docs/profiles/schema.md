---
title: Profile YAML — canonical schema
created: 2026-10-10
updated: 2026-10-10
status: ARCHIVED (Phase 3+ per ADR-006)
---

# Profile YAML — schema

> **⚠️ ARCHIVED 2026-10-10 per ADR-006**: per-profile filtering отложен в Phase 3+. MVP (Phase 1) работает без профилей — только конфиг upstream'ов в `~/.harness-hub/config.yaml`. Этот документ сохранён для Phase 3+.
>
> Активная документация Phase 1: [`../specs/002-skeleton-core/spec.md`](../specs/002-skeleton-core/spec.md).

Каждый profile — это YAML-файл в `~/.harness-hub/profiles/<name>.yaml`. Hub читает файл при `initialize` MCP-handshake, валидирует через Pydantic (`src/hub_mcp/types.py::Profile`), фильтрует tools.

**Canonical source of truth**: этот файл. Pydantic-модель в коде должна матчить один-в-один. Если есть расхождение — это баг в коде.

## Полная schema

```yaml
# Обязательные поля
name: developer-tools               # kebab-case, ≤ 64 chars. Должно совпадать с именем файла.
description: "Personal dev projects" # ≤ 200 chars. Видно в логах и audit.

# Что разрешено. Минимум 1 элемент.
include:
  # Включить все tools с server
  - server: repomix
  
  # Включить конкретные tools с server
  - server: fetch
    tools: [fetch_html, fetch_markdown, fetch_readable]
  
  # Server с inline policy override (см. policy ниже)
  - server: hindsight
    tools: [recall, retain]
    policy:
      max_response_tokens: 4000

# Что запрещено. Опционально, для подстраховки.
exclude:
  # Глобальные паттерны (glob)
  - pattern: "*delete_*"
  - pattern: "*.admin_*"
  # По конкретному tool
  - server: fetch
    tool: fetch_txt                # запретить конкретный tool на server

# Опциональные лимиты
limits:
  max_calls_per_session: 500       # защита от runaway agent
  max_calls_per_tool: 100          # per-tool
  max_session_duration_seconds: 3600  # TTL сессии

# Опциональные policy overrides
policy:
  redact_tags: ["private-*", "salary-*"]   # для response truncation в Phase 3
  max_response_tokens: 4000                # default для всех tools в profile
  audit_level: full                        # full | metadata_only | none
```

## Поля

### `name` (обязательно)

- Тип: string, kebab-case.
- ≤ 64 chars.
- Должно совпадать с именем файла без расширения (`developer-tools.yaml` → `name: developer-tools`).
- Pydantic validator: `^[a-z][a-z0-9-]*[a-z0-9]$`.

### `description` (обязательно)

- ≤ 200 chars.
- Видно в `audit` log и при `GET /admin/profiles` (Phase 4).
- Не используется для runtime logic.

### `include` (обязательно, минимум 1 элемент)

Список разрешённых tools. Каждый элемент:

- `server` (обязательно): имя upstream MCP-сервера из `upstream.yaml`.
- `tools` (опционально): список конкретных tools. Если не указано — все tools с этого server.
- `policy` (опционально): override глобального `policy` для этого server'а.

**Важно**: `include` обрабатывается ДО `exclude`. Если tool есть в `include` И `exclude` — он запрещён (deny-wins).

### `exclude` (опционально)

Чёрный список. Каждый элемент:

- `pattern` (опционально): glob-паттерн, матчится против `<server>.<tool>`. `*` = любая последовательность, `?` = один символ.
- `server` + `tool` (опционально): точечное исключение конкретного tool.

**Лимит**: ≤ 1000 элементов (защита от misconfigured YAML с миллионом правил).

### `limits` (опционально)

- `max_calls_per_session`: integer ≥ 1. При превышении — MCP error `-32000` с сообщением "session limit reached".
- `max_calls_per_tool`: integer ≥ 1. Per-tool счётчик.
- `max_session_duration_seconds`: integer ≥ 60. После — session считается expired, `tools/call` отвечает ошибкой.

Если не указано — defaults: `max_calls_per_session=1000`, `max_calls_per_tool=200`, `max_session_duration_seconds=7200`.

### `policy` (опционально)

Глобальные overrides для всех tools в profile (конкретный server может override'нуть):

- `redact_tags`: список glob-паттернов для тегов в response (Phase 3). Сейчас не используется.
- `max_response_tokens`: integer ≥ 100. Phase 3 truncation. Сейчас не используется.
- `audit_level`: `full` (default) | `metadata_only` (только profile + server + tool + timestamp) | `none` (не писать в audit).

## Примеры

См. [`examples/developer-tools.yaml`](examples/developer-tools.yaml) и [`examples/harness-infra.yaml`](examples/harness-infra.yaml).

## Что НЕ включаем в MVP schema

- **Profile inheritance** (`extends: harness-infra`). Полезно, но усложняет loader. Phase 2.
- **Per-upstream выбор** (какой Hindsight bank per profile). Phase 2 (см. OQ-hub-006).
- **Time-based access** («разрешить только в рабочие часы»). YAGNI.
- **Tool-level RBAC** (конкретный agent может вызывать tool X, но не Y). У нас profile-id достаточно.

## Расширение schema

Когда Kolya хочет добавить поле:

1. Сначала обновить этот файл (`docs/profiles/schema.md`).
2. Обновить Pydantic-модель в `src/hub_mcp/types.py::Profile`.
3. Добавить test case в `tests/test_profile_loader.py`.
4. Если поле меняет runtime behavior — добавить ADR в `docs/decisions/`.

Никогда не добавлять поле только в код без schema.