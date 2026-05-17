"""Orchestrates Phase 4 publish: master doc append + Gmail draft + correlation log."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import MCPSettings
from .gmail_client import MCPGmailClient
from .google_docs_client import MCPGoogleDocsClient
from .mcp_http_client import MCPHttpClient
from .publish_result import PublishResult, write_publish_log

logger = logging.getLogger(__name__)


def week_label_from_path(path: Path) -> str:
    match = re.search(r"pulse_(\d{4}-\d{2}-\d{2})", path.name)
    if match:
        try:
            dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            return dt.strftime("%d %b %Y")
        except ValueError:
            pass
    return datetime.today().strftime("%d %b %Y")


class PulsePublisher:
    def __init__(self, settings: MCPSettings | None = None, project_root: Path | None = None):
        root = project_root or Path(__file__).resolve().parent.parent.parent
        self.settings = settings or MCPSettings.load(project_root=root)
        self._http = MCPHttpClient(
            base_url=self.settings.base_url,
            timeout_seconds=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
            retry_backoff_seconds=self.settings.retry_backoff_seconds,
        )
        self._docs = MCPGoogleDocsClient(self._http, self.settings)
        self._gmail = MCPGmailClient(self._http, self.settings)

    def publish(
        self,
        pulse_md_path: Path,
        pulse_txt_path: Path | None = None,
        week_label: str | None = None,
    ) -> tuple[PublishResult, Path]:
        if not pulse_md_path.exists():
            raise FileNotFoundError(f"Pulse Markdown not found: {pulse_md_path}")

        label = week_label or week_label_from_path(pulse_md_path)
        md_content = pulse_md_path.read_text(encoding="utf-8")
        txt_path = pulse_txt_path
        if txt_path is None:
            candidate = pulse_md_path.with_suffix(".txt")
            txt_path = candidate if candidate.exists() else None
        email_body = (
            txt_path.read_text(encoding="utf-8")
            if txt_path
            else md_content
        )

        self._http.health_check()

        doc_id, doc_url = self._docs.append_pulse_section(md_content, label)
        subject = self._gmail.build_subject(label)
        draft_id = self._gmail.create_draft(
            body=email_body,
            subject=subject,
            doc_url=doc_url,
        )

        run_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        result = PublishResult(
            document_id=doc_id,
            document_url=doc_url,
            draft_id=draft_id,
            run_timestamp=run_ts,
            week_label=label,
            pulse_md_path=str(pulse_md_path),
            pulse_txt_path=str(txt_path) if txt_path else None,
        )
        log_path = write_publish_log(result, self.settings.logs_dir)
        logger.info("Publish correlation log: %s", log_path)
        return result, log_path
