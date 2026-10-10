"""Tests for AuditWriter + AuditEvent (spec-002 Task 4.1)."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from hub_mcp.audit import AuditEvent, AuditWriter


@pytest.fixture
def mock_hindsight() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Mock Hindsight endpoint; tests can inspect captured requests."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "mem_123"})

    return httpx.MockTransport(handler), captured


def test_log_event_writes_to_hindsight(
    mock_hindsight: tuple[httpx.MockTransport, list[httpx.Request]],
) -> None:
    """Successful Hindsight POST with correct tag and body."""
    transport, captured = mock_hindsight
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=transport,
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="fetch",
        tool="fetch_html",
        qualified_name="fetch.fetch_html",
        success=True,
        response_size=1234,
        duration_ms=50,
    )
    asyncio.run(writer.log_event(event))
    assert len(captured) == 1
    body = captured[0]
    content = body.content.decode() if isinstance(body.content, bytes) else body.content
    assert "mcp-audit-fetch-fetch_html-2026-10-10" in content


def test_log_event_hindsight_down_does_not_raise() -> None:
    """Hindsight 503 → AuditWriter swallows error (no raise)."""
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=False,
    )
    asyncio.run(writer.log_event(event))  # must not raise


def test_log_event_transport_error_does_not_raise() -> None:
    """httpx.ConnectError → AuditWriter swallows."""
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused"))
        ),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=True,
    )
    asyncio.run(writer.log_event(event))


def test_audit_event_tag_format() -> None:
    """Tag is mcp-audit-{server}-{tool}-{date}."""
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="fetch",
        tool="fetch_html",
        qualified_name="fetch.fetch_html",
        success=True,
    )
    today = date(2026, 10, 10)
    assert event.tag(today) == "mcp-audit-fetch-fetch_html-2026-10-10"


def test_log_event_disabled_is_noop() -> None:
    """If AuditWriter enabled=False, log_event is no-op."""
    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),  # would fail if called
        enabled=False,
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=True,
    )
    asyncio.run(writer.log_event(event))  # no-op, no raise


def test_log_event_4xx_logs_warning_does_not_raise() -> None:
    """Hindsight 4xx → log_event logs warning but does not raise."""
    import logging

    captured_logs: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_logs.append(record)

    handler = _Capture()
    logging.getLogger("hub_mcp.audit").addHandler(handler)
    logging.getLogger("hub_mcp.audit").setLevel(logging.WARNING)

    writer = AuditWriter(
        bank_id="default",
        base_url="http://hindsight:8888/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(401)),
    )
    event = AuditEvent(
        timestamp="2026-10-10T12:00:00Z",
        server="x",
        tool="y",
        qualified_name="x.y",
        success=True,
    )
    asyncio.run(writer.log_event(event))  # no raise
    assert any("audit failed" in r.getMessage() for r in captured_logs)


def test_log_event_async_context_manager() -> None:
    """AuditWriter supports async context manager."""

    async def inner() -> None:
        async with AuditWriter(
            bank_id="default",
            base_url="http://hindsight:8888/v1",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"id": "x"})),
        ) as writer:
            event = AuditEvent(
                timestamp="2026-10-10T12:00:00Z",
                server="x",
                tool="y",
                qualified_name="x.y",
                success=True,
            )
            await writer.log_event(event)

    asyncio.run(inner())
