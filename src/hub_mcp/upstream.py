"""HTTP client to upstream MCP servers (spec-002 Task 3.1, post-ADR-007).

Thin wrapper over `mcp.client.streamable_http.streamable_http_client`.
Owns a long-lived persistent SSE connection to one upstream MCP server,
manages the session lifecycle (initialize → notifications/initialized → DELETE).

See ADR-007 for design rationale.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


class UpstreamNotStartedError(RuntimeError):
    """Raised when calling list_tools/call_tool before start()."""


class UpstreamUnavailableError(RuntimeError):
    """Raised when upstream MCP server is unreachable or fails to initialize."""


class UpstreamClient:
    """Persistent MCP client to one upstream server.

    Lifecycle:
        1. start() opens streamable_http transport, sends initialize, sends
           notifications/initialized. Stores session_id, protocol_version,
           server_info from initialize response.
        2. list_tools() / call_tool() proxy through the live session.
        3. stop() sends HTTP DELETE to terminate session, closes streams.

    Thread-safety: start() and stop() are idempotent and not safe to call
    concurrently with each other or with list_tools/call_tool. Use from a
    single async context (Starlette lifespan).
    """

    def __init__(
        self,
        *,
        name: str,
        url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._name = name
        self._url = url
        self._timeout = timeout
        self._transport = transport
        self._http_client: httpx.AsyncClient | None = None
        self._streams_cm: Any = None
        self._session: ClientSession | None = None
        self._session_cm: Any = None
        self.protocol_version: str | None = None
        self.server_info: Any = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_started(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        """Open persistent connection, send initialize + notifications/initialized.

        Raises:
            UpstreamUnavailableError: cannot reach upstream or initialize fails.
        """
        if self._session is not None:
            return

        try:
            if self._transport is not None:
                self._http_client = httpx.AsyncClient(
                    transport=self._transport, timeout=self._timeout
                )
                self._streams_cm = streamable_http_client(
                    url=self._url,
                    http_client=self._http_client,  # type: ignore[arg-type]
                )
                read, write = await self._streams_cm.__aenter__()
            else:
                self._streams_cm = streamable_http_client(url=self._url)
                read, write = await self._streams_cm.__aenter__()

            self._session = ClientSession(read, write)
            self._session_cm = self._session
            await self._session_cm.__aenter__()

            init_result = await self._session.initialize()
            self.protocol_version = init_result.protocol_version
            self.server_info = init_result.server_info

            # Send notifications/initialized per MCP spec
            from mcp import types as mcp_types

            await self._session.send_notification(mcp_types.InitializedNotification())

            logger.info(
                "upstream %s connected: %s v%s (protocol %s)",
                self._name,
                self.server_info.name,
                self.server_info.version,
                self.protocol_version,
            )
        except UpstreamUnavailableError:
            raise
        except BaseException as e:
            # SDK's streamable_http_client may leave cancel scopes in a different
            # task; our _cleanup_partial swallows those secondary errors.
            await self._cleanup_partial()
            if isinstance(e, UpstreamUnavailableError):
                raise
            raise UpstreamUnavailableError(
                f"upstream {self._name!r} failed to start: {type(e).__name__}: {e}"
            ) from e

    async def _cleanup_partial(self) -> None:
        """Best-effort cleanup of partial state from a failed start()."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None
        if self._streams_cm is not None:
            try:
                await self._streams_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._streams_cm = None
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None
        self._session = None

    async def stop(self) -> None:
        """Send DELETE to terminate session, close streams."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("upstream %s session close failed: %s", self._name, e)
            self._session_cm = None
        if self._streams_cm is not None:
            try:
                await self._streams_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("upstream %s streams close failed: %s", self._name, e)
            self._streams_cm = None
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.warning("upstream %s http client close failed: %s", self._name, e)
            self._http_client = None
        self._session = None
        self.protocol_version = None
        self.server_info = None

    def _require_started(self) -> ClientSession:
        if self._session is None:
            raise UpstreamNotStartedError(
                f"upstream {self._name!r} not started; call start() first"
            )
        return self._session

    async def list_tools(self) -> list[Any]:
        """Return list of Tool objects from upstream's tools/list response."""
        session = self._require_started()
        result = await session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on upstream. Returns CallToolResult."""
        session = self._require_started()
        return await session.call_tool(name=name, arguments=arguments or {})
