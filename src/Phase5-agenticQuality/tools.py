"""
tools.py — LangChain @tool wrappers for the Phase 5 quality loop.

Tools reuse Phase 2–3 modules (ThemeGrouper, PulseNoteGenerator) — no duplicate LLM logic.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import pandas as pd
from langchain_core.tools import tool

try:
    from langgraph.prebuilt import InjectedState
except ImportError:  # pragma: no cover - older langgraph builds
    from langchain.tools import InjectedState  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_phase_module(pkg_dir: Path, pkg_name: str, mod_file: str, mod_name: str):
    import importlib.util as _ilu

    if pkg_name not in sys.modules:
        pkg = type(sys)(pkg_name)
        pkg.__path__ = [str(pkg_dir)]
        sys.modules[pkg_name] = pkg
    spec = _ilu.spec_from_file_location(mod_name, pkg_dir / mod_file)
    mod = _ilu.module_from_spec(spec)
    mod.__package__ = pkg_name
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _get_generator(model: Optional[str] = None):
    gen_dir = PROJECT_ROOT / "src" / "Phase3-generator"
    mod = _load_phase_module(gen_dir, "Phase3_generator", "pulse_note.py", "Phase3_generator.pulse_note")
    return mod.PulseNoteGenerator(model=model), mod.PulseNote, mod.ThemeSummary


def _get_formatter():
    gen_dir = PROJECT_ROOT / "src" / "Phase3-generator"
    mod = _load_phase_module(gen_dir, "Phase3_generator", "formatter.py", "Phase3_generator.formatter")
    return mod.PulseNoteFormatter


def _get_grouper(model: Optional[str] = None, batch_size: int = 50):
    themes_dir = PROJECT_ROOT / "src" / "Phase2-themes"
    _load_phase_module(themes_dir, "Phase2_themes", "prompts.py", "Phase2_themes.prompts")
    mod = _load_phase_module(themes_dir, "Phase2_themes", "grouper.py", "Phase2_themes.grouper")
    return mod.ThemeGrouper(model=model, batch_size=batch_size)


def pulse_note_to_dict(note: Any) -> dict[str, Any]:
    """Serialize PulseNote for pipeline state / quality checks."""
    return {
        "week_label": note.week_label,
        "date_range": list(note.date_range),
        "top_themes": [
            {
                "theme_id": t.theme_id,
                "theme_name": t.theme_name,
                "count": t.count,
                "avg_rating": t.avg_rating,
                "sentiment": t.sentiment,
                "quote": t.quote,
                "quote_rating": t.quote_rating,
            }
            for t in note.top_themes
        ],
        "actions": list(note.actions),
        "total_reviews": note.total_reviews,
    }


def pulse_note_from_dict(data: dict[str, Any], PulseNote: type, ThemeSummary: type) -> Any:
    themes = [
        ThemeSummary(
            theme_id=t["theme_id"],
            theme_name=t["theme_name"],
            count=t["count"],
            avg_rating=t["avg_rating"],
            sentiment=t["sentiment"],
            quote=t.get("quote", ""),
            quote_rating=t.get("quote_rating", 0.0),
        )
        for t in data.get("top_themes", [])
    ]
    dr = data.get("date_range") or ["", ""]
    return PulseNote(
        week_label=data.get("week_label", ""),
        date_range=(dr[0], dr[1]),
        top_themes=themes,
        actions=list(data.get("actions") or []),
        total_reviews=int(data.get("total_reviews", 0)),
    )


def write_pulse_outputs(
    note: Any,
    *,
    pulse_md: str,
    pulse_txt: Optional[str] = None,
    pulse_html: Optional[str] = None,
) -> None:
    """Rewrite pulse note files after remediation."""
    formatter = _get_formatter()
    Path(pulse_md).write_text(formatter.format_for_docs(note), encoding="utf-8")
    if pulse_txt:
        Path(pulse_txt).write_text(formatter.format_for_email(note), encoding="utf-8")
    if pulse_html:
        Path(pulse_html).write_text(formatter.format_for_html(note), encoding="utf-8")


@tool
def check_word_count(note_text: str, limit: int = 250) -> dict[str, Any]:
    """Check if the pulse note text is within the word limit."""
    from .quality_checks import count_words

    count = count_words(note_text)
    return {"count": count, "within_limit": count <= limit, "limit": limit}


@tool
def trim_quotes(
    state: Annotated[dict, InjectedState],
) -> dict[str, Any]:
    """
    Trim representative quotes in the pulse note to bring word count under the limit.
    Updates pulse markdown/txt/html on disk and pulse_note_data in graph state.
    """
    pulse_data = state.get("pulse_note_data")
    if not pulse_data:
        return {"status": "error", "message": "No pulse_note_data in state"}

    generator, PulseNote, ThemeSummary = _get_generator(state.get("model"))
    note = pulse_note_from_dict(pulse_data, PulseNote, ThemeSummary)
    trimmed = generator._enforce_word_limit(note)

    pulse_md = state.get("pulse_md")
    if pulse_md:
        write_pulse_outputs(
            trimmed,
            pulse_md=pulse_md,
            pulse_txt=state.get("pulse_txt"),
            pulse_html=state.get("pulse_html"),
        )

    new_data = pulse_note_to_dict(trimmed)
    logger.info("[trim_quotes] Word count after trim: %d", trimmed.word_count())
    return {
        "status": "ok",
        "word_count": trimmed.word_count(),
        "pulse_note_data": new_data,
        "post_tool_route": "quality_agent",
    }


@tool
def regenerate_actions(
    theme_summary: str,
    feedback: str = "",
    state: Annotated[dict, InjectedState] = None,  # noqa: RUF013
) -> dict[str, Any]:
    """
    Re-invoke the action LLM chain when fewer than three actions are present.
    Optional feedback steers the model toward more specific recommendations.
    """
    _ = theme_summary  # built from pulse note; kept for tool schema / agent calls
    pulse_data = (state or {}).get("pulse_note_data")
    if not pulse_data:
        return {"status": "error", "message": "No pulse_note_data in state"}

    generator, PulseNote, ThemeSummary = _get_generator((state or {}).get("model"))
    note = pulse_note_from_dict(pulse_data, PulseNote, ThemeSummary)

    summary = "\n".join(
        f"- {t.theme_name}: {t.count} reviews, avg {t.avg_rating}/5, "
        f"{t.sentiment}. Sample: \"{t.quote[:120]}\""
        for t in note.top_themes
    )
    if feedback:
        summary = f"{summary}\n\nADDITIONAL FEEDBACK:\n{feedback}"

    try:
        raw = generator._action_chain.invoke({"theme_summary": summary})
        actions = generator._parse_actions(raw)
    except Exception as exc:
        logger.warning("[regenerate_actions] LLM failed (%s) — rule-based fallback.", exc)
        actions = generator._fallback_actions(note.top_themes)

    while len(actions) < 3:
        actions.append("Review and address remaining user feedback themes.")
    note.actions = actions[:3]

    pulse_md = (state or {}).get("pulse_md")
    if pulse_md:
        write_pulse_outputs(
            note,
            pulse_md=pulse_md,
            pulse_txt=(state or {}).get("pulse_txt"),
            pulse_html=(state or {}).get("pulse_html"),
        )

    new_data = pulse_note_to_dict(note)
    logger.info("[regenerate_actions] Regenerated %d actions", len(note.actions))
    return {
        "status": "ok",
        "actions": note.actions,
        "pulse_note_data": new_data,
        "post_tool_route": "quality_agent",
    }


@tool
def reclassify_ambiguous_reviews(
    review_ids: list[int],
    hint: str = "",
    state: Annotated[dict, InjectedState] = None,  # noqa: RUF013
) -> dict[str, Any]:
    """
    Re-run theme classification on selected reviews (with optional hint), then
    re-group the full cleaned dataset and overwrite theme_groups.json.
    """
    cleaned_csv = (state or {}).get("cleaned_csv") or str(
        PROJECT_ROOT / "data" / "cleaned" / "cleaned_reviews.csv"
    )
    path = Path(cleaned_csv)
    if not path.exists():
        return {"status": "error", "message": f"Cleaned CSV not found: {cleaned_csv}"}

    df = pd.read_csv(path, encoding="utf-8")
    work = df.reset_index(drop=True).copy()
    if not review_ids:
        review_ids = list(range(min(20, len(work))))

    text_col = "llm_text" if "llm_text" in work.columns else "review_text"

    if hint:
        for rid in review_ids:
            if 0 <= rid < len(work):
                work.at[rid, text_col] = (
                    f"[Reclassification hint: {hint}] {work.at[rid, text_col]}"
                )

    grouper = _get_grouper(
        model=(state or {}).get("model"),
        batch_size=(state or {}).get("batch_size", 50),
    )
    groups = grouper.group_reviews(work)

    themes_json = (state or {}).get("themes_json") or str(
        PROJECT_ROOT / "output" / "notes" / "theme_groups.json"
    )
    themes_path = Path(themes_json)
    themes_path.parent.mkdir(parents=True, exist_ok=True)
    result = {k: v.to_dict() for k, v in groups.items()}
    with themes_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    logger.info(
        "[reclassify_ambiguous_reviews] Reclassified %d flagged reviews; full regroup -> %s",
        len(review_ids),
        themes_path,
    )
    return {
        "status": "ok",
        "reclassified": len(review_ids),
        "themes_json": str(themes_path),
        "post_tool_route": "generate_pulse",
    }


QUALITY_TOOLS = [check_word_count, trim_quotes, regenerate_actions, reclassify_ambiguous_reviews]


def build_quality_tools():
    """Return the tool list for ToolNode registration."""
    return list(QUALITY_TOOLS)
