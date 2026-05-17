import logging
from datetime import datetime
from typing import Optional
import pandas as pd
from dateutil import parser

logger = logging.getLogger(__name__)

class InsufficientDataError(Exception):
    """Raised when there are no reviews left after filtering."""
    pass

class DateFilter:
    """
    Handles parsing dates and filtering reviews by a specified date range.
    """
    
    def __init__(self, weeks: int = 12):
        self.weeks = weeks
        
    def parse_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Parses the 'date' column into datetime objects.
        Handles EC-2.5 (Malformed Date Strings).
        """
        df_clean = df.copy()
        
        def flexible_parse(d_str):
            if pd.isna(d_str) or str(d_str).strip() == "":
                return pd.NaT
            try:
                # dayfirst=False for standard US-style parsing, but dateutil is smart
                return parser.parse(str(d_str), dayfirst=False)
            except Exception:
                return pd.NaT
                
        # Parse dates
        df_clean['parsed_date'] = df_clean['date'].apply(flexible_parse)
        
        # Check for unparseable dates
        unparseable_count = df_clean['parsed_date'].isna().sum()
        total_count = len(df_clean)
        
        if unparseable_count > 0:
            logger.info(f"Failed to parse {unparseable_count} dates. These will be excluded from date-range filtering.")
            
        if unparseable_count / total_count > 0.3:
            import warnings
            from .csv_loader import DataQualityWarning
            warnings.warn(f"More than 30% of rows ({unparseable_count}/{total_count}) have unparseable dates.", DataQualityWarning)
            logger.warning(f"DataQualityWarning: >30% unparseable dates detected.")
            
        return df_clean
        
    def filter_by_date_range(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filters the DataFrame to only include reviews within the target date range.
        Handles EC-2.4 (All Reviews Outside Date Window).
        """
        df_filtered = df.copy()
        
        # Calculate the cutoff date (N weeks ago from now)
        cutoff_date = pd.Timestamp.now() - pd.Timedelta(weeks=self.weeks)
        
        # Exclude NaT dates first
        valid_dates_df = df_filtered.dropna(subset=['parsed_date'])
        
        # Apply filter
        df_filtered = valid_dates_df[valid_dates_df['parsed_date'] >= cutoff_date]
        
        # EC-2.4 check
        if df_filtered.empty:
            if not valid_dates_df.empty:
                oldest = valid_dates_df['parsed_date'].min().strftime('%Y-%m-%d')
                msg = f"No reviews found in the last {self.weeks} weeks. Oldest review date: {oldest}."
            else:
                msg = f"No reviews found in the last {self.weeks} weeks. No valid dates found."
            raise InsufficientDataError(msg)
            
        # Clean up the parsed_date column if we just want to keep the string 'date' column?
        # Actually, it's better to format parsed_date back to standard YYYY-MM-DD
        df_filtered['date'] = df_filtered['parsed_date'].dt.strftime('%Y-%m-%d')
        df_filtered = df_filtered.drop(columns=['parsed_date'])
        
        return df_filtered
