"""Tests for Starlette ASGI server (spec-002 Task 5.1, post-ADR-007).

Why no async tests: pytest-asyncio creates a new event-loop task per test.
mcp.client.streamable_http_client creates anyio task_group with cancel scopes
bound to the task at creation. When lifespan exits in a different task than
where streamable_http_client was entered, the cancel-scope-exited-in-different-
task RuntimeError fires (even with httpx.AsyncClient + lifespan_context).

Solution: each test is sync and runs the entire scenario (lifespan + requests
+ shutdown) via a single asyncio.run() call. That keeps everything in one task,
matching direct_test.py behavior that works against real context7.

Mock upstream uses httpx.MockTransport + spec-compliant SSE responses.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from hub_mcp.server import create_app

MOCK_PROTOCOL_VERSION = "2025-11-25"
MOCK_SESSION_ID = "test-session-server"


def sse_response(body_json: dict[str, Any]) -> httpx.Response:
    payload = json.dumps(body_json)
    sse = f"event: message\ndata: {payload}\n\n"
    return httpx.Response(
        200,
        content=sse.encode(),
        headers={"Content-Type": "text/event-stream"},
    )


def make_initialize_response(server_name: str = "MockServer") -> httpx.Response:
    r = sse_response(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "protocolVersion": MOCK_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": server_name, "version": "1.0"},
            },
        }
    )
    r.headers["Mcp-Session-Id"] = MOCK_SESSION_ID
    return r


def make_tools_list_response(tool_names: list[str]) -> httpx.Response:
    return sse_response(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "result": {
                "tools": [
                    {
                        "name": n,
                        "description": f"Mock {n}",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                    for n in tool_names
                ]
            },
        }
    )


def make_call_tool_response(text: str) -> httpx.Response:
    return sse_response(
        {
            "jsonrpc": "2.0",
            "id": "3",
            "result": {"content": [{"type": "text", "text": text}]},
        }
    )


class MockUpstream:
    def __init__(self, tools: list[str] | None = None) -> None:
        self.tools = tools or ["fetch_html"]
        self.tool_result: str = "<html>OK</html>"
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "DELETE":
            r = httpx.Response(200)
            r.headers["Mcp-Session-Id"] = MOCK_SESSION_ID
            return r
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            return make_initialize_response("MockServer")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return make_tools_list_response(self.tools)
        if method == "tools/call":
            return make_call_tool_response(self.tool_result)
        return httpx.Response(404)


# === Configurations ===

VALID_CONFIG_ONE_UPSTREAM = """
listen:
  host: 127.0.0.1
  port: 46380
hindsight:
  url: http://127.0.0.1:8888/v1
  bank_id: default
  enabled: false
upstream:
  - name: fetch
    url: http://localhost:46381/mcp
    enabled: false
    timeout: 5.0
"""

VALID_CONFIG_TWO_UPSTREAM_MOCKED = """
listen:
  host: 127.0.0.1
  port: 46380
hindsight:
  url: http://127.0.0.1:8888/v1
  bank_id: default
  enabled: false
upstream:
  - name: fetch
    url: http://localhost:46381/mcp
    enabled: true
    timeout: 5.0
  - name: ghost
    url: http://localhost:9999/mcp
    enabled: false
    timeout: 5.0
