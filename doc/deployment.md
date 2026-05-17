# Deployment Plan: Render & Vercel

This document outlines the strategy for deploying the **Groww Weekly Product Review Pulse** in a decoupled architecture:
1. **Backend API**: Render (Free Tier)
2. **Frontend UI**: Vercel (Hobby Tier)

## 1. Strategy Overview

- **Backend (Render)**: Runs the FastAPI server which encapsulates the LangGraph orchestrator. Exposes endpoints to trigger the pipeline and fetch the latest pulse data.
- **Frontend (Vercel)**: Hosts the Next.js application, providing a beautiful, interactive dashboard to trigger the pipeline and visualize the generated pulse note and metrics.

> [!NOTE]
> Render Free Web Services spin down after 15 minutes of inactivity. The first API request from the Vercel frontend may take ~30-50 seconds if the backend is waking up.

---

## 2. Backend Deployment (Render Free Tier)

### 2.1 Infrastructure Requirements
| Component | Specification |
|---|---|
| **Service Type** | Web Service |
| **Instance Type** | Free (0.1 CPU, 512MB RAM) |
| **Runtime** | Python 3.11+ |
| **Root Directory**| `/` |

### 2.2 Environment Variables
Configure these in the Render Dashboard:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.11.0` |
| `GROQ_API_KEY` | *(Your Secret)* |
| `MCP_SERVER_URL` | *(Your Railway URL)* |
| `GOOGLE_MASTER_DOC_ID` | *(Your Doc ID)* |
| `PULSE_EMAIL_RECIPIENT` | *(Your Email)* |
| `PORT` | `10001` (Or Render default `10000`) |

### 2.3 Build & Start Commands
- **Build Command**: 
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**: 
  ```bash
  uvicorn src.phase6_api.app:app --host 0.0.0.0 --port $PORT
  ```

### 2.4 Managing Resource Constraints
To prevent `OOM` (Out of Memory) errors on Render's 512MB limit:
- We use CSV-on-disk processing to avoid large pandas dataframes in memory.
- `uvicorn` runs with a single worker by default.

---

## 3. Frontend Deployment (Vercel)

### 3.1 Infrastructure Requirements
| Component | Specification |
|---|---|
| **Platform** | Vercel (Hobby Tier) |
| **Framework Preset** | Next.js |
| **Root Directory**| `frontend` |
| **Node Version** | 18.x or 20.x |

### 3.2 Environment Variables
Configure these in the Vercel Project Settings:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | `https://your-render-app.onrender.com` |

### 3.3 Build & Start Commands
Vercel automatically detects Next.js, but verify the following if needed:
- **Build Command**: `npm run build`
- **Install Command**: `npm install`
- **Output Directory**: `.next`

---

## 4. GitHub Actions Automation

While the frontend allows manual triggering, the scheduled weekly run is still managed by GitHub Actions (`.github/workflows/weekly_pulse.yml`). 
- **Cron Job**: Runs every Monday at 09:20 AM IST.
- **Data Persistence**: After a successful run, the Action automatically commits the updated `output/notes/` directory back to the repository (Render ephemeral disks clear on restart, so this ensures Vercel and Render always have the latest static data via git sync).

---

## 5. Limitations & Considerations

- **CORS Setup**: Ensure the Render backend's `CORSMiddleware` in `src/phase6_api/app.py` allows origins from your Vercel domain.
- **Ephemeral Disk (Render)**: Any logs or output notes generated directly on Render will be deleted when the service restarts. That is why the GitHub Action pushes the generated artifacts back to the repository.
- **Timeout Limits**: Render's free tier HTTP connections timeout after 100 seconds. The frontend uses a background polling mechanism to avoid HTTP timeouts while the pipeline runs for ~2-3 minutes.
