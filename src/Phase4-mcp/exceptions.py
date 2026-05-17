"""Phase 4 MCP client exceptions."""


class ConfigurationError(Exception):
    """Missing or invalid configuration."""


class MCPError(Exception):
    """MCP HTTP server returned an error or was unreachable."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.details = details


class MCPRejectedError(MCPError):
    """MCP server rejected the action (approval layer)."""
