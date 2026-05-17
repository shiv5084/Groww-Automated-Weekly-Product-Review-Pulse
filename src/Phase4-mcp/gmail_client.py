"""Gmail draft client — create draft only via deployed MCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import MCPSettings
    from .mcp_http_client import MCPHttpClient

logger = logging.getLogger(__name__)


class MCPGmailClient:
    """Creates Gmail drafts via POST /create_email_draft (never sends)."""

    def __init__(self, http: "MCPHttpClient", settings: "MCPSettings"):
        self._http = http
        self._settings = settings

    def create_draft(
        self,
        body: str,
        subject: str,
        doc_url: str,
        to: str | None = None,
    ) -> str:
        recipient = (to or self._settings.email_recipient).strip()
        full_body = (
            f"{body.strip()}\n\n"
            f"---\n"
            f"Master pulse log (Google Doc): {doc_url}\n"
        )

        logger.info("Creating Gmail draft for %s …", recipient)
        result = self._http.post_tool(
            "/create_email_draft",
            {
                "to": recipient,
                "subject": subject,
                "body": full_body,
            },
        )

        draft_id = result.get("draft_id")
        if not draft_id:
            raise ValueError("MCP server did not return draft_id")
        logger.info("Gmail draft created — draft_id=%s", draft_id)
        return str(draft_id)

    def build_subject(self, week_label: str) -> str:
        prefix = self._settings.email_subject_prefix
        return f"[Weekly Pulse] {prefix} — Week of {week_label}"
