"""Starlette ASGI app for hub-mcp.

Endpoints:
- GET /health → 200 OK
- POST /mcp → MCP JSON-RPC 2.0 (initialize, tools/list, tools/call)

Per ADR-007: UpstreamClient uses `mcp.client.streamable_http.streamable_http_client`.
We open persistent SSE streams to every enabled upstream at lifespan startup,
close them on shutdown. tools/list aggregates from all connected upstream.
tools/call routes by `<server>.<tool>` qualified name.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hub_mcp.audit import AuditEvent, AuditWriter
from hub_mcp.config import HubConfig, load_config
from hub_mcp.exceptions import UpstreamUnavailableError
from hub_mcp.upstream import UpstreamClient

logger = logging.getLogger(__name__)

SERVER_VERSION = "0.1.0"
JSONRPC_VERSION = "2025-11-25"


def _jsonrpc_error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _jsonrpc_result(result: dict[str, Any], request_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def _handle_initialize(request: Request) -> dict[str, Any]:
    body = await request.json()
    return _jsonrpc_result(
        result={
            "protocolVersion": JSONRPC_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hub-mcp", "version": SERVER_VERSION},
        },
        request_id=body.get("id"),
    )


async def _handle_tools_list(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    upstream_map: dict[str, UpstreamClient] = request.app.state.upstream_map

    async def fetch_one(client: UpstreamClient) -> list[dict[str, Any]]:
        try:
            tools = await client.list_tools()
        except UpstreamUnavailableError as e:
            logger.warning("upstream %s tools/list failed: %s", client.name, e)
            return []
        except Exception as e:  # noqa: BLE001 — defensive, log and skip
            logger.warning("upstream %s tools/list unexpected error: %s", client.name, e)
            return []
        return [
            {
                "name": f"{client.name}.{t.name}",
                "description": getattr(t, "description", "") or "",
                "inputSchema": getattr(t, "inputSchema", None)
                or {"type": "object", "properties": {}},
            }
            for t in tools
        ]

    tasks = [fetch_one(client) for client in upstream_map.values()]
    results_per_upstream = await asyncio.gather(*tasks, return_exceptions=False)
    tools = [tool for upstream_tools in results_per_upstream for tool in upstream_tools]

    return _jsonrpc_result(result={"tools": tools}, request_id=request_id)


async def _handle_tools_call(request: Request) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    params = body.get("params", {})
    qualified_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if "." not in qualified_name:
        return _jsonrpc_error(
            code=-32602,
            message=f"tool name must be '<server>.<tool>': got {qualified_name!r}",
            request_id=request_id,
        )
    server_name, tool_name = qualified_name.split(".", 1)

    upstream_map: dict[str, UpstreamClient] = request.app.state.upstream_map
    audit: AuditWriter = request.app.state.audit

    if server_name not in upstream_map:
        return _jsonrpc_error(
            code=-32601,
            message=f"tool {qualified_name!r} not found (unknown upstream {server_name!r})",
            request_id=request_id,
        )

    client = upstream_map[server_name]
    start_time = time.time()
    timestamp = datetime.now(UTC).isoformat()

    try:
        result = await client.call_tool(tool_name, arguments)
        duration_ms = int((time.time() - start_time) * 1000)
        response_size = len(str(result).encode())
        await audit.log_event(
            AuditEvent(
                timestamp=timestamp,
                server=server_name,
                tool=tool_name,
                qualified_name=qualified_name,
                success=True,
                response_size=response_size,
                duration_ms=duration_ms,
            )
        )
        # Tool result is mcp.types.CallToolResult; serialize content list
        result_dict = _serialize_call_tool_result(result)
        return _jsonrpc_result(result=result_dict, request_id=request_id)
    except UpstreamUnavailableError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await audit.log_event(
            AuditEvent(
                timestamp=timestamp,
                server=server_name,
                tool=tool_name,
                qualified_name=qualified_name,
                success=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )
        )
        return _jsonrpc_error(
            code=-32002,
            message=f"upstream {server_name!r} unavailable: {e}",
            request_id=request_id,
        )


def _serialize_call_tool_result(result: Any) -> dict[str, Any]:
    """Convert CallToolResult to JSON-RPC result dict.

    CallToolResult has .content (list of TextContent|ImageContent|EmbeddedResource)
    and .isError (optional bool).
    """
    if hasattr(result, "model_dump"):
        return result.model_dump(exclude_none=True)
    # Fallback for plain dicts
    return dict(result)


METHOD_DISPATCH: dict[str, Any] = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


async def mcp_endpoint(request: Request) -> Response:
    """POST /mcp — JSON-RPC 2.0 dispatcher."""
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(_jsonrpc_error(code=-32700, message=f"invalid JSON: {e}"))

    method = body.get("method")
    request_id = body.get("id")

    handler = METHOD_DISPATCH.get(method)
    if handler is None:
        return JSONResponse(
            _jsonrpc_error(
                code=-32601,
                message=f"method not found: {method!r}",
                request_id=request_id,
            )
        )

    result = await handler(request)
    return JSONResponse(result)


async def health_endpoint(request: Request) -> Response:
    uptime = int(time.time() - request.app.state.start_time)
    return JSONResponse({"status": "ok", "version": SERVER_VERSION, "uptime_seconds": uptime})


@asynccontextmanager
async def _lifespan(app: Starlette):
    """Start upstream connections + audit writer; clean up on shutdown.

    Per ADR-007: opens persistent SSE streams to all enabled upstream MCPs.
    On startup failure of individual upstream, logs warning and skips —
    other upstream still serve traffic.
    """
    config: HubConfig = app.state.config
    app.state.start_time = time.time()

    transport_overrides: dict[str, httpx.AsyncBaseTransport] = getattr(
        app.state, "transport_overrides", {}
    )

    # Open upstream connections (best-effort: failures logged, not fatal)
    upstream_map: dict[str, UpstreamClient] = {}
    for u in config.upstream:
        if not u.enabled:
            continue
        transport = transport_overrides.get(u.name)
        client = UpstreamClient(name=u.name, url=u.url, timeout=u.timeout, transport=transport)
        try:
            await client.start()
            upstream_map[u.name] = client
        except UpstreamUnavailableError as e:
            logger.warning("upstream %s unavailable at startup: %s", u.name, e)
            # Continue without this upstream — others still work
    app.state.upstream_map = upstream_map

    audit = AuditWriter(
        bank_id=config.hindsight.bank_id,
        base_url=config.hindsight.url,
        enabled=config.hindsight.enabled,
    )
    app.state.audit = audit

    try:
        yield
    finally:
        # Close all upstream connections (best-effort)
        for client in list(upstream_map.values()):
            try:
                await client.stop()
            except Exception as e:  # noqa: BLE001 — defensive
                logger.warning("upstream %s stop failed: %s", client.name, e)
        await audit.__aexit__(None, None, None)


def create_app(
    *,
    config_path: Path | None = None,
    transport_overrides: dict[str, httpx.AsyncBaseTransport] | None = None,
) -> Starlette:
    """Build the Starlette app with the given config."""
    cfg = load_config(config_path)
    app = Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/mcp", mcp_endpoint, methods=["POST"]),
        ],
        lifespan=_lifespan,
    )
    app.state.config = cfg
    app.state.transport_overrides = transport_overrides or {}
    return app


_app_instance: Starlette | None = None


def get_app() -> Starlette:
    """Return the lazily-initialized module-level app."""
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance
