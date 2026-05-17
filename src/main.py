"""
main.py — LangGraph pipeline orchestrator (Step 2 of agentic migration).

Replaces the Phase 0 stub with a fully wired LangGraph StateGraph that
orchestrates all pipeline phases end-to-end.

Architecture (from agenticUseCase.md — Step 2):
    PipelineState (TypedDict) carries paths + metadata between nodes.
    DataFrames are NOT passed in-memory — CSV-on-disk pattern is kept
    for resumability (Q2 decision).

Graph nodes:
    scrape           → Phase 1A  (ReviewScraperOrchestrator)
    ingest           → Phase 1   (ReviewIngestion + DateFilter)
    pii_scrub        → Phase 1   (PIIScrubber)
    classify_themes  → Phase 2   (ThemeGrouper — LangChain chain)
    generate_pulse   → Phase 3   (PulseNoteGenerator — LangChain chain)
    quality_agent    → Phase 5   (self-correcting quality gate)
    tools            → Phase 5   (ToolNode — trim / regen actions / reclassify)
    publish          → Phase 4   (PulsePublisher → Custom Google MCP HTTP API)

Conditional edges:
    entry  → "scrape"  if --scrape flag is set, else "ingest"
    after generate_pulse → quality_agent (always)
    quality_agent ⇄ tools → publish (or END on --dry-run)

Usage (run from project root with langgraph_env):
    langgraph_env\\Scripts\\python.exe src/main.py --dry-run --weeks 12
    langgraph_env\\Scripts\\python.exe src/main.py --scrape --weeks 12
    langgraph_env\\Scripts\\python.exe src/main.py --csv data/raw --weeks 12
    langgraph_env\\Scripts\\python.exe src/main.py --weeks 12
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util as _ilu
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages

# ---------------------------------------------------------------------------
# Project root — add to sys.path so all phase modules are importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("groww_pulse.pipeline")

# ---------------------------------------------------------------------------
# Dynamic module loader (handles hyphenated folder names)
# ---------------------------------------------------------------------------

def _load_module(module_name: str, file_path: Path, package_name: Optional[str] = None):
    """Load a module from a file path, registering it in sys.modules."""
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _register_package(pkg_name: str, pkg_dir: Path) -> None:
    """Register a fake package so relative imports inside modules resolve."""
    pkg = type(sys)("pkg_name")
    pkg.__path__ = [str(pkg_dir)]
    sys.modules[pkg_name] = pkg


# ---------------------------------------------------------------------------
# Phase module directories
# ---------------------------------------------------------------------------
SCRAPER_DIR   = PROJECT_ROOT / "src" / "Phase1A-scraper"
INGESTION_DIR = PROJECT_ROOT / "src" / "Phase1-ingestion"
PII_DIR       = PROJECT_ROOT / "src" / "Phase1-pii"
THEMES_DIR    = PROJECT_ROOT / "src" / "Phase2-themes"
GEN_DIR       = PROJECT_ROOT / "src" / "Phase3-generator"
MCP_DIR       = PROJECT_ROOT / "src" / "Phase4-mcp"
QUALITY_DIR   = PROJECT_ROOT / "src" / "Phase5-agenticQuality"

# ---------------------------------------------------------------------------
# PipelineState — TypedDict (Q2: CSV-on-disk, no DataFrames in state)
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    # ── Config (set once from CLI args) ──────────────────────────────────
    weeks:       int
    dry_run:     bool
    do_scrape:   bool          # True when --scrape flag is set
    csv_dir:     Optional[str] # path to pre-scraped CSV dir (--csv flag)
    model:       Optional[str] # LLM model override
    batch_size:  int           # Phase 2 batch size

    # ── File paths written by each node (CSV-on-disk pattern) ────────────
    raw_csv:     Optional[str]  # combined_reviews.csv written by scrape node
    cleaned_csv: Optional[str]  # cleaned_reviews.csv written by pii_scrub node
    themes_json: Optional[str]  # theme_groups.json written by classify node
    pulse_md:    Optional[str]  # pulse_YYYY-MM-DD.md written by generate node
    pulse_txt:   Optional[str]  # pulse_YYYY-MM-DD.txt
    pulse_html:  Optional[str]  # pulse_YYYY-MM-DD.html

    # ── Publish outputs ───────────────────────────────────────────────────
    doc_id:      Optional[str]  # Master Google Doc ID (Phase 4)
    doc_url:     Optional[str]  # Master Google Doc URL (Phase 4)
    draft_id:    Optional[str]  # Gmail draft ID (Phase 4)
    publish_log: Optional[str]  # output/logs/publish_YYYY-MM-DD.json

    # ── Phase 5 — quality loop ────────────────────────────────────────────
    messages:              Annotated[list, add_messages]
    pulse_note_data:       Optional[dict]
    quality_status:        Optional[str]
    quality_passed:        Optional[bool]
    quality_iterations:    int
    max_quality_iterations:  int
    quality_word_limit:    int
    quality_last_failure:  Optional[str]
    quality_remediation:   list[str]
    quality_log:           Optional[str]
    post_tool_route:       Optional[str]
    skip_quality:          bool
    project_root:          Optional[str]
    reclassify_hint:       Optional[str]

    # ── Error tracking ────────────────────────────────────────────────────
    errors:      list[str]


# ===========================================================================
# NODE IMPLEMENTATIONS
# ===========================================================================

# ---------------------------------------------------------------------------
# Node 1 — scrape
# ---------------------------------------------------------------------------

def scrape_node(state: PipelineState) -> PipelineState:
    """
    Phase 1A — Scrape reviews from Play Store + App Store.
    Writes combined_reviews.csv to data/raw/.
    Skipped when --scrape is not set (entry point routes around it).
    """
    logger.info("[scrape] Starting review scraping …")

    _register_package("Phase1A_scraper", SCRAPER_DIR)
    _load_module("Phase1A_scraper.playstore_scraper", SCRAPER_DIR / "playstore_scraper.py", "Phase1A_scraper")
    _load_module("Phase1A_scraper.appstore_scraper",  SCRAPER_DIR / "appstore_scraper.py",  "Phase1A_scraper")
    orch_mod = _load_module("Phase1A_scraper.orchestrator", SCRAPER_DIR / "orchestrator.py", "Phase1A_scraper")

    ReviewScraperOrchestrator = orch_mod.ReviewScraperOrchestrator

    output_dir = PROJECT_ROOT / "data" / "raw"
    orchestrator = ReviewScraperOrchestrator(
        max_reviews_per_store=500,
        output_dir=str(output_dir),
    )

    combined_df = asyncio.run(orchestrator.scrape_all(save_individual=True))
    orchestrator.save_combined(combined_df)

    combined_csv = str(output_dir / "combined_reviews.csv")
    logger.info("[scrape] Done — %d reviews → %s", len(combined_df), combined_csv)

    return {**state, "raw_csv": combined_csv}


# ---------------------------------------------------------------------------
# Node 2 — ingest
# ---------------------------------------------------------------------------

def ingest_node(state: PipelineState) -> PipelineState:
    """
    Phase 1 — Load CSV, validate schema, filter by date range.
    Reads from raw_csv (if set by scrape node) or csv_dir (--csv flag)
    or the default data/raw/combined_reviews.csv.
    Writes nothing — passes the validated path forward for pii_scrub.
    """
    logger.info("[ingest] Starting data ingestion …")

    _register_package("Phase1_ingestion", INGESTION_DIR)
    csv_mod  = _load_module("Phase1_ingestion.csv_loader",  INGESTION_DIR / "csv_loader.py",  "Phase1_ingestion")
    date_mod = _load_module("Phase1_ingestion.date_filter", INGESTION_DIR / "date_filter.py", "Phase1_ingestion")

    ReviewIngestion = csv_mod.ReviewIngestion
    DateFilter      = date_mod.DateFilter

    # Resolve input CSV path
    if state.get("raw_csv"):
        input_path = state["raw_csv"]
    elif state.get("csv_dir"):
        input_path = str(Path(state["csv_dir"]) / "combined_reviews.csv")
    else:
        input_path = str(PROJECT_ROOT / "data" / "raw" / "combined_reviews.csv")

    ingestion = ReviewIngestion()
    df = ingestion.load_csv(input_path)
    ingestion.validate_schema(df)
    df = ingestion.clean_ratings(df)

    d_filter = DateFilter(weeks=state["weeks"])
    df = d_filter.parse_dates(df)
    df = d_filter.filter_by_date_range(df)

    # -----------------------------------------------------------------------
    # Cleanup data/cleaned (User requirement: delete old cleaned data first)
    # -----------------------------------------------------------------------
    cleaned_dir = PROJECT_ROOT / "data" / "cleaned"
    if cleaned_dir.exists():
        for item in cleaned_dir.iterdir():
            if item.is_file() and item.name != ".gitkeep":
                try:
                    item.unlink()
                except Exception as e:
                    logger.warning("[ingest] Failed to delete %s: %s", item, e)

    # Save the ingested (but not yet PII-scrubbed) CSV to a temp location
    ingested_path = cleaned_dir / "_ingested_reviews.csv"
    ingested_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ingested_path, index=False, encoding="utf-8")

    logger.info("[ingest] Done — %d reviews after date filter → %s", len(df), ingested_path)
    return {**state, "raw_csv": str(ingested_path)}


# ---------------------------------------------------------------------------
# Node 3 — pii_scrub
# ---------------------------------------------------------------------------

def pii_scrub_node(state: PipelineState) -> PipelineState:
    """
    Phase 1 — PII scrubbing + short-review filtering.
    Reads the ingested CSV, writes cleaned_reviews.csv.
    """
    logger.info("[pii_scrub] Starting PII scrubbing …")

    _register_package("Phase1_pii", PII_DIR)
    _load_module("Phase1_pii.patterns", PII_DIR / "patterns.py", "Phase1_pii")
    scrub_mod = _load_module("Phase1_pii.scrubber", PII_DIR / "scrubber.py", "Phase1_pii")

    PIIScrubber = scrub_mod.PIIScrubber

    import pandas as pd
    input_path = state.get("raw_csv") or str(PROJECT_ROOT / "data" / "cleaned" / "_ingested_reviews.csv")
    df = pd.read_csv(input_path, encoding="utf-8")

    scrubber = PIIScrubber()
    df_clean = scrubber.scrub_dataframe(df)

    cleaned_path = PROJECT_ROOT / "data" / "cleaned" / "cleaned_reviews.csv"
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(cleaned_path, index=False, encoding="utf-8")

    report = scrubber.get_scrub_report()
    logger.info(
        "[pii_scrub] Done — %d reviews → %s | short_dropped=%d pii_dropped=%d",
        len(df_clean), cleaned_path,
        report["short_reviews_dropped"],
        report["fully_redacted_reviews_dropped"],
    )

    # Clean up intermediate temporary file
    try:
        Path(input_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning("[pii_scrub] Failed to delete intermediate file %s: %s", input_path, e)

    return {**state, "cleaned_csv": str(cleaned_path)}


# ---------------------------------------------------------------------------
# Node 4 — classify_themes
# ---------------------------------------------------------------------------

def classify_themes_node(state: PipelineState) -> PipelineState:
    """
    Phase 2 — LangChain-powered theme classification.
    Reads cleaned_reviews.csv, writes theme_groups.json.
    """
    logger.info("[classify_themes] Starting LangChain theme classification …")

    _register_package("Phase2_themes", THEMES_DIR)
    _load_module("Phase2_themes.prompts", THEMES_DIR / "prompts.py", "Phase2_themes")
    grouper_mod = _load_module("Phase2_themes.grouper", THEMES_DIR / "grouper.py", "Phase2_themes")

    ThemeGrouper = grouper_mod.ThemeGrouper

    import pandas as pd
    cleaned_csv = state.get("cleaned_csv") or str(PROJECT_ROOT / "data" / "cleaned" / "cleaned_reviews.csv")
    df = pd.read_csv(cleaned_csv, encoding="utf-8")

    grouper = ThemeGrouper(
        model=state.get("model"),
        batch_size=state.get("batch_size", 50),
    )
    groups = grouper.group_reviews(df)

    themes_path = PROJECT_ROOT / "output" / "notes" / "theme_groups.json"
    themes_path.parent.mkdir(parents=True, exist_ok=True)
    result = {k: v.to_dict() for k, v in groups.items()}
    with themes_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    logger.info("[classify_themes] Done — %d themes → %s", len(groups), themes_path)
    return {**state, "themes_json": str(themes_path)}


# ---------------------------------------------------------------------------
# Node 5 — generate_pulse
# ---------------------------------------------------------------------------

def generate_pulse_node(state: PipelineState) -> PipelineState:
    """
    Phase 3 — LangChain-powered pulse note generation.
    Reads theme_groups.json, writes pulse_YYYY-MM-DD.{md,txt,html}.
    """
    logger.info("[generate_pulse] Starting LangChain pulse note generation …")

    _register_package("Phase3_generator", GEN_DIR)
    pulse_mod     = _load_module("Phase3_generator.pulse_note", GEN_DIR / "pulse_note.py", "Phase3_generator")
    formatter_mod = _load_module("Phase3_generator.formatter",  GEN_DIR / "formatter.py",  "Phase3_generator")

    PulseNoteGenerator = pulse_mod.PulseNoteGenerator
    PulseNoteFormatter = formatter_mod.PulseNoteFormatter

    themes_json = state.get("themes_json") or str(PROJECT_ROOT / "output" / "notes" / "theme_groups.json")
    with open(themes_json, encoding="utf-8") as fh:
        themes = json.load(fh)

    # -----------------------------------------------------------------------
    # Cleanup old logs and notes (Phase 3 requirement)
    # -----------------------------------------------------------------------
    logs_dir = PROJECT_ROOT / "output" / "logs"
    notes_dir = PROJECT_ROOT / "output" / "notes"
    for d in [logs_dir, notes_dir]:
        if d.exists():
            for item in d.iterdir():
                if item.is_file() and item.name != ".gitkeep":
                    try:
                        item.unlink()
                    except Exception as e:
                        logger.warning("[generate_pulse] Failed to delete %s: %s", item, e)

    # Re-save themes_json because it's needed by Phase 5 and we just deleted it
    # if it was in output/notes
    themes_path = Path(themes_json)
    themes_path.parent.mkdir(parents=True, exist_ok=True)
    with open(themes_path, "w", encoding="utf-8") as fh:
        json.dump(themes, fh, ensure_ascii=False, indent=2)

    logger.info("[generate_pulse] Cleaned up old output logs/notes and started fresh.")

    generator = PulseNoteGenerator(model=state.get("model"))
    note = generator.generate(themes)

    formatter = PulseNoteFormatter()
    output_dir = PROJECT_ROOT / "output" / "notes"
    output_dir.mkdir(parents=True, exist_ok=True)
    date_slug = datetime.today().strftime("%Y-%m-%d")

    md_path   = output_dir / f"pulse_{date_slug}.md"
    txt_path  = output_dir / f"pulse_{date_slug}.txt"
    html_path = output_dir / f"pulse_{date_slug}.html"

    md_path.write_text(formatter.format_for_docs(note),   encoding="utf-8")
    txt_path.write_text(formatter.format_for_email(note),  encoding="utf-8")
    html_path.write_text(formatter.format_for_html(note),  encoding="utf-8")

    _register_package("Phase5_agenticQuality", QUALITY_DIR)
    tools_mod = _load_module(
        "Phase5_agenticQuality.tools",
        QUALITY_DIR / "tools.py",
        "Phase5_agenticQuality",
    )

    logger.info(
        "[generate_pulse] Done — %d words | md=%s",
        note.word_count(), md_path,
    )
    return {
        **state,
        "pulse_md":        str(md_path),
        "pulse_txt":       str(txt_path),
        "pulse_html":      str(html_path),
        "pulse_note_data": tools_mod.pulse_note_to_dict(note),
    }


# ---------------------------------------------------------------------------
# Node 6 — publish  (Phase 4 — Custom Google MCP HTTP server)
# ---------------------------------------------------------------------------

def publish_node(state: PipelineState) -> PipelineState:
    """Phase 4 — append master Google Doc + Gmail draft via Railway MCP API."""
    pulse_md = state.get("pulse_md")
    if not pulse_md:
        msg = "No pulse_md in state — run generate_pulse first."
        logger.error("[publish] %s", msg)
        return {**state, "errors": state.get("errors", []) + [msg]}

    md_path = Path(pulse_md)
    txt_path = Path(state["pulse_txt"]) if state.get("pulse_txt") else None

    _register_package("Phase4_mcp", MCP_DIR)
    _load_module("Phase4_mcp.exceptions", MCP_DIR / "exceptions.py", "Phase4_mcp")
    _load_module("Phase4_mcp.publish_result", MCP_DIR / "publish_result.py", "Phase4_mcp")
    config_mod = _load_module("Phase4_mcp.config", MCP_DIR / "config.py", "Phase4_mcp")
    _load_module("Phase4_mcp.mcp_http_client", MCP_DIR / "mcp_http_client.py", "Phase4_mcp")
    _load_module("Phase4_mcp.google_docs_client", MCP_DIR / "google_docs_client.py", "Phase4_mcp")
    _load_module("Phase4_mcp.gmail_client", MCP_DIR / "gmail_client.py", "Phase4_mcp")
    publisher_mod = _load_module(
        "Phase4_mcp.publisher", MCP_DIR / "publisher.py", "Phase4_mcp"
    )

    try:
        publisher = publisher_mod.PulsePublisher(project_root=PROJECT_ROOT)
        result, log_path = publisher.publish(md_path, txt_path)
    except config_mod.ConfigurationError as exc:
        logger.error("[publish] Configuration error: %s", exc)
        return {**state, "errors": state.get("errors", []) + [str(exc)]}
    except Exception as exc:
        logger.error("[publish] MCP publish failed: %s", exc)
        return {**state, "errors": state.get("errors", []) + [str(exc)]}

    logger.info("[publish] Master doc: %s", result.document_url)
    logger.info("[publish] Gmail draft ID: %s", result.draft_id)
    logger.info("[publish] Correlation log: %s", log_path)

    return {
        **state,
        "doc_id": result.document_id,
        "doc_url": result.document_url,
        "draft_id": result.draft_id,
        "publish_log": str(log_path),
    }


# ===========================================================================
# ROUTING FUNCTIONS (conditional edges)
# ===========================================================================

def _route_entry(state: PipelineState) -> str:
    """Entry point router: scrape first if --scrape flag is set."""
    return "scrape" if state.get("do_scrape") else "ingest"


def _route_after_quality_resolve(state: PipelineState) -> str:
    """After quality passes: publish unless --dry-run."""
    if state.get("dry_run"):
        return "END"
    return "publish"


def _load_quality_nodes():
    """Load Phase 5 quality agent helpers."""
    _register_package("Phase5_agenticQuality", QUALITY_DIR)
    _load_module(
        "Phase5_agenticQuality.quality_checks",
        QUALITY_DIR / "quality_checks.py",
        "Phase5_agenticQuality",
    )
    agent_mod = _load_module(
        "Phase5_agenticQuality.quality_agent",
        QUALITY_DIR / "quality_agent.py",
        "Phase5_agenticQuality",
    )
    tools_mod = _load_module(
        "Phase5_agenticQuality.tools",
        QUALITY_DIR / "tools.py",
        "Phase5_agenticQuality",
    )
    return agent_mod, tools_mod


def quality_agent_wrapper(state: PipelineState) -> PipelineState:
    agent_mod, _ = _load_quality_nodes()
    return agent_mod.quality_agent_node(dict(state))


def tools_result_wrapper(state: PipelineState) -> PipelineState:
    agent_mod, _ = _load_quality_nodes()
    return agent_mod.tools_result_node(dict(state))


def _route_after_quality(state: PipelineState) -> str:
    agent_mod, _ = _load_quality_nodes()
    return agent_mod.route_after_quality(dict(state))


def _route_after_tools_result(state: PipelineState) -> str:
    agent_mod, _ = _load_quality_nodes()
    return agent_mod.route_after_tools(dict(state))


# ===========================================================================
# GRAPH CONSTRUCTION
# ===========================================================================

def build_pipeline() -> object:
    """
    Build and compile the LangGraph StateGraph for the full pipeline.

    Graph topology:
        [entry] ──(do_scrape?)──► scrape ──► ingest ──► pii_scrub
                └──────────────► ingest ──► pii_scrub
                                                │
                                         classify_themes
                                                │
                                         generate_pulse
                                                │
                                         quality_agent ⇄ tools
                                                │
                                    (dry_run?)──┤
                                    END ◄───────┘
                                    publish ◄───┘
                                        │
                                       END
    """
    from langgraph.graph import StateGraph, END
    from langgraph.prebuilt import ToolNode

    _, tools_mod = _load_quality_nodes()
    quality_tools = tools_mod.build_quality_tools()

    graph = StateGraph(PipelineState)

    # Register all nodes
    graph.add_node("scrape",           scrape_node)
    graph.add_node("ingest",           ingest_node)
    graph.add_node("pii_scrub",        pii_scrub_node)
    graph.add_node("classify_themes",  classify_themes_node)
    graph.add_node("generate_pulse",   generate_pulse_node)
    graph.add_node("quality_agent",    quality_agent_wrapper)
    graph.add_node("tools",            ToolNode(quality_tools))
    graph.add_node("tools_result",     tools_result_wrapper)
    graph.add_node("quality_resolve",  lambda state: state)
    graph.add_node("publish",          publish_node)

    # Conditional entry point: scrape → ingest, or ingest directly
    graph.set_conditional_entry_point(
        _route_entry,
        path_map={"scrape": "scrape", "ingest": "ingest"},
    )

    # Linear edges through the pipeline
    graph.add_edge("scrape",          "ingest")
    graph.add_edge("ingest",          "pii_scrub")
    graph.add_edge("pii_scrub",       "classify_themes")
    graph.add_edge("classify_themes", "generate_pulse")
    graph.add_edge("generate_pulse",  "quality_agent")

    graph.add_conditional_edges(
        "quality_agent",
        _route_after_quality,
        path_map={"tools": "tools", "quality_resolve": "quality_resolve"},
    )
    graph.add_edge("tools", "tools_result")
    graph.add_conditional_edges(
        "tools_result",
        _route_after_tools_result,
        path_map={
            "quality_agent": "quality_agent",
            "generate_pulse": "generate_pulse",
            "classify_themes": "classify_themes",
        },
    )
    graph.add_conditional_edges(
        "quality_resolve",
        _route_after_quality_resolve,
        path_map={"END": END, "publish": "publish"},
    )

    graph.add_edge("publish", END)

    return graph.compile()


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Groww Automated Weekly Product Review Pulse — "
            "LangGraph agentic pipeline"
        )
    )
    parser.add_argument(
        "--scrape",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Scrape fresh reviews from Play Store and App Store before processing. Use --no-scrape to skip scraping.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        metavar="DIR",
        help="Path to directory containing pre-scraped CSV files (skips scraping).",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        metavar="N",
        help="Number of weeks of reviews to include (default: 12).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline but skip Google Docs / Gmail publishing.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Override LLM model (default: env LLM_MODEL or llama-3.3-70b-versatile).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        metavar="N",
        help="Reviews per LLM call in Phase 2 (default: 50).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip Phase 5 quality loop (generate_pulse → publish/dry-run directly).",
    )
    parser.add_argument(
        "--max-quality-iterations",
        type=int,
        default=3,
        metavar="N",
        help="Max quality remediation loops before force-approve (default: 3).",
    )
    return parser.parse_args()


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def run_pipeline_logic(
    weeks: int = 12,
    dry_run: bool = False,
    scrape: bool = True,
    csv_dir: Optional[str] = None,
    model: Optional[str] = None,
    batch_size: int = 50,
    max_quality_iterations: int = 3,
    skip_quality: bool = False,
    verbose: bool = False
) -> dict:
    """
    Programmatic entry point to run the LangGraph pipeline.
    Returns the final state dictionary.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    logger.info("=== Groww Weekly Product Review Pulse — LangGraph Pipeline ===")
    logger.info(
        "Config: scrape=%s  csv=%s  weeks=%s  dry_run=%s  model=%s",
        scrape, csv_dir, weeks, dry_run, model,
    )

    # Build the compiled graph
    pipeline = build_pipeline()
    logger.info("LangGraph pipeline compiled — quality loop enabled")

    start_time = time.time()

    # Initial state
    initial_state: PipelineState = {
        "weeks":       weeks,
        "dry_run":     dry_run,
        "do_scrape":   scrape,
        "csv_dir":     csv_dir,
        "model":       model,
        "batch_size":  batch_size,
        "raw_csv":     None,
        "cleaned_csv": None,
        "themes_json": None,
        "pulse_md":    None,
        "pulse_txt":   None,
        "pulse_html":  None,
        "doc_id":      None,
        "doc_url":     None,
        "draft_id":    None,
        "publish_log": None,
        "messages":    [],
        "pulse_note_data": None,
        "quality_status": None,
        "quality_passed": None,
        "quality_iterations": 0,
        "max_quality_iterations": max_quality_iterations,
        "quality_word_limit": 250,
        "quality_last_failure": None,
        "quality_remediation": [],
        "quality_log": None,
        "post_tool_route": None,
        "skip_quality": skip_quality,
        "project_root": str(PROJECT_ROOT),
        "reclassify_hint": None,
        "errors":      [],
    }

    # Execute the graph
    try:
        result = pipeline.invoke(initial_state)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=verbose)
        raise exc

    if result.get("pulse_md") and not result.get("skip_quality") and not result.get("quality_log"):
        try:
            agent_mod, _ = _load_quality_nodes()
            checks_mod = sys.modules["Phase5_agenticQuality.quality_checks"]
            log_mod = _load_module(
                "Phase5_agenticQuality.quality_log",
                QUALITY_DIR / "quality_log.py",
                "Phase5_agenticQuality",
            )
            report = checks_mod.evaluate_quality(
                pulse_md_path=result.get("pulse_md"),
                pulse_note_data=result.get("pulse_note_data"),
                themes_json_path=result.get("themes_json"),
                word_limit=int(result.get("quality_word_limit") or 250),
            )
            log_path = log_mod.record_quality_check(
                PROJECT_ROOT,
                event="pipeline_summary",
                passed=bool(result.get("quality_passed", report.passed)),
                failures=report.failures,
                details=report.details,
                iterations=int(result.get("quality_iterations") or 0),
                remediations=result.get("quality_remediation"),
                pulse_md=result.get("pulse_md"),
            )
            result = {**result, "quality_log": str(log_path)}
            logger.info("[pipeline] Wrote fallback quality log: %s", log_path)
        except Exception as exc:
            logger.warning("[pipeline] Could not write fallback quality log: %s", exc)

    # Final summary
    duration = time.time() - start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    print("\n" + "=" * 60)
    print("  GROWW PULSE PIPELINE — COMPLETE")
    print(f"  Duration: {minutes}m {seconds}s")
    print("=" * 60)
    if result.get("pulse_md"):
        print(f"  Markdown   : {result['pulse_md']}")
    if result.get("pulse_txt"):
        print(f"  Plain text : {result['pulse_txt']}")
    if result.get("pulse_html"):
        print(f"  HTML       : {result['pulse_html']}")
    if result.get("doc_id"):
        print(f"  Master doc ID : {result['doc_id']}")
    if result.get("doc_url"):
        print(f"  Master doc URL: {result['doc_url']}")
    if result.get("draft_id"):
        print(f"  Gmail draft   : {result['draft_id']}")
    if result.get("publish_log"):
        print(f"  Publish log   : {result['publish_log']}")
    if result.get("quality_log"):
        print(f"  Quality log   : {result['quality_log']}")

    if result.get("errors"):
        print("\n  Warnings/Errors:")
        for err in result["errors"]:
            print(f"  - {err}")

    if result.get("quality_status"):
        passed_icon = "✅" if result.get("quality_passed") else "❌"
        print(f"\n  Quality: {passed_icon} {result['quality_status']} ({result.get('quality_iterations', 0)} iterations)")

    print("=" * 60 + "\n")

    if result.get("pulse_md"):
        print("\n--- Pulse Note Preview ---")
        try:
            print(Path(result["pulse_md"]).read_text(encoding="utf-8"))
        except Exception:
            print("(Preview unavailable)")

    return result


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    args = parse_args()
    try:
        run_pipeline_logic(
            weeks=args.weeks,
            dry_run=args.dry_run,
            scrape=args.scrape,
            csv_dir=args.csv,
            model=args.model,
            batch_size=args.batch_size,
            max_quality_iterations=args.max_quality_iterations,
            skip_quality=args.skip_quality,
            verbose=args.verbose
        )
    except Exception as exc:
        logger.exception("Pipeline failed with exception:")
        sys.exit(1)


if __name__ == "__main__":
    main()
