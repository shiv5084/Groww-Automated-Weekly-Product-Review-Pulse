import logging
import pandas as pd
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

class EmptyDatasetError(Exception):
    """Raised when a CSV file is completely empty or has 0 data rows."""
    pass

class SchemaValidationError(Exception):
    """Raised when required columns are missing from the dataset."""
    pass

class DataQualityWarning(Warning):
    """Issued when a significant portion of data is malformed."""
    pass

class ReviewIngestion:
    """
    Handles loading, schema validation, and basic cleaning of review CSVs.
    """
    
    REQUIRED_COLUMNS = ['rating', 'title', 'review_text', 'date', 'source']
    
    def __init__(self):
        pass
        
    def load_csv(self, filepath: str) -> pd.DataFrame:
        """
        Loads a CSV file with robust encoding fallback.
        Handles EC-2.1 (Empty CSV) and EC-2.8 (Encoding Issues).
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found at: {filepath}")
            
        # Try UTF-8 first
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            logger.warning(f"UTF-8 decode failed for {filepath}. Retrying with latin-1.")
            df = pd.read_csv(filepath, encoding='latin-1')
            
        # EC-2.1: Empty CSV
        if df.empty:
            raise EmptyDatasetError(f"CSV at {filepath} contains no reviews. Re-run scraper or provide a valid CSV.")
            
        return df
        
    def validate_schema(self, df: pd.DataFrame) -> bool:
        """
        Validates that all required columns are present.
        Handles EC-2.2 (Missing Required Columns).
        """
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise SchemaValidationError(
                f"Missing required columns: {missing_cols}. Expected schema: {self.REQUIRED_COLUMNS}"
            )
        return True
        
    def clean_ratings(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans the 'rating' column.
        Handles EC-2.3 (Rating Out of Range).
        """
        df_clean = df.copy()
        
        # Convert to numeric, setting errors='coerce' to turn non-numeric strings into NaN
        df_clean['rating'] = pd.to_numeric(df_clean['rating'], errors='coerce')
        
        # Clamp values outside [1, 5]
        def clamp_rating(r):
            if pd.isna(r):
                return r
            if r < 1:
                return 1
            if r > 5:
                return 5
            return r
            
        df_clean['rating'] = df_clean['rating'].apply(clamp_rating)
        
        # Check if >20% of rows have invalid ratings
        invalid_count = df_clean['rating'].isna().sum()
        total_count = len(df_clean)
        if invalid_count / total_count > 0.2:
            import warnings
            warnings.warn(f"More than 20% of rows ({invalid_count}/{total_count}) have invalid ratings.", DataQualityWarning)
            logger.warning(f"DataQualityWarning: >20% invalid ratings detected.")
            
        # Drop rows where rating is completely NaN
        df_clean = df_clean.dropna(subset=['rating'])
        
        return df_clean
        
    def merge_sources(self, dfs: List[pd.DataFrame]) -> pd.DataFrame:
        """Merges multiple DataFrames into one."""
        if not dfs:
            raise EmptyDatasetError("No DataFrames provided to merge.")
            
        combined = pd.concat(dfs, ignore_index=True)
        if combined.empty:
            raise EmptyDatasetError("Combined DataFrame is empty.")
            
        return combined
