"""
quality_checks.py — Pure pass/fail quality gate rules (no LLM).

Pass criteria (Phase 5 plan):
  - Pulse note <= 250 words (formatted markdown body)
  - Top 3 themes present in pulse note
  - Exactly 3 recommended actions
  - No excessive fallback-theme clustering (ambiguous assignments)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_WORD_LIMIT = 250
FALLBACK_THEME_ID = "onboarding"
# Themes with at most this many reviews are treated as fragmented / ambiguous
FRAGMENTED_THEME_MAX_COUNT = 2
FRAGMENTED_THEME_MIN_THEMES = 3


@dataclass
class QualityReport:
    """Result of running all quality gate rules."""

    passed: bool
    failures: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def primary_failure(self) -> Optional[str]:
        return self.failures[0] if self.failures else None


def count_words(text: str) -> int:
    """Count words in prose (collapse whitespace)."""
    return len(re.sub(r"\s+", " ", text.strip()).split()) if text.strip() else 0


def evaluate_quality(
    *,
    pulse_md_path: Optional[str] = None,
    pulse_note_data: Optional[dict[str, Any]] = None,
    themes_json_path: Optional[str] = None,
    word_limit: int = DEFAULT_WORD_LIMIT,
) -> QualityReport:
    """
    Run all quality checks. At least one of pulse_md_path or pulse_note_data
    must be provided for pulse-level checks.
    """
    failures: list[str] = []
    details: dict[str, Any] = {"word_limit": word_limit}

    note = pulse_note_data or {}
    md_text = ""
    if pulse_md_path:
        path = Path(pulse_md_path)
        if path.exists():
            md_text = path.read_text(encoding="utf-8")
            details["pulse_md_path"] = str(path)

    if not note and md_text:
        note = _parse_note_from_markdown(md_text)

    # --- Word count ---
    word_count = count_words(md_text) if md_text else _note_word_count(note)
    details["word_count"] = word_count
    details["within_limit"] = word_count <= word_limit
    if word_count > word_limit:
        failures.append("word_count")

    # --- Top 3 themes ---
    top_themes = note.get("top_themes") or []
    details["theme_count"] = len(top_themes)
    if len(top_themes) < 3:
        failures.append("missing_themes")

    # --- Exactly 3 actions ---
    actions = note.get("actions") or []
    details["action_count"] = len(actions)
    if len(actions) != 3:
        failures.append("insufficient_actions")

    # --- Ambiguous theme clustering (from theme_groups.json) ---
    ambiguous_ids: list[int] = []
    if themes_json_path:
        ambiguous_ids, fragmented_theme_count = _detect_ambiguous_assignments(
            themes_json_path
        )
        details["ambiguous_review_ids"] = ambiguous_ids
        details["fragmented_theme_count"] = fragmented_theme_count
        if fragmented_theme_count >= FRAGMENTED_THEME_MIN_THEMES:
            failures.append("ambiguous_themes")

    return QualityReport(
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


def _note_word_count(note: dict[str, Any]) -> int:
    parts: list[str] = [str(note.get("week_label", ""))]
    for t in note.get("top_themes") or []:
        if isinstance(t, dict):
            parts.extend([str(t.get("theme_name", "")), str(t.get("quote", ""))])
    parts.extend(str(a) for a in (note.get("actions") or []))
    return count_words(" ".join(parts))


def _parse_note_from_markdown(md: str) -> dict[str, Any]:
    """Best-effort extraction of theme/action counts from saved pulse markdown."""
    actions: list[str] = []
    in_actions = False
    for line in md.splitlines():
        if line.strip().startswith("## Recommended Actions"):
            in_actions = True
            continue
        if in_actions and line.strip():
            m = re.match(r"^\d+\.\s+(.+)$", line.strip())
            if m:
                actions.append(m.group(1))

    theme_lines = [
        ln for ln in md.splitlines()
        if re.match(r"^\d+\.\s+\*\*", ln.strip())
    ]
    return {
        "top_themes": [{}] * len(theme_lines),
        "actions": actions,
    }


def _detect_ambiguous_assignments(
    themes_json_path: str,
) -> tuple[list[int], int]:
    """
    Detect fragmented classification (many tiny themes), not dominant fallback volume.

    A high share in the configured fallback theme (e.g. onboarding) is expected
    for Groww and must not fail the gate by itself.

    Returns (sample_review_row_ids, count_of_fragmented_themes).
    """
    path = Path(themes_json_path)
    if not path.exists():
        return [], 0

    with path.open(encoding="utf-8") as fh:
        groups = json.load(fh)

    fragmented_theme_count = 0
    ambiguous_ids: list[int] = []

    for theme_id, group in groups.items():
        count = int(group.get("count", 0))
        if 0 < count <= FRAGMENTED_THEME_MAX_COUNT:
            fragmented_theme_count += 1
            for review in group.get("reviews") or []:
                rid = review.get("row_id")
                if rid is not None:
                    ambiguous_ids.append(int(rid))

    return list(dict.fromkeys(ambiguous_ids))[:50], fragmented_theme_count


def failure_to_tool(failure: str) -> str:
    """Map a failure code to the remediation tool name."""
    return {
        "word_count": "trim_quotes",
        "insufficient_actions": "regenerate_actions",
        "ambiguous_themes": "reclassify_ambiguous_reviews",
        "missing_themes": "regenerate_actions",
    }.get(failure, "trim_quotes")
