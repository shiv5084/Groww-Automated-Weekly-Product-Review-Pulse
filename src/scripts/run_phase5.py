"""
run_phase5.py — CLI runner for Phase 5 agentic quality loop.

Runs quality gates and remediation tools on an existing pulse note (from Phase 3)
before publish (Phase 4). Reuses the same rules and tools as the LangGraph
quality_agent node in src/main.py.

Usage (run from project root):
    python src/scripts/run_phase5.py
    python src/scripts/run_phase5.py --input output/notes/pulse_2026-05-16.md
    python src/scripts/run_phase5.py --themes output/notes/theme_groups.json
    python src/scripts/run_phase5.py --max-iterations 3 --verbose
    python src/scripts/run_phase5.py --check-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import importlib.util as _ilu

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

QUALITY_DIR = PROJECT_ROOT / "src" / "Phase5-agenticQuality"
GEN_DIR = PROJECT_ROOT / "src" / "Phase3-generator"


def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_quality_modules():
    sys.modules["Phase5_agenticQuality"] = type(sys)("Phase5_agenticQuality")
    sys.modules["Phase5_agenticQuality"].__path__ = [str(QUALITY_DIR)]
    _load(
        "Phase5_agenticQuality.quality_checks",
        QUALITY_DIR / "quality_checks.py",
        "Phase5_agenticQuality",
    )
    agent_mod = _load(
        "Phase5_agenticQuality.quality_agent",
        QUALITY_DIR / "quality_agent.py",
        "Phase5_agenticQuality",
    )
    tools_mod = _load(
        "Phase5_agenticQuality.tools",
        QUALITY_DIR / "tools.py",
        "Phase5_agenticQuality",
    )
    return agent_mod, tools_mod


def _load_generator_modules():
    sys.modules["Phase3_generator"] = type(sys)("Phase3_generator")
    sys.modules["Phase3_generator"].__path__ = [str(GEN_DIR)]
    pulse_mod = _load(
        "Phase3_generator.pulse_note",
        GEN_DIR / "pulse_note.py",
        "Phase3_generator",
    )
    formatter_mod = _load(
        "Phase3_generator.formatter",
        GEN_DIR / "formatter.py",
        "Phase3_generator",
    )
    return pulse_mod, formatter_mod


def _latest_pulse_md(notes_dir: Path) -> Path:
    candidates = sorted(notes_dir.glob("pulse_*.md"), reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No pulse_*.md files in {notes_dir}. Run Phase 3 first."
        )
    return candidates[0]


def _pulse_data_sidecar(md_path: Path) -> Path:
    return md_path.with_suffix(".json")


def _load_or_build_pulse_note_data(
    themes_path: Path,
    md_path: Path,
    pulse_data_path: Optional[Path],
    model: Optional[str],
    max_words: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Load pulse_note_data JSON or rebuild from theme_groups via Phase 3."""
    tools_mod = _load_quality_modules()[1]

    if pulse_data_path and pulse_data_path.exists():
        with pulse_data_path.open(encoding="utf-8") as fh:
            logger.info("Loaded pulse note data from %s", pulse_data_path)
            return json.load(fh)

    sidecar = _pulse_data_sidecar(md_path)
    if sidecar.exists():
        with sidecar.open(encoding="utf-8") as fh:
            logger.info("Loaded pulse note data from %s", sidecar)
            return json.load(fh)

    if not themes_path.exists():
        raise FileNotFoundError(
            f"Themes file not found: {themes_path}. "
            "Run Phase 2 or pass --pulse-data."
        )

    with themes_path.open(encoding="utf-8") as fh:
        themes = json.load(fh)
    if not themes:
        raise ValueError(f"Empty themes file: {themes_path}")

    pulse_mod, _ = _load_generator_modules()
    logger.info(
        "No pulse note data sidecar — rebuilding from themes (%s)", themes_path
    )
    generator = pulse_mod.PulseNoteGenerator(model=model, max_words=max_words)
    note = generator.generate(themes)
    return tools_mod.pulse_note_to_dict(note)


