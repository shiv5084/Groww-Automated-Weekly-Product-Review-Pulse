"""
run_phase3.py — CLI runner for Phase 3 pulse note generation.

Reads the theme_groups.json produced by Phase 2, generates a <=250 word
weekly pulse note, and saves it as Markdown, plain text, and HTML to
output/notes/.

Usage (run from project root):
    python src/scripts/run_phase3.py
    python src/scripts/run_phase3.py --input output/notes/theme_groups.json
    python src/scripts/run_phase3.py --output-dir output/notes
    python src/scripts/run_phase3.py --model llama-3.3-70b-versatile
    python src/scripts/run_phase3.py --verbose
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import importlib.util as _ilu

# ---------------------------------------------------------------------------
# Project root & module loading
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GEN_DIR = PROJECT_ROOT / "src" / "Phase3-generator"


def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod  = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.modules["Phase3_generator"] = type(sys)("Phase3_generator")
sys.modules["Phase3_generator"].__path__ = [str(GEN_DIR)]

_pulse_mod     = _load("Phase3_generator.pulse_note", GEN_DIR / "pulse_note.py",  "Phase3_generator")
_formatter_mod = _load("Phase3_generator.formatter",  GEN_DIR / "formatter.py",   "Phase3_generator")

PulseNoteGenerator = _pulse_mod.PulseNoteGenerator
PulseNoteFormatter = _formatter_mod.PulseNoteFormatter

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 3 — Generate weekly pulse note from theme groups"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="output/notes/theme_groups.json",
        metavar="FILE",
        help="Theme groups JSON from Phase 2 (default: output/notes/theme_groups.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/notes",
        metavar="DIR",
        help="Directory for output files (default: output/notes)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Groq model to use (default: env LLM_MODEL or llama-3.3-70b-versatile)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=250,
        metavar="N",
        help="Maximum word count for the pulse note (default: 250)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    """Main runner. Returns exit code (0 = success, 1 = failure)."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    logger = logging.getLogger(__name__)

    input_file = PROJECT_ROOT / args.input
    output_dir = PROJECT_ROOT / args.output_dir

    if not input_file.exists():
        logger.error("Input file not found: %s", input_file)
        logger.error("Run Phase 2 first: python src/scripts/run_phase2.py")
        return 1

    # Load theme groups
    with input_file.open(encoding="utf-8") as fh:
        themes = json.load(fh)

    # -----------------------------------------------------------------------
    # Cleanup old logs and notes (Phase 3 requirement)
    # -----------------------------------------------------------------------
    logs_dir = PROJECT_ROOT / "output" / "logs"
    # We use output_dir from args, which defaults to output/notes
    target_dirs = [logs_dir, output_dir]
    
    # Remove duplicates if any
    unique_dirs = list(set(target_dirs))
    
    for d in unique_dirs:
        if d.exists():
            for item in d.iterdir():
                if item.is_file() and item.name != ".gitkeep":
                    try:
                        item.unlink()
                    except Exception as e:
                        logger.warning("Failed to delete %s: %s", item, e)

    # Re-save the input themes to the (potentially deleted) input_file path
    # so it stays available for reference or Phase 5
    input_file.parent.mkdir(parents=True, exist_ok=True)
    with input_file.open("w", encoding="utf-8") as fh:
        json.dump(themes, fh, ensure_ascii=False, indent=2)

    logger.info("Cleaned up old output logs/notes and started fresh.")

    if not themes:
        logger.error("theme_groups.json is empty — re-run Phase 2.")
        return 1

    logger.info("Loaded %d themes from %s", len(themes), input_file)

    # Generate pulse note
    generator = PulseNoteGenerator(model=args.model, max_words=args.max_words)
    note = generator.generate(themes)

    # Format outputs
    formatter  = PulseNoteFormatter()
    md_content   = formatter.format_for_docs(note)
    txt_content  = formatter.format_for_email(note)
    html_content = formatter.format_for_html(note)

    # Save files
    output_dir.mkdir(parents=True, exist_ok=True)
    date_slug = datetime.today().strftime("%Y-%m-%d")

    md_path   = output_dir / f"pulse_{date_slug}.md"
    txt_path  = output_dir / f"pulse_{date_slug}.txt"
    html_path = output_dir / f"pulse_{date_slug}.html"

    md_path.write_text(md_content,   encoding="utf-8")
    txt_path.write_text(txt_content,  encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")

    # Summary
    word_count = note.word_count()
    within_limit = "OK" if generator.validate_word_count(note) else "OVER LIMIT"

    print("\n=== Phase 3 Complete ===")
    print(f"  Input      : {input_file}")
    print(f"  Markdown   : {md_path}")
    print(f"  Plain text : {txt_path}")
    print(f"  HTML       : {html_path}")
    print(f"  Word count : {word_count} / {args.max_words}  [{within_limit}]")
    print(f"  Themes     : {len(note.top_themes)}")
    print(f"  Actions    : {len(note.actions)}")
    print()
    print("--- Preview (Markdown) ---")
    print(md_content)

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        exit_code = run(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nGeneration interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).error("Fatal error: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
