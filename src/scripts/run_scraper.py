"""
run_scraper.py — CLI runner for Phase 1A review scraping.

Runs the ReviewScraperOrchestrator to scrape Groww app reviews from
Google Play Store and Apple App Store, saving results to data/raw/.

Usage (run from project root):
    python src/scripts/run_scraper.py
    python src/scripts/run_scraper.py --max-reviews 200
    python src/scripts/run_scraper.py --store playstore
    python src/scripts/run_scraper.py --store appstore
    python src/scripts/run_scraper.py --max-reviews 500 --output-dir data/raw
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Resolve project root (two levels up from src/scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Add project root to sys.path so playwright_config can be imported
sys.path.insert(0, str(PROJECT_ROOT))

# Phase1A-scraper uses a hyphen in its folder name which is not a valid Python
# identifier, so we add the src/ directory to sys.path and import via importlib.
SCRAPER_DIR = PROJECT_ROOT / "src" / "Phase1A-scraper"
sys.path.insert(0, str(SCRAPER_DIR.parent))  # adds src/ so sub-imports work

import importlib.util as _ilu

def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path, submodule_search_locations=[str(SCRAPER_DIR)])
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

# Load scrapers first (no relative imports)
_playstore_mod      = _load("Phase1A_scraper.playstore_scraper",   SCRAPER_DIR / "playstore_scraper.py", "Phase1A_scraper")
_appstore_mod       = _load("Phase1A_scraper.appstore_scraper",    SCRAPER_DIR / "appstore_scraper.py", "Phase1A_scraper")

# Create package marker
sys.modules["Phase1A_scraper"] = type(sys)("Phase1A_scraper")
sys.modules["Phase1A_scraper"].__path__ = [str(SCRAPER_DIR)]
sys.modules["Phase1A_scraper"].playstore_scraper = _playstore_mod
sys.modules["Phase1A_scraper"].appstore_scraper = _appstore_mod

# Now load orchestrator (has relative imports)
_orchestrator_mod   = _load("Phase1A_scraper.orchestrator",        SCRAPER_DIR / "orchestrator.py", "Phase1A_scraper")

ReviewScraperOrchestrator = _orchestrator_mod.ReviewScraperOrchestrator
PlayStoreScraper          = _playstore_mod.PlayStoreScraper
AppStoreScraper           = _appstore_mod.AppStoreScraper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1A — Scrape Groww app reviews from Play Store and App Store"
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=500,
        metavar="N",
        help="Maximum reviews to scrape per store (default: 500)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw",
        metavar="DIR",
        help="Output directory for CSV files (default: data/raw)",
    )
    parser.add_argument(
        "--store",
        choices=["both", "playstore", "appstore"],
        default="both",
        help="Which store to scrape (default: both)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    """
    Main async runner. Returns exit code (0 = success, 1 = failure).
    """
    output_dir = PROJECT_ROOT / args.output_dir

    if args.store == "both":
        orchestrator = ReviewScraperOrchestrator(
            max_reviews_per_store=args.max_reviews,
            output_dir=str(output_dir),
        )
        combined_df = await orchestrator.scrape_all(save_individual=True)
        orchestrator.save_combined(combined_df)

        ps_count = len(combined_df[combined_df["source"] == "play_store"])
        as_count = len(combined_df[combined_df["source"] == "app_store"])

        print("\n=== Scraping Complete ===")
        print(f"  Play Store : {ps_count} reviews  ->  {output_dir / 'playstore_reviews.csv'}")
        print(f"  App Store  : {as_count} reviews  ->  {output_dir / 'appstore_reviews.csv'}")
        print(f"  Total      : {len(combined_df)} reviews (after deduplication)")

        if len(combined_df) == 0:
            logging.getLogger(__name__).warning(
                "No reviews scraped. Check network connectivity and store URLs."
            )
            return 1

    elif args.store == "playstore":
        scraper = PlayStoreScraper(max_reviews=args.max_reviews)
        df = await scraper.scrape()
        if df.empty:
            logging.getLogger(__name__).warning("No Play Store reviews scraped.")
            return 1
        out_path = output_dir / "playstore_reviews.csv"
        scraper.save_to_csv(df, str(out_path))
        print(f"\n=== Play Store Scraping Complete ===")
        print(f"  Reviews : {len(df)}")
        print(f"  Output  : {out_path}")

    elif args.store == "appstore":
        scraper = AppStoreScraper(max_reviews=args.max_reviews)
        df = await scraper.scrape()
        if df.empty:
            logging.getLogger(__name__).warning("No App Store reviews scraped.")
            return 1
        out_path = output_dir / "appstore_reviews.csv"
        scraper.save_to_csv(df, str(out_path))
        print(f"\n=== App Store Scraping Complete ===")
        print(f"  Reviews : {len(df)}")
        print(f"  Output  : {out_path}")

    return 0


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        exit_code = asyncio.run(run(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).error(f"Fatal error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
