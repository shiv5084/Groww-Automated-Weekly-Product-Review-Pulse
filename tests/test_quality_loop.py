"""
test_quality_loop.py — Integration tests for Phase 5 quality loop routing.
"""

from __future__ import annotations

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
_agent = _load(
    "Phase5_agenticQuality.quality_agent",
    QUALITY_DIR / "quality_agent.py",
    "Phase5_agenticQuality",
)

evaluate_quality = _checks.evaluate_quality
quality_agent_node = _agent.quality_agent_node
route_after_quality = _agent.route_after_quality
apply_tool_result_to_state = _agent.apply_tool_result_to_state


GOOD_NOTE = {
    "week_label": "Week of 16 May 2026",
    "date_range": ["2026-02-21", "2026-05-16"],
    "top_themes": [
        {
            "theme_id": "a",
            "theme_name": "Onboarding",
            "count": 10,
            "avg_rating": 4.0,
            "sentiment": "positive",
            "quote": "Smooth sign up.",
            "quote_rating": 5.0,
        },
        {
            "theme_id": "b",
            "theme_name": "Payments",
            "count": 8,
            "avg_rating": 2.0,
            "sentiment": "negative",
            "quote": "Payment failed twice.",
            "quote_rating": 1.0,
        },
        {
            "theme_id": "c",
            "theme_name": "Statements",
            "count": 5,
            "avg_rating": 3.0,
            "sentiment": "neutral",
            "quote": "Statement was delayed.",
            "quote_rating": 3.0,
        },
    ],
    "actions": ["A", "B", "C"],
    "total_reviews": 23,
}


def test_quality_agent_passes_clean_note(tmp_path):
    md = tmp_path / "pulse.md"
    md.write_text("# Groww Weekly Pulse\n\nShort body.\n", encoding="utf-8")
    state = {
        "pulse_note_data": GOOD_NOTE,
        "pulse_md": str(md),
        "quality_iterations": 0,
        "max_quality_iterations": 3,
        "project_root": str(tmp_path),
        "messages": [],
    }
    out = quality_agent_node(state)
    assert out["quality_passed"] is True
    assert route_after_quality({**state, **out}) == "quality_resolve"


def test_quality_agent_requests_tool_on_bad_actions(tmp_path):
    md = tmp_path / "pulse.md"
    md.write_text("# Pulse\n", encoding="utf-8")
    bad = dict(GOOD_NOTE)
    bad["actions"] = ["only one"]
    state = {
        "pulse_note_data": bad,
        "pulse_md": str(md),
        "quality_iterations": 0,
        "max_quality_iterations": 3,
        "project_root": str(tmp_path),
        "messages": [],
    }
    out = quality_agent_node(state)
    assert out["quality_passed"] is False
    assert route_after_quality({**state, **out}) == "tools"
    tool_calls = out["messages"][-1].tool_calls
    assert tool_calls[0]["name"] == "regenerate_actions"


def test_quality_agent_max_iterations_force_pass(tmp_path):
    md = tmp_path / "pulse.md"
    md.write_text("x " * 400, encoding="utf-8")
    bad = dict(GOOD_NOTE)
    bad["actions"] = []
    state = {
        "pulse_note_data": bad,
        "pulse_md": str(md),
        "quality_iterations": 3,
        "max_quality_iterations": 3,
        "project_root": str(tmp_path),
        "messages": [],
    }
    out = quality_agent_node(state)
    assert out["quality_passed"] is True
    assert out["quality_status"] == "max_iterations"
    assert route_after_quality({**state, **out}) == "quality_resolve"


def test_apply_tool_result_increments_iteration():
    state = {"quality_iterations": 1}
    merged = apply_tool_result_to_state(
        state,
        {"pulse_note_data": GOOD_NOTE, "post_tool_route": "quality_agent"},
    )
    assert merged["quality_iterations"] == 2
    assert merged["pulse_note_data"] == GOOD_NOTE


def test_build_pipeline_includes_quality_nodes():
    """Compiled graph exposes quality_agent and tools nodes."""
    main_path = PROJECT_ROOT / "src" / "main.py"
    spec = _ilu.spec_from_file_location("groww_main", main_path)
    main_mod = _ilu.module_from_spec(spec)
    sys.modules["groww_main"] = main_mod
    spec.loader.exec_module(main_mod)

    pipeline = main_mod.build_pipeline()
    node_names = set(pipeline.get_graph().nodes.keys())
    assert "quality_agent" in node_names
    assert "tools" in node_names
    assert "generate_pulse" in node_names
