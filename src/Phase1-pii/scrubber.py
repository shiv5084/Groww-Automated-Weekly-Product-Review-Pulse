import logging
import pandas as pd
from typing import Tuple, Dict, Any
from .patterns import PII_PATTERNS, ALLOWLIST

logger = logging.getLogger(__name__)

class PIIScrubber:
    """
    Detects and redacts PII from reviews.
    Applies text length filters and length truncation.
    """
    
    def __init__(self):
        self.report = {
            "title_redactions": {k: 0 for k in PII_PATTERNS.keys()},
            "review_text_redactions": {k: 0 for k in PII_PATTERNS.keys()},
            "fully_redacted_reviews_dropped": 0,
            "short_reviews_dropped": 0,
            "non_english_reviews_dropped": 0,
            "reviews_truncated": 0
        }
        
    def _is_allowlisted(self, text: str) -> bool:
        """Check if text is an allowlisted term."""
        return text.lower() in ALLOWLIST
        
    def scrub_text(self, text: str, column: str) -> str:
        """
        Scrubs PII from a single text string.
        Logs redactions into self.report under the specified column.
        """
        if pd.isna(text) or not isinstance(text, str):
            return ""
            
        scrubbed_text = text
        for pii_type, pattern in PII_PATTERNS.items():
            matches = pattern.finditer(scrubbed_text)
            
            # Since we modify the string, we do it carefully or use sub with a function
            def replacer(match):
                matched_str = match.group(0)
                if self._is_allowlisted(matched_str):
                    return matched_str
                    
                self.report[f"{column}_redactions"][pii_type] += 1
                return f"[{pii_type}_REDACTED]"
                
            scrubbed_text = pattern.sub(replacer, scrubbed_text)
            
        return scrubbed_text
        
    def truncate_for_llm(self, text: str) -> str:
        """
        Truncates extremely long text to 1000 characters for the LLM.
        EC-2.9: Extremely Long Review Text.
        """
        if len(text) > 1000:
            self.report["reviews_truncated"] += 1
            logger.info(f"Review truncated from {len(text)} to 1000 chars for LLM processing")
            return text[:1000]
        return text
        
    def remove_emojis(self, text: str) -> str:
        """
        Remove all emojis and unicode symbols from text (Task 1.6).
        Uses a combination of unicodedata and a robust regex range check.
        """
        if not text or not isinstance(text, str):
            return ""
        
        # 1. Strip via unicodedata category 'So' (Symbol, other) which covers almost all emojis
        import unicodedata
        text = "".join(ch for ch in text if unicodedata.category(ch) != "So")
        
        # 2. Additional regex check to catch any leftover emoticons or specific symbol ranges
        import re
        emoji_pattern = re.compile(
            r"["
            r"\U0001F600-\U0001F64F"  # emoticons
            r"\U0001F300-\U0001F5FF"  # symbols & pictographs
            r"\U0001F680-\U0001F6FF"  # transport & map symbols
            r"\U0001F1E0-\U0001F1FF"  # flags
            r"\U00002702-\U000027B0"  # dingbats
            r"\u2600-\u27BF"          # misc symbols
            r"]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub(r"", text)

    def _is_english(self, text: str) -> bool:
        """
        Check if text is written in English (Task 1.6).
        Uses a standard, highly accurate ASCII and alphabet ratio check
        combined with an explicit Indian script blocker.
        """
        if not text or not isinstance(text, str):
            return False
            
        # Clean text for evaluation
        cleaned = "".join(c for c in text if c.isalnum() or c.isspace())
        if not cleaned:
            return False
            
        # Check ASCII ratio (English reviews are primarily ASCII)
        ascii_chars = sum(1 for c in cleaned if ord(c) < 128)
        if ascii_chars / len(cleaned) < 0.7:
            return False
            
        # Explicitly exclude Indian scripts (Hindi, Tamil, Telugu, Kannada, Bengali)
        import re
        indian_scripts = re.compile(
            r"[\u0900-\u097F"  # Devanagari (Hindi, Marathi, etc.)
            r"\u0980-\u09FF"  # Bengali
            r"\u0B80-\u0BFF"  # Tamil
            r"\u0C00-\u0C7F"  # Telugu
            r"\u0C80-\u0CFF]" # Kannada
        )
        if indian_scripts.search(text):
            return False
            
        return True

    def scrub_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Scrubs PII from 'title' and 'review_text' columns.
        Applies emoji removal, non-English exclusion, and length constraints.
        """
        df_clean = df.copy()
        
        # Ensure string type
        df_clean['title'] = df_clean['title'].fillna("").astype(str)
        df_clean['review_text'] = df_clean['review_text'].fillna("").astype(str)
        
        # 1. Remove all emojis from title and review_text (Task 1.6)
        logger.info("Removing emojis from review titles and texts...")
        df_clean['title'] = df_clean['title'].apply(self.remove_emojis)
        df_clean['review_text'] = df_clean['review_text'].apply(self.remove_emojis)

        # 2. Exclude reviews written in languages other than English (Task 1.6)
        logger.info("Filtering non-English reviews...")
        original_count = len(df_clean)
        df_clean = df_clean[df_clean['review_text'].apply(self._is_english)]
        dropped_non_english = original_count - len(df_clean)
        self.report["non_english_reviews_dropped"] += dropped_non_english
        
        # 3. Scrub PII
        logger.info("Scrubbing PII from title and review_text...")
        df_clean['title'] = df_clean['title'].apply(lambda x: self.scrub_text(x, 'title'))
        df_clean['review_text'] = df_clean['review_text'].apply(lambda x: self.scrub_text(x, 'review_text'))
        
        # 4. Filter short reviews (Task 1.5: < 5 words)
        def word_count(text):
            return len(str(text).split())
            
        original_count = len(df_clean)
        df_clean = df_clean[df_clean['review_text'].apply(word_count) >= 5]
        dropped_short = original_count - len(df_clean)
        self.report["short_reviews_dropped"] += dropped_short
        
        # 5. Check for fully redacted/unusable reviews (EC-2.6)
        def is_only_pii(text):
            import re
            cleaned = re.sub(r'\[\w+_REDACTED\]', '', text).strip()
            return len(cleaned) == 0
            
        original_count = len(df_clean)
        df_clean['is_usable'] = ~df_clean['review_text'].apply(is_only_pii)
        
        df_clean = df_clean[df_clean['is_usable'] == True]
        df_clean = df_clean.drop(columns=['is_usable'])
        
        dropped_pii = original_count - len(df_clean)
        self.report["fully_redacted_reviews_dropped"] += dropped_pii
        
        # 6. Truncate for LLM (EC-2.9)
        df_clean['llm_text'] = df_clean['review_text'].apply(self.truncate_for_llm)
        
        logger.info(
            f"Scrubbing and cleaning complete. "
            f"Dropped {dropped_non_english} non-English reviews, "
            f"{dropped_short} short reviews, and {dropped_pii} fully redacted reviews."
        )
        
        return df_clean
        
    def get_scrub_report(self) -> Dict[str, Any]:
        """Returns the scrubbing statistics."""
        return self.report
