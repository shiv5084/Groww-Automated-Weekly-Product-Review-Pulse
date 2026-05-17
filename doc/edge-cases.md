# Groww — Automated Weekly Product Review Pulse: Edge Cases

> **Version:** 1.0
> **Date:** 2026-05-13
> **Linked Docs:** architecture.md, phase-wise-implementationplan.md

---

## Overview

This document catalogs all identified edge cases across every pipeline stage — from API scraping through MCP publishing. Each case includes the trigger condition, expected behavior, and the phase/component it belongs to.

---

## EC-1: API Scraper (Phase 1A)

### EC-1.1 — Zero Reviews Loaded After Scroll

**Trigger:** The Play Store or App Store API responds but returns 0 review items (e.g., API structure changed, or region-locked content).

**Expected Behavior:**
- Log a `WARNING: 0 reviews scraped from <source>` message
- Do NOT write an empty CSV — raise `ScraperEmptyResultError`
- Pipeline halts with a clear message; does not proceed to ingestion with empty data

**Risk Level:** High — API endpoints and schemas can change without notice

---

### EC-1.2 — Anti-Bot Block / CAPTCHA Interception

**Trigger:** Google Play or Apple App Store APIs return a 429 Too Many Requests, or a block instead of the review data.

**Expected Behavior:**
- Detect non-review API response (check for expected JSON schemas)
- Log `ERROR: Anti-bot block detected on <source>. Retrying after <delay>s`
- Retry up to 3 times with exponential backoff (5s, 15s, 45s)
- If all retries fail, fall back to `data/sample/sample_reviews.csv` and log a `FALLBACK` warning
- Never silently continue with partial/empty data

---

### EC-1.3 — Partial Scrape (Fewer Reviews Than Expected)

**Trigger:** Scraper loads only 50 reviews when 500 were expected — scroll limit hit, network timeout mid-scroll, or store shows fewer reviews for the date range.

**Expected Behavior:**
- Accept partial results if count >= configurable minimum threshold (default: 30 reviews)
- Log `WARNING: Only <n> reviews scraped; expected ~<target>. Proceeding with partial data.`
- If count < minimum threshold, raise `InsufficientDataError`

---

### EC-1.4 — Duplicate Reviews Across Runs

**Trigger:** Pipeline is re-run for the same week; scraper collects reviews already present in `data/raw/` from a previous run.

**Expected Behavior:**
- Deduplication key: `(review_text_hash, date, source)`
- Merge new scrape with existing CSV, drop exact duplicates
- Log count of duplicates removed
- Idempotent: running twice produces the same output CSV

---

### EC-1.5 — Review Date in Relative Format

**Trigger:** Play Store returns dates as relative strings like `"3 days ago"`, `"a week ago"`, `"2 months ago"` instead of absolute ISO dates.

**Expected Behavior:**
- Resolve relative dates against the scrape timestamp (stored in CSV metadata)
- Convert to absolute `YYYY-MM-DD` format before saving
- Log any dates that could not be resolved as `[DATE_UNKNOWN]`
- Reviews with `[DATE_UNKNOWN]` are excluded from date-range filtering

---

### EC-1.6 — App Store Pagination Failure (No "Load More" Button)

**Trigger:** App Store RSS API pagination returns a URL format that cannot be parsed, or the pagination loop gets stuck.

**Expected Behavior:**
- Detect stalled pagination (API returns same reviews or fails to load next page)
- Stop pagination loop after 3 consecutive no-change cycles
- Save whatever reviews were collected up to that point
- Log `WARNING: App Store pagination stalled at <n> reviews`

---

### EC-1.7 — Non-English Reviews

