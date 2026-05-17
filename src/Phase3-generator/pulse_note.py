"""
pulse_note.py — Pulse note data model and generation logic for Phase 3.

Responsibilities
----------------
- Accept themed review groups from Phase 2
- Select the top 3 themes by review count
- Pick 3 representative, PII-free verbatim quotes (one per top theme)
- Generate 3 concrete action recommendations via a LangChain chain
  (ChatGroq + ChatPromptTemplate + StrOutputParser) with .with_retry()
- Enforce the <=250 word limit (trim if needed)
- Produce a PulseNote dataclass ready for formatting

LangChain chain (primary path):
    ACTION_CHAIN_V1 | ChatGroq | StrOutputParser
    → .with_retry() handles RateLimitError / APIConnectionError automatically

Raw Groq SDK (fallback path, tenacity-decorated):
    Used only if the LangChain chain raises an unexpected exception type.
    tenacity kept as fallback (Q4 decision).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# LangChain imports (primary LLM path)
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Raw Groq SDK kept as fallback (Q4 decision)
from groq import Groq, RateLimitError, APIConnectionError, APIStatusError

# tenacity kept as fallback (Q4 decision)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Action generation prompt template (LangChain)
# ---------------------------------------------------------------------------

ACTION_CHAIN_V1 = ChatPromptTemplate.from_template(
    "You are a product manager at Groww, India's leading investment app.\n"
    "Based on the following weekly user review themes, generate exactly 3 concrete,\n"
    "prioritised action recommendations for the product team.\n\n"
    "THEMES THIS WEEK:\n{theme_summary}\n\n"
    "RULES:\n"
    "1. Each action must be specific and actionable (not vague like \"improve UX\").\n"
    "2. Prioritise by severity: negative sentiment themes first.\n"
    "3. Each action must be a single sentence, max 20 words.\n"
    "4. Return ONLY a numbered list (1. ... 2. ... 3. ...) — no preamble, no explanation.\n\n"
    "ACTIONS:"
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ThemeSummary:
    """Compact summary of a single theme for the pulse note."""
    theme_id:   str
    theme_name: str
    count:      int
    avg_rating: float
    sentiment:  str
    quote:      str   = ""   # representative verbatim quote
    quote_rating: float = 0.0


@dataclass
class PulseNote:
    """Complete weekly pulse note ready for formatting."""
    week_label:   str                    # e.g. "Week of 12 May 2026"
    date_range:   tuple[str, str]        # (start_date, end_date) ISO strings
    top_themes:   list[ThemeSummary]     # top 3 themes
    actions:      list[str]              # 3 recommended actions
    total_reviews: int = 0

    def word_count(self) -> int:
        """Count words across all prose sections of the note."""
        parts = [self.week_label]
        for t in self.top_themes:
            parts += [t.theme_name, t.quote]
        parts += self.actions
        return len(" ".join(parts).split())


# ---------------------------------------------------------------------------
# PulseNoteGenerator
# ---------------------------------------------------------------------------

class PulseNoteGenerator:
    """
    Generates a <=250 word weekly pulse note from Phase 2 theme groups.

    Parameters
    ----------
    model : str | None
        Groq model.  Defaults to env LLM_MODEL or llama-3.3-70b-versatile.
    api_key : str | None
        Groq API key.  Falls back to GROQ_API_KEY env var.
    max_words : int
        Hard word-count ceiling (default 250).
    """

    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    MAX_WORDS     = 250
    # Minimum quote length (words) to be considered representative
    MIN_QUOTE_WORDS = 8
    # Maximum quote length (chars) to keep notes scannable
    MAX_QUOTE_CHARS = 200

    def __init__(
        self,
        model:    str | None = None,
        api_key:  str | None = None,
        max_words: int       = MAX_WORDS,
    ) -> None:
        self.model     = model or os.getenv("LLM_MODEL", self.DEFAULT_MODEL)
        self.max_words = max_words

        _key = api_key or os.getenv("GROQ_API_KEY")
        if not _key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY in your .env file "
                "or pass api_key= to PulseNoteGenerator()."
            )

        # ----------------------------------------------------------------
        # Primary path: LangChain chain
        #   ACTION_CHAIN_V1 | ChatGroq | StrOutputParser
        #   .with_retry() handles RateLimitError / APIConnectionError automatically
        # ----------------------------------------------------------------
        _llm = ChatGroq(
            model=self.model,
            temperature=0.3,
            max_tokens=512,
            api_key=_key,
        )
        self._action_chain = (
            ACTION_CHAIN_V1
            | _llm
            | StrOutputParser()
        ).with_retry(
            retry_if_exception_type=(RateLimitError, APIConnectionError),
            wait_exponential_jitter=True,
            stop_after_attempt=3,
        )
        logger.info(
            "PulseNoteGenerator initialised with LangChain chain (ChatGroq / %s)", self.model
        )

        # ----------------------------------------------------------------
        # Fallback path: raw Groq SDK (tenacity-decorated, Q4 decision)
        # ----------------------------------------------------------------
        self._client = Groq(api_key=_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        themes: dict[str, Any],
        date_range: tuple[str, str] | None = None,
    ) -> PulseNote:
        """
        Generate a PulseNote from a dict of theme groups.

        Parameters
        ----------
        themes : dict
            Keyed by theme_id.  Each value is either a ThemeGroup instance
            or a plain dict with keys: theme_id, theme_name, count,
            avg_rating, sentiment, reviews.
        date_range : (start_iso, end_iso) | None
            If None, defaults to last 12 weeks ending today.
        """
        if not themes:
            raise ValueError("No themes provided — run Phase 2 first.")

        # Normalise to plain dicts
        theme_dicts = self._normalise(themes)

        # Date range
        if date_range is None:
            end   = datetime.today()
            start = end - timedelta(weeks=12)
            date_range = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

        week_label = f"Week of {datetime.today().strftime('%d %b %Y')}"
        total_reviews = sum(t["count"] for t in theme_dicts.values())

        # Select top 3 themes by count
        top3 = self._select_top_themes(theme_dicts, n=3)

        # Pick one representative quote per theme
        for ts in top3:
            ts.quote, ts.quote_rating = self._pick_quote(
                theme_dicts[ts.theme_id]["reviews"]
            )

        # Generate action recommendations via LLM
        actions = self._generate_actions(top3)

        note = PulseNote(
            week_label=week_label,
            date_range=date_range,
            top_themes=top3,
            actions=actions,
            total_reviews=total_reviews,
        )

        # Enforce word limit
        note = self._enforce_word_limit(note)
        logger.info(
            "PulseNote generated: %d themes, %d actions, %d words",
            len(note.top_themes), len(note.actions), note.word_count(),
        )
        return note

    def validate_word_count(self, note: PulseNote) -> bool:
        """Return True if the note is within the word limit."""
        return note.word_count() <= self.max_words

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(themes: dict[str, Any]) -> dict[str, dict]:
        """Convert ThemeGroup objects or plain dicts to plain dicts."""
        result = {}
        for k, v in themes.items():
            if hasattr(v, "to_dict"):
                result[k] = v.to_dict()
            else:
                result[k] = dict(v)
        return result

    def _select_top_themes(
        self, theme_dicts: dict[str, dict], n: int = 3
    ) -> list[ThemeSummary]:
        """Return top-n themes sorted by count descending. Always guarantees exactly n themes."""
        sorted_themes = sorted(
            theme_dicts.values(), key=lambda t: t["count"], reverse=True
        )
        top = []
        for t in sorted_themes[:n]:
            top.append(ThemeSummary(
                theme_id=t["theme_id"],
                theme_name=t["theme_name"],
                count=t["count"],
                avg_rating=t["avg_rating"],
                sentiment=t["sentiment"],
            ))

        # Pad to exactly n themes if there are fewer than n themes populated
        if len(top) < n:
            ALL_POSSIBLE_THEMES = [
                {"id": "onboarding", "name": "Onboarding"},
                {"id": "payments", "name": "Payments"},
                {"id": "statements", "name": "Statements"},
                {"id": "kyc", "name": "KYC"},
                {"id": "withdrawals", "name": "Withdrawals"}
            ]
            existing_ids = {t.theme_id for t in top}
            for candidate in ALL_POSSIBLE_THEMES:
                if len(top) >= n:
                    break
                if candidate["id"] not in existing_ids:
                    # Inject an empty group into theme_dicts so caller's quote finder handles it safely
                    theme_dicts[candidate["id"]] = {
                        "theme_id": candidate["id"],
                        "theme_name": candidate["name"],
                        "count": 0,
                        "avg_rating": 0.0,
                        "sentiment": "neutral",
                        "reviews": []
                    }
                    top.append(ThemeSummary(
                        theme_id=candidate["id"],
                        theme_name=candidate["name"],
                        count=0,
                        avg_rating=0.0,
                        sentiment="neutral",
                        quote="No representative quote available.",
                        quote_rating=0.0
                    ))
        return top

    def _pick_quote(self, reviews: list[dict]) -> tuple[str, float]:
        """
        Select the most representative verbatim quote from a theme's reviews.

        Strategy:
        1. Filter to reviews with word count >= MIN_QUOTE_WORDS
        2. Prefer reviews with ratings at the extremes (1 or 5) for signal
        3. Among those, pick the longest quote up to MAX_QUOTE_CHARS
        4. Fall back to the longest available quote if no extremes found
        """
        if not reviews:
            return ("No representative quote available.", 0.0)

        # Clean and filter
        candidates = []
        for r in reviews:
            text = str(r.get("text", "")).strip()
            # Remove emoji and non-ASCII noise for cleaner quotes
            text = re.sub(r'[^\x00-\x7F]+', '', text).strip()
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text)
            words = len(text.split())
            if words >= self.MIN_QUOTE_WORDS and len(text) <= self.MAX_QUOTE_CHARS:
                candidates.append({
                    "text":   text,
                    "rating": float(r.get("rating", 3)),
                    "words":  words,
                })

        if not candidates:
            # Fall back: take the longest review, truncate if needed
            longest = max(reviews, key=lambda r: len(str(r.get("text", ""))))
            text = re.sub(r'[^\x00-\x7F]+', '', str(longest.get("text", ""))).strip()
            text = re.sub(r'\s+', ' ', text)[:self.MAX_QUOTE_CHARS]
            return (text, float(longest.get("rating", 3)))

        # Prefer extreme ratings (strong signal)
        extremes = [c for c in candidates if c["rating"] in (1.0, 2.0, 5.0)]
        pool = extremes if extremes else candidates

        # Among pool, pick the one with most words (most informative)
        best = max(pool, key=lambda c: c["words"])
        return (best["text"], best["rating"])

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call_llm_fallback(self, prompt: str) -> str:
        """
        Fallback: raw Groq SDK call with tenacity retry (Q4 decision).
        Only invoked when the LangChain chain raises an unexpected error.
        """
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
        )
        return response.choices[0].message.content

    def _generate_actions(self, top_themes: list[ThemeSummary]) -> list[str]:
        """
        Ask the LLM to generate 3 concrete, prioritised action recommendations
        based on the top themes.

        Primary path: LangChain chain (ACTION_CHAIN_V1 | ChatGroq | StrOutputParser)
        Fallback: raw Groq SDK (tenacity-decorated) → rule-based if both fail.
        """
        theme_summary = "\n".join(
            f"- {t.theme_name}: {t.count} reviews, avg {t.avg_rating}/5, "
            f"{t.sentiment}. Sample: \"{t.quote[:120]}\""
            for t in top_themes
        )

        try:
            # Primary: LangChain chain with .with_retry()
            raw = self._action_chain.invoke({"theme_summary": theme_summary})
            actions = self._parse_actions(raw)
            if len(actions) >= 3:
                logger.info("Actions generated via LangChain chain.")
                return actions[:3]
            logger.warning("LangChain chain returned fewer than 3 actions — trying fallback SDK.")
        except (RateLimitError, APIConnectionError, APIStatusError) as exc:
            logger.warning(
                "LangChain chain failed after retries (%s) — trying raw Groq SDK fallback.", exc
            )
        except Exception as exc:
            logger.warning(
                "LangChain chain raised unexpected error (%s: %s) — trying raw Groq SDK fallback.",
                type(exc).__name__, exc,
            )

        # Fallback: raw Groq SDK (tenacity-decorated)
        try:
            fallback_prompt = (
                "You are a product manager at Groww, India's leading investment app.\n"
                "Based on the following weekly user review themes, generate exactly 3 concrete,\n"
                "prioritised action recommendations for the product team.\n\n"
                f"THEMES THIS WEEK:\n{theme_summary}\n\n"
                "RULES:\n"
                "1. Each action must be specific and actionable (not vague like \"improve UX\").\n"
                "2. Prioritise by severity: negative sentiment themes first.\n"
                "3. Each action must be a single sentence, max 20 words.\n"
                "4. Return ONLY a numbered list (1. ... 2. ... 3. ...) — no preamble, no explanation.\n\n"
                "ACTIONS:"
            )
            raw = self._call_llm_fallback(fallback_prompt)
            actions = self._parse_actions(raw)
            if len(actions) >= 3:
                logger.info("Actions generated via raw Groq SDK fallback.")
                return actions[:3]
            logger.warning("Raw Groq SDK fallback returned fewer than 3 actions — using rule-based fallback.")
        except (RateLimitError, APIConnectionError, APIStatusError) as exc:
            logger.error("Action generation failed entirely: %s — using rule-based fallback.", exc)

        return self._fallback_actions(top_themes)

        return self._fallback_actions(top_themes)

    @staticmethod
    def _parse_actions(raw: str) -> list[str]:
        """Extract numbered action items from LLM output."""
        lines = raw.strip().splitlines()
        actions = []
        for line in lines:
            line = line.strip()
            # Match "1. ...", "1) ...", "- ..."
            m = re.match(r'^(?:\d+[.)]\s*|-\s*)(.+)', line)
            if m:
                action = m.group(1).strip()
                if action:
                    actions.append(action)
        return actions

    @staticmethod
    def _fallback_actions(top_themes: list[ThemeSummary]) -> list[str]:
        """Rule-based fallback actions when LLM is unavailable."""
        actions = []
        for t in top_themes:
            if t.sentiment == "negative":
                actions.append(
                    f"Investigate and resolve top {t.theme_name.lower()} "
                    f"complaints (avg {t.avg_rating}/5, {t.count} reviews)."
                )
            else:
                actions.append(
                    f"Maintain and amplify {t.theme_name.lower()} strengths "
                    f"highlighted by {t.count} positive reviews."
                )
        # Pad to 3 if needed
        while len(actions) < 3:
            actions.append("Review and address remaining user feedback themes.")
        return actions[:3]

    def _enforce_word_limit(self, note: PulseNote) -> PulseNote:
        """
        Trim quotes if the note exceeds max_words.
        Quotes are trimmed first (least critical content).
        """
        if self.validate_word_count(note):
            return note

        logger.warning(
            "Note exceeds %d words (%d) — trimming quotes.",
            self.max_words, note.word_count(),
        )
        for ts in note.top_themes:
            if note.word_count() <= self.max_words:
                break
            # Shorten quote by 20% iteratively
            words = ts.quote.split()
            while len(words) > 10 and note.word_count() > self.max_words:
                words = words[: int(len(words) * 0.8)]
                ts.quote = " ".join(words) + "..."

        return note
