"""
test_theme_grouper.py — Unit tests for Phase 2 LLM Theme Grouping Engine.

All LLM calls are mocked so these tests run without a real Groq API key.
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module loading (mirrors the pattern used in other test files)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR   = PROJECT_ROOT / "src" / "Phase2-themes"

import importlib.util as _ilu


def _load(module_name: str, file_path: Path, package_name: str | None = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod  = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register package marker
pkg = types.ModuleType("Phase2_themes")
pkg.__path__ = [str(THEMES_DIR)]
sys.modules["Phase2_themes"] = pkg

_prompts_mod = _load("Phase2_themes.prompts", THEMES_DIR / "prompts.py", "Phase2_themes")
_grouper_mod = _load("Phase2_themes.grouper", THEMES_DIR / "grouper.py", "Phase2_themes")

ThemeGrouper = _grouper_mod.ThemeGrouper
ThemeGroup   = _grouper_mod.ThemeGroup

THEMES_CONFIG = PROJECT_ROOT / "config" / "themes.yaml"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_df() -> pd.DataFrame:
    """Small DataFrame that mirrors the cleaned Phase 1 output."""
    return pd.DataFrame(
        {
            "rating":      [5, 2, 1, 4, 3],
            "title":       ["Great", "KYC slow", "Withdrawal stuck", "Nice UI", "Statement confusing"],
            "review_text": [
                "I love the app. Onboarding was super smooth and quick.",
                "KYC verification took three days. Very slow process.",
                "My withdrawal has been pending for five days. No response from support.",
                "Good app overall. Payments work fine most of the time.",
                "The portfolio statement is hard to read and confusing.",
            ],
            "llm_text": [
                "I love the app. Onboarding was super smooth and quick.",
                "KYC verification took three days. Very slow process.",
                "My withdrawal has been pending for five days. No response from support.",
                "Good app overall. Payments work fine most of the time.",
                "The portfolio statement is hard to read and confusing.",
            ],
            "date":   ["2026-04-01"] * 5,
            "source": ["play_store"] * 5,
        }
    )


def _make_grouper(monkeypatch) -> ThemeGrouper:
    """Return a ThemeGrouper with a fake API key (no real Groq calls)."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-fake")
    return ThemeGrouper(themes_config_path=THEMES_CONFIG)


# ---------------------------------------------------------------------------
# ThemeGroup unit tests
# ---------------------------------------------------------------------------

class TestThemeGroup:
    def test_avg_rating_empty(self):
        g = ThemeGroup(theme_id="kyc", theme_name="KYC")
        assert g.avg_rating == 0.0

    def test_avg_rating_calculated(self):
        g = ThemeGroup(theme_id="kyc", theme_name="KYC", count=2, total_rating=7.0)
        assert g.avg_rating == 3.5

    def test_sentiment_positive(self):
        g = ThemeGroup(theme_id="kyc", theme_name="KYC", count=1, total_rating=5.0)
        assert g.sentiment == "positive"

    def test_sentiment_neutral(self):
        g = ThemeGroup(theme_id="kyc", theme_name="KYC", count=1, total_rating=3.0)
        assert g.sentiment == "neutral"

    def test_sentiment_negative(self):
        g = ThemeGroup(theme_id="kyc", theme_name="KYC", count=1, total_rating=1.0)
        assert g.sentiment == "negative"

    def test_to_dict_keys(self):
        g = ThemeGroup(theme_id="payments", theme_name="Payments", count=3, total_rating=9.0)
        d = g.to_dict()
        assert set(d.keys()) == {"theme_id", "theme_name", "count", "avg_rating", "sentiment", "reviews"}


# ---------------------------------------------------------------------------
# parse_response tests (no LLM call needed)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_array(self, monkeypatch):
        grouper = _make_grouper(monkeypatch)
        raw = json.dumps([{"id": 0, "theme": "kyc"}, {"id": 1, "theme": "payments"}])
        result = grouper.parse_response(raw)
        assert len(result) == 2
        assert result[0] == {"id": 0, "theme": "kyc"}

    def test_strips_markdown_fences(self, monkeypatch):
        grouper = _make_grouper(monkeypatch)
        raw = '```json\n[{"id": 0, "theme": "kyc"}]\n```'
        result = grouper.parse_response(raw)
        assert result == [{"id": 0, "theme": "kyc"}]

    def test_invalid_json_returns_empty(self, monkeypatch):
        grouper = _make_grouper(monkeypatch)
        result = grouper.parse_response("not json at all")
        assert result == []

    def test_non_array_returns_empty(self, monkeypatch):
        grouper = _make_grouper(monkeypatch)
        result = grouper.parse_response('{"id": 0, "theme": "kyc"}')
        assert result == []


