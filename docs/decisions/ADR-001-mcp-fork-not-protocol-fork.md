# ADR-001 — hub-mcp — это собственный проект, а не fork протокола MCP

**Status**: Accepted
**Date**: 2026-10-10

## Context

Изучение [InternScience/scp](https://github.com/InternScience/scp) показало, что Shanghai AI Lab построил «MCP-fork»: взяли Python SDK MCP, добавили Flask-hub для Hub-Spoke orchestration + MQTT/Redis-pubsub для lab/IoT + skill catalog. SCP — это **wire-compatible fork MCP с новыми runtime-слоями** (см. `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md`).

Kolya обсуждает альтернативу: взять `hub_server.py` из SCP и адаптировать под наши runtime.

## Decision

**Мы не форкаем MCP-протокол и не форкаем SCP**. hub-mcp — это **новый, standalone-проект**, который:

1. Использует стандартный MCP Python SDK (`mcp` package от Anthropic, MIT license) как зависимость.
2. Не модифицирует wire-формат JSON-RPC 2.0. Hub — это просто ещё один MCP-сервер, с точки зрения клиента неотличимый от остальных.
3. Не использует код SCP напрямую. Дизайн (Flask hub, Redis state, Aliyun OSS) — это специфика SCP, не общий.

## Consequences

**Плюсы**:

- **Лицензия чистая**: MCP SDK = MIT Anthropic, можно использовать без attribution surprises. SCP = MIT Anthropic на protocol + новый код без явного breakdown — license-compliance риск.
- **Минимальная поверхность**: hub-mcp — это ~150 строк (profile loader + filter + bridge). Не 2k+ строк Flask с глобальным state (см. ADR-004).
- **Стек под Kolya's conventions**: Python + Starlette + uv + pytest (см. `AGENT_CONTEXT.md`), а не Flask + paho-mqtt + Redis + Aliyun OSS.
- **Тестируемость**: можно поднять hub с фиктивным upstream, прогнать через MCP Inspector, без Docker / cloud / MQTT.

**Минусы**:

- **Нет готового hub / lab backend**. Если когда-то захочется Hub-Spoke для scientific tools (как у SCP) — придётся доделывать с нуля. Но это не наш use case сейчас.
- **Свой код поддерживать**: вместо «форкнул и забыл» — сами ведём ~150-300 строк. На таком объёме это плюс, не минус.

## Alternatives considered

**Форкнуть `hub_server.py` из SCP**. Минусы:

- Flask вместо Starlette (см. ADR-003).
- Redis + Aliyun OSS — ненужные зависимости для нашего use case.
- Module-level state через глобальные dict'ы (`servers: Dict[str, Server]`) — тестировать сложно (см. ADR-004).
- `init_app()` на module import — анти-паттерн (см. `references/live-debug-event-driven.md`).
- License ambiguity (см. выше).

**Сразу multi-host distributed hub с mTLS, Redis backing, multi-tenant profiles**. Overengineering для MVP. Откладываем в Phase 4.

## References

- [InternScience/scp wiki page](https://github.com/InternScience/scp)
- `/home/gna/workspase/workspaces/harness/llmwiki/internscience-scp-architecture.md`
- MCP Python SDK: `https://github.com/modelcontextprotocol/python-sdk` (MIT)
- ADR-003 — почему не Flask
- ADR-004 — почему без server-side state