"""


# === Helpers: synchronous wrapper around full async scenario ===


def run_scenario(
    config_yaml: str,
    tmp_path: Path,
    *,
    mock_factory: Any = None,
    transport_overrides: dict[str, Any] | None = None,
    requests_to_run: list[tuple[str, str, dict[str, Any]]] = None,
) -> list[httpx.Response]:
    """Run full async scenario (lifespan + requests + shutdown) in one task.

    Args:
        config_yaml: hub-mcp config YAML text.
        tmp_path: pytest tmp_path fixture.
        mock_factory: callable returning a MockUpstream instance (for default case).
        transport_overrides: explicit dict of name -> httpx.MockTransport instance.
        requests_to_run: list of (method, path, json_body) to execute.

    Returns:
        List of httpx.Response objects in order.
    """
    if requests_to_run is None:
        requests_to_run = []
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_yaml)

    if mock_factory is not None and transport_overrides is None:
        mock = mock_factory()
        transport_overrides = {"fetch": httpx.MockTransport(mock)}
    elif transport_overrides is None:
        transport_overrides = {}

    app = create_app(
        config_path=config_path,
        transport_overrides=transport_overrides,
    )

    async def scenario() -> list[httpx.Response]:
        # Manually run lifespan in this task (not via TestClient)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                responses: list[httpx.Response] = []
                for method, path, body in requests_to_run:
                    if method == "GET":
                        r = await ac.get(path)
                    elif method == "POST":
                        r = await ac.post(path, json=body)
                    else:
                        raise ValueError(f"unsupported method {method}")
                    responses.append(r)
                return responses

    return asyncio.run(scenario())


# === Tests ===


def test_health_endpoint(tmp_path: Path) -> None:
    """GET /health returns 200 with status, version, uptime."""
    responses = run_scenario(
        VALID_CONFIG_ONE_UPSTREAM,
        tmp_path,
        requests_to_run=[("GET", "/health", {})],
    )
    r = responses[0]
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert isinstance(body["uptime_seconds"], int)


def test_mcp_initialize(tmp_path: Path) -> None:
    """POST /mcp initialize returns serverInfo + capabilities."""
    responses = run_scenario(
        VALID_CONFIG_ONE_UPSTREAM,
        tmp_path,
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MOCK_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                },
            )
        ],
    )
    r = responses[0]
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    assert body["result"]["serverInfo"]["name"] == "hub-mcp"
    assert "tools" in body["result"]["capabilities"]


def test_mcp_method_not_found(tmp_path: Path) -> None:
    """Unknown method → JSON-RPC error -32601."""
    responses = run_scenario(
        VALID_CONFIG_ONE_UPSTREAM,
        tmp_path,
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {"jsonrpc": "2.0", "id": 1, "method": "unknown/method", "params": {}},
            )
        ],
    )
    body = responses[0].json()
    assert body["error"]["code"] == -32601


def test_tools_list_aggregates_enabled_upstream(tmp_path: Path) -> None:
    """tools/list returns qualified names from enabled upstream."""
    responses = run_scenario(
        VALID_CONFIG_TWO_UPSTREAM_MOCKED,
        tmp_path,
        mock_factory=lambda: MockUpstream(tools=["fetch_html", "fetch_markdown"]),
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
        ],
    )
    body = responses[0].json()
    names = {t["name"] for t in body["result"]["tools"]}
    assert names == {"fetch.fetch_html", "fetch.fetch_markdown"}


def test_tools_list_excludes_disabled_upstream(tmp_path: Path) -> None:
    """tools/list does not include disabled upstream tools."""
    responses = run_scenario(
        VALID_CONFIG_TWO_UPSTREAM_MOCKED,
        tmp_path,
        mock_factory=lambda: MockUpstream(tools=["fetch_html"]),
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
        ],
    )
    body = responses[0].json()
    names = {t["name"] for t in body["result"]["tools"]}
    assert all(not n.startswith("ghost.") for n in names), (
        f"disabled upstream leaked into tools/list: {names}"
    )


def test_tools_call_routes_to_upstream(tmp_path: Path) -> None:
    """tools/call with qualified name routes to upstream and returns result."""
    mock_holder: dict[str, MockUpstream] = {}

    def factory() -> MockUpstream:
        m = MockUpstream(tools=["fetch_html"])
        m.tool_result = "<html>custom-content</html>"
        mock_holder["mock"] = m
        return m

    responses = run_scenario(
        VALID_CONFIG_TWO_UPSTREAM_MOCKED,
        tmp_path,
        mock_factory=factory,
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "fetch.fetch_html",
                        "arguments": {"url": "https://example.com"},
                    },
                },
            )
        ],
    )
    body = responses[0].json()
    assert "result" in body, f"expected result, got {body}"
    content = body["result"].get("content", [])
    assert content[0]["text"] == "<html>custom-content</html>"


def test_tools_call_invalid_qualified_name(tmp_path: Path) -> None:
    """tools/call with name lacking '.' → -32602."""
    responses = run_scenario(
        VALID_CONFIG_ONE_UPSTREAM,
        tmp_path,
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "no-dot-here", "arguments": {}},
                },
            )
        ],
    )
    body = responses[0].json()
    assert body["error"]["code"] == -32602


def test_tools_call_unknown_upstream(tmp_path: Path) -> None:
    """tools/call with unknown upstream → -32601."""
    responses = run_scenario(
        VALID_CONFIG_TWO_UPSTREAM_MOCKED,
        tmp_path,
        mock_factory=lambda: MockUpstream(tools=["fetch_html"]),
        requests_to_run=[
            (
                "POST",
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "ghost.fetch", "arguments": {}},
                },
            )
        ],
    )
    body = responses[0].json()
    assert body["error"]["code"] == -32601
