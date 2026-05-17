"""
quality_agent.py — Rule-based quality agent node and graph routing helpers.

The agent evaluates pulse output via quality_checks, then either approves publish
or emits an AIMessage with tool_calls for LangGraph ToolNode execution.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage

from .quality_checks import (
    DEFAULT_WORD_LIMIT,
    QualityReport,
    evaluate_quality,
    failure_to_tool,
)
from .quality_log import record_quality_check, write_quality_log

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 3


def _build_tool_args(failure: str, report: QualityReport, state: dict[str, Any]) -> dict[str, Any]:
    """Build tool invocation arguments for a given failure type."""
    note = state.get("pulse_note_data") or {}
    if failure == "word_count":
        md_path = state.get("pulse_md")
        text = Path(md_path).read_text(encoding="utf-8") if md_path and Path(md_path).exists() else ""
        return {}  # trim_quotes uses InjectedState only

    if failure in ("insufficient_actions", "missing_themes"):
        summary = "\n".join(
            f"- {t.get('theme_name')}: {t.get('count')} reviews"
            for t in (note.get("top_themes") or [])
        )
        feedback = state.get("quality_last_failure") or "Provide exactly three distinct actions."
        return {"theme_summary": summary or "Weekly Groww review themes.", "feedback": feedback}

    if failure == "ambiguous_themes":
        ids = report.details.get("ambiguous_review_ids") or []
        if not ids:
            ids = list(range(min(5, 10)))
        return {
            "review_ids": ids[:50],
            "hint": state.get("reclassify_hint") or "Assign each review to the most specific theme.",
        }

    return {}


def pick_remediation(report: QualityReport, state: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """
    Choose one remediation tool and post-tool route.

    Returns (tool_name, tool_args, post_tool_route).
    """
    failure = report.primary_failure() or "word_count"
    tool_name = failure_to_tool(failure)
    tool_args = _build_tool_args(failure, report, state)
    post_route = "generate_pulse" if tool_name == "reclassify_ambiguous_reviews" else "quality_agent"
    return tool_name, tool_args, post_route


def quality_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate quality gates; pass through to publish or request a remediation tool.
    """
    if state.get("skip_quality"):
        log_path = write_quality_log(
            Path(state.get("project_root") or "."),
            {"event": "skipped", "reason": "skip_quality flag"},
        )
        return {
            "quality_status": "skipped",
            "quality_passed": True,
            "quality_log": str(log_path),
            "messages": [AIMessage(content="Quality checks skipped.")],
        }

    iterations = int(state.get("quality_iterations") or 0)
    max_iter = int(state.get("max_quality_iterations") or DEFAULT_MAX_ITERATIONS)
    word_limit = int(state.get("quality_word_limit") or DEFAULT_WORD_LIMIT)

    report = evaluate_quality(
        pulse_md_path=state.get("pulse_md"),
        pulse_note_data=state.get("pulse_note_data"),
        themes_json_path=state.get("themes_json"),
        word_limit=word_limit,
    )

    remediation: list[str] = list(state.get("quality_remediation") or [])
    errors: list[str] = list(state.get("errors") or [])

    if report.passed:
        log_path = write_quality_log(
            Path(state.get("project_root") or "."),
            {
                "event": "passed",
                "iterations": iterations,
                "details": report.details,
            },
        )
        logger.info("[quality_agent] All checks passed (iterations=%d)", iterations)
        return {
            "quality_status": "passed",
            "quality_passed": True,
            "quality_log": str(log_path),
            "messages": [AIMessage(content="Quality checks passed.")],
        }

    if iterations >= max_iter:
        msg = (
            f"Quality loop reached max iterations ({max_iter}); "
            f"proceeding with warnings: {report.failures}"
        )
        errors.append(msg)
        log_path = write_quality_log(
            Path(state.get("project_root") or "."),
            {
                "event": "max_iterations",
                "iterations": iterations,
                "failures": report.failures,
                "details": report.details,
            },
        )
        logger.warning("[quality_agent] %s", msg)
        return {
            "quality_status": "max_iterations",
            "quality_passed": True,
            "quality_log": str(log_path),
            "errors": errors,
            "messages": [AIMessage(content=msg)],
        }

    tool_name, tool_args, post_route = pick_remediation(report, state)
    failure = report.primary_failure() or "unknown"
    remediation.append(f"iter={iterations}: {tool_name} ({failure})")

    log_path = write_quality_log(
        Path(state.get("project_root") or "."),
        {
            "event": "remediate",
            "iteration": iterations,
            "failure": failure,
            "tool": tool_name,
            "tool_args": tool_args,
            "details": report.details,
        },
    )

    ai_msg = AIMessage(
        content=f"Quality check failed: {', '.join(report.failures)}. Invoking {tool_name}.",
        tool_calls=[
            {
                "name": tool_name,
                "args": tool_args,
                "id": f"quality_{iterations}_{tool_name}",
            }
        ],
    )
    logger.info(
        "[quality_agent] Failure=%s -> tool=%s (iteration %d/%d)",
        failure,
        tool_name,
        iterations,
        max_iter,
    )
    return {
        "quality_status": "remediating",
        "quality_passed": False,
        "quality_last_failure": failure,
        "quality_remediation": remediation,
        "quality_log": str(log_path),
        "post_tool_route": post_route,
        "messages": (state.get("messages") or []) + [ai_msg],
    }


