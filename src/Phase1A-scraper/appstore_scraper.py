"""
appstore_scraper.py — Apple App Store review fetcher.

Uses Apple's official public iTunes RSS Feed API to fetch reviews.
No browser, no login, no CSS selectors, and no broken tokens required.

Public endpoint:
  https://itunes.apple.com/in/rss/customerreviews/id=1404871703/sortBy=mostRecent/json
"""

import logging
import time
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Groww App Store app ID (India store)
GROWW_APP_ID = "1404871703"
GROWW_APP_COUNTRY = "in"

# iTunes RSS Feed base URL — Apple's official public API
ITUNES_RSS_BASE = (
    f"https://itunes.apple.com/{GROWW_APP_COUNTRY}/rss/customerreviews"
    f"/id={GROWW_APP_ID}/sortBy=mostRecent/json"
)

MAX_PAGES = 10  # Apple caps at 10 pages (500 reviews)


class AppStoreScraper:
    """
    Fetches reviews from Apple App Store using the iTunes RSS Feed public API.
    This replaces the broken app-store-scraper package.
    """

    def __init__(self, max_reviews: int = 500):
        self.max_reviews = max_reviews
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        })

    async def scrape(self) -> pd.DataFrame:
        """
        Fetch reviews from Apple App Store via the iTunes RSS Feed API.
        (Kept async to match the orchestrator interface)
        """
        logger.info(f"Fetching App Store reviews via official RSS API (Target: {self.max_reviews})")

        all_reviews = []
        page = 1
        next_url = ITUNES_RSS_BASE

        while page <= MAX_PAGES and len(all_reviews) < self.max_reviews:
            try:
                response = self.session.get(next_url, timeout=30)
                if response.status_code != 200:
                    logger.error(f"App Store API returned HTTP {response.status_code}")
                    break

                data = response.json()
                feed = data.get("feed", {})
                entries = feed.get("entry", [])

                # First entry is app info (not a review) — skip it
                if page == 1 and entries:
                    entries = entries[1:]

                if not entries:
                    break

                parsed = self._parse_entries(entries)
                all_reviews.extend(parsed)
                logger.info(f"Fetched {len(all_reviews)} reviews from App Store so far...")

                # Find next page URL from feed links
                next_url = self._get_next_page_url(feed)
                if not next_url:
                    break

                page += 1
                time.sleep(random.uniform(1.0, 2.0))

            except Exception as e:
                logger.error(f"Error fetching App Store reviews: {e}")
                break

        if not all_reviews:
            logger.warning("No reviews fetched from App Store")
            return pd.DataFrame(columns=["rating", "title", "review_text", "date", "source"])

        df = pd.DataFrame(all_reviews[:self.max_reviews])
        logger.info(f"App Store: {len(df)} clean English reviews")
        return df

    def _parse_entries(self, entries: list[dict]) -> list[dict]:
        reviews = []
        for entry in entries:
            try:
                rating_raw = entry.get("im:rating", {}).get("label", "0")
                rating = int(rating_raw) if str(rating_raw).isdigit() else 0
                title = entry.get("title", {}).get("label", "").strip()
                review_text = entry.get("content", {}).get("label", "").strip()
                date_raw = entry.get("updated", {}).get("label", "")
                date_str = self._parse_date(date_raw)

                if not review_text or not self._is_english(review_text):
                    continue

                reviews.append({
                    "rating": rating,
                    "title": title,
                    "review_text": review_text,
                    "date": date_str,
                    "source": "app_store",
                })
            except Exception:
                continue
        return reviews

    def _get_next_page_url(self, feed: dict) -> str | None:
        links = feed.get("link", [])
        if isinstance(links, dict):
            links = [links]
        for link in links:
            attrs = link.get("attributes", {})
            if attrs.get("rel") == "next":
                href = attrs.get("href", "")
                # Apple sometimes returns XML pagination URLs even when JSON is requested
                return href.replace("/xml", "/json")
        return None

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            clean = date_str.split("T")[0]
            return datetime.strptime(clean, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return datetime.now().strftime("%Y-%m-%d")

    def _is_english(self, text: str) -> bool:
        if not text:
            return False
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        return ascii_chars / len(text) > 0.7

    def save_to_csv(self, df: pd.DataFrame, output_path: str) -> None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_file, index=False, encoding="utf-8")
        logger.info(f"Saved {len(df)} App Store reviews to {output_file}")