# Groww — Decision Log (decision.md)

> **Purpose:** Record all significant technical and business decisions with context, alternatives considered, and rationale.  
> **Format:** Newest decisions at the top.

---

## Decision Template

```
### DEC-XXX: <Title>
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Deciders:** <who made the decision>
- **Context:** <what prompted this decision>
- **Decision:** <what was decided>
- **Alternatives Considered:** <what else was evaluated>
- **Rationale:** <why this option was chosen>
- **Consequences:** <impact, trade-offs, follow-up actions>
```

---

## Accepted Decisions

### DEC-011: Google Docs — Append-Only Master Log (Not New Doc Per Run)

- **Date:** 2026-05-16
- **Status:** Accepted
- **Context:** Phase 4 can either create a new Google Doc each week/run or append each pulse to a single long-running document.
- **Decision:** Use an **append-only master log**: one pre-created Google Doc (`GOOGLE_MASTER_DOC_ID`). Each pipeline run appends a dated section (separator + pulse Markdown) at the end of the document.
- **Alternatives Considered:**
  - **New doc per week/run:** Easier to share per-week links but fragments history and complicates Drive search.
  - **Replace in-place section for same week:** Rejected for v1; re-runs append another section (see EC-5.3). Operators may manually remove duplicates if needed.
- **Rationale:** Single source of truth for weekly pulses; aligns with team review habits; avoids Drive file proliferation.
- **Consequences:** Master doc grows over time; need clear section headers per run; Gmail body should link to the master doc URL.

---

### DEC-012: Fixed Google Doc ID — Google Docs API Only (No Google Drive MCP)

- **Date:** 2026-05-16
- **Status:** Accepted
- **Context:** Community MCP packages such as `@modelcontextprotocol/server-gdrive` target Drive file creation, not append-to-existing Docs.
- **Decision:** Do **not** use Google Drive MCP or Drive “create file” flows. Publish only via **Google Docs API** `documents.batchUpdate` append operations against `GOOGLE_MASTER_DOC_ID` exposed through the project’s custom MCP server.
- **Alternatives Considered:**
  - **Drive MCP + create by title:** Wrong surface area; duplicates and title-based idempotency are fragile.
  - **Direct `google-api-python-client` in pipeline:** Rejected — still goes through custom MCP per DEC-001.
- **Rationale:** Docs-only scope matches the master-log model; fixed ID removes ambiguity about which document receives content.
- **Consequences:** Operators must create the master doc once and grant OAuth user edit access; invalid or missing doc ID fails fast (EC-5.8).

---

### DEC-013: External Deployed MCP Server (Not Stock npx MCP Packages)

