"""
run_phase2.py — CLI runner for Phase 2 LLM theme classification.

Reads the cleaned reviews produced by Phase 1, classifies each review into
one of the configured themes using Groq, and saves the per-theme statistics
as a JSON file in output/notes/.

Usage (run from project root):
    python src/scripts/run_phase2.py
    python src/scripts/run_phase2.py --input data/cleaned/cleaned_reviews.csv
    python src/scripts/run_phase2.py --batch-size 30
    python src/scripts/run_phase2.py --model llama3-70b-8192
    python src/scripts/run_phase2.py --verbose
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import importlib.util as _ilu

# ---------------------------------------------------------------------------
# Project root & module loading
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

THEMES_DIR = PROJECT_ROOT / "src" / "Phase2-themes"


def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod  = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.modules["Phase2_themes"] = type(sys)("Phase2_themes")
sys.modules["Phase2_themes"].__path__ = [str(THEMES_DIR)]

_prompts_mod = _load("Phase2_themes.prompts",  THEMES_DIR / "prompts.py",  "Phase2_themes")
_grouper_mod = _load("Phase2_themes.grouper",  THEMES_DIR / "grouper.py",  "Phase2_themes")

ThemeGrouper = _grouper_mod.ThemeGrouper

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 2 — Classify cleaned reviews into themes using Groq LLM"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/cleaned/cleaned_reviews.csv",
        metavar="FILE",
        help="Cleaned reviews CSV from Phase 1 (default: data/cleaned/cleaned_reviews.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/notes/theme_groups.json",
        metavar="FILE",
        help="Output JSON file for theme statistics (default: output/notes/theme_groups.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        metavar="N",
        help="Reviews per LLM call (default: 50)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Groq model to use (default: env LLM_MODEL or llama3-8b-8192)",
    )
    parser.add_argument(
        "--themes-config",
        type=str,
        default=None,
        metavar="FILE",
        help="Path to themes.yaml (default: config/themes.yaml)",
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
    import pandas as pd
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    logger = logging.getLogger(__name__)

    input_file  = PROJECT_ROOT / args.input
    output_file = PROJECT_ROOT / args.output

    if not input_file.exists():
        logger.error("Input file not found: %s", input_file)
        return 1

    # Load cleaned reviews
    df = pd.read_csv(input_file, encoding="utf-8")
    logger.info("Loaded %d reviews from %s", len(df), input_file)

    if df.empty:
        logger.error("Input CSV is empty — run Phase 1 first.")
        return 1

    # Initialise grouper
    grouper = ThemeGrouper(
        themes_config_path=args.themes_config,
        model=args.model,
        batch_size=args.batch_size,
    )

    # Classify
    groups = grouper.group_reviews(df)

    if not groups:
        logger.error("No theme groups produced — check LLM connectivity and API key.")
        return 1

    # Serialise to JSON
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result = {k: v.to_dict() for k, v in groups.items()}
    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    # Summary
    print("\n=== Phase 2 Complete ===")
    print(f"  Input    : {input_file}")
    print(f"  Output   : {output_file}")
    print(f"  Themes   : {len(groups)}")
    print()
    for theme_id, group in sorted(groups.items(), key=lambda x: -x[1].count):
        bar = "#" * min(group.count // 5, 40)
        print(
            f"  {group.theme_name:<14}  {group.count:>4} reviews  "
            f"avg {group.avg_rating:.1f}*  {group.sentiment:<8}  {bar}"
        )

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        exit_code = run(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nClassification interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).error("Fatal error: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
