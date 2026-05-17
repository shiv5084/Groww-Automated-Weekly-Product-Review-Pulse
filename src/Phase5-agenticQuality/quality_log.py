"""
quality_log.py — Quality remediation audit log writer (mirrors Phase 4 publish_result).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def resolve_logs_dir(project_root: Path | str) -> Path:
    """Resolve output/logs from env or project root."""
    root = Path(project_root)
    custom = os.environ.get("OUTPUT_LOGS_DIR")
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else root / p
    return root / "output" / "logs"


def write_quality_log(
    project_root: Path | str,
    payload: dict[str, Any],
    logs_dir: Optional[Path] = None,
) -> Path:
    """
    Append an event to output/logs/quality_YYYY-MM-DD.json.

    Always creates the logs directory if missing. Each call appends one object
    to the day's JSON array.
    """
    base = logs_dir or resolve_logs_dir(project_root)
    base.mkdir(parents=True, exist_ok=True)
    date_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base / f"quality_{date_slug}.json"

    entry = {
        **payload,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
                existing = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            existing = []

    existing.append(entry)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def record_quality_check(
    project_root: Path | str,
    *,
    event: str,
    passed: bool,
    failures: list[str],
    details: dict[str, Any],
    iterations: int = 0,
    remediations: Optional[list[str]] = None,
    pulse_md: Optional[str] = None,
) -> Path:
    """Convenience wrapper for check-only and summary events."""
    payload: dict[str, Any] = {
        "event": event,
        "passed": passed,
        "failures": failures,
        "iterations": iterations,
        "details": details,
    }
    if remediations:
        payload["remediations"] = remediations
    if pulse_md:
        payload["pulse_md"] = pulse_md
    return write_quality_log(project_root, payload)
