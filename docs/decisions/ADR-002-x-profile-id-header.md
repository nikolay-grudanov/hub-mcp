# ADR-002 — Profile identification через HTTP-header `X-Profile-Id`

**Status**: Superseded (by ADR-006, 2026-10-10)
**Date**: 2026-10-10
**Superseded by**: [ADR-006](ADR-006-skeleton-core-no-profiles-no-ui.md) — per-profile фильтрация отложена в Phase 3+, MVP работает без профилей.

> **Внимание**: ADR-002 остаётся как записанное намерение, но **не реализуется в MVP**. Решение Kolya 2026-10-10: «Профили тоже уберем из списка работ. Нам надо создать хорошее ядро». Если Phase 3+ восстановит per-profile фильтрацию — этот ADR становится актуальным снова. Если нет — формально остаётся «отложен, не реализован».

## Context

Hub должен различать, какие tools отдавать разным runtime (Hermes profile `harness`, Hermes profile `researcher`, GigaCode project profile, zai-copilot, и т.д.). Каждое подключение MCP-клиента — отдельная сессия. Внутри сессии нужно знать, какой profile применять.

Варианты передачи profile-id от клиента к hub:

- (a) **HTTP-header** при подключении (`X-Profile-Id: developer-tools` или `Authorization: Bearer <token>`).
- (b) **Sub-protocol selection** (MCP `initialize` принимает `_meta.profile_id` или аналог).
- (c) **Out-of-band registration** — runtime регистрирует session в hub перед подключением, получает session-id, передаёт его в header.
- (d) **Per-profile listen port** — hub слушает на разных портах для разных профилей (`46381` = `developer-tools`, `46382` = `harness-infra`).
- (e) **Per-profile connect URL** — `http://hub/profiles/developer-tools/mcp`.

## Decision

**MVP использует HTTP-header `X-Profile-Id: <profile-name>`** для идентификации профиля. **Phase 2 добавляет опциональный `Authorization: Bearer <token>` для rotation без правки конфигов.**

### Почему header, а не остальное

- **(a) header** — стандартный HTTP механизм, поддерживается всеми MCP-клиентами (`headers:` поле в Hermes / GigaCode / OpenCode / Qwen / Claude Code config). Не требует изменения клиентов. Не требует per-profile инфраструктуры (порты, URL'ы).
- **(b) sub-protocol** — не стандартизовано MCP, придётся ломать совместимость. Все клиенты сломаются.
- **(c) out-of-band registration** — двухфазный handshake, добавляет +1 round-trip и +1 точку отказа. Не даёт ничего, чего не даёт header.
- **(d) per-port** — операционная пытка (N портов на хост), firewall проблемы, нет центрального audit log.
- **(e) per-URL path** — работает, но усложняет конфиг клиентов (`url: http://hub/profiles/developer-tools/mcp` vs просто `url: http://hub/mcp` + header). Header чище.

### Header name

- **`X-Profile-Id`** — прямой, понятный, custom X-header по конвенции.
- Альтернативы: `X-Hub-Profile`, `Harness-Profile`. Выбираем `X-Profile-Id` — короткий, нейтральный к бренду.

### Token variant (Phase 2)

Phase 2 (production polish) добавляет `Authorization: Bearer <token>` для rotation. Hub читает token → смотрит в `~/.harness-hub/tokens.yaml` → находит profile. Backward compatible: если есть оба header'а, `Authorization` побеждает.

### CORS preflight

Если клиент — браузерный MCP Inspector, preflight OPTIONS шлёт `Access-Control-Request-Headers: x-profile-id`. Hub должен отвечать `Access-Control-Allow-Headers: x-profile-id` для CORS preflight. Это +5 строк в middleware.

## Consequences

**Плюсы**:

- **Нулевая стоимость входа**: все MCP-клиенты уже умеют HTTP headers. Не нужны новые фичи в Hermes / GigaCode.
- **Single-port**: hub слушает на одном порту 46380 для всех профилей. Простой firewall, простой audit log.
- **Per-runtime customization**: каждый runtime имеет свою запись в `mcp_servers` со своим `X-Profile-Id`. Конфиг явно показывает, какой набор tools у какого runtime.

**Минусы**:

- **Header виден в debug-логах клиента**. Не критично для profile-name (не secret), но если потом добавим token в header — нужен redaction в client-side логах.
- **Header может быть stripped** CORS proxy / firewall. Локально не проблема; на multi-host (Phase 4) — обходимо mTLS.
- **Open header = no auth**. Для localhost допустимо. Для multi-host нужна token-варианта. **Для admin API auth уже используется отдельный механизм** (см. ADR-005).

## Alternatives considered

**Без header'а — через URL path**. `http://hub/profiles/<name>/mcp`. Минусы: длиннее, ломает стандартный `mcp_servers.url`, не даёт никакого выигрыша.

**Per-profile port**. `developer-tools` на 46381. Минусы: N портов на хост, нет shared audit log, firewall rules.

**Без профилей — runtime сам выбирает, какие tools вызывать через `<server>.<tool>`**. Hub просто проксирует все. Минусы: защиты нет (любой runtime вызовет любой tool), экономии на tool schema нет.

## References

- Hermes MCP config schema (`~/.hermes/profiles/harness/config.yaml` — поле `headers:` для HTTP MCP).
- MCP Python SDK: `mcp.client.streamable_http` принимает произвольные headers.
- ADR-001 — почему не форкаем SCP (в SCP нет профилей, есть только tool routing через `<server>.<tool>` namespace).