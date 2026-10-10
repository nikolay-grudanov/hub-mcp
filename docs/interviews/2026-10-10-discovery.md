# Interview / discovery — hub-mcp

**Дата**: 2026-10-10
**Участники**: Kolya (user) + Hermes-harness (agent, профиль `harness`)
**Контекст**: решение о начале нового проекта `hub-mcp`.

## Что было до разговора

Kolya попросил изучить [InternScience/scp](https://github.com/InternScience/scp) через `/learn` (10 октября 2026). Результат — `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md`, 24 KB, с разбором Shanghai AI Lab MCP-fork.

## Триггер обсуждения

Kolya спросил, как SCP поможет с настройкой и развитием harness. После детального объяснения архитектуры — спросил, чем конкретно.

## Ключевые реплики Kolya (восстановлено по логике чата)

> «У нас несколько hermes профилей, opencode профили в проектах, zcode от zai для copilot разработки и я часто везде копирую и дублирую одни и теже mcp»

→ Боль №1: дублирование MCP между runtime.

> «Кажется мы доросли для создания такого hub»

→ Решение: пилить свой hub.

> «Возможно ли сделать профили с набором доступных mcp tools? Просто не хочу чтоб все тулы были всем доступны»

→ Боль №2: нет per-runtime access control.

> «И второй вопрос, поможет ли это уменьшить потребления токенов. Ведь полное описание всех tools уходит в модель»

→ Боль №3: tool schema жрёт контекст (~75k токенов на 250 tools × 300 токенов).

> «Я бы сделал так. Мы подключаем 1 mcp который работает с hub-mcp. В env переменных mcp или в api key указываем название или id или токен профиля»

→ Архитектурное решение: hub = единый MCP, profile-id передаётся через env или header.

> «HTTP header (X-Profile-Id) Это стандартный механизм mcp? Он будет для всех runtime работать?»

→ Вопрос про compatibility. Ответ: header — стандартное поле конфига у всех MCP-клиентов (Hermes / GigaCode / OpenCode / Qwen / Claude Code).

## Решения, принятые в чате

1. **hub = собственный проект, не fork SCP** (позже закреплено в ADR-001).
2. **Profile-id через HTTP-header `X-Profile-Id`** (позже закреплено в ADR-002).
3. **MVP scope**: HTTP upstream + per-profile filter + audit log в Hindsight. stdio upstream и token auth — Phase 2.

## Что НЕ было обсуждено (отложено)

- Web UI для редактирования профилей (Phase 4).
- Multi-host distributed hub (Phase 4).
- Lazy tool loading / мета-tool `hub.search_tools` (Phase 3).
- Circuit breaker / auto-restart upstream (Phase 2).
- Token-based auth с rotation (Phase 2).

## Где живёт проект

`/home/gna/workspase/projects/hub-mcp/` — новый standalone-репозиторий (ещё не закоммичен; ждём «коммить» от Kolya).

## Связь с llmwiki

Дополнение к `/home/gna/workspase/workspaces/harness/llmwiki/`:
- `llmwiki/hub-mcp-project.md` — short pointer page для cross-reference (создаётся в Phase 9 плана, после Kolya review).
- `llmwiki/internscience-scp-architecture.md` — reference-проект, оттуда взяты идеи, ничего не скопировано.

## Open questions, поднятые в чате (закрытые позже)

- **«Что если все tools всем доступны?»** → Phase 0 показал: profile-based filter + audit log = базовая access control. Расширение в Phase 2+.
- **«Стандартный ли механизм HTTP-header для всех runtime?»** → Да, для Hermes / GigaCode / OpenCode / Qwen / Claude Code. Для stdio-only MCP — через `env:` секцию в `mcp_servers` config. Подробности в ADR-002.