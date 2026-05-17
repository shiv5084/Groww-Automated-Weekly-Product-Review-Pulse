# Groww — Evaluation Criteria (eval.md)

> **Version:** 1.0 | **Date:** 2026-05-13

---

## Phase 0 — Project Scaffold & Environment Setup

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T0.1 | Virtual env creation | Manual | `python -m venv venv` succeeds on 3.11+ |
| T0.2 | Dependency install | Manual | `pip install -r requirements.txt` — zero errors |
| T0.3 | Import smoke test | Script | `python -c "import src"` — no ImportError |
| T0.4 | Directory structure | Script | All dirs from architecture.md exist |
| T0.5 | `.env.example` | Manual | Contains `LLM_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| T0.6 | `.gitignore` | Manual | Covers `.env`, `venv/`, `__pycache__/`, `data/raw/`, `credentials/` |
| T0.7 | Sample CSV | Script | Loads with pandas; has `rating`, `title`, `review_text`, `date` |
| T0.8 | MCP config | Manual | `mcp_config.json` is valid JSON |
| T0.9 | Themes config | Manual | `themes.yaml` loads, has 5 themes |
| T0.10 | pytest runs | Manual | `pytest` executes without crash |

### Exit Criteria
1. Fresh clone + `pip install` works without errors
2. All directories exist
3. `python -c "from src import main"` succeeds
4. Sample CSV has correct schema
5. No secrets committed to git

---

## Phase 1A — Review Scraping

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T1A.1 | Play Store API connection | Integration | Connects to Google Play scraper without error |
| T1A.2 | App Store RSS Feed connection | Integration | Connects to iTunes RSS Feed API (HTTP 200) |
| T1A.3 | Data Schema Verification | Integration | Parsed JSON matches expected review format |
| T1A.4 | Play Store review extraction | Integration | Extracts ≥10 reviews with rating, title, text, date |
| T1A.5 | App Store review extraction | Integration | Extracts ≥10 reviews with rating, title, text, date |
| T1A.6 | Review data structure | Unit | Each review has: rating (1–5), title, review_text, date, source |
| T1A.7 | CSV output — Play Store | Integration | `data/raw/playstore_reviews.csv` created with correct schema |
| T1A.8 | CSV output — App Store | Integration | `data/raw/appstore_reviews.csv` created with correct schema |
| T1A.9 | Deduplication | Unit | Duplicate reviews removed across runs |
| T1A.10 | Anti-bot delays | Unit | Random delay ≥1s between scroll actions |
| T1A.11 | Error — network timeout | Unit | Graceful failure with clear error message |
| T1A.12 | Error — empty results | Unit | Returns empty DataFrame, no crash |
| T1A.13 | No login required | Manual | Scraper never navigates to login pages |

### Performance Metrics

| Metric | Target |
|---|---|
| Play Store scrape (500 reviews) | < 120s |
| App Store scrape (500 reviews) | < 120s |
| Total reviews scraped | ≥ 200 (combined) |

### Exit Criteria
1. Both scrapers produce valid CSVs with correct schema
2. Combined output has ≥200 reviews from public pages
3. No login-gated pages are accessed
4. Deduplication works across multiple runs
5. Scraper handles network failures gracefully

---

## Phase 1 — Data Ingestion & PII Scrubbing

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T1.1 | CSV load — happy path | Unit | Returns DataFrame with ≥20 rows |
| T1.2 | CSV load — missing file | Unit | Raises `FileNotFoundError` |
| T1.3 | Schema validation — valid | Unit | Returns `True` for correct columns |
| T1.4 | Schema validation — missing col | Unit | Raises error naming the missing column |
| T1.5 | Date filter — 12 weeks | Unit | Only returns reviews within range |
| T1.6 | Date filter — empty result | Unit | Returns empty DataFrame, no crash |
| T1.7 | PII — email redaction | Unit | `user@gmail.com` → `[EMAIL_REDACTED]` |
| T1.8 | PII — phone redaction | Unit | `+91 98765 43210` → `[PHONE_REDACTED]` |
| T1.9 | PII — username redaction | Unit | `@user123` → `[USER_REDACTED]` |
| T1.10 | PII — no false positives | Unit | `"rated 5 stars"` unchanged |
| T1.11 | PII — multiple patterns | Unit | Text with email + phone — both redacted |
| T1.12 | Scrub report | Unit | Correct counts per pattern type |

### Performance Metrics

| Metric | Target |
|---|---|
| CSV load (1000 rows) | < 2s |
| PII scrub (1000 rows) | < 5s |
| PII recall | ≥ 95% |
| PII precision | ≥ 98% |

### Exit Criteria
1. All unit tests pass
2. PII recall ≥ 95% on planted PII dataset
3. Zero false positives on clean 50-row dataset
4. Pipeline handles empty CSV / malformed dates without crash

---

## Phase 2 — LLM Theme Grouping Engine

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T2.1 | Prompt generation | Unit | Includes all reviews, requests ≤5 themes |
| T2.2 | Response parsing — valid JSON | Unit | Parses into theme dict |
| T2.3 | Response parsing — malformed | Unit | Fallback parsing, no crash |
| T2.4 | Theme count ≤ 5 | Unit | Never more than 5 themes |
| T2.5 | Stats — count sums to total | Unit | Per-theme counts sum correctly |
| T2.6 | Stats — avg rating 1.0–5.0 | Unit | Valid range |
| T2.7 | Retry on rate limit | Unit | 3 retries with backoff |
| T2.8 | Retry exhaustion | Unit | Clear error after 3 failures |
| T2.9 | E2E — data to themes | Integration | Cleaned DataFrame → themed output |

### Performance Metrics

| Metric | Target |
|---|---|
| LLM call latency | < 10s per batch |
| Theme accuracy | ≥ 80% (manual spot-check of 20 reviews) |

### Exit Criteria
1. All unit tests pass
2. Output contains 3–5 themes
3. Per-theme stats are mathematically correct
4. LLM failures trigger retries with clear errors
5. Manual spot-check shows ≥ 80% theme accuracy

---

## Phase 3 — Pulse Note Generation

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T3.1 | Note — happy path | Unit | Contains themes + quotes + actions |
| T3.2 | Word count ≤ 250 | Unit | Every note under limit |
| T3.3 | Top 3 themes by volume | Unit | Correct selection |
| T3.4 | Exactly 3 quotes | Unit | PII-free verbatim quotes |
| T3.5 | Exactly 3 actions | Unit | Concrete suggestions |
| T3.6 | Docs format | Unit | Has Markdown headings + bullets |
| T3.7 | Email format | Unit | Plain text + HTML variants |
| T3.8 | Title format | Unit | `Groww Weekly Pulse — Week of <date>` |
| T3.9 | Empty themes | Unit | Graceful output if < 3 themes |

### Performance Metrics

| Metric | Target |
|---|---|
| Generation time | < 15s |
| Word count compliance | 100% |

### Exit Criteria
1. All unit tests pass
2. Every note ≤ 250 words
3. 3 themes + 3 quotes + 3 actions present
4. Title includes correct date range
5. Both Docs and email formats render

---

## Phase 4 — MCP Server Integration (Google Docs + Gmail)

> Design: append-only master doc (`GOOGLE_MASTER_DOC_ID`), custom MCP server, draft-only Gmail. See [decision.md — DEC-011–014](decision.md).

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T4.1 | MCP config loads | Unit | Valid JSON; points at custom `groww-pulse-mcp` server |
| T4.2 | OAuth token flow | Integration | Token obtained/refreshed for Docs + Gmail scopes |
| T4.3 | Master doc append | Integration | New section appended to `GOOGLE_MASTER_DOC_ID` (not a new file) |
| T4.4 | Section content | Integration | Dated header + pulse Markdown present in master doc |
| T4.5 | IDs returned | Integration | Valid `document_id` and `document_url` logged and in publish JSON |
| T4.6 | Gmail draft created | Integration | Appears in Drafts folder |
| T4.7 | Draft subject format | Integration | `[Weekly Pulse] Groww App Reviews — Week of <date>` |
| T4.8 | Draft NOT sent | Integration | Email stays in Drafts; no `users.messages.send` |
| T4.9 | Draft body has doc link | Integration | Body includes `document_url` from append result |
| T4.10 | Publish correlation file | Integration | `output/logs/publish_YYYY-MM-DD.json` has id/url/draft_id |
| T4.11 | MCP failure handling | Unit | Clear error on timeout |
| T4.12 | Fallback to local | Integration | Phase 3 Markdown retained on MCP fail |
| T4.13 | Invalid doc ID | Unit | `ConfigurationError` before MCP calls (EC-5.8) |

### Performance Metrics

| Metric | Target |
|---|---|
| MCP connection | < 5s |
| Doc append | < 10s |
| Draft creation | < 5s |

### Exit Criteria
1. Pulse section appended to configured master Google Doc (no Drive create, no new doc per run)
2. `document_id` and `document_url` captured in logs and `publish_YYYY-MM-DD.json`
3. Gmail draft created with doc link, **NOT** auto-sent
4. MCP failures retain local Markdown; Phase 4 can be re-run standalone
5. OAuth tokens refresh automatically

---

## Phase 5 — End-to-End Pipeline, Polish & Deployment

### Test Checklist

| # | Test | Type | Criteria |
|---|---|---|---|
| T5.1 | Full pipeline | E2E | `python src/main.py --csv sample.csv` completes |
| T5.2 | CLI help | Unit | `--help` shows all options |
| T5.3 | Dry-run mode | E2E | Skips MCP, generates note locally |
| T5.4 | Custom week range | E2E | `--weeks 8` filters correctly |
| T5.5 | Logging — console | E2E | Timestamped stage logs |
| T5.6 | Logging — file | E2E | Logs in `output/logs/` |
| T5.7 | Error — missing CSV | E2E | Clear error, non-zero exit |
| T5.8 | Error — MCP failure | E2E | Falls back, logs warning |
| T5.9 | GitHub Actions syntax | CI | Workflow YAML is valid |
| T5.10 | README complete | Manual | Setup, usage, theme legend |
| T5.11 | Code linting | CI | `ruff check src/` — zero errors |
| T5.12 | Test coverage | CI | ≥ 80% line coverage |

### Performance Metrics

| Metric | Target |
|---|---|
| Full pipeline time | < 60s |
| Unit test suite | < 30s |
| Test coverage | ≥ 80% |

### Exit Criteria
1. Full pipeline appends to master Google Doc + creates Gmail draft
2. `--dry-run` works without Google credentials
3. All unit tests pass with ≥ 80% coverage
4. GitHub Actions workflow is valid
5. README is complete
6. Code passes linting with zero errors

---

## Overall Deliverables Checklist

| # | Deliverable | Location | Status |
|---|---|---|---|
| D1 | Working prototype | `src/main.py` | ⬜ |
| D2 | Weekly pulse note | Master Google Doc section + `document_url` | ⬜ |
| D3 | Gmail draft evidence | `output/` | ⬜ |
| D4 | Sample reviews CSV | `data/sample/sample_reviews.csv` | ⬜ |
| D5 | Complete README | `README.md` | ⬜ |
