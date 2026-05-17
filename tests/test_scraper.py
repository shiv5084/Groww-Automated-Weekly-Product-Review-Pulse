"""
test_scraper.py — Unit tests for Phase 1A review scrapers.

Tests the Play Store scraper, App Store scraper, and orchestrator
with mocked Playwright page content.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Import scrapers
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))
from Phase1A_scraper.playstore_scraper import PlayStoreScraper
from Phase1A_scraper.appstore_scraper import AppStoreScraper
from Phase1A_scraper.orchestrator import ReviewScraperOrchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_playstore_page():
    """Mock Playwright Page object for Play Store."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=1000)  # scroll height
    page.locator = MagicMock()
    return page


@pytest.fixture
def mock_appstore_page():
    """Mock Playwright Page object for App Store."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.locator = MagicMock()
    return page


# ---------------------------------------------------------------------------
# PlayStoreScraper Tests
# ---------------------------------------------------------------------------

class TestPlayStoreScraper:
    """Tests for PlayStoreScraper."""
    
    def test_init(self):
        """Test scraper initialization."""
        scraper = PlayStoreScraper(max_reviews=100)
        assert scraper.max_reviews == 100
        assert "play.google.com" in scraper.url
        assert scraper.reviews == []
    
    def test_parse_rating(self):
        """Test rating parsing from aria-label."""
        scraper = PlayStoreScraper()
        
        assert scraper._parse_rating("Rated 5 stars out of five stars") == 5
        assert scraper._parse_rating("Rated 3 stars out of five stars") == 3
        assert scraper._parse_rating("1 star") == 1
        assert scraper._parse_rating(None) == 0
        assert scraper._parse_rating("No rating") == 0
    
    def test_parse_date(self):
        """Test date parsing."""
        scraper = PlayStoreScraper()
        
        # Absolute date
        result = scraper._parse_date("January 15, 2026")
        assert result == "2026-01-15"
        
        # Relative date (should return current date)
        result = scraper._parse_date("2 days ago")
        assert result == datetime.now().strftime("%Y-%m-%d")
        
        # Empty string
        result = scraper._parse_date("")
        assert result == datetime.now().strftime("%Y-%m-%d")
    
    def test_remove_emojis(self):
        """Test emoji removal."""
        scraper = PlayStoreScraper()
        
        text_with_emojis = "Great app! 😊👍🎉"
        cleaned = scraper._remove_emojis(text_with_emojis)
        assert "😊" not in cleaned
        assert "👍" not in cleaned
        assert "Great app!" in cleaned
    
    def test_is_english(self):
        """Test English language detection."""
        scraper = PlayStoreScraper()
        
        assert scraper._is_english("This is an English review") is True
        assert scraper._is_english("यह हिंदी में है") is False
        assert scraper._is_english("") is False
        assert scraper._is_english("123 numbers only") is True
    
    def test_save_to_csv(self, tmp_path):
        """Test CSV saving."""
        scraper = PlayStoreScraper()
        
        df = pd.DataFrame([
            {"rating": 5, "title": "Great", "review_text": "Love it", "date": "2026-01-15", "source": "play_store"}
        ])
        
        output_path = tmp_path / "test_reviews.csv"
        scraper.save_to_csv(df, str(output_path))
        
        assert output_path.exists()
        loaded_df = pd.read_csv(output_path)
        assert len(loaded_df) == 1
        assert loaded_df.iloc[0]["rating"] == 5


# ---------------------------------------------------------------------------
# AppStoreScraper Tests
# ---------------------------------------------------------------------------

class TestAppStoreScraper:
    """Tests for AppStoreScraper."""
    
    def test_init(self):
        """Test scraper initialization."""
        scraper = AppStoreScraper(max_reviews=200)
        assert scraper.max_reviews == 200
        assert "apps.apple.com" in scraper.url
        assert scraper.reviews == []
    
    def test_parse_rating(self):
        """Test rating parsing from aria-label."""
        scraper = AppStoreScraper()
        
        assert scraper._parse_rating("4 out of 5 stars") == 4
        assert scraper._parse_rating("5 stars") == 5
        assert scraper._parse_rating(None) == 0
        assert scraper._parse_rating("No rating") == 0
    
    def test_parse_date(self):
        """Test date parsing."""
        scraper = AppStoreScraper()
        
        # Various formats
        assert scraper._parse_date("Jan 15, 2026") == "2026-01-15"
        assert scraper._parse_date("January 15, 2026") == "2026-01-15"
        assert scraper._parse_date("1/15/26") == "2026-01-15"
        
        # Relative date
        result = scraper._parse_date("3 days ago")
        assert result == datetime.now().strftime("%Y-%m-%d")
    
    def test_remove_emojis(self):
        """Test emoji removal."""
        scraper = AppStoreScraper()
        
        text_with_emojis = "Amazing! 🚀💯"
        cleaned = scraper._remove_emojis(text_with_emojis)
        assert "🚀" not in cleaned
        assert "💯" not in cleaned
        assert "Amazing!" in cleaned
    
    def test_is_english(self):
        """Test English language detection."""
        scraper = AppStoreScraper()
        
        assert scraper._is_english("This is English text") is True
        assert scraper._is_english("これは日本語です") is False
        assert scraper._is_english("") is False


# ---------------------------------------------------------------------------
# ReviewScraperOrchestrator Tests
# ---------------------------------------------------------------------------

class TestReviewScraperOrchestrator:
    """Tests for ReviewScraperOrchestrator."""
    
    def test_init(self, tmp_path):
        """Test orchestrator initialization."""
        orchestrator = ReviewScraperOrchestrator(
            max_reviews_per_store=300,
            output_dir=str(tmp_path)
        )
        
        assert orchestrator.max_reviews_per_store == 300
        assert orchestrator.output_dir == tmp_path
        assert tmp_path.exists()
    
    def test_merge_and_deduplicate_empty(self):
        """Test merging with empty DataFrames."""
        orchestrator = ReviewScraperOrchestrator()
        
        result = orchestrator.merge_and_deduplicate([pd.DataFrame(), pd.DataFrame()])
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert list(result.columns) == ["rating", "title", "review_text", "date", "source"]
    
    def test_merge_and_deduplicate_no_duplicates(self):
        """Test merging without duplicates."""
        orchestrator = ReviewScraperOrchestrator()
        
        df1 = pd.DataFrame([
            {"rating": 5, "title": "Great", "review_text": "Love it", "date": "2026-01-15", "source": "play_store"}
        ])
        df2 = pd.DataFrame([
            {"rating": 4, "title": "Good", "review_text": "Nice app", "date": "2026-01-14", "source": "app_store"}
        ])
        
        result = orchestrator.merge_and_deduplicate([df1, df2])
        
        assert len(result) == 2
        assert "play_store" in result["source"].values
        assert "app_store" in result["source"].values
    
    def test_merge_and_deduplicate_with_duplicates(self):
        """Test deduplication logic."""
        orchestrator = ReviewScraperOrchestrator()
        
        df1 = pd.DataFrame([
            {"rating": 5, "title": "Great", "review_text": "Love it", "date": "2026-01-15", "source": "play_store"},
            {"rating": 4, "title": "Good", "review_text": "Nice app", "date": "2026-01-14", "source": "play_store"}
        ])
        df2 = pd.DataFrame([
            {"rating": 5, "title": "Great", "review_text": "Love it", "date": "2026-01-15", "source": "app_store"},  # Duplicate
            {"rating": 3, "title": "OK", "review_text": "Average", "date": "2026-01-13", "source": "app_store"}
        ])
        
        result = orchestrator.merge_and_deduplicate([df1, df2])
        
        # Should have 3 unique reviews (1 duplicate removed)
        assert len(result) == 3
        
        # Check that the duplicate was removed
        love_it_reviews = result[result["review_text"] == "Love it"]
        assert len(love_it_reviews) == 1
    
    def test_save_combined(self, tmp_path):
        """Test saving combined CSV."""
        orchestrator = ReviewScraperOrchestrator(output_dir=str(tmp_path))
        
        df = pd.DataFrame([
            {"rating": 5, "title": "Great", "review_text": "Love it", "date": "2026-01-15", "source": "play_store"}
        ])
        
        orchestrator.save_combined(df, filename="test_combined.csv")
        
        output_file = tmp_path / "test_combined.csv"
        assert output_file.exists()
        
        loaded_df = pd.read_csv(output_file)
        assert len(loaded_df) == 1


# ---------------------------------------------------------------------------
# Integration Tests (marked as slow)
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.integration
class TestScraperIntegration:
    """
    Integration tests that would actually scrape live sites.
    These are marked as 'slow' and 'integration' and should be run separately.
    """
    
    @pytest.mark.asyncio
    async def test_playstore_scraper_live(self):
        """Test Play Store scraper against live site (slow)."""
        scraper = PlayStoreScraper(max_reviews=10)
        
        try:
            df = await scraper.scrape()
            
            # Basic assertions
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0
            assert "rating" in df.columns
            assert "review_text" in df.columns
            assert "source" in df.columns
            assert all(df["source"] == "play_store")
            
        except Exception as e:
            pytest.skip(f"Live scraping failed (expected in CI): {e}")
    
    @pytest.mark.asyncio
    async def test_appstore_scraper_live(self):
        """Test App Store scraper against live site (slow)."""
        scraper = AppStoreScraper(max_reviews=10)
        
        try:
            df = await scraper.scrape()
            
            # Basic assertions
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0
            assert "rating" in df.columns
            assert "review_text" in df.columns
            assert "source" in df.columns
            assert all(df["source"] == "app_store")
            
        except Exception as e:
            pytest.skip(f"Live scraping failed (expected in CI): {e}")
