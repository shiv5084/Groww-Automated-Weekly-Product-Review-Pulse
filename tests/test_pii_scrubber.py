import pytest
import pandas as pd
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
sys.modules["Phase1_pii"] = type(sys)("Phase1_pii")
sys.modules["Phase1_pii"].__path__ = [str(PROJECT_ROOT / "src" / "Phase1-pii")]

patterns = load_module("Phase1_pii.patterns", "src/Phase1-pii/patterns.py", "Phase1_pii")
scrubber = load_module("Phase1_pii.scrubber", "src/Phase1-pii/scrubber.py", "Phase1_pii")

PIIScrubber = scrubber.PIIScrubber

def test_pii_email_redaction():
    s = PIIScrubber()
    text = "Contact me at user@gmail.com for details."
    res = s.scrub_text(text, "review_text")
    assert "user@gmail.com" not in res
    assert "[EMAIL_REDACTED]" in res

def test_pii_phone_redaction():
    s = PIIScrubber()
    text = "Call me: +91 98765 43210 please"
    res = s.scrub_text(text, "review_text")
    assert "+91 98765 43210" not in res
    assert "[PHONE_REDACTED]" in res

def test_pii_username_redaction():
    s = PIIScrubber()
    text = "Follow @user123 on twitter"
    res = s.scrub_text(text, "review_text")
    assert "@user123" not in res
    assert "[USERNAME_REDACTED]" in res

def test_pii_allowlist():
    s = PIIScrubber()
    text = "I use @groww for trading."
    res = s.scrub_text(text, "review_text")
    assert "@groww" in res
    assert "[USERNAME_REDACTED]" not in res

def test_pii_no_false_positives():
    s = PIIScrubber()
    text = "rated 5 stars. The app is good."
    res = s.scrub_text(text, "review_text")
    assert res == text

def test_scrub_dataframe():
    s = PIIScrubber()
    df = pd.DataFrame({
        'title': ['My email is user@gmail.com', 'Good app'],
        'review_text': ['Call me +919876543210', 'Very good experience. I like it a lot.'],
        'rating': [1, 5]
    })
    
    clean_df = s.scrub_dataframe(df)
    
    # First row has 3 words: "Call", "me", "[PHONE_REDACTED]" -> length is 3, which is < 5 words.
    # Actually wait: The original had 3 words: 'Call', 'me', '+919876543210'. It will be filtered out!
    # Let's verify short review dropping.
    assert len(clean_df) == 1
    
    # Row 1 is dropped, row 2 is kept
    assert "Very good experience. I like it a lot." in clean_df.iloc[0]['review_text']

def test_truncate_for_llm():
    s = PIIScrubber()
    long_text = "A" * 1500
    res = s.truncate_for_llm(long_text)
    assert len(res) == 1000

def test_scrub_report():
    s = PIIScrubber()
    df = pd.DataFrame({
        'title': ['user@gmail.com', 'No PII'],
        'review_text': ['Short review @baduser', 'This is a long review that has more than five words! +919876543210'],
        'rating': [1, 5]
    })
    
    s.scrub_dataframe(df)
    rep = s.get_scrub_report()
    
    # title redactions
    assert rep['title_redactions']['EMAIL'] == 1
    # review_text redactions (row 1 drops because <5 words, but it is scrubbed before length check)
    assert rep['review_text_redactions']['USERNAME'] == 1
    assert rep['review_text_redactions']['PHONE'] == 1
    
    assert rep['short_reviews_dropped'] == 1

def test_remove_emojis():
    s = PIIScrubber()
    text_with_emojis = "This is a great app! 😍🚀 Standard reviews should not have icons like 👍 or 😅."
    cleaned = s.remove_emojis(text_with_emojis)
    assert "😍" not in cleaned
    assert "🚀" not in cleaned
    assert "👍" not in cleaned
    assert "😅" not in cleaned
    assert "This is a great app!  Standard reviews should not have icons like  or ." in cleaned

def test_exclude_non_english():
    s = PIIScrubber()
    english_text = "This is a perfect app for trading stocks and mutual funds online."
    hindi_text = "बहुत ही अच्छा ऐप है ट्रेडिंग के लिए"
    kannada_text = "ತುಂಬಾ ಒಳ್ಳೆಯ ಆಪ್"
    
    assert s._is_english(english_text) is True
    assert s._is_english(hindi_text) is False
    assert s._is_english(kannada_text) is False

def test_scrub_dataframe_with_emoji_and_non_english():
    s = PIIScrubber()
    df = pd.DataFrame({
        'title': ['Nice app! 👍', 'Hindi review', 'Good trading'],
        'review_text': [
            'Very good experience with groww app! 🚀🔥',
            'यह बहुत ही बेहतरीन और सुरक्षित ऐप है',
            'I love this application, it has great user experience.'
        ],
        'rating': [5, 4, 5]
    })
    
    cleaned_df = s.scrub_dataframe(df)
    
    # The Hindi review is non-English and should be dropped completely.
    assert len(cleaned_df) == 2
    
    # Emojis must be removed from the kept reviews
    assert "👍" not in cleaned_df.iloc[0]['title']
    assert "🚀" not in cleaned_df.iloc[0]['review_text']
    assert "🔥" not in cleaned_df.iloc[0]['review_text']
    
    # Check that report is populated
    rep = s.get_scrub_report()
    assert rep['non_english_reviews_dropped'] == 1
