"""
formatter.py — Output formatters for Phase 3 pulse notes.

Produces two output formats from a PulseNote:
  - Markdown  : for Google Docs (headings, bullets, blockquotes)
  - Plain text : for email body (no markdown syntax)
  - HTML       : for rich email clients
"""

from __future__ import annotations

from .pulse_note import PulseNote

# Sentiment emoji mapping (ASCII-safe fallbacks used in plain text)
_SENTIMENT_EMOJI = {"positive": ":)", "neutral": ":|", "negative": ":("}
_SENTIMENT_LABEL = {"positive": "[+]", "neutral": "[~]", "negative": "[-]"}


class PulseNoteFormatter:
    """Stateless formatter — all methods are static."""

    # ------------------------------------------------------------------
    # Markdown (Google Docs)
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_docs(note: PulseNote) -> str:
        """
        Render the pulse note as Markdown suitable for Google Docs.
        Uses ATX headings, bullet lists, and blockquotes.
        """
        lines: list[str] = []

        # Title
        lines.append(f"# Groww Weekly Pulse — {note.week_label}")
        lines.append(
            f"*{note.date_range[0]} to {note.date_range[1]} "
            f"| {note.total_reviews} reviews analysed*"
        )
        lines.append("")

        # Top themes
        lines.append("## Top Themes")
        lines.append("")
        for i, t in enumerate(note.top_themes, 1):
            sentiment_tag = _SENTIMENT_EMOJI.get(t.sentiment, "")
            lines.append(
                f"{i}. **{t.theme_name}** — {t.count} reviews, "
                f"avg {t.avg_rating}/5 {sentiment_tag}"
            )
        lines.append("")

        # User voices
        lines.append("## User Voices")
        lines.append("")
        for t in note.top_themes:
            if t.quote:
                lines.append(f"> \"{t.quote}\" — {t.avg_rating}/5")
                lines.append("")

        # Recommended actions
        lines.append("## Recommended Actions")
        lines.append("")
        for i, action in enumerate(note.actions, 1):
            lines.append(f"{i}. {action}")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Plain text (email body)
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_email(note: PulseNote) -> str:
        """
        Render the pulse note as plain text for email.
        No markdown syntax — uses dashes and indentation.
        """
        lines: list[str] = []
        sep = "-" * 60

        lines.append(f"GROWW WEEKLY PULSE — {note.week_label.upper()}")
        lines.append(
            f"{note.date_range[0]} to {note.date_range[1]} "
            f"| {note.total_reviews} reviews analysed"
        )
        lines.append(sep)
        lines.append("")

        lines.append("TOP THEMES")
        lines.append("")
        for i, t in enumerate(note.top_themes, 1):
            label = _SENTIMENT_LABEL.get(t.sentiment, "")
            lines.append(
                f"  {i}. {t.theme_name} — {t.count} reviews, "
                f"avg {t.avg_rating}/5 {label}"
            )
        lines.append("")

        lines.append("USER VOICES")
        lines.append("")
        for t in note.top_themes:
            if t.quote:
                lines.append(f'  "{t.quote}"')
                lines.append(f"  Rating: {t.avg_rating}/5")
                lines.append("")

        lines.append("RECOMMENDED ACTIONS")
        lines.append("")
        for i, action in enumerate(note.actions, 1):
            lines.append(f"  {i}. {action}")
        lines.append("")
        lines.append(sep)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # HTML (rich email)
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_html(note: PulseNote) -> str:
        """
        Render the pulse note as an HTML email body.
        Self-contained, inline styles, no external dependencies.
        """
        _SENTIMENT_COLOR = {
            "positive": "#2e7d32",   # green
            "neutral":  "#f57c00",   # amber
            "negative": "#c62828",   # red
        }

        def esc(s: str) -> str:
            return (
                s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;")
            )

        parts: list[str] = []
        parts.append(
            '<div style="font-family:Arial,sans-serif;max-width:600px;'
            'margin:0 auto;color:#212121;">'
        )

        # Header
        parts.append(
            f'<h1 style="font-size:20px;border-bottom:2px solid #00b386;'
            f'padding-bottom:8px;">Groww Weekly Pulse &mdash; {esc(note.week_label)}</h1>'
        )
        parts.append(
            f'<p style="color:#757575;font-size:13px;">'
            f'{esc(note.date_range[0])} to {esc(note.date_range[1])} '
            f'&bull; {note.total_reviews} reviews analysed</p>'
        )

        # Top themes
        parts.append('<h2 style="font-size:16px;margin-top:24px;">Top Themes</h2>')
        parts.append('<ol style="padding-left:20px;">')
        for t in note.top_themes:
            color = _SENTIMENT_COLOR.get(t.sentiment, "#212121")
            parts.append(
                f'<li style="margin-bottom:6px;">'
                f'<strong>{esc(t.theme_name)}</strong> &mdash; '
                f'{t.count} reviews, avg {t.avg_rating}/5 '
                f'<span style="color:{color};font-weight:bold;">'
                f'({esc(t.sentiment)})</span></li>'
            )
        parts.append('</ol>')

        # User voices
        parts.append('<h2 style="font-size:16px;margin-top:24px;">User Voices</h2>')
        for t in note.top_themes:
            if t.quote:
                parts.append(
                    f'<blockquote style="border-left:4px solid #00b386;'
                    f'margin:8px 0;padding:8px 16px;background:#f5f5f5;'
                    f'font-style:italic;">'
                    f'&ldquo;{esc(t.quote)}&rdquo; '
                    f'<span style="color:#757575;">({t.avg_rating}/5)</span>'
                    f'</blockquote>'
                )

        # Recommended actions
        parts.append('<h2 style="font-size:16px;margin-top:24px;">Recommended Actions</h2>')
        parts.append('<ol style="padding-left:20px;">')
        for action in note.actions:
            parts.append(f'<li style="margin-bottom:6px;">{esc(action)}</li>')
        parts.append('</ol>')

        parts.append('</div>')
        return "\n".join(parts)
