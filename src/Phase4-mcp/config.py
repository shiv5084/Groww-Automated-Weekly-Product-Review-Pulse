"""MCP server configuration (deployed HTTP API on Railway)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return _ENV_VAR_PATTERN.sub(_replace, value)


@dataclass
class MCPSettings:
    base_url: str
    master_doc_id: str
    email_recipient: str
    email_subject_prefix: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    logs_dir: Path

    @classmethod
    def load(
        cls,
        project_root: Path | None = None,
        config_path: Path | None = None,
    ) -> "MCPSettings":
        root = project_root or Path(__file__).resolve().parent.parent.parent
        cfg_file = config_path or root / "config" / "mcp_config.json"

        timeout = 30.0
        max_retries = 3
        retry_backoff = 2.0
        base_url = os.environ.get(
            "MCP_SERVER_URL",
            "https://mcp-server-production-5084.up.railway.app",
        ).rstrip("/")

        if cfg_file.exists():
            with cfg_file.open(encoding="utf-8") as fh:
                raw = json.load(fh)
            settings = raw.get("settings", {})
            timeout = float(settings.get("timeout_seconds", timeout))
            max_retries = int(settings.get("max_retries", max_retries))
            retry_backoff = float(settings.get("retry_backoff_seconds", retry_backoff))
            servers = raw.get("mcpServers", {})
            groww = servers.get("groww-pulse", {})
            if groww.get("url"):
                base_url = _expand_env(str(groww["url"])).rstrip("/")

        master_doc_id = os.environ.get("GOOGLE_MASTER_DOC_ID", "").strip()
        if not master_doc_id:
            raise ConfigurationError(
                "GOOGLE_MASTER_DOC_ID is not set. Add your master Google Doc ID to .env."
            )

        recipient = os.environ.get("PULSE_EMAIL_RECIPIENT", "").strip()
        if not recipient:
            raise ConfigurationError(
                "PULSE_EMAIL_RECIPIENT is not set. Add the Gmail draft recipient to .env."
            )

        subject_prefix = os.environ.get(
            "PULSE_EMAIL_SUBJECT_PREFIX", "Groww Weekly Pulse"
        ).strip()

        logs_dir = Path(
            os.environ.get("OUTPUT_LOGS_DIR", str(root / "output" / "logs"))
        )

        return cls(
            base_url=base_url,
            master_doc_id=master_doc_id,
            email_recipient=recipient,
            email_subject_prefix=subject_prefix,
            timeout_seconds=timeout,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff,
            logs_dir=logs_dir,
        )
