"""
test_pulse_generator.py — Unit tests for Phase 3 Pulse Note Generator.

All LLM calls are mocked so these tests run without a real Groq API key.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEN_DIR      = PROJECT_ROOT / "src" / "Phase3-generator"

import importlib.util as _ilu


def _load(module_name: str, file_path: Path, package_name: str | None = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod  = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


pkg = types.ModuleType("Phase3_generator")
pkg.__path__ = [str(GEN_DIR)]
sys.modules["Phase3_generator"] = pkg

_pulse_mod     = _load("Phase3_generator.pulse_note", GEN_DIR / "pulse_note.py",  "Phase3_generator")
_formatter_mod = _load("Phase3_generator.formatter",  GEN_DIR / "formatter.py",   "Phase3_generator")

PulseNoteGenerator = _pulse_mod.PulseNoteGenerator
PulseNote          = _pulse_mod.PulseNote
ThemeSummary       = _pulse_mod.ThemeSummary
PulseNoteFormatter = _formatter_mod.PulseNoteFormatter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_THEMES = {
    "onboarding": {
        "theme_id":   "onboarding",
        "theme_name": "Onboarding",
        "count":      279,
        "avg_rating": 4.43,
        "sentiment":  "positive",
        "reviews": [
            {"text": "The sign-up process was quick and very easy to complete.", "rating": 5.0},
            {"text": "Account creation took less than five minutes, very smooth.", "rating": 5.0},
            {"text": "Onboarding was seamless and the tutorial was very helpful.", "rating": 5.0},
        ],
    },
    "payments": {
        "theme_id":   "payments",
        "theme_name": "Payments",
        "count":      30,
        "avg_rating": 2.7,
        "sentiment":  "negative",
        "reviews": [
            {"text": "Payment failed and money was deducted but order not placed.", "rating": 1.0},
            {"text": "UPI transaction keeps failing every time I try to add money.", "rating": 1.0},
            {"text": "Refund for failed payment took more than seven days to arrive.", "rating": 2.0},
        ],
    },
    "withdrawals": {
        "theme_id":   "withdrawals",
        "theme_name": "Withdrawals",
        "count":      14,
        "avg_rating": 2.1,
        "sentiment":  "negative",
        "reviews": [
            {"text": "Withdrawal has been pending for five days with no update.", "rating": 1.0},
            {"text": "Money is stuck and customer support is not responding at all.", "rating": 1.0},
        ],
    },
    "statements": {
        "theme_id":   "statements",
        "theme_name": "Statements",
        "count":      32,
        "avg_rating": 3.4,
        "sentiment":  "neutral",
        "reviews": [
            {"text": "Portfolio statement is hard to read and confusing to understand.", "rating": 3.0},
        ],
    },
    "kyc": {
        "theme_id":   "kyc",
        "theme_name": "KYC",
        "count":      3,
        "avg_rating": 1.0,
        "sentiment":  "negative",
        "reviews": [
            {"text": "KYC verification took three days and was rejected without reason.", "rating": 1.0},
        ],
    },
}


def _make_generator(monkeypatch) -> PulseNoteGenerator:
    monkeypatch.setenv("GROQ_API_KEY", "test-key-fake")
    return PulseNoteGenerator()


def _mock_action_response(actions: list[str]) -> MagicMock:
    content = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
    mock_choice   = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


# ---------------------------------------------------------------------------
# ThemeSummary / PulseNote unit tests
# ---------------------------------------------------------------------------

class TestPulseNote:
    def test_word_count_empty(self):
        note = PulseNote(
            week_label="Week of 14 May 2026",
            date_range=("2026-02-12", "2026-05-14"),
            top_themes=[],
            actions=[],
        )
        # Only week_label contributes
        assert note.word_count() > 0

    def test_word_count_with_content(self):
        ts = ThemeSummary(
            theme_id="payments", theme_name="Payments",
            count=30, avg_rating=2.7, sentiment="negative",
            quote="Payment failed and money was deducted.",
        )
        note = PulseNote(
            week_label="Week of 14 May 2026",
            date_range=("2026-02-12", "2026-05-14"),
            top_themes=[ts],
            actions=["Fix payment gateway failures immediately."],
        )
        assert note.word_count() >= 10

    def test_validate_word_count_within_limit(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        ts = ThemeSummary(
            theme_id="payments", theme_name="Payments",
            count=30, avg_rating=2.7, sentiment="negative",
            quote="Short quote.",
        )
        note = PulseNote(
            week_label="Week of 14 May 2026",
            date_range=("2026-02-12", "2026-05-14"),
            top_themes=[ts],
            actions=["Fix it."],
        )
        assert gen.validate_word_count(note) is True

    def test_validate_word_count_over_limit(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        gen.max_words = 5  # artificially low
        ts = ThemeSummary(
            theme_id="payments", theme_name="Payments",
            count=30, avg_rating=2.7, sentiment="negative",
            quote="This is a very long quote that exceeds the word limit easily.",
        )
        note = PulseNote(
            week_label="Week of 14 May 2026",
            date_range=("2026-02-12", "2026-05-14"),
            top_themes=[ts],
            actions=["Fix payment gateway failures immediately."],
        )
        assert gen.validate_word_count(note) is False


# ---------------------------------------------------------------------------
# Quote selection tests
# ---------------------------------------------------------------------------

class TestPickQuote:
    def test_picks_from_non_empty_reviews(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        reviews = [
            {"text": "Payment failed and money was deducted but order not placed.", "rating": 1.0},
            {"text": "Short.", "rating": 3.0},
        ]
        quote, rating = gen._pick_quote(reviews)
        assert len(quote) > 0
        assert isinstance(rating, float)

    def test_prefers_extreme_ratings(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        reviews = [
            {"text": "Neutral review with average rating and some words here.", "rating": 3.0},
            {"text": "Payment failed and money was deducted but order not placed.", "rating": 1.0},
        ]
        quote, rating = gen._pick_quote(reviews)
        # Should prefer the 1-star review
        assert rating == 1.0

    def test_empty_reviews_returns_fallback(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        quote, rating = gen._pick_quote([])
        assert "No representative quote" in quote

    def test_quote_within_char_limit(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        reviews = [{"text": "x " * 300, "rating": 5.0}]
        quote, _ = gen._pick_quote(reviews)
        assert len(quote) <= gen.MAX_QUOTE_CHARS + 10  # small tolerance for truncation


# ---------------------------------------------------------------------------
# Top theme selection tests
# ---------------------------------------------------------------------------

class TestSelectTopThemes:
    def test_returns_top_3_by_count(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        top3 = gen._select_top_themes(SAMPLE_THEMES, n=3)
        assert len(top3) == 3
        # Onboarding (279) > Statements (32) > Payments (30)
        assert top3[0].theme_id == "onboarding"
        counts = [t.count for t in top3]
        assert counts == sorted(counts, reverse=True)

    def test_returns_fewer_if_not_enough_themes(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        small = {"onboarding": SAMPLE_THEMES["onboarding"]}
        top = gen._select_top_themes(small, n=3)
        assert len(top) == 1


# ---------------------------------------------------------------------------
# Action parsing tests
# ---------------------------------------------------------------------------

class TestParseActions:
    def test_numbered_list(self):
        raw = "1. Fix payment gateway.\n2. Improve KYC speed.\n3. Add withdrawal tracking."
        actions = PulseNoteGenerator._parse_actions(raw)
        assert len(actions) == 3
        assert actions[0] == "Fix payment gateway."

    def test_parenthesis_numbering(self):
        raw = "1) Fix payment gateway.\n2) Improve KYC speed.\n3) Add withdrawal tracking."
        actions = PulseNoteGenerator._parse_actions(raw)
        assert len(actions) == 3

    def test_dash_list(self):
        raw = "- Fix payment gateway.\n- Improve KYC speed.\n- Add withdrawal tracking."
        actions = PulseNoteGenerator._parse_actions(raw)
        assert len(actions) == 3

    def test_ignores_preamble(self):
        raw = "Here are the actions:\n1. Fix payment gateway.\n2. Improve KYC.\n3. Track withdrawals."
        actions = PulseNoteGenerator._parse_actions(raw)
        assert len(actions) == 3


# ---------------------------------------------------------------------------
# Full generate() integration tests (LLM mocked)
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generates_note_with_3_themes(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response([
            "Fix payment gateway failures immediately.",
            "Expedite withdrawal processing to under 24 hours.",
            "Maintain onboarding quality with regular UX audits.",
        ])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES)
        assert len(note.top_themes) == 3
        assert len(note.actions) == 3

    def test_top_themes_sorted_by_count(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response(["A.", "B.", "C."])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES)
        counts = [t.count for t in note.top_themes]
        assert counts == sorted(counts, reverse=True)

    def test_note_within_word_limit(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response([
            "Fix payment gateway failures immediately.",
            "Expedite withdrawal processing to under 24 hours.",
            "Maintain onboarding quality with regular UX audits.",
        ])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES)
        assert gen.validate_word_count(note), (
            f"Note exceeds {gen.max_words} words: {note.word_count()}"
        )

    def test_raises_on_empty_themes(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        with pytest.raises(ValueError, match="No themes provided"):
            gen.generate({})

    def test_fallback_actions_on_llm_failure(self, monkeypatch):
        from groq import APIConnectionError
        gen = _make_generator(monkeypatch)
        gen._client.chat.completions.create = MagicMock(
            side_effect=APIConnectionError.__new__(APIConnectionError)
        )
        note = gen.generate(SAMPLE_THEMES)
        assert len(note.actions) == 3

    def test_quotes_populated(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response(["A.", "B.", "C."])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES)
        for t in note.top_themes:
            assert len(t.quote) > 0

    def test_date_range_defaults(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response(["A.", "B.", "C."])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES)
        assert note.date_range[0] < note.date_range[1]

    def test_custom_date_range(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response(["A.", "B.", "C."])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)

        note = gen.generate(SAMPLE_THEMES, date_range=("2026-05-01", "2026-05-14"))
        assert note.date_range == ("2026-05-01", "2026-05-14")


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------

class TestPulseNoteFormatter:
    @pytest.fixture()
    def sample_note(self, monkeypatch) -> PulseNote:
        gen = _make_generator(monkeypatch)
        mock_resp = _mock_action_response([
            "Fix payment gateway failures immediately.",
            "Expedite withdrawal processing to under 24 hours.",
            "Maintain onboarding quality with regular UX audits.",
        ])
        gen._client.chat.completions.create = MagicMock(return_value=mock_resp)
        return gen.generate(SAMPLE_THEMES)

    def test_markdown_contains_title(self, sample_note):
        md = PulseNoteFormatter.format_for_docs(sample_note)
        assert "# Groww Weekly Pulse" in md

    def test_markdown_contains_top_themes_section(self, sample_note):
        md = PulseNoteFormatter.format_for_docs(sample_note)
        assert "## Top Themes" in md

    def test_markdown_contains_user_voices(self, sample_note):
        md = PulseNoteFormatter.format_for_docs(sample_note)
        assert "## User Voices" in md

    def test_markdown_contains_actions(self, sample_note):
        md = PulseNoteFormatter.format_for_docs(sample_note)
        assert "## Recommended Actions" in md

    def test_plain_text_no_markdown_syntax(self, sample_note):
        txt = PulseNoteFormatter.format_for_email(sample_note)
        assert "##" not in txt
        assert "**" not in txt

    def test_plain_text_contains_sections(self, sample_note):
        txt = PulseNoteFormatter.format_for_email(sample_note)
        assert "TOP THEMES" in txt
        assert "USER VOICES" in txt
        assert "RECOMMENDED ACTIONS" in txt

    def test_html_is_valid_structure(self, sample_note):
        html = PulseNoteFormatter.format_for_html(sample_note)
        assert "<div" in html
        assert "<h1" in html
        assert "<ol" in html
        assert "<blockquote" in html
        assert "</div>" in html

    def test_html_escapes_special_chars(self):
        ts = ThemeSummary(
            theme_id="payments", theme_name="Payments & Fees",
            count=10, avg_rating=2.0, sentiment="negative",
            quote='Quote with <script>alert("xss")</script>',
        )
        note = PulseNote(
            week_label="Week of 14 May 2026",
            date_range=("2026-05-01", "2026-05-14"),
            top_themes=[ts],
            actions=["Fix it."],
        )
        html = PulseNoteFormatter.format_for_html(note)
        assert "<script>" not in html
        assert "&amp;" in html or "&lt;" in html
