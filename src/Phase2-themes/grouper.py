"""
grouper.py — LLM-powered theme classification engine for Phase 2.

Responsibilities
----------------
- Load theme definitions from config/themes.yaml
- Batch cleaned reviews to fit within the LLM context window
- Send each batch to Groq via a LangChain chain (ChatGroq + ChatPromptTemplate
  + StrOutputParser) with built-in .with_retry() for transient failures
- Parse the LLM response into per-review theme assignments
- Aggregate per-theme statistics: count, average rating, sentiment signal
- tenacity kept as a fallback decorator on the raw-SDK path (Q4 decision)

LangChain chain (primary path):
    CLASSIFY_CHAIN_V1 | ChatGroq | StrOutputParser
    → .with_retry() handles RateLimitError / APIConnectionError automatically

Raw Groq SDK (fallback path, tenacity-decorated):
    Used only if the LangChain chain raises an unexpected exception type.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# LangChain imports (primary LLM path)
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser

# Raw Groq SDK kept as fallback
from groq import Groq, RateLimitError, APIStatusError, APIConnectionError

# tenacity kept as fallback (Q4 decision)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .prompts import CLASSIFY_CHAIN_V1, CLASSIFY_PROMPT_V1, build_theme_list

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ThemeGroup:
    """Aggregated statistics for a single theme."""
    theme_id:   str
    theme_name: str
    count:      int                  = 0
    total_rating: float              = 0.0
    reviews:    list[dict[str, Any]] = field(default_factory=list)

    @property
    def avg_rating(self) -> float:
        return round(self.total_rating / self.count, 2) if self.count else 0.0

    @property
    def sentiment(self) -> str:
        """Simple bucketed sentiment derived from average rating."""
        if self.avg_rating >= 4.0:
            return "positive"
        if self.avg_rating >= 3.0:
            return "neutral"
        return "negative"

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_id":   self.theme_id,
            "theme_name": self.theme_name,
            "count":      self.count,
            "avg_rating": self.avg_rating,
            "sentiment":  self.sentiment,
            "reviews":    self.reviews,
        }


# ---------------------------------------------------------------------------
# ThemeGrouper
# ---------------------------------------------------------------------------

class ThemeGrouper:
    """
    Classifies a DataFrame of cleaned reviews into themes using Groq LLM.

    Parameters
    ----------
    themes_config_path : str | Path
        Path to config/themes.yaml.  Defaults to the standard project location.
    model : str
        Groq model identifier.  Defaults to env var LLM_MODEL or llama-3.3-70b-versatile.
    batch_size : int
        Number of reviews per LLM call.  Keep low enough to stay within the
        model's context window (default 50).
    api_key : str | None
        Groq API key.  Falls back to GROQ_API_KEY env var.
    """

    DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "themes.yaml"
    DEFAULT_MODEL  = "llama-3.3-70b-versatile"
    DEFAULT_BATCH  = 50

    def __init__(
        self,
        themes_config_path: str | Path | None = None,
        model:      str | None = None,
        batch_size: int        = DEFAULT_BATCH,
        api_key:    str | None = None,
    ) -> None:
        config_path = Path(themes_config_path or self.DEFAULT_CONFIG)
        self._themes_cfg = self._load_themes(config_path)
        self._themes_map = {t["id"]: t for t in self._themes_cfg["themes"]}
        self._fallback   = self._themes_cfg["settings"]["fallback_theme"]
        self._max_themes = self._themes_cfg["settings"]["max_themes"]

        self.model      = model or os.getenv("LLM_MODEL", self.DEFAULT_MODEL)
        self.batch_size = batch_size

        _key = api_key or os.getenv("GROQ_API_KEY")
        if not _key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY in your .env file "
                "or pass api_key= to ThemeGrouper()."
            )

        # ----------------------------------------------------------------
        # Primary path: LangChain chain
        #   CLASSIFY_CHAIN_V1 | ChatGroq | StrOutputParser
        #   .with_retry() handles RateLimitError / APIConnectionError
        # ----------------------------------------------------------------
        _llm = ChatGroq(
            model=self.model,
            temperature=0.0,
            max_tokens=2048,
            api_key=_key,
        )
        self._chain = (
            CLASSIFY_CHAIN_V1
            | _llm
            | StrOutputParser()
        ).with_retry(
            retry_if_exception_type=(RateLimitError, APIConnectionError),
            wait_exponential_jitter=True,
            stop_after_attempt=3,
        )
        logger.info(
            "ThemeGrouper initialised with LangChain chain (ChatGroq / %s)", self.model
        )

        # ----------------------------------------------------------------
        # Fallback path: raw Groq SDK (tenacity-decorated, Q4 decision)
        # ----------------------------------------------------------------
        self._client = Groq(api_key=_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def group_reviews(self, df: pd.DataFrame) -> dict[str, ThemeGroup]:
        """
        Classify all reviews in *df* and return a dict of ThemeGroup objects
        keyed by theme_id.

        The DataFrame must contain at least: llm_text (or review_text), rating.
        An 'id' column is added internally if absent.
        """
        if df.empty:
            logger.warning("ThemeGrouper received an empty DataFrame — nothing to classify.")
            return {}

        # Use llm_text if available (truncated), else fall back to review_text
        text_col = "llm_text" if "llm_text" in df.columns else "review_text"

        # Work on a copy with a stable integer id for round-tripping through JSON
        work = df.reset_index(drop=True).copy()
        work["_row_id"] = work.index

        # Initialise all theme groups
        groups: dict[str, ThemeGroup] = {
            t["id"]: ThemeGroup(theme_id=t["id"], theme_name=t["name"])
            for t in self._themes_cfg["themes"]
        }

        # Process in batches
        total = len(work)
        for start in range(0, total, self.batch_size):
            batch = work.iloc[start : start + self.batch_size]
            logger.info(
                "Classifying batch %d–%d of %d reviews …",
                start + 1, min(start + self.batch_size, total), total,
            )
            assignments = self._classify_batch(batch, text_col)
            self._apply_assignments(batch, assignments, groups, text_col)

        # Drop empty groups
        groups = {k: v for k, v in groups.items() if v.count > 0}
        logger.info(
            "Classification complete. %d themes populated: %s",
            len(groups),
            {k: v.count for k, v in groups.items()},
        )
        return groups

    def build_prompt(self, batch: pd.DataFrame, text_col: str) -> str:
        """Build the classification prompt string for a single batch (used for logging/debug)."""
        theme_list = build_theme_list(self._themes_cfg["themes"])
        reviews_payload = [
            {"id": int(row["_row_id"]), "text": str(row[text_col])}
            for _, row in batch.iterrows()
        ]
        return CLASSIFY_PROMPT_V1.format(
            theme_list=theme_list,
            fallback=self._fallback,
            reviews_json=json.dumps(reviews_payload, ensure_ascii=False, indent=2),
        )

    def _build_chain_input(self, batch: pd.DataFrame, text_col: str) -> dict:
        """Build the input dict for the LangChain chain."""
        theme_list = build_theme_list(self._themes_cfg["themes"])
        reviews_payload = [
            {"id": int(row["_row_id"]), "text": str(row[text_col])}
            for _, row in batch.iterrows()
        ]
        return {
            "theme_list":   theme_list,
            "fallback":     self._fallback,
            "reviews_json": json.dumps(reviews_payload, ensure_ascii=False, indent=2),
        }

    def parse_response(self, llm_output: str) -> list[dict[str, Any]]:
        """
        Parse the LLM JSON response into a list of {id, theme} dicts.
        Returns an empty list on parse failure (caller handles fallback).
        """
        # Strip markdown code fences if the model wraps output
        text = llm_output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # drop first and last fence lines
            text = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            ).strip()

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array at top level.")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse LLM response as JSON: %s\nRaw output:\n%s", exc, llm_output)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_themes(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Themes config not found: {path}")
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)

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
            temperature=0.0,
            max_tokens=2048,
        )
        return response.choices[0].message.content

    def _call_llm(self, chain_input: dict) -> str:
        """
        Primary path: invoke the LangChain chain.
        Falls back to the raw Groq SDK if the chain raises an unexpected error.
        """
        try:
            return self._chain.invoke(chain_input)
        except (RateLimitError, APIConnectionError, APIStatusError):
            # Already retried by .with_retry() — re-raise so _classify_batch can handle
            raise
        except Exception as exc:
            logger.warning(
                "LangChain chain raised unexpected error (%s: %s) — "
                "falling back to raw Groq SDK.",
                type(exc).__name__, exc,
            )
            # Reconstruct the raw prompt string for the fallback path
            prompt = CLASSIFY_PROMPT_V1.format(**chain_input)
            return self._call_llm_fallback(prompt)

    def _classify_batch(
        self, batch: pd.DataFrame, text_col: str
    ) -> list[dict[str, Any]]:
        """
        Classify one batch.  Falls back to the fallback theme for the entire
        batch if the LLM call or parse fails after all retries.
        """
        chain_input = self._build_chain_input(batch, text_col)
        try:
            raw = self._call_llm(chain_input)
            assignments = self.parse_response(raw)
        except (RateLimitError, APIConnectionError, APIStatusError) as exc:
            logger.error("LLM call failed after retries: %s — applying fallback theme to batch.", exc)
            assignments = []

        # Validate and fill missing / invalid assignments with fallback
        valid_ids = {int(r["_row_id"]) for _, r in batch.iterrows()}
        assigned_ids: set[int] = set()
        clean: list[dict[str, Any]] = []

        for item in assignments:
            try:
                row_id    = int(item["id"])
                theme_id  = str(item["theme"]).lower().strip()
                if row_id not in valid_ids:
                    continue
                if theme_id not in self._themes_map:
                    logger.debug("Unknown theme '%s' for id %d — using fallback.", theme_id, row_id)
                    theme_id = self._fallback
                clean.append({"id": row_id, "theme": theme_id})
                assigned_ids.add(row_id)
            except (KeyError, TypeError, ValueError):
                continue

        # Any row not returned by the LLM gets the fallback
        for row_id in valid_ids - assigned_ids:
            logger.debug("No assignment for row %d — using fallback theme.", row_id)
            clean.append({"id": row_id, "theme": self._fallback})

        return clean

    def _apply_assignments(
        self,
        batch:       pd.DataFrame,
        assignments: list[dict[str, Any]],
        groups:      dict[str, ThemeGroup],
        text_col:    str,
    ) -> None:
        """Merge assignment results into the ThemeGroup accumulators."""
        id_to_theme = {a["id"]: a["theme"] for a in assignments}

        for _, row in batch.iterrows():
            row_id   = int(row["_row_id"])
            theme_id = id_to_theme.get(row_id, self._fallback)

            # Ensure the theme exists (safety net for unexpected theme ids)
            if theme_id not in groups:
                theme_id = self._fallback

            group = groups[theme_id]
            rating = float(row.get("rating", 0) or 0)
            group.count        += 1
            group.total_rating += rating
            group.reviews.append({
                "text":   str(row.get(text_col, "")),
                "rating": rating,
                "source": str(row.get("source", "")),
                "date":   str(row.get("date", "")),
            })