# ---------------------------------------------------------------------------
# build_prompt tests
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_prompt_contains_theme_ids(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        work = sample_df.copy()
        work["_row_id"] = work.index
        prompt = grouper.build_prompt(work, "llm_text")
        for theme_id in ["onboarding", "kyc", "payments", "statements", "withdrawals"]:
            assert theme_id in prompt

    def test_prompt_contains_review_text(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        work = sample_df.copy()
        work["_row_id"] = work.index
        prompt = grouper.build_prompt(work, "llm_text")
        assert "Onboarding was super smooth" in prompt

    def test_prompt_contains_fallback(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        work = sample_df.copy()
        work["_row_id"] = work.index
        prompt = grouper.build_prompt(work, "llm_text")
        assert "onboarding" in prompt  # fallback theme from themes.yaml


# ---------------------------------------------------------------------------
# group_reviews integration tests (LLM mocked)
# ---------------------------------------------------------------------------

def _mock_llm_response(assignments: list[dict]) -> MagicMock:
    """Build a mock that mimics groq client.chat.completions.create()."""
    mock_choice  = MagicMock()
    mock_choice.message.content = json.dumps(assignments)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


class TestGroupReviews:
    def test_empty_dataframe_returns_empty(self, monkeypatch):
        grouper = _make_grouper(monkeypatch)
        result = grouper.group_reviews(pd.DataFrame())
        assert result == {}

    def test_correct_theme_assignment(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        # Simulate LLM returning one theme per review
        llm_assignments = [
            {"id": 0, "theme": "onboarding"},
            {"id": 1, "theme": "kyc"},
            {"id": 2, "theme": "withdrawals"},
            {"id": 3, "theme": "payments"},
            {"id": 4, "theme": "statements"},
        ]
        mock_resp = _mock_llm_response(llm_assignments)
        grouper._client.chat.completions.create = MagicMock(return_value=mock_resp)

        groups = grouper.group_reviews(sample_df)

        assert "onboarding"  in groups
        assert "kyc"         in groups
        assert "withdrawals" in groups
        assert "payments"    in groups
        assert "statements"  in groups
        assert groups["kyc"].count == 1
        assert groups["kyc"].avg_rating == 2.0

    def test_unknown_theme_falls_back(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        # LLM returns an unknown theme for row 0
        llm_assignments = [
            {"id": 0, "theme": "unknown_theme_xyz"},
            {"id": 1, "theme": "kyc"},
            {"id": 2, "theme": "withdrawals"},
            {"id": 3, "theme": "payments"},
            {"id": 4, "theme": "statements"},
        ]
        mock_resp = _mock_llm_response(llm_assignments)
        grouper._client.chat.completions.create = MagicMock(return_value=mock_resp)

        groups = grouper.group_reviews(sample_df)
        # Row 0 should land in the fallback theme (onboarding)
        assert groups["onboarding"].count == 1

    def test_missing_assignment_falls_back(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        # LLM omits row 2 entirely
        llm_assignments = [
            {"id": 0, "theme": "onboarding"},
            {"id": 1, "theme": "kyc"},
            # id 2 missing
            {"id": 3, "theme": "payments"},
            {"id": 4, "theme": "statements"},
        ]
        mock_resp = _mock_llm_response(llm_assignments)
        grouper._client.chat.completions.create = MagicMock(return_value=mock_resp)

        groups = grouper.group_reviews(sample_df)
        # Row 2 (withdrawal review) should fall back to onboarding
        assert groups["onboarding"].count == 2  # row 0 + row 2

    def test_llm_failure_applies_fallback_to_batch(self, monkeypatch, sample_df):
        from groq import APIConnectionError
        grouper = _make_grouper(monkeypatch)
        grouper._client.chat.completions.create = MagicMock(
            side_effect=APIConnectionError.__new__(APIConnectionError)
        )

        # Should not raise; all reviews fall back to the fallback theme
        groups = grouper.group_reviews(sample_df)
        fallback_count = groups.get(grouper._fallback, ThemeGroup("x", "x")).count
        assert fallback_count == len(sample_df)

    def test_counts_sum_to_total(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        llm_assignments = [
            {"id": 0, "theme": "onboarding"},
            {"id": 1, "theme": "kyc"},
            {"id": 2, "theme": "withdrawals"},
            {"id": 3, "theme": "payments"},
            {"id": 4, "theme": "statements"},
        ]
        mock_resp = _mock_llm_response(llm_assignments)
        grouper._client.chat.completions.create = MagicMock(return_value=mock_resp)

        groups = grouper.group_reviews(sample_df)
        total = sum(g.count for g in groups.values())
        assert total == len(sample_df)

    def test_batching_splits_correctly(self, monkeypatch, sample_df):
        """With batch_size=2 and 5 reviews, we expect 3 LLM calls."""
        grouper = _make_grouper(monkeypatch)
        grouper.batch_size = 2

        call_count = 0

        def fake_create(**kwargs):
            nonlocal call_count
            # Parse the reviews from the prompt to return correct ids
            content = kwargs["messages"][0]["content"]
            # Extract the JSON array from the prompt
            start = content.rfind("[")
            end   = content.rfind("]") + 1
            reviews = json.loads(content[start:end])
            assignments = [{"id": r["id"], "theme": "onboarding"} for r in reviews]
            call_count += 1
            mock_choice = MagicMock()
            mock_choice.message.content = json.dumps(assignments)
            mock_resp = MagicMock()
            mock_resp.choices = [mock_choice]
            return mock_resp

        grouper._client.chat.completions.create = fake_create
        grouper.group_reviews(sample_df)
        assert call_count == 3  # ceil(5 / 2)

    def test_avg_rating_accuracy(self, monkeypatch, sample_df):
        grouper = _make_grouper(monkeypatch)
        # Put all reviews into 'payments' to test avg rating
        llm_assignments = [{"id": i, "theme": "payments"} for i in range(len(sample_df))]
        mock_resp = _mock_llm_response(llm_assignments)
        grouper._client.chat.completions.create = MagicMock(return_value=mock_resp)

        groups = grouper.group_reviews(sample_df)
        expected_avg = round(sum(sample_df["rating"]) / len(sample_df), 2)
        assert groups["payments"].avg_rating == expected_avg
