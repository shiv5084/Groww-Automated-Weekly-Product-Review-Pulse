"""
orchestrator.py — Review scraper orchestrator.

Combines Play Store and App Store scrapers, deduplicates reviews,
and saves the merged output to CSV files.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .playstore_scraper import PlayStoreScraper
from .appstore_scraper import AppStoreScraper

logger = logging.getLogger(__name__)


class ReviewScraperOrchestrator:
    """
    Orchestrates the scraping of reviews from both Play Store and App Store.
    Handles deduplication and CSV output.
    """
    
    def __init__(
        self,
        max_reviews_per_store: int = 500,
        output_dir: str = "data/raw"
    ):
        """
        Initialize the orchestrator.
        
        Args:
            max_reviews_per_store: Maximum reviews to scrape per store
            output_dir: Directory to save output CSVs
        """
        self.max_reviews_per_store = max_reviews_per_store
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.playstore_scraper = PlayStoreScraper(max_reviews=max_reviews_per_store)
        self.appstore_scraper = AppStoreScraper(max_reviews=max_reviews_per_store)
    
    async def scrape_all(self, save_individual: bool = True) -> pd.DataFrame:
        """
        Scrape reviews from both stores concurrently.
        
        Args:
            save_individual: If True, save individual CSVs for each store
            
        Returns:
            Combined DataFrame with all reviews
        """
        logger.info("=== Starting Review Scraping Orchestrator ===")
        logger.info(f"Target: {self.max_reviews_per_store} reviews per store")
        
        # Scrape both stores concurrently
        logger.info("Launching concurrent scrapers...")
        playstore_task = asyncio.create_task(self._scrape_playstore())
        appstore_task = asyncio.create_task(self._scrape_appstore())
        
        playstore_df, appstore_df = await asyncio.gather(
            playstore_task,
            appstore_task,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(playstore_df, Exception):
            logger.error(f"Play Store scraping failed: {playstore_df}")
            playstore_df = pd.DataFrame()
        
        if isinstance(appstore_df, Exception):
            logger.error(f"App Store scraping failed: {appstore_df}")
            appstore_df = pd.DataFrame()
        
        # Save individual CSVs if requested
        if save_individual:
            if not playstore_df.empty:
                playstore_path = self.output_dir / "playstore_reviews.csv"
                playstore_df.to_csv(playstore_path, index=False, encoding="utf-8")
                logger.info(f"Saved Play Store reviews to {playstore_path}")
            
            if not appstore_df.empty:
                appstore_path = self.output_dir / "appstore_reviews.csv"
                appstore_df.to_csv(appstore_path, index=False, encoding="utf-8")
                logger.info(f"Saved App Store reviews to {appstore_path}")
        
        # Merge and deduplicate
        combined_df = self.merge_and_deduplicate([playstore_df, appstore_df])
        
        logger.info(f"=== Scraping Complete ===")
        logger.info(f"Play Store: {len(playstore_df)} reviews")
        logger.info(f"App Store: {len(appstore_df)} reviews")
        logger.info(f"Combined (after dedup): {len(combined_df)} reviews")
        
        return combined_df
    
    async def _scrape_playstore(self) -> pd.DataFrame:
        """Scrape Play Store reviews."""
        try:
            return await self.playstore_scraper.scrape()
        except Exception as e:
            logger.error(f"Play Store scraping failed: {e}")
            raise
    
    async def _scrape_appstore(self) -> pd.DataFrame:
        """Scrape App Store reviews."""
        try:
            return await self.appstore_scraper.scrape()
        except Exception as e:
            logger.error(f"App Store scraping failed: {e}")
            raise
    
    def merge_and_deduplicate(self, dfs: list[pd.DataFrame]) -> pd.DataFrame:
        """
        Merge multiple DataFrames and remove duplicates.
        
        Deduplication logic:
        - Reviews with identical (review_text, rating, date) are considered duplicates
        - Keep the first occurrence
        
        Args:
            dfs: List of DataFrames to merge
            
        Returns:
            Merged and deduplicated DataFrame
        """
        # Filter out empty DataFrames
        valid_dfs = [df for df in dfs if not df.empty]
        
        if not valid_dfs:
            logger.warning("No valid DataFrames to merge")
            return pd.DataFrame(columns=["rating", "title", "review_text", "date", "source"])
        
        # Concatenate all DataFrames
        combined = pd.concat(valid_dfs, ignore_index=True)
        
        # Count before deduplication
        before_count = len(combined)
        
        # Deduplicate based on review_text, rating, and date
        # Keep first occurrence
        combined = combined.drop_duplicates(
            subset=["review_text", "rating", "date"],
            keep="first"
        )
        
        after_count = len(combined)
        duplicates_removed = before_count - after_count
        
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate reviews")
        
        # Sort by date (most recent first)
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        combined = combined.sort_values("date", ascending=False)
        combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
        
        return combined
    
    def save_combined(self, df: pd.DataFrame, filename: str = "combined_reviews.csv") -> None:
        """
        Save the combined DataFrame to CSV.
        
        Args:
            df: Combined reviews DataFrame
            filename: Output filename
        """
        output_path = self.output_dir / filename
        df.to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"Saved combined reviews to {output_path}")


async def main():
    """
    CLI entry point for running the scraper orchestrator standalone.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Groww app reviews from Play Store and App Store")
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=500,
        help="Maximum reviews to scrape per store (default: 500)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw",
        help="Output directory for CSV files (default: data/raw)"
    )
    parser.add_argument(
        "--save-combined",
        action="store_true",
        help="Save a combined CSV file in addition to individual store files"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    )
    
    # Run orchestrator
    orchestrator = ReviewScraperOrchestrator(
        max_reviews_per_store=args.max_reviews,
        output_dir=args.output_dir
    )
    
    combined_df = await orchestrator.scrape_all(save_individual=True)
    
    if args.save_combined:
        orchestrator.save_combined(combined_df)
    
    print(f"\n✅ Scraping complete!")
    print(f"   Total reviews: {len(combined_df)}")
    print(f"   Output directory: {args.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