def _regenerate_pulse_files(state: dict[str, Any]) -> dict[str, Any]:
    """Rebuild pulse md/txt/html from theme_groups.json (after reclassify)."""
    tools_mod = _load_quality_modules()[1]
    pulse_mod, formatter_mod = _load_generator_modules()

    themes_path = Path(state["themes_json"])
    with themes_path.open(encoding="utf-8") as fh:
        themes = json.load(fh)

    generator = pulse_mod.PulseNoteGenerator(
        model=state.get("model"),
        max_words=int(state.get("quality_word_limit") or 250),
    )
    note = generator.generate(themes)
    formatter = formatter_mod.PulseNoteFormatter()

    md_path = Path(state["pulse_md"])
    txt_path = Path(state["pulse_txt"]) if state.get("pulse_txt") else md_path.with_suffix(".txt")
    html_path = (
        Path(state["pulse_html"])
        if state.get("pulse_html")
        else md_path.with_name(md_path.stem + ".html")
    )

    md_path.write_text(formatter.format_for_docs(note), encoding="utf-8")
    txt_path.write_text(formatter.format_for_email(note), encoding="utf-8")
    html_path.write_text(formatter.format_for_html(note), encoding="utf-8")

    pulse_data = tools_mod.pulse_note_to_dict(note)
    sidecar = _pulse_data_sidecar(md_path)
    sidecar.write_text(json.dumps(pulse_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        **state,
        "pulse_txt": str(txt_path),
        "pulse_html": str(html_path),
        "pulse_note_data": pulse_data,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 5 — Agentic quality loop on a pulse note "
            "(word count, themes, actions, reclassify)"
        )
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        metavar="FILE",
        help="Pulse Markdown file (default: latest output/notes/pulse_*.md)",
    )
    parser.add_argument(
        "--themes",
        type=str,
        default="output/notes/theme_groups.json",
        metavar="FILE",
        help="Theme groups JSON from Phase 2",
    )
    parser.add_argument(
        "--cleaned-csv",
        type=str,
        default="data/cleaned/cleaned_reviews.csv",
        metavar="FILE",
        help="Cleaned reviews CSV for reclassify tool",
    )
    parser.add_argument(
        "--pulse-data",
        type=str,
        default=None,
        metavar="FILE",
        help="Optional pulse_note_data JSON (default: <pulse>.json or rebuild from themes)",
    )
    parser.add_argument(
        "--notes-dir",
        type=str,
        default="output/notes",
        metavar="DIR",
        help="Directory to search for latest pulse when --input omitted",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        metavar="N",
        help="Max remediation loops (default: 3)",
    )
    parser.add_argument(
        "--word-limit",
        type=int,
        default=250,
        metavar="N",
        help="Maximum pulse word count (default: 250)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Groq model for regenerate_actions / reclassify",
    )
    parser.add_argument(
        "--reclassify-hint",
        type=str,
        default=None,
        help="Hint passed to reclassify_ambiguous_reviews tool",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run quality checks once without remediation tools",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    logger = logging.getLogger(__name__)

    agent_mod, _tools_mod = _load_quality_modules()
    checks_mod = sys.modules["Phase5_agenticQuality.quality_checks"]
    evaluate_quality = checks_mod.evaluate_quality
    run_quality_loop = agent_mod.run_quality_loop

    notes_dir = PROJECT_ROOT / args.notes_dir
    if args.input:
        md_path = PROJECT_ROOT / args.input
    else:
        md_path = _latest_pulse_md(notes_dir)

    if not md_path.exists():
        logger.error("Pulse file not found: %s", md_path)
        return 1

    txt_path = md_path.with_suffix(".txt")
    html_path = md_path.with_name(md_path.stem + ".html")
    themes_path = PROJECT_ROOT / args.themes
    cleaned_csv = PROJECT_ROOT / args.cleaned_csv
    pulse_data_path = PROJECT_ROOT / args.pulse_data if args.pulse_data else None

    try:
        pulse_note_data = _load_or_build_pulse_note_data(
            themes_path,
            md_path,
            pulse_data_path,
            args.model,
            args.word_limit,
            logger,
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    sidecar = _pulse_data_sidecar(md_path)
    if not sidecar.exists():
        sidecar.write_text(
            json.dumps(pulse_note_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Wrote pulse note data sidecar -> %s", sidecar)

    state: dict[str, Any] = {
        "project_root": str(PROJECT_ROOT),
        "pulse_md": str(md_path),
        "pulse_txt": str(txt_path) if txt_path.exists() else str(txt_path),
        "pulse_html": str(html_path) if html_path.exists() else str(html_path),
        "themes_json": str(themes_path),
        "cleaned_csv": str(cleaned_csv),
        "pulse_note_data": pulse_note_data,
        "quality_iterations": 0,
        "max_quality_iterations": args.max_iterations,
        "quality_word_limit": args.word_limit,
        "quality_remediation": [],
        "errors": [],
        "model": args.model,
        "reclassify_hint": args.reclassify_hint,
        "skip_quality": False,
    }

    if args.check_only:
        report = evaluate_quality(
            pulse_md_path=state["pulse_md"],
            pulse_note_data=state["pulse_note_data"],
            themes_json_path=state["themes_json"],
            word_limit=args.word_limit,
        )
        log_mod = _load(
            "Phase5_agenticQuality.quality_log",
            QUALITY_DIR / "quality_log.py",
            "Phase5_agenticQuality",
        )
        log_path = log_mod.record_quality_check(
            PROJECT_ROOT,
            event="check_only",
            passed=report.passed,
            failures=report.failures,
            details=report.details,
            pulse_md=str(md_path),
        )
        _print_report(
            md_path,
            report,
            passed=report.passed,
            iterations=0,
            quality_log=str(log_path),
        )
        return 0 if report.passed else 1

    logger.info("Starting quality loop on %s", md_path)
    final_state, passed, report = run_quality_loop(
        state,
        regenerate_pulse=_regenerate_pulse_files,
    )

    log_mod = _load(
        "Phase5_agenticQuality.quality_log",
        QUALITY_DIR / "quality_log.py",
        "Phase5_agenticQuality",
    )
    quality_log = final_state.get("quality_log")
    if not quality_log:
        log_path = log_mod.record_quality_check(
            PROJECT_ROOT,
            event=final_state.get("quality_status") or "completed",
            passed=passed,
            failures=report.failures,
            details=report.details,
            iterations=int(final_state.get("quality_iterations") or 0),
            remediations=final_state.get("quality_remediation"),
            pulse_md=str(md_path),
        )
        quality_log = str(log_path)
        final_state["quality_log"] = quality_log

    _print_report(
        md_path,
        report,
        passed=passed,
        iterations=int(final_state.get("quality_iterations") or 0),
        remediations=final_state.get("quality_remediation"),
        quality_log=quality_log,
        errors=final_state.get("errors"),
    )
    return 0 if passed else 1


def _print_report(
    md_path: Path,
    report: Any,
    *,
    passed: bool,
    iterations: int,
    remediations: list[str] | None = None,
    quality_log: str | None = None,
    errors: list[str] | None = None,
) -> None:
    status = "PASSED" if passed else "FAILED"
    print("\n=== Phase 5 Complete ===")
    print(f"  Pulse input   : {md_path}")
    print(f"  Quality       : {status}")
    print(f"  Iterations    : {iterations}")
    print(f"  Word count    : {report.details.get('word_count', '?')} "
          f"(limit {report.details.get('word_limit', 250)})")
    if report.failures:
        print(f"  Failures      : {', '.join(report.failures)}")
    if remediations:
        print(f"  Remediations  : {remediations}")
    if quality_log:
        print(f"  Quality log   : {quality_log}")
    if errors:
        print(f"  Warnings      : {errors}")
    print()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        print("\nQuality loop interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