def route_after_quality(state: dict[str, Any]) -> Literal["tools", "quality_resolve"]:
    """Route to ToolNode when the last message contains tool calls."""
    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        if tool_calls:
            return "tools"
    return "quality_resolve"


def route_after_tools(state: dict[str, Any]) -> str:
    """After ToolNode: increment iteration and route to next pipeline node."""
    return state.get("post_tool_route") or "quality_agent"


def apply_tool_result_to_state(state: dict[str, Any], tool_output: dict[str, Any]) -> dict[str, Any]:
    """Merge ToolNode JSON output back into pipeline state."""
    updates: dict[str, Any] = {
        "quality_iterations": int(state.get("quality_iterations") or 0) + 1,
    }
    if "pulse_note_data" in tool_output:
        updates["pulse_note_data"] = tool_output["pulse_note_data"]
    if "themes_json" in tool_output:
        updates["themes_json"] = tool_output["themes_json"]
    if "post_tool_route" in tool_output:
        updates["post_tool_route"] = tool_output["post_tool_route"]
    return updates


def tools_result_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Read the latest ToolMessage content and merge structured tool output into state.
    Runs immediately after ToolNode in the graph.
    """
    messages = state.get("messages") or []
    tool_output: dict[str, Any] = {}
    for msg in reversed(messages):
        if msg.__class__.__name__ == "ToolMessage":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                try:
                    tool_output = json.loads(content)
                except json.JSONDecodeError:
                    tool_output = {"status": "ok", "raw": content}
            elif isinstance(content, dict):
                tool_output = content
            break

    updates = apply_tool_result_to_state(state, tool_output)
    remediation = list(state.get("quality_remediation") or [])
    if tool_output.get("status"):
        remediation.append(f"tool_result: {tool_output.get('status')}")
    updates["quality_remediation"] = remediation
    return updates


def quality_resolve_node(state: dict[str, Any]) -> dict[str, Any]:
    """Passthrough node used for routing after quality_agent (no tool calls)."""
    return {}


def invoke_quality_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Execute a remediation tool outside LangGraph ToolNode (standalone CLI)."""
    from .tools import (
        reclassify_ambiguous_reviews,
        regenerate_actions,
        trim_quotes,
    )

    if tool_name == "trim_quotes":
        return trim_quotes.invoke({"state": state})
    if tool_name == "regenerate_actions":
        return regenerate_actions.invoke({**tool_args, "state": state})
    if tool_name == "reclassify_ambiguous_reviews":
        return reclassify_ambiguous_reviews.invoke({**tool_args, "state": state})
    raise ValueError(f"Unknown quality tool: {tool_name}")


