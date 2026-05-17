"""HTTP client for the deployed Google MCP server (FastAPI on Railway)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .exceptions import MCPError, MCPRejectedError

logger = logging.getLogger(__name__)


class MCPHttpClient:
    """
    Calls the external MCP server's REST endpoints:
      POST /append_to_doc
      POST /create_email_draft
    OAuth credentials are configured on the MCP server (Railway), not in this project.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def health_check(self) -> dict[str, Any]:
        return self._request("GET", "/")

    def list_tools(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/tools")
        if isinstance(data, list):
            return data
        return []

    def post_tool(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json_body=payload)

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    if method == "GET":
                        response = client.get(url)
                    else:
                        response = client.post(url, json=json_body)

                response.raise_for_status()
                if not response.content:
                    return {}

                data = response.json()
                if isinstance(data, dict):
                    self._raise_on_tool_error(data)
                return data

            except (httpx.HTTPError, MCPError, MCPRejectedError) as exc:
                last_exc = exc
                if attempt < self.max_retries and self._is_retryable(exc):
                    wait = self.retry_backoff_seconds * attempt
                    logger.warning(
                        "MCP request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                break

        raise MCPError(
            f"MCP server request failed after {self.max_retries} attempts: {last_exc}"
        ) from last_exc

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (MCPError, MCPRejectedError)):
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return True

    @staticmethod
    def _raise_on_tool_error(data: dict[str, Any]) -> None:
        status = data.get("status")
        if status == "rejected":
            raise MCPRejectedError(
                data.get("message", "Action rejected by MCP approval layer"),
                details=data.get("details"),
            )
        if status == "error":
            raise MCPError(
                data.get("message", "MCP tool returned error"),
                details=data.get("details"),
            )
