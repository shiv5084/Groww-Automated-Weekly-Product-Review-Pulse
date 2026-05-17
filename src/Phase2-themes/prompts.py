"""
prompts.py — Versioned LLM prompt templates for Phase 2 theme classification.

Each prompt version is a standalone string constant AND a LangChain
ChatPromptTemplate.  The active versions used by ThemeGrouper are:
  - CLASSIFY_PROMPT_V1        (raw string — kept for reference / fallback)
  - CLASSIFY_CHAIN_V1         (ChatPromptTemplate — used by LangChain chain)

To iterate on prompts, add new constants (V2, V3 …) and update
ThemeGrouper.build_chain() to reference them.
"""

from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# v1 — structured JSON classification prompt (raw string — kept as fallback)
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT_V1 = """\
You are a product analyst for Groww, India's leading investment app.
Your task is to classify each user review into exactly ONE of the following themes:

THEMES:
{theme_list}

RULES:
1. Assign exactly one theme_id to each review.
2. Use the theme whose description and keywords best match the review content.
3. If a review mentions multiple themes, pick the PRIMARY complaint or praise.
4. If a review is too generic to fit any theme, assign the fallback theme: "{fallback}".
5. Return ONLY a valid JSON array — no markdown, no explanation, no extra text.

OUTPUT FORMAT (strict JSON array):
[
  {{"id": <original_id>, "theme": "<theme_id>"}},
  ...
]

REVIEWS TO CLASSIFY:
{reviews_json}
"""

# ---------------------------------------------------------------------------
# v1 — LangChain ChatPromptTemplate (used by ThemeGrouper LangChain chain)
# Note: LangChain uses single braces for variables; literal braces are doubled.
# ---------------------------------------------------------------------------

CLASSIFY_CHAIN_V1 = ChatPromptTemplate.from_template(
    "You are a product analyst for Groww, India's leading investment app.\n"
    "Your task is to classify each user review into exactly ONE of the following themes:\n\n"
    "THEMES:\n{theme_list}\n\n"
    "RULES:\n"
    "1. Assign exactly one theme_id to each review.\n"
    "2. Use the theme whose description and keywords best match the review content.\n"
    "3. If a review mentions multiple themes, pick the PRIMARY complaint or praise.\n"
    '4. If a review is too generic to fit any theme, assign the fallback theme: "{fallback}".\n'
    "5. Return ONLY a valid JSON array — no markdown, no explanation, no extra text.\n\n"
    "OUTPUT FORMAT (strict JSON array):\n"
    '[\n  {{"id": <original_id>, "theme": "<theme_id>"}},\n  ...\n]\n\n'
    "REVIEWS TO CLASSIFY:\n{reviews_json}"
)

# ---------------------------------------------------------------------------
# Helper: build the theme list block injected into the prompt
# ---------------------------------------------------------------------------

def build_theme_list(themes: list[dict]) -> str:
    """
    Converts the themes list (from themes.yaml) into a readable block
    for injection into the prompt.

    Args:
        themes: list of theme dicts with keys id, name, description, keywords.

    Returns:
        Formatted multi-line string.
    """
    lines = []
    for t in themes:
        kw = ", ".join(t.get("keywords", []))
        lines.append(
            f"- {t['id']}: {t['name']}\n"
            f"  Description: {t['description'].strip()}\n"
            f"  Keywords: {kw}"
        )
    return "\n".join(lines)