**Trigger:** Scraped reviews include Hindi, Gujarati, Tamil, or other regional language text (common for Groww's Indian user base).

**Expected Behavior:**
- Do NOT filter out non-English reviews at scrape time
- Pass them through to the LLM — modern LLMs handle multilingual input
- PII scrubber must still apply regex patterns (phone numbers, emails are language-agnostic)
- Pulse note generator should prefer English quotes for the final output; non-English quotes are acceptable if no English equivalent exists

---

## EC-2: Data Ingestion & PII Scrubbing (Phase 1)

### EC-2.1 — Empty CSV File

**Trigger:** `data/raw/playstore_reviews.csv` or `data/raw/appstore_reviews.csv` exists but contains 0 data rows (only headers, or completely empty).

**Expected Behavior:**
- `ReviewIngestion.load_csv()` raises `EmptyDatasetError` with the file path
- Pipeline halts; does not proceed to PII scrubbing with an empty DataFrame
- Error message: `"CSV at <path> contains no reviews. Re-run scraper or provide a valid CSV."`

---

### EC-2.2 — Missing Required Columns

**Trigger:** CSV is missing one or more of: `rating`, `title`, `review_text`, `date`, `source`.

**Expected Behavior:**
- `validate_schema()` raises `SchemaValidationError` listing the missing columns
- Do NOT attempt to infer or fill missing columns silently
- Error message includes the expected schema and the actual columns found

---

### EC-2.3 — Rating Out of Range

**Trigger:** A row has `rating = 0`, `rating = 6`, `rating = -1`, or a non-numeric value like `"five"`.

**Expected Behavior:**
- Rows with non-numeric ratings: coerce to `NaN`, log as malformed
- Rows with numeric ratings outside [1, 5]: clamp to nearest valid value (0→1, 6→5) and log a warning
- If >20% of rows have invalid ratings, raise `DataQualityWarning` but continue

---

### EC-2.4 — All Reviews Outside the Date Window

**Trigger:** After date-range filtering (last 8–12 weeks), zero reviews remain — e.g., the CSV contains only very old reviews.

**Expected Behavior:**
- `filter_date_range()` raises `InsufficientDataError`: `"No reviews found in the last <weeks> weeks. Oldest review date: <date>."`
- Pipeline halts with a clear message
- Do NOT generate a pulse note from zero reviews

---

### EC-2.5 — Malformed Date Strings

**Trigger:** `date` column contains values like `"N/A"`, `""`, `"13/32/2025"`, or mixed formats (`"May 5"` vs `"2025-05-05"`).

**Expected Behavior:**
- Use `python-dateutil` with `dayfirst=False` for flexible parsing
- Rows where date cannot be parsed: set `date = NaT`, log as `[DATE_PARSE_FAILED]`
- Exclude `NaT` rows from date-range filtering
- If >30% of rows have unparseable dates, raise `DataQualityWarning`

---

### EC-2.6 — Review Text Contains Only PII

**Trigger:** After PII scrubbing, a review's `review_text` becomes empty or contains only redaction tokens like `"[EMAIL_REDACTED] [PHONE_REDACTED]"`.

**Expected Behavior:**
- Mark such rows with `is_usable = False`
- Exclude them from LLM processing and quote selection
- Log count of fully-redacted reviews in the scrub report
- Do NOT pass empty/token-only text to the LLM

---

### EC-2.7 — PII in Review Title (Not Just Body)

**Trigger:** A user includes their email or phone number in the review title field, not just the body.

**Expected Behavior:**
- `scrub_dataframe()` must apply PII patterns to BOTH `title` and `review_text` columns
- Scrub report must count redactions per column separately

---

### EC-2.8 — Encoding Issues (Non-UTF-8 Characters)

**Trigger:** CSV contains Windows-1252 or Latin-1 encoded characters (e.g., `â€™` instead of `'`), or emoji characters that break pandas parsing.

**Expected Behavior:**
- `load_csv()` attempts UTF-8 first, then falls back to `latin-1` encoding
- Emoji characters are preserved (they are valid review content)
- Log encoding fallback: `"WARNING: UTF-8 decode failed for <file>. Retrying with latin-1."`

---

### EC-2.9 — Extremely Long Review Text

**Trigger:** A single review has `review_text` of 5,000+ characters (rare but possible — some users write essays).

**Expected Behavior:**
- Truncate to 1,000 characters for LLM processing, preserving the first 1,000 chars
- Log: `"Review truncated from <original_len> to 1000 chars for LLM processing"`
- Original full text is preserved in the cleaned CSV; only the LLM input is truncated

---

## EC-3: LLM Theme Grouping Engine (Phase 2)

### EC-3.1 — LLM Returns More Than 5 Themes

**Trigger:** Despite the prompt constraint, the LLM returns 6 or 7 theme labels.

**Expected Behavior:**
- `parse_response()` detects theme count > 5
- Merge the lowest-volume extra themes into the closest matching theme from the allowed 5
- Log: `"WARNING: LLM returned <n> themes. Merged <extra_theme> into <target_theme>."`
- Never surface more than 5 themes downstream

---

### EC-3.2 — LLM Returns Malformed / Non-JSON Response

**Trigger:** LLM outputs free-form text instead of the expected JSON structure, or returns truncated JSON.

**Expected Behavior:**
- Attempt JSON extraction with regex from the raw response
- If extraction fails, retry the LLM call once with a stricter prompt: `"Respond ONLY with valid JSON. No explanation."`
- If second attempt also fails, fall back to keyword-based theme assignment (regex matching against theme keywords)
- Log the raw LLM response for debugging

---

### EC-3.3 — All Reviews Assigned to One Theme

**Trigger:** LLM assigns 95%+ of reviews to a single theme (e.g., all to "Payments"), leaving other themes empty.

**Expected Behavior:**
- Detect theme imbalance: if any single theme has >80% of reviews, log a `DataQualityWarning`
- Do NOT re-run automatically — surface the warning and proceed
- The pulse note will reflect the actual distribution; this is valid data, not an error

---

### EC-3.4 — LLM Rate Limit / Quota Exhaustion

**Trigger:** Groq/OpenAI API returns `429 Too Many Requests` or `RateLimitError`.

**Expected Behavior:**
- Exponential backoff: wait 5s, 15s, 45s between retries (max 3 retries)
- If all retries exhausted, raise `LLMUnavailableError` with a clear message
- Pipeline halts; does not produce a partial pulse note
- Log the full error response for debugging

---

### EC-3.5 — LLM Context Window Exceeded

**Trigger:** The batch of reviews sent to the LLM exceeds the model's context window (e.g., 500 reviews × 200 words each = 100K tokens).

**Expected Behavior:**
- Batching logic splits reviews into chunks of max 50 reviews per LLM call
- Each chunk is classified independently; results are merged
- If a single review exceeds 500 tokens, it is truncated before batching (see EC-2.9)

---

### EC-3.6 — Review Doesn't Fit Any Theme

**Trigger:** A review is about something outside the 5 defined themes (e.g., a review about the Groww website, not the app).

**Expected Behavior:**
- LLM assigns it to the closest theme or an `"Other"` bucket
- `"Other"` bucket reviews are excluded from the top-3 theme selection
- If >40% of reviews fall into `"Other"`, log a `ThemeConfigWarning` suggesting theme definitions need updating

---

### EC-3.7 — Fewer Than 3 Themes Have Sufficient Data

**Trigger:** After grouping, only 1 or 2 themes have enough reviews to be meaningful (e.g., only 5 reviews total).

**Expected Behavior:**
- Pulse note uses however many themes are available (1 or 2 instead of 3)
- Template adjusts: `"Top <n> Themes"` instead of hardcoded `"Top 3 Themes"`
- Log: `"WARNING: Only <n> themes have sufficient data. Pulse note will reflect <n> themes."`

---

## EC-4: Pulse Note Generator (Phase 3)

### EC-4.1 — Generated Note Exceeds 250 Words

**Trigger:** LLM-generated action recommendations or theme descriptions push the note over the 250-word limit.

**Expected Behavior:**
- `validate_word_count()` detects the violation
- Truncation strategy (in order): shorten action descriptions → shorten theme descriptions → shorten quotes (to first sentence)
- Re-validate after each truncation step
- Log: `"Note truncated from <original_count> to <final_count> words"`
- Never truncate verbatim user quotes mid-sentence

---

### EC-4.2 — Fewer Than 3 Usable Quotes Available

**Trigger:** After PII scrubbing and filtering, fewer than 3 reviews have usable verbatim text (e.g., most reviews are very short like "Good app" or fully redacted).

**Expected Behavior:**
- Use however many quotes are available (1 or 2)
- Template adjusts: `"User Voices (<n> quotes)"` instead of hardcoded `"3 Verbatim Quotes"`
- Do NOT fabricate or paraphrase quotes — only verbatim text from actual reviews
- Log: `"WARNING: Only <n> usable quotes found."`

---

### EC-4.3 — Quote Contains Residual PII (Post-Scrub)

**Trigger:** A quote selected for the pulse note still contains PII that the regex scrubber missed (e.g., a name embedded in a sentence: "I, Rahul, had this issue...").

**Expected Behavior:**
- Run a secondary PII check on all selected quotes before including them in the note
- If PII is detected, replace that quote with the next best candidate
- If no clean quotes are available, use `[Quote unavailable — PII detected]` as a placeholder
- Log the incident for audit purposes

---

### EC-4.4 — Date Range Spans Two Calendar Months

**Trigger:** The 8–12 week window crosses a month boundary (e.g., April 1 – May 13).

**Expected Behavior:**
- Title format: `"Groww Weekly Pulse — Apr 1 – May 13, 2026"` (show both months)
- Do NOT use `"Week of <single date>"` when the range spans months
- Date range is always derived from the actual min/max dates in the filtered dataset

---

### EC-4.5 — Action Generation Returns Generic Advice

**Trigger:** LLM generates vague action items like "Improve the app" or "Fix bugs" instead of specific, actionable recommendations.

**Expected Behavior:**
- Validate actions against a specificity heuristic: each action must reference a theme name and a concrete verb (e.g., "Reduce KYC re-submission rate by...")
- If an action fails the heuristic, retry the LLM call once with a more constrained prompt
- Log: `"WARNING: Generic action detected. Retrying with stricter prompt."`

---

## EC-5: MCP Integration Layer (Phase 4)

### EC-5.1 — OAuth Token Expired

**Trigger:** The stored OAuth 2.0 token has expired when the pipeline attempts to connect to the Google Docs or Gmail MCP server.

**Expected Behavior:**
- MCP server config includes a refresh token; attempt auto-refresh first
- If refresh succeeds, continue silently
- If refresh fails (revoked token, expired refresh token), raise `OAuthRefreshError`
- Log: `"ERROR: OAuth token expired and refresh failed. Re-authenticate using: python src/main.py --reauth"`
- Pipeline halts; does not attempt to create docs/drafts with invalid credentials

---

### EC-5.2 — MCP Server Unreachable / Connection Timeout

**Trigger:** The Google Docs or Gmail MCP server is unreachable (network issue, server down, wrong config).

**Expected Behavior:**
- Retry connection up to 3 times with 10s timeout each
- If all retries fail, activate fallback: save pulse note as `output/notes/pulse_<date>.md`
- Log: `"ERROR: MCP server unreachable. Pulse note saved locally at <path>. Resolve MCP config and re-run Phase 4 only."`
- Pipeline does NOT re-run the entire pipeline — only the MCP step needs to be retried

---

### EC-5.3 — Pipeline Re-Run Appends Another Section (Master Log)

**Trigger:** Phase 4 runs again for the same calendar week (operator re-run, or full pipeline retry after a partial failure).

**Expected Behavior:**
- **Do not** create a new Google Doc or search Drive by title
- Append another dated section to the same `GOOGLE_MASTER_DOC_ID` (append-only master log per DEC-011)
- Log: `"INFO: Appended pulse section to master doc <document_id> for week <label>."`
- Return the same `document_id` and current `document_url`
- Operators who need a single section per week must manually remove the duplicate section in the master doc

---

### EC-5.8 — Missing or Invalid `GOOGLE_MASTER_DOC_ID`

**Trigger:** `GOOGLE_MASTER_DOC_ID` is unset, malformed, or points to a doc the OAuth user cannot edit.

**Expected Behavior:**
- Phase 4 initialization raises `ConfigurationError` before any MCP tool call
- Log: `"ERROR: GOOGLE_MASTER_DOC_ID invalid or inaccessible. Create a master doc, share with the OAuth account, and set the ID in .env."`
- No Gmail draft is created
- Local Phase 3 Markdown remains available under `output/notes/`

---

### EC-5.9 — Append Succeeds but Gmail Draft Fails

**Trigger:** `append_pulse_to_doc` succeeds but `create_gmail_draft` fails (quota, auth scope, network).

**Expected Behavior:**
- Log: `"WARNING: Master doc updated but Gmail draft failed. document_id=<id> document_url=<url>"`
- Write partial `publish_YYYY-MM-DD.json` with `document_id`, `document_url`, and `draft_id: null`
- Do **not** roll back the doc append
- Operator can re-run `python src/scripts/run_phase4.py` to retry draft only (implementation may skip append if same-day publish log exists)

---

### EC-5.4 — Gmail Draft Already Exists for This Week

**Trigger:** A Gmail draft with the same subject line already exists (pipeline re-run for the same week).

**Expected Behavior:**
- Check for existing draft by subject line before creating a new one
- If found: update the existing draft's body content
- Log: `"INFO: Existing draft found for this week. Updating draft content."`
- Do NOT create duplicate drafts

---

### EC-5.5 — Google Docs Append Formatting Degraded

**Trigger:** The MCP server appends content but structured formatting (headings, bold) is lost — plain Markdown appears as unstyled text in the master doc.

**Expected Behavior:**
- Detect degraded append if possible; log: `"WARNING: Doc append succeeded with plain/unstyled content."`
- Do NOT retry append indefinitely — accept degraded content as valid output
- `document_id` and `document_url` are still returned and logged

---

### EC-5.6 — Gmail Draft Body Too Large

**Trigger:** The pulse note formatted as HTML for email exceeds Gmail's draft size limit (25 MB, though practically unlikely).

**Expected Behavior:**
- Use plain-text email body as fallback (strip HTML formatting)
- Log: `"WARNING: HTML email body too large. Falling back to plain text."`
- Plain text version is always generated alongside HTML (see `format_for_email()`)

---

### EC-5.7 — MCP Config File Missing or Malformed

**Trigger:** `config/mcp_config.json` is missing, empty, or contains invalid JSON.

**Expected Behavior:**
- `MCPConfig.load()` raises `ConfigurationError` with a clear message
- Error message: `"MCP config not found at config/mcp_config.json. Copy config/mcp_config.example.json and fill in your credentials."`
- Pipeline halts at Phase 4 initialization; does not attempt any MCP calls

---

## EC-6: End-to-End Pipeline (Phase 5)

### EC-6.1 — Pipeline Interrupted Mid-Run

**Trigger:** The pipeline crashes or is killed between phases (e.g., after theme grouping but before note generation).

**Expected Behavior:**
- Each phase saves its output to disk before the next phase begins (checkpointing)
- On re-run, detect existing intermediate outputs and skip completed phases
- CLI flag `--force` re-runs all phases regardless of existing outputs
- Log: `"INFO: Resuming from Phase <n>. Use --force to re-run all phases."`

---

### EC-6.2 — Both Scrapers Fail Simultaneously

**Trigger:** Both Play Store and App Store scrapers fail (e.g., both stores block the scraper on the same run).

**Expected Behavior:**
- If `data/sample/sample_reviews.csv` exists, use it as fallback with a prominent warning
- Log: `"CRITICAL: Both scrapers failed. Using sample data. Output is for demo purposes only."`
- Pulse note includes a watermark: `"[DEMO — Based on sample data, not live reviews]"`
- Do NOT silently produce a pulse note that appears to be from live data

---

### EC-6.3 — Weekly Re-Run Produces Identical Output

**Trigger:** The pipeline is re-run for the same week with the same data — idempotency check.

**Expected Behavior:**
- Same input data → same themes, same quotes, same actions (deterministic LLM calls via fixed seed/temperature=0)
- Master doc receives another append section if Phase 4 re-runs — see EC-5.3
- Same Gmail draft is updated when subject matches — see EC-5.4
- Log: `"INFO: Idempotent run detected. Existing outputs updated."`

---

### EC-6.4 — GitHub Actions Run Fails Due to Missing Secrets

**Trigger:** The GitHub Actions weekly cron job runs but `LLM_API_KEY` or `GOOGLE_OAUTH_TOKEN` secrets are not set in the repository.

**Expected Behavior:**
- Pipeline fails fast at environment validation (before any scraping or LLM calls)
- GitHub Actions step fails with exit code 1 and a clear error message
- Error: `"Missing required environment variable: LLM_API_KEY. Set this in GitHub repository secrets."`
- Workflow sends a failure notification (if configured)

---

### EC-6.5 — `--dry-run` Flag Behavior

**Trigger:** User runs `python src/main.py --dry-run` to test the pipeline without publishing.

**Expected Behavior:**
- All phases run normally (scrape, ingest, PII scrub, theme group, generate note)
- MCP calls are skipped — no Google Doc created, no Gmail draft created
- Pulse note is saved locally to `output/notes/pulse_<date>_dryrun.md`
- Log: `"DRY RUN: MCP publishing skipped. Note saved to <path>"`

---

## EC-7: Security & PII Edge Cases

### EC-7.1 — PII Regex False Positive

**Trigger:** A legitimate product term is flagged as PII — e.g., `"UPI@groww"` is flagged as a username, or `"1234-5678"` is flagged as a phone number.

**Expected Behavior:**
- Maintain an allowlist of known false-positive patterns (e.g., `@groww`, `@zerodha`, common app names)
- Allowlisted patterns are not redacted
- Log false-positive candidates for periodic review

---

### EC-7.2 — PII in LLM-Generated Action Items

**Trigger:** The LLM generates an action item that inadvertently includes a user's name or detail from a review (hallucination or context bleed).

**Expected Behavior:**
- Run PII scrubber on all LLM-generated text (not just review text)
- This includes: action items, theme descriptions, and any LLM-generated summaries
- If PII is found in LLM output, redact and log: `"WARNING: PII detected in LLM output. Redacted before publishing."`

---

### EC-7.3 — Credentials Accidentally Committed to Git

**Trigger:** A developer accidentally stages `.env` or `credentials.json` for a commit.

**Expected Behavior:**
- `.gitignore` must include: `.env`, `credentials.json`, `token.json`, `config/mcp_config.json`, `data/raw/`
- Pre-commit hook (optional): scan staged files for credential patterns before allowing commit
- If detected: block commit with message `"Potential credentials detected in staged files. Remove before committing."`

---

## Edge Case Summary Matrix

| ID | Component | Severity | Handling Strategy |
|---|---|---|---|
| EC-1.1 | Scraper | High | Raise error, halt pipeline |
| EC-1.2 | Scraper | High | Retry + fallback to sample CSV |
| EC-1.3 | Scraper | Medium | Accept partial if above threshold |
| EC-1.4 | Scraper | Low | Deduplicate on hash key |
| EC-1.5 | Scraper | Medium | Resolve relative dates at scrape time |
| EC-1.6 | Scraper | Medium | Detect stall, save partial results |
| EC-1.7 | Scraper | Low | Pass through; LLM handles multilingual |
| EC-2.1 | Ingestion | High | Raise EmptyDatasetError |
| EC-2.2 | Ingestion | High | Raise SchemaValidationError |
| EC-2.3 | Ingestion | Medium | Clamp + warn |
| EC-2.4 | Ingestion | High | Raise InsufficientDataError |
| EC-2.5 | Ingestion | Medium | Parse flexibly, exclude NaT rows |
| EC-2.6 | PII Scrubber | High | Mark unusable, exclude from LLM |
| EC-2.7 | PII Scrubber | High | Scrub both title and body columns |
| EC-2.8 | Ingestion | Medium | Fallback encoding |
| EC-2.9 | Ingestion | Low | Truncate to 1000 chars for LLM |
| EC-3.1 | Theme Engine | Medium | Merge extra themes |
| EC-3.2 | Theme Engine | High | Retry + keyword fallback |
| EC-3.3 | Theme Engine | Low | Warn, proceed with skewed data |
| EC-3.4 | Theme Engine | High | Exponential backoff, halt |
| EC-3.5 | Theme Engine | Medium | Chunk into batches of 50 |
| EC-3.6 | Theme Engine | Low | Other bucket, warn if >40% |
| EC-3.7 | Theme Engine | Medium | Adjust template dynamically |
| EC-4.1 | Pulse Generator | Medium | Truncate in priority order |
| EC-4.2 | Pulse Generator | Medium | Use available quotes, adjust template |
| EC-4.3 | Pulse Generator | High | Secondary PII check on quotes |
| EC-4.4 | Pulse Generator | Low | Show full date range in title |
| EC-4.5 | Pulse Generator | Medium | Retry with stricter prompt |
| EC-5.1 | MCP Layer | High | Auto-refresh, halt if fails |
| EC-5.2 | MCP Layer | High | Retry + local fallback |
| EC-5.3 | MCP Layer | Low | Append another section to master doc |
| EC-5.4 | MCP Layer | Low | Update existing draft |
| EC-5.5 | MCP Layer | Low | Accept plain/unstyled append |
| EC-5.6 | MCP Layer | Low | Fallback to plain text |
| EC-5.7 | MCP Layer | High | Halt with config error message |
| EC-5.8 | MCP Layer | High | Halt before MCP calls |
| EC-5.9 | MCP Layer | Medium | Partial publish log; retry draft |
| EC-6.1 | Pipeline | Medium | Checkpoint + resume |
| EC-6.2 | Pipeline | Critical | Sample fallback + watermark |
| EC-6.3 | Pipeline | Low | Idempotent updates |
| EC-6.4 | Pipeline | High | Fail fast on missing secrets |
| EC-6.5 | Pipeline | Low | Skip MCP, save locally |
| EC-7.1 | Security | Medium | Allowlist false positives |
| EC-7.2 | Security | High | Scrub all LLM output |
| EC-7.3 | Security | Critical | .gitignore + pre-commit hook |