- **Date:** 2026-05-16
- **Status:** Accepted
- **Context:** `config/mcp_config.json` initially referenced `@modelcontextprotocol/server-gdrive` and `server-gmail`, which do not match DEC-011/012. A separate repo ([shiv5084/MCP-SERVER](https://github.com/shiv5084/MCP-SERVER)) implements the tools and is deployed on Railway.
- **Decision:** Use the **deployed HTTP MCP server** at `MCP_SERVER_URL` (default `https://mcp-server-production-5084.up.railway.app`). This pipeline calls:
  - `POST /append_to_doc` — `{ doc_id, content }` (see `docs_tool.py`)
  - `POST /create_email_draft` — `{ to, subject, body }` (see `gmail_tool.py`)
  OAuth credentials live on Railway (`GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`, `AUTO_APPROVE=true`). **No MCP server code in this repo.**
- **Alternatives Considered:**
  - **Stock Google Drive + Gmail MCP servers:** Wrong tools (Drive vs Docs).
  - **In-repo `mcp-servers/groww-pulse-mcp/`:** Duplicates the external server; rejected.
  - **Direct API calls from Python without MCP:** Violates MCP-first policy in DEC-001.
- **Rationale:** Reuse existing deployed server; pipeline only needs HTTP clients in `src/Phase4-mcp/`.
- **Consequences:** Phase 4 depends on Railway uptime and server-side token refresh; `httpx` client with retries in this project.

---

### DEC-014: Publish Correlation — Capture Doc ID, URL, and Draft ID

- **Date:** 2026-05-16
- **Status:** Accepted
- **Context:** Operators need to tie a pipeline run to the exact Google Doc section and Gmail draft for debugging and stakeholder follow-up.
- **Decision:** After each successful publish, persist `output/logs/publish_YYYY-MM-DD.json` containing at minimum: `run_timestamp`, `document_id`, `document_url`, `draft_id`, `week_label`, and paths to local pulse artifacts. Log the same fields at INFO. Include `document_url` in the Gmail draft body.
- **Alternatives Considered:**
  - **URL only in logs:** Insufficient for API-level debugging.
  - **No local artifact:** Harder to audit without re-querying Google APIs.
- **Rationale:** Correlates Phase 3 output, Phase 4 MCP results, and human review in Gmail.
- **Consequences:** `output/logs/` must be gitignored; publish node and `run_phase4.py` write this file.

---

### DEC-001: Use MCP Servers for Google Workspace Integration (Not Direct APIs)

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** The pipeline needs to create Google Docs and Gmail drafts. Two approaches exist: (1) Direct Google API calls via `google-api-python-client`, or (2) MCP (Model Context Protocol) servers that wrap these APIs.
- **Decision:** Use MCP servers for all Google Workspace interactions.
- **Alternatives Considered:**
  - **Direct Google APIs:** More documentation, wider community support, but tightly coupled and requires managing API clients directly.
  - **MCP servers:** Standardized tool protocol, decoupled from API specifics, aligns with AI agent architecture patterns.
- **Rationale:** MCP provides a standardized integration layer that decouples the pipeline from Google API specifics. This makes it easier to swap providers, test with mocks, and aligns with the AI agent paradigm. The problem statement explicitly requires MCP.
- **Consequences:** Depends on MCP SDK maturity; need to handle MCP server lifecycle; adds a layer of abstraction.

---

### DEC-002: Playwright for Automated Review Scraping (Not Manual CSV Exports)

- **Date:** 2026-05-13
- **Status:** Superseded by DEC-010
- **Context:** The pipeline needs Groww app reviews as input. The original approach assumed manually exported CSVs from App Store Connect / Google Play Console (both require login). We need a fully automated, login-free approach.
- **Decision:** Use Playwright to scrape reviews from the **public-facing** Google Play Store and Apple App Store pages. Scraped data is saved as CSVs in `data/raw/`. No manually exported CSVs.
- **Alternatives Considered:**
  - **Manual CSV exports:** Requires logging into App Store Connect / Google Play Console — violates "no scraping behind logins" rule. Not automatable.
  - **google-play-scraper / app-store-scraper (npm packages):** Lightweight but limited control, no browser rendering, may miss dynamically loaded reviews.
  - **Official APIs (App Store Connect API, Google Play Developer API):** Require authentication and developer account access — violates public-data-only constraint.
  - **Publicly available datasets (Kaggle, etc.):** Static and stale; not suitable for weekly fresh reviews.
- **Rationale:** Playwright provides full browser automation with headless Chromium, enabling scraping of dynamically-loaded review pages. It handles JavaScript-rendered content, supports anti-bot mitigations (random delays, stealth), and works with GitHub Actions for CI/CD. Only public-facing pages are accessed — zero authentication required.
- **Consequences:** Depends on Play Store / App Store DOM stability (selectors may break). Adds `playwright` as a dependency (~50MB browser binary). Requires `playwright install chromium` during setup. Anti-bot measures may occasionally block requests — mitigated with delays and rotating User-Agents.

---

### DEC-003: Python as Primary Language

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** Need to choose a language for the pipeline that supports CSV processing, LLM integration, and MCP.
- **Decision:** Python 3.11+
- **Alternatives Considered:**
  - **Node.js/TypeScript:** Good MCP ecosystem but weaker data processing libraries.
  - **Go:** Fast but lacks mature LLM client libraries.
- **Rationale:** Python has the richest ecosystem for data processing (pandas), LLM integration (groq/openai SDKs), and a growing MCP SDK. The team has strongest expertise in Python.
- **Consequences:** Must manage virtual environments; performance is adequate for this workload.

---

### DEC-004: Maximum 5 Themes Constraint

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** LLM theme grouping could produce any number of clusters. Need to balance granularity with scannability.
- **Decision:** Hard cap at 5 themes; display top 3 in the pulse note.
- **Alternatives Considered:**
  - **Dynamic clustering (unlimited):** More granular but overwhelming for a weekly pulse.
  - **Fixed 3 themes:** Too restrictive, may miss important signals.
- **Rationale:** 5 themes provides enough coverage for Groww's review landscape (Onboarding, KYC, Payments, Statements, Withdrawals) while keeping the output actionable. Top 3 in the note keeps it scannable.
- **Consequences:** Some niche issues may be grouped into broader themes; review theme definitions periodically.

---

### DEC-005: PII Scrubbing Before LLM Processing

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** Reviews may contain user emails, phone numbers, or usernames. LLM providers process data on their servers.
- **Decision:** Strip all PII at the ingestion stage, before any data reaches the LLM.
- **Alternatives Considered:**
  - **PII scrub after LLM:** Simpler pipeline but sends PII to external LLM servers — unacceptable.
  - **No scrubbing (assume clean data):** Risky; reviews frequently contain PII.
- **Rationale:** Privacy by design. Zero PII should reach external services. Regex-based scrubbing is fast and handles common patterns; optional NER can enhance recall.
- **Consequences:** Possible false positives (over-redaction); need to tune patterns. Some context may be lost in redacted reviews.

---

### DEC-006: Gmail Drafts — No Auto-Send

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** The pipeline creates a Gmail message with the pulse note. Should it send automatically or create a draft?
- **Decision:** Create a draft only; require human review before sending.
- **Alternatives Considered:**
  - **Auto-send:** Fully automated but risky — no human review of LLM-generated content.
  - **Slack/Teams notification:** Different channel, not requested.
- **Rationale:** LLM-generated content should be reviewed by a human before distribution to stakeholders. A draft preserves full automation while adding a safety check. The problem statement explicitly requires draft-only.
- **Consequences:** One manual step (reviewing and clicking send); acceptable trade-off for quality control.

---

### DEC-007: Groq as Primary LLM Provider

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** Need an LLM for theme classification and note generation. Multiple providers available.
- **Decision:** Use Groq as the primary LLM provider with OpenAI as a fallback option.
- **Alternatives Considered:**
  - **OpenAI (GPT-4o):** Most capable but more expensive, rate limits on free tier.
  - **Anthropic (Claude):** Strong but no free tier.
  - **Local models (Ollama):** Free but requires GPU; unreliable for structured output.
- **Rationale:** Groq offers fast inference with a generous free tier, sufficient for weekly batch processing. The team has prior experience (from Zomato project). OpenAI can be swapped in via env config if needed.
- **Consequences:** Dependent on Groq's availability; structured output may need prompt engineering.

---

### DEC-008: Pulse Note ≤250 Words Limit

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** The weekly note must be scannable by busy stakeholders. Need to set a word limit.
- **Decision:** Hard limit of 250 words for the pulse note body.
- **Alternatives Considered:**
  - **500 words:** More detail but too long for a "pulse."
  - **No limit:** Risk of verbose, unread reports.
  - **100 words:** Too restrictive for 3 themes + 3 quotes + 3 actions.
- **Rationale:** 250 words is approximately 1 minute of reading — ideal for a weekly pulse consumed in meetings or email. Enforced programmatically with trimming if exceeded.
- **Consequences:** Some nuance may be lost; the note is a trigger for deeper investigation, not a full report.

---

### DEC-009: OAuth 2.0 via MCP Server Configuration

- **Date:** 2026-05-13
- **Status:** Accepted
- **Context:** Google Workspace APIs require authentication. Credentials must be managed securely.
- **Decision:** Use OAuth 2.0 configured through the MCP server, with tokens stored in environment variables — never hardcoded or committed to git.
- **Alternatives Considered:**
  - **Service account:** Simpler but doesn't work for personal Gmail drafts.
  - **API key:** Insufficient permissions for Docs/Gmail.
  - **Hardcoded credentials:** Never acceptable.
- **Rationale:** OAuth 2.0 is the standard for user-context Google API access. MCP servers handle the token lifecycle. Environment variables keep secrets out of the codebase.
- **Consequences:** Initial OAuth setup requires browser-based consent flow; tokens need periodic refresh.

---

### DEC-010: Shift from Playwright to Public APIs for Scraping

- **Date:** 2026-05-14
- **Status:** Accepted
- **Context:** Playwright scraping proved brittle against Apple's anti-bot measures and DOM structure changes.
- **Decision:** Use google-play-scraper and Apple's official iTunes RSS Feed API via requests.
- **Alternatives Considered:** Updating Playwright CSS selectors, but it remains brittle.
- **Rationale:** API-based ingestion is 100x faster, strictly structured, entirely circumvents DOM/bot issues, and requires no browser binaries.
- **Consequences:** Eliminates headless browser overhead and makes the scraper extremely reliable.

---

## Proposed Decisions (Pending)

_No pending decisions at this time._

---

## Superseded Decisions

_No superseded decisions at this time._
