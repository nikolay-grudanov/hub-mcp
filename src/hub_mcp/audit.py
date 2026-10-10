"""Hindsight audit log writer for hub-mcp tool calls.

Tag format: mcp-audit-{server}-{tool}-{YYYY-MM-DD} (see AGENT_CONTEXT.md §6).
Best-effort: Hindsight failures are logged but do not raise — audit is
observability, not a critical path.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuditEvent(BaseModel):
    """One tool call event."""

    timestamp: str  # ISO 8601 with Z
    server: str
    tool: str
    qualified_name: str
    success: bool
    response_size: int = 0
    duration_ms: int = 0
    error_message: str | None = None

    def tag(self, on_date: date | None = None) -> str:
        """Generate Hindsight tag for this event."""
        d = on_date or datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).date()
        return f"mcp-audit-{self.server}-{self.tool}-{d.isoformat()}"


class AuditWriter:
    """Best-effort Hindsight audit writer."""

    def __init__(
        self,
        *,
        bank_id: str,
        base_url: str = "http://127.0.0.1:8888/v1",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self._bank_id = bank_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._enabled = enabled
        if transport is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def __aenter__(self) -> AuditWriter:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def log_event(self, event: AuditEvent) -> None:
        """Write event to Hindsight. Best-effort: never raises."""
        if not self._enabled:
            return

        url = f"{self._base_url}/{self._bank_id}/memories"
        try:
            response = await self._client.post(
                url,
                json={
                    "content": event.model_dump_json(),
                    "tags": [event.tag()],
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "hindsight audit failed: status=%s body=%s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as e:
            logger.warning("hindsight audit transport error: %s", e)
