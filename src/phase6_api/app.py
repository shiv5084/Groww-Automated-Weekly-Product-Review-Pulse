from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import os
import sys
from pathlib import Path
import logging

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.middleware.cors import CORSMiddleware
from src.main import run_pipeline_logic

app = FastAPI(
    title="Groww Weekly Pulse API",
    description="Render-compatible FastAPI wrapper for the Groww Product Review Pulse pipeline.",
    version="1.0.0"
)

# Enable CORS for Vercel deployment
frontend_url = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:3000"] if frontend_url != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("groww_pulse_api")

class PipelineRunResponse(BaseModel):
    message: str
    status: str
    run_id: Optional[str] = None

@app.get("/")
def read_root():
    return {
        "name": "Groww Weekly Pulse API",
        "endpoints": {
            "health": "/health",
            "run": "/run (POST)"
        },
        "documentation": "Deployed on Render Free Tier"
    }

@app.get("/health")
def health():
    """Health check for Render monitoring."""
    from datetime import datetime
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

@app.get("/latest-report")
def get_latest_report():
    """Fetch the latest pulse note and theme distribution."""
    notes_dir = PROJECT_ROOT / "output" / "notes"
    
    # Get latest pulse_*.md by filename sorting (lexicographical descending)
    md_files = sorted(notes_dir.glob("pulse_*.md"), reverse=True)
    pulse_md = ""
    if md_files:
        pulse_md = md_files[0].read_text(encoding="utf-8")
        
    # Get theme_groups.json
    themes_path = notes_dir / "theme_groups.json"
    themes_data = {}
    if themes_path.exists():
        import json
        themes_data = json.loads(themes_path.read_text(encoding="utf-8"))
        
    return {
        "pulse_md": pulse_md,
        "themes": themes_data,
        "last_updated": os.path.getmtime(md_files[0]) if md_files else None
    }


@app.post("/run", response_model=PipelineRunResponse)
async def trigger_pipeline(
    background_tasks: BackgroundTasks,
    weeks: int = Query(12, ge=1, le=52),
    dry_run: bool = False,
    scrape: bool = True,
    model: str = "llama-3.3-70b-versatile"
):
    """
    Trigger the end-to-end pipeline in the background.
    
    - **weeks**: Number of weeks of reviews to analyze (default 12)
    - **dry_run**: If true, skips publishing to Google Docs/Gmail
    - **scrape**: If true, fetches fresh reviews from stores
    - **model**: Groq model to use for LLM tasks
    """
    try:
        # We run in background because the pipeline takes 2-3 minutes, 
        # which would exceed HTTP timeout limits.
        background_tasks.add_task(
            run_pipeline_logic,
            weeks=weeks,
            dry_run=dry_run,
            scrape=scrape,
            model=model,
            verbose=True
        )
        return PipelineRunResponse(
            message="Pipeline triggered successfully. Results will be published to Google Docs.",
            status="accepted"
        )
    except Exception as e:
        logger.error(f"Failed to trigger pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))
