import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import importlib.util as _ilu

# Setup to import from directories with hyphens
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_module(module_name, rel_path, package_name=None):
    file_path = PROJECT_ROOT / rel_path
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

# Create package marker
sys.modules["Phase1_ingestion"] = type(sys)("Phase1_ingestion")
sys.modules["Phase1_ingestion"].__path__ = [str(PROJECT_ROOT / "src" / "Phase1-ingestion")]

csv_loader = load_module("Phase1_ingestion.csv_loader", "src/Phase1-ingestion/csv_loader.py", "Phase1_ingestion")
date_filter = load_module("Phase1_ingestion.date_filter", "src/Phase1-ingestion/date_filter.py", "Phase1_ingestion")

ReviewIngestion = csv_loader.ReviewIngestion
EmptyDatasetError = csv_loader.EmptyDatasetError
SchemaValidationError = csv_loader.SchemaValidationError
DateFilter = date_filter.DateFilter
InsufficientDataError = date_filter.InsufficientDataError

@pytest.fixture
def sample_good_df():
    return pd.DataFrame({
        'rating': [5, 4, 3],
        'title': ['Great', 'Good', 'Okay'],
        'review_text': ['This app is great', 'Works well', 'Just okay'],
        'date': ['2026-05-10', '2026-05-09', '2026-05-08'],
        'source': ['play_store', 'play_store', 'app_store']
    })

def test_schema_validation_valid(sample_good_df):
    ingestion = ReviewIngestion()
    assert ingestion.validate_schema(sample_good_df) is True

def test_schema_validation_missing_col(sample_good_df):
    ingestion = ReviewIngestion()
    bad_df = sample_good_df.drop(columns=['rating'])
    with pytest.raises(SchemaValidationError):
        ingestion.validate_schema(bad_df)

def test_clean_ratings(sample_good_df):
    ingestion = ReviewIngestion()
    
    df = sample_good_df.copy()
    # Add bad ratings
    df.loc[3] = [-1, 'Bad', 'Too low', '2026-05-07', 'play_store']
    df.loc[4] = [6, 'Bad', 'Too high', '2026-05-07', 'play_store']
    df.loc[5] = ['five', 'Bad', 'String', '2026-05-07', 'play_store']
    
    clean_df = ingestion.clean_ratings(df)
    
    # -1 should clamp to 1
    assert clean_df.loc[3, 'rating'] == 1
    # 6 should clamp to 5
    assert clean_df.loc[4, 'rating'] == 5
    # 'five' should become NaN and be dropped
    assert len(clean_df) == 5

def test_date_filter_12_weeks(sample_good_df):
    # Set dates to be exactly right now and 20 weeks ago
    df = sample_good_df.copy()
    now = pd.Timestamp.now()
    old = now - pd.Timedelta(weeks=20)
    
    df.loc[0, 'date'] = now.strftime('%Y-%m-%d')
    df.loc[1, 'date'] = old.strftime('%Y-%m-%d')
    df.loc[2, 'date'] = 'invalid date'
    
    dfilter = DateFilter(weeks=12)
    df_parsed = dfilter.parse_dates(df)
    df_filtered = dfilter.filter_by_date_range(df_parsed)
    
    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]['date'] == now.strftime('%Y-%m-%d')

def test_date_filter_empty():
    df = pd.DataFrame({
        'rating': [1], 'title': ['old'], 'review_text': ['old'],
        'date': [(pd.Timestamp.now() - pd.Timedelta(weeks=20)).strftime('%Y-%m-%d')],
        'source': ['play_store']
    })
    
    dfilter = DateFilter(weeks=12)
    df_parsed = dfilter.parse_dates(df)
    with pytest.raises(InsufficientDataError):
        dfilter.filter_by_date_range(df_parsed)
