# Groww — Automated Weekly Product Review Pulse

## Overview

This project automates the process of turning recent Groww App Store and Play Store reviews into a concise, actionable one-page weekly pulse. The pipeline ingests raw review data, groups it into themes using an LLM, generates a structured weekly note, and delivers it as a Google Doc — with a draft Gmail message ready to send to yourself or your team alias.

---

## Who This Helps

| Audience | Value |
|---|---|
| **Product / Growth Teams** | Understand what to fix next, backed by real user language |
| **Support Teams** | Know what users are saying and what's being acknowledged |
| **Leadership** | Quick weekly health pulse without reading hundreds of reviews |

---

## What You Must Build

### 1. Review Ingestion
- Import reviews from the **last 8–12 weeks** containing: rating (1–5), title, review text, and date
- Source: public review exports only (e.g., manually exported CSVs from App Store Connect / Google Play Console, or publicly available datasets)
- **No scraping behind logins**
- Strip all PII before processing (no usernames, emails, device IDs, or any identifiable information)

### 2. Theme Grouping (LLM-Powered)
- Use an LLM to cluster reviews into a **maximum of 5 themes**
- Suggested themes for Groww: `Onboarding`, `KYC`, `Payments`, `Statements`, `Withdrawals`
- Each theme should include a representative count and average rating

### 3. Weekly Pulse Note Generation
- Generate a **one-page weekly note** (≤250 words, scannable format) containing:
  - **Top 3 themes** — name, volume, sentiment signal
  - **3 real user quotes** — verbatim review excerpts (PII-free)
  - **3 action ideas** — concrete, prioritized suggestions for the product team

### 4. Google Docs Integration (via MCP Server)
- Use the **Google Docs MCP server** to create the weekly pulse note as a new Google Doc
- The doc should be formatted cleanly with headings, bullet points, and the date range in the title (e.g., `Groww Weekly Pulse — Week of May 12, 2026`)
- No manual copy-paste; the MCP server handles doc creation programmatically

### 5. Gmail Draft Integration (via MCP Server)
- Use the **Gmail MCP server** to create a draft email containing the weekly note
- Draft should be addressed to yourself or a team alias
- Subject line format: `[Weekly Pulse] Groww App Reviews — Week of <date>`
- Body should embed the pulse note content (plain text or HTML)
- The draft is created but **not auto-sent** — a human reviews and sends it

---

## Key Constraints

- **Public data only** — use exported CSVs or publicly available review datasets; no authenticated scraping
- **Max 5 themes** — keep grouping tight and actionable
- **≤250 words** — the pulse note must be scannable, not a report
- **Zero PII** — no usernames, emails, device IDs, or any identifiable strings in any artifact
- **MCP servers for Google integrations** — do NOT use direct Google API calls; use the Google Docs MCP server and Gmail MCP server for all Google Workspace interactions

---

## MCP Server Requirements

### Google Docs MCP Server
- Tool used: create/write a new Google Doc with formatted content
- Auth: OAuth 2.0 via MCP server configuration (not hardcoded credentials)

### Gmail MCP Server
- Tool used: create a Gmail draft (not send)
- Auth: OAuth 2.0 via MCP server configuration (not hardcoded credentials)

---

## Deliverables

1. **Working prototype** — runnable script or notebook that executes the full pipeline end-to-end
2. **Latest one-page weekly note** — as a Google Doc (link) and/or exported PDF/MD
3. **Gmail draft screenshot or text** — showing the draft created in your inbox
4. **Reviews CSV** — the sample/redacted dataset used as input
5. **README** covering:
   - How to re-run for a new week
   - MCP server setup instructions (Google Docs + Gmail)
   - Theme legend explaining the 5 themes

---

## Skills Being Tested

**W2 — LLMs & Prompting**
- Summarization of noisy review data
- Representative quote selection
- Tone control for a professional weekly note

**W3 — AI Workflow Automations**
- End-to-end pipeline: Import → Scrub → Group → Generate Note → Publish to Google Docs → Draft Gmail
- MCP server integration for Google Workspace (Docs + Gmail)