def run_quality_loop(
    state: dict[str, Any],
    *,
    regenerate_pulse: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], bool, QualityReport]:
    """
    Run the agentic quality loop until checks pass or max iterations is reached.

    Parameters
    ----------
    state : dict
        Pipeline-like state (pulse_md, pulse_note_data, themes_json, etc.).
    regenerate_pulse : callable | None
        Called after reclassify_ambiguous_reviews to rebuild pulse files from themes.

    Returns
    -------
    (final_state, passed, last_report)
    """
    if state.get("skip_quality"):
        report = evaluate_quality(
            pulse_md_path=state.get("pulse_md"),
            pulse_note_data=state.get("pulse_note_data"),
            themes_json_path=state.get("themes_json"),
            word_limit=int(state.get("quality_word_limit") or DEFAULT_WORD_LIMIT),
        )
        state["quality_status"] = "skipped"
        state["quality_passed"] = True
        return state, True, report

    max_iter = int(state.get("max_quality_iterations") or DEFAULT_MAX_ITERATIONS)
    word_limit = int(state.get("quality_word_limit") or DEFAULT_WORD_LIMIT)
    project_root = Path(state.get("project_root") or ".")

    last_report = evaluate_quality(
        pulse_md_path=state.get("pulse_md"),
        pulse_note_data=state.get("pulse_note_data"),
        themes_json_path=state.get("themes_json"),
        word_limit=word_limit,
    )

    while True:
        iterations = int(state.get("quality_iterations") or 0)
        last_report = evaluate_quality(
            pulse_md_path=state.get("pulse_md"),
            pulse_note_data=state.get("pulse_note_data"),
            themes_json_path=state.get("themes_json"),
            word_limit=word_limit,
        )

        if last_report.passed:
            log_path = write_quality_log(
                project_root,
                {
                    "event": "passed",
                    "iterations": iterations,
                    "details": last_report.details,
                },
            )
            state["quality_status"] = "passed"
            state["quality_passed"] = True
            state["quality_log"] = str(log_path)
            logger.info("[quality_loop] Passed after %d remediation(s)", iterations)
            return state, True, last_report

        if iterations >= max_iter:
            msg = (
                f"Quality loop reached max iterations ({max_iter}); "
                f"remaining failures: {last_report.failures}"
            )
            errors = list(state.get("errors") or [])
            errors.append(msg)
            log_path = write_quality_log(
                project_root,
                {
                    "event": "max_iterations",
                    "iterations": iterations,
                    "failures": last_report.failures,
                    "details": last_report.details,
                },
            )
            state["quality_status"] = "max_iterations"
            state["quality_passed"] = False
            state["quality_log"] = str(log_path)
            state["errors"] = errors
            logger.warning("[quality_loop] %s", msg)
            return state, False, last_report

        tool_name, tool_args, post_route = pick_remediation(last_report, state)
        failure = last_report.primary_failure() or "unknown"
        remediation = list(state.get("quality_remediation") or [])
        remediation.append(f"iter={iterations}: {tool_name} ({failure})")
        state["quality_remediation"] = remediation
        state["quality_last_failure"] = failure

        write_quality_log(
            project_root,
            {
                "event": "remediate",
                "iteration": iterations,
                "failure": failure,
                "tool": tool_name,
                "tool_args": tool_args,
                "details": last_report.details,
            },
        )
        logger.info(
            "[quality_loop] Failure=%s -> %s (iteration %d/%d)",
            failure,
            tool_name,
            iterations,
            max_iter,
        )

        tool_output = invoke_quality_tool(tool_name, tool_args, state)
        updates = apply_tool_result_to_state(state, tool_output)
        state = {**state, **updates}
        if tool_output.get("status"):
            state["quality_remediation"] = remediation + [
                f"tool_result: {tool_output.get('status')}",
            ]

        if post_route == "generate_pulse" and regenerate_pulse is not None:
            state = regenerate_pulse(state)
        elif post_route == "generate_pulse":
            logger.warning(
                "[quality_loop] reclassify completed but no regenerate_pulse callback — "
                "re-run Phase 3 or pass regenerate_pulse to run_quality_loop."
            )
