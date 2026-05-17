# Groww — Automated Weekly Product Review Pulse

An **agentic AI pipeline** that transforms raw Groww app reviews into a concise weekly pulse note — top themes, verbatim user quotes, and concrete product actions — ready for Google Docs and email distribution.

The pipeline is orchestrated by a **LangGraph `StateGraph`** with a self-correcting **Agentic Quality Loop**. It features a **FastAPI backend** for Render deployment and a **Next.js dashboard** for Vercel.

---

## What It Does

1.  **Scrapes** Groww reviews from Google Play Store and Apple App Store.
2.  **Cleans** data, strips PII, and filters by date and quality.
3.  **Classifies** reviews into 5 actionable themes (KYC, Payments, Onboarding, etc.) via LangChain.
4.  **Generates** a scannable weekly pulse note with prioritized product actions.
5.  **Audit Loop**: Automatically remediates reports that are too long or lack sufficient detail.
6.  **Publishes**: Appends to a Master Google Doc and creates a Gmail draft via MCP.
7.  **Visualizes**: A professional Next.js dashboard to trigger runs and view insights.

---

## Project Status

| Phase | Name | Status |
|---|---|---|
| **Phase 0** | Scaffold & Environment | ✅ Complete |
| **Phase 1** | Ingestion, Scraping & PII | ✅ Complete |
| **Phase 2** | LLM Theme Engine | ✅ Complete |
| **Phase 3** | Pulse Note Generation | ✅ Complete |
| **Phase 4** | MCP Server Integration | ✅ Complete |
| **Phase 5** | Agentic Quality Loop | ✅ Complete |
| **Phase 6** | End-to-End Pipeline & API | ✅ Complete |
| **Phase 7** | Polish & Deployment | ✅ Complete |
| **Phase 8** | Frontend Web Dashboard | ✅ Complete |

---

## Project Structure

```
Groww-Automated-Weekly-Product-Review-Pulse/
├── src/
│   ├── main.py                          # LangGraph pipeline orchestrator
│   ├── Phase1A-scraper/                 # App Store & Play Store scrapers
│   ├── Phase1-pii/                      # PII scrubbing & cleaning
│   ├── Phase2-themes/                   # LLM classification logic
│   ├── Phase3-generator/                # Pulse note generation
│   ├── Phase4-mcp/                      # Google Docs & Gmail clients
│   ├── Phase5-agenticQuality/           # Quality audit & remediation tools
│   └── phase6_api/                      # FastAPI wrapper (Render)
├── frontend/                            # Next.js Dashboard (Vercel)
├── data/                                # Local CSV storage (gitignored)
├── output/                              # Generated notes and audit logs
├── tests/                               # Unit & E2E tests
├── config/                              # themes.yaml & MCP configs
├── .github/workflows/                   # Weekly Cron Job (GHA)
└── doc/                                 # Architecture & Implementation plans
```

---

## Quick Start

### 1. Backend Setup (Render/Local)

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Set GROQ_API_KEY, MCP_SERVER_URL, etc.

# Run the API server
python src/scripts/run_api.py
```

### 2. Frontend Setup (Vercel/Local)

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000`. Ensure `NEXT_PUBLIC_BACKEND_URL` is set in `.env.local`.

---

## Deployment Strategy

### Backend (Render Free Tier)
Deployed as a **Web Service**.
- **Start Command**: `uvicorn src.phase6_api.app:app --host 0.0.0.0 --port $PORT`
- **Health Check**: `/health`
- **CORS**: Configured to allow Vercel origins.

### Frontend (Vercel)
Deployed as a **Next.js App**.
- **Trigger**: One-click "Generate Report" hits the Render `/run` endpoint.
- **Insights**: Real-time markdown preview of the latest generated pulse.

---

## Automated Execution

### GitHub Actions (Weekly Cron)
The pipeline runs every **Monday at 9:20 AM IST** via `.github/workflows/weekly_pulse.yml`. It scrapes fresh data and publishes to the master doc automatically.

### Local Scheduler
Simulate the cron job locally:
```bash
python src/scripts/local_scheduler.py --run-now
```

---

## Core Technologies

- **Orchestration**: LangGraph (Stateful Agentic Workflow)
- **LLM Framework**: LangChain (ChatGroq + Prompt Templates)
- **Model**: Llama-3.3-70b-versatile (via Groq)
- **Integration**: Model Context Protocol (MCP) for Google Ecosystem
- **Web**: FastAPI (Backend) & Next.js + Shadcn/UI (Frontend)

---

## License
MIT
