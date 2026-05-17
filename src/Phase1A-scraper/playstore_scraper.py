"""
playstore_scraper.py — Google Play Store review scraper using google-play-scraper API.

Uses the google-play-scraper library which calls Google's internal APIs
instead of web scraping. Much more reliable and faster.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from google_play_scraper import app, reviews, Sort

logger = logging.getLogger(__name__)


class PlayStoreScraper:
    """
    Scrapes reviews from Google Play Store using the google-play-scraper API.
    
    This is much more reliable than web scraping as it uses Google's internal APIs.
    """
    
    def __init__(self, max_reviews: int = 500):
        """
        Initialize the Play Store scraper.
        
        Args:
            max_reviews: Maximum number of reviews to scrape (default: 500)
        """
        self.max_reviews = max_reviews
        self.app_id = "com.nextbillion.groww"
        self.reviews_data: list[dict] = []
        
    async def scrape(self) -> pd.DataFrame:
        """
        Main scraping method using Google Play Store API.
        
        Returns:
            DataFrame with columns: rating, title, review_text, date, source
        """
        logger.info(f"Starting Play Store scraper — target: {self.max_reviews} reviews")
        
        try:
            # Get app info first
            app_info = app(self.app_id)
            logger.info(f"App: {app_info['title']} (Rating: {app_info['score']:.1f})")
            
            # Get reviews using the API
            logger.info("Fetching reviews from Google Play Store API...")
            
            # Fetch reviews in batches
            result, continuation_token = reviews(
                self.app_id,
                lang='en',  # English reviews
                country='us',  # US store
                sort=Sort.NEWEST,  # Get newest reviews first
                count=min(self.max_reviews, 200),  # API limit per request
                filter_score_with=None  # All ratings
            )
            
            self.reviews_data.extend(result)
            
            # If we need more reviews and there's a continuation token, fetch more
            while len(self.reviews_data) < self.max_reviews and continuation_token:
                logger.info(f"Fetched {len(self.reviews_data)} reviews, getting more...")
                
                result, continuation_token = reviews(
                    self.app_id,
                    continuation_token=continuation_token,
                    lang='en',
                    country='us',
                    sort=Sort.NEWEST,
                    count=min(self.max_reviews - len(self.reviews_data), 200)
                )
                
                self.reviews_data.extend(result)
            
            logger.info(f"Fetched {len(self.reviews_data)} reviews from API")
            
            # Convert to our format
            processed_reviews = self._process_reviews(self.reviews_data)
            
            logger.info(f"Processed {len(processed_reviews)} reviews from Play Store")
            
        except Exception as e:
            logger.error(f"Error during Play Store scraping: {e}")
            processed_reviews = []
        
        # Convert to DataFrame
        df = pd.DataFrame(processed_reviews)
        if not df.empty:
            df["source"] = "play_store"
        
        return df
    
    def _process_reviews(self, raw_reviews: list[dict]) -> list[dict]:
        """
        Process raw API reviews into our standard format.
        
        Args:
            raw_reviews: Raw reviews from google-play-scraper
            
        Returns:
            List of processed review dictionaries
        """
        processed = []
        
        for review in raw_reviews:
            try:
                # Extract data from API response
                rating = review.get('score', 0)
                review_text = review.get('content', '').strip()
                date_obj = review.get('at')
                
                # Skip empty reviews
                if not review_text or rating == 0:
                    continue
                
                # Format date
                if date_obj:
                    date = date_obj.strftime("%Y-%m-%d")
                else:
                    date = datetime.now().strftime("%Y-%m-%d")
                
                # Remove emojis and clean text
                review_text = self._remove_emojis(review_text)
                
                # Basic English check
                if not self._is_english(review_text):
                    continue
                
                processed.append({
                    "rating": rating,
                    "title": "",  # Google Play doesn't have review titles
                    "review_text": review_text,
                    "date": date,
                })
                
            except Exception as e:
                logger.warning(f"Failed to process review: {e}")
                continue
        
        return processed
    
    def _remove_emojis(self, text: str) -> str:
        """Remove all emojis from text."""
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub(r'', text)
    
    def _is_english(self, text: str) -> bool:
        """
        Basic check if text is in English.
        Checks if majority of characters are ASCII.
        """
        if not text:
            return False
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        return ascii_chars / len(text) > 0.7
    
    def save_to_csv(self, df: pd.DataFrame, output_path: str) -> None:
        """
        Save reviews DataFrame to CSV.
        
        Args:
            df: Reviews DataFrame
            output_path: Path to output CSV file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(output_file, index=False, encoding="utf-8")
        logger.info(f"Saved {len(df)} reviews to {output_file}")