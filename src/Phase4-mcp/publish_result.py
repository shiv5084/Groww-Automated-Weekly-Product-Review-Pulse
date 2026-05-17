"""Publish result types and correlation log writer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def document_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


@dataclass
class PublishResult:
    document_id: str
    document_url: str
    draft_id: str
    run_timestamp: str
    week_label: str
    pulse_md_path: Optional[str] = None
    pulse_txt_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def write_publish_log(result: PublishResult, logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    date_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = logs_dir / f"publish_{date_slug}.json"
    payload = {
        **result.to_dict(),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
