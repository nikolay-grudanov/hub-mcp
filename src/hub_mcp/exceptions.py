"""Hub-specific exceptions."""


class HubMcpError(Exception):
    """Base class for all hub-mcp exceptions."""


class ConfigError(HubMcpError):
    """Config file invalid or unreadable."""


class UpstreamUnavailableError(HubMcpError):
    """Upstream MCP server did not respond."""


class ToolNotFoundError(HubMcpError):
    """Tool not found in any enabled upstream."""
