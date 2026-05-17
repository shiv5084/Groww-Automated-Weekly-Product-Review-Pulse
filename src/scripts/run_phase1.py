"""
run_phase1.py — CLI runner for Phase 1 data ingestion & PII scrubbing.

Loads scraped review CSVs from data/raw/, validates schema, filters by date
range, scrubs PII, drops short reviews, and saves the cleaned dataset to
data/cleaned/.

Usage (run from project root):
    python src/scripts/run_phase1.py
    python src/scripts/run_phase1.py --weeks 8
    python src/scripts/run_phase1.py --input data/raw/combined_reviews.csv
    python src/scripts/run_phase1.py --output data/cleaned/cleaned_reviews.csv
    python src/scripts/run_phase1.py --weeks 12 --verbose
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import importlib.util as _ilu

# Resolve project root (two levels up from src/scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INGESTION_DIR = PROJECT_ROOT / "src" / "Phase1-ingestion"
PII_DIR       = PROJECT_ROOT / "src" / "Phase1-pii"


def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod  = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register package markers so relative imports inside the modules resolve
sys.modules["Phase1_ingestion"] = type(sys)("Phase1_ingestion")
sys.modules["Phase1_ingestion"].__path__ = [str(INGESTION_DIR)]
sys.modules["Phase1_pii"] = type(sys)("Phase1_pii")
sys.modules["Phase1_pii"].__path__ = [str(PII_DIR)]

_csv_loader_mod  = _load("Phase1_ingestion.csv_loader",  INGESTION_DIR / "csv_loader.py",  "Phase1_ingestion")
_date_filter_mod = _load("Phase1_ingestion.date_filter", INGESTION_DIR / "date_filter.py", "Phase1_ingestion")
_patterns_mod    = _load("Phase1_pii.patterns",          PII_DIR       / "patterns.py",    "Phase1_pii")
_scrubber_mod    = _load("Phase1_pii.scrubber",          PII_DIR       / "scrubber.py",    "Phase1_pii")

ReviewIngestion = _csv_loader_mod.ReviewIngestion
DateFilter      = _date_filter_mod.DateFilter
PIIScrubber     = _scrubber_mod.PIIScrubber


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 — Ingest scraped reviews, filter by date, and scrub PII"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/combined_reviews.csv",
        metavar="FILE",
        help="Path to the input CSV file (default: data/raw/combined_reviews.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/cleaned/cleaned_reviews.csv",
        metavar="FILE",
        help="Path for the cleaned output CSV (default: data/cleaned/cleaned_reviews.csv)",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        metavar="N",
        help="Number of weeks of reviews to keep (default: 12)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    """
    Main runner. Returns exit code (0 = success, 1 = failure).
    """
    logger = logging.getLogger(__name__)

    input_file  = PROJECT_ROOT / args.input
    output_file = PROJECT_ROOT / args.output

    logger.info("=== Starting Phase 1: Ingestion & PII Scrubbing ===")

    # 1. Load & validate
    ingestion = ReviewIngestion()
    df = ingestion.load_csv(str(input_file))
    logger.info(f"Loaded {len(df)} reviews from {input_file}")

    ingestion.validate_schema(df)
    df = ingestion.clean_ratings(df)
    logger.info(f"After rating cleanup : {len(df)} reviews")

    # 2. Date filtering
    d_filter = DateFilter(weeks=args.weeks)
    df = d_filter.parse_dates(df)
    df = d_filter.filter_by_date_range(df)
    logger.info(f"After {args.weeks}-week date filter : {len(df)} reviews")

    # 3. PII scrubbing + short-review filtering
    pii_scrubber = PIIScrubber()
    df_clean = pii_scrubber.scrub_dataframe(df)
    logger.info(f"After PII scrubbing & short-review filter : {len(df_clean)} reviews")

    # 4. Save output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(output_file, index=False, encoding="utf-8")

    # Summary
    report = pii_scrubber.get_scrub_report()
    print("\n=== Phase 1 Complete ===")
    print(f"  Input            : {input_file}")
    print(f"  Output           : {output_file}")
    print(f"  Reviews saved    : {len(df_clean)}")
    print(f"  Short dropped    : {report['short_reviews_dropped']}  (< 5 words)")
    print(f"  PII-only dropped : {report['fully_redacted_reviews_dropped']}")
    print(f"  Truncated (LLM)  : {report['reviews_truncated']}")

    redactions = {
        **{f"title/{k}": v for k, v in report["title_redactions"].items() if v > 0},
        **{f"text/{k}":  v for k, v in report["review_text_redactions"].items() if v > 0},
    }
    if redactions:
        print("  PII redactions   :")
        for label, count in redactions.items():
            print(f"    {label}: {count}")
    else:
        print("  PII redactions   : none")

    if len(df_clean) == 0:
        logger.warning("No reviews remain after filtering. Check input data or widen the date range.")
        return 1

    return 0


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
        print("\nPipeline interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).error(f"Fatal error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
