"""Google Docs publish client — append to master doc via deployed MCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .exceptions import MCPError
from .publish_result import document_url

if TYPE_CHECKING:
    from .config import MCPSettings
    from .mcp_http_client import MCPHttpClient

logger = logging.getLogger(__name__)


class MCPGoogleDocsClient:
    """Appends pulse content to GOOGLE_MASTER_DOC_ID via POST /append_to_doc."""

    def __init__(self, http: "MCPHttpClient", settings: "MCPSettings"):
        self._http = http
        self._settings = settings

    def append_pulse_section(
        self,
        markdown: str,
        week_label: str,
        doc_id: str | None = None,
    ) -> tuple[str, str]:
        doc_id = (doc_id or self._settings.master_doc_id).strip()
        if not doc_id:
            raise MCPError("document_id is required for append")

        header = f"\n\n---\n## Groww Weekly Pulse — {week_label}\n\n"
        content = f"{header}{markdown.strip()}\n"

        logger.info("Appending pulse section to master doc %s …", doc_id)
        result = self._http.post_tool(
            "/append_to_doc",
            {"doc_id": doc_id, "content": content},
        )

        returned_id = result.get("document_id") or doc_id
        url = document_url(returned_id)
        logger.info("Master doc append OK — %s", url)
        return returned_id, url
