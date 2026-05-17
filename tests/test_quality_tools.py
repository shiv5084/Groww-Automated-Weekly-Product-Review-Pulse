"""
test_quality_tools.py — Unit tests for Phase 5 quality checks and @tools.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_DIR = PROJECT_ROOT / "src" / "Phase5-agenticQuality"

import importlib.util as _ilu


def _load(module_name: str, file_path: Path, package_name: str | None = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


pkg = type(sys)("Phase5_agenticQuality")
pkg.__path__ = [str(QUALITY_DIR)]
sys.modules["Phase5_agenticQuality"] = pkg

_checks = _load(
    "Phase5_agenticQuality.quality_checks",
    QUALITY_DIR / "quality_checks.py",
    "Phase5_agenticQuality",
)
_tools = _load(
    "Phase5_agenticQuality.tools",
    QUALITY_DIR / "tools.py",
    "Phase5_agenticQuality",
)

evaluate_quality = _checks.evaluate_quality
count_words = _checks.count_words
check_word_count = _tools.check_word_count
trim_quotes = _tools.trim_quotes
regenerate_actions = _tools.regenerate_actions
pulse_note_from_dict = _tools.pulse_note_from_dict
pulse_note_to_dict = _tools.pulse_note_to_dict


SAMPLE_NOTE = {
    "week_label": "Week of 16 May 2026",
    "date_range": ["2026-02-21", "2026-05-16"],
    "top_themes": [
        {
            "theme_id": "onboarding",
            "theme_name": "Onboarding",
            "count": 100,
            "avg_rating": 4.5,
            "sentiment": "positive",
            "quote": "Great onboarding experience overall.",
            "quote_rating": 5.0,
        },
        {
            "theme_id": "payments",
            "theme_name": "Payments",
            "count": 50,
            "avg_rating": 2.5,
            "sentiment": "negative",
            "quote": "Payments fail too often for my liking.",
            "quote_rating": 1.0,
        },
        {
            "theme_id": "statements",
            "theme_name": "Statements",
            "count": 30,
            "avg_rating": 3.2,
            "sentiment": "neutral",
            "quote": "Statements are sometimes hard to read.",
            "quote_rating": 3.0,
        },
    ],
    "actions": [
        "Fix payment reliability issues immediately.",
        "Resolve statement discrepancies within 7 days.",
        "Enhance onboarding flow for new users.",
    ],
    "total_reviews": 180,
}


def test_check_word_count_tool():
    result = check_word_count.invoke({"note_text": "one two three four", "limit": 250})
    assert result["count"] == 4
    assert result["within_limit"] is True


def test_evaluate_quality_passes_valid_note(tmp_path):
    md = tmp_path / "pulse.md"
    md.write_text("# Title\n\nShort note with few words.\n", encoding="utf-8")
    report = evaluate_quality(pulse_note_data=SAMPLE_NOTE, pulse_md_path=str(md))
    assert report.passed is True
    assert report.failures == []


def test_evaluate_quality_fails_insufficient_actions():
    bad = dict(SAMPLE_NOTE)
    bad["actions"] = ["Only one action"]
    report = evaluate_quality(pulse_note_data=bad)
    assert report.passed is False
    assert "insufficient_actions" in report.failures


def test_evaluate_quality_fails_word_count(tmp_path):
    long_quote = "word " * 200
    bad = dict(SAMPLE_NOTE)
    bad["top_themes"] = [
        {**SAMPLE_NOTE["top_themes"][0], "quote": long_quote},
        *SAMPLE_NOTE["top_themes"][1:],
    ]
    md = tmp_path / "long.md"
    md.write_text(long_quote * 3, encoding="utf-8")
    report = evaluate_quality(pulse_note_data=bad, pulse_md_path=str(md), word_limit=50)
    assert report.passed is False
    assert "word_count" in report.failures


def test_trim_quotes_updates_state(tmp_path):
    gen_dir = PROJECT_ROOT / "src" / "Phase3-generator"
    pulse_mod = _load(
        "Phase3_generator.pulse_note",
        gen_dir / "pulse_note.py",
        "Phase3_generator",
    )
    long_quote = " ".join(["feedback"] * 80)
    note_data = dict(SAMPLE_NOTE)
    for t in note_data["top_themes"]:
        t["quote"] = long_quote

    md_path = tmp_path / "pulse.md"
    md_path.write_text("placeholder", encoding="utf-8")

    state = {
        "pulse_note_data": note_data,
        "pulse_md": str(md_path),
        "model": "llama-3.3-70b-versatile",
    }
    with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
        generator = pulse_mod.PulseNoteGenerator()
        note = pulse_note_from_dict(note_data, pulse_mod.PulseNote, pulse_mod.ThemeSummary)
        assert note.word_count() > generator.max_words

        result = trim_quotes.invoke({"state": state})
        assert result["status"] == "ok"
        assert result["word_count"] <= generator.max_words


def test_regenerate_actions_mock_chain(tmp_path):
    gen_dir = PROJECT_ROOT / "src" / "Phase3-generator"
    pulse_mod = _load(
        "Phase3_generator.pulse_note",
        gen_dir / "pulse_note.py",
        "Phase3_generator",
    )
    md_path = tmp_path / "pulse.md"
    md_path.write_text("placeholder", encoding="utf-8")

    bad = dict(SAMPLE_NOTE)
    bad["actions"] = ["one"]

    state = {
        "pulse_note_data": bad,
        "pulse_md": str(md_path),
        "model": "llama-3.3-70b-versatile",
    }

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = (
        "1. Fix payments.\n2. Improve statements.\n3. Polish onboarding.\n"
    )

    with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
        with patch.object(pulse_mod.PulseNoteGenerator, "_action_chain", mock_chain, create=True):
            generator = pulse_mod.PulseNoteGenerator()
            generator._action_chain = mock_chain
            with patch.object(_tools, "_get_generator", return_value=(generator, pulse_mod.PulseNote, pulse_mod.ThemeSummary)):
                result = regenerate_actions.invoke(
                    {
                        "theme_summary": "themes",
                        "feedback": "need three items",
                        "state": state,
                    }
                )
    assert result["status"] == "ok"
    assert len(result["actions"]) == 3
