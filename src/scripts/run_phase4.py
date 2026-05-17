"""
run_phase4.py — CLI runner for Phase 4 MCP publish.

Appends the latest pulse note to the master Google Doc and creates a Gmail
draft via the deployed MCP server (Railway HTTP API).

Usage (run from project root):
    python src/scripts/run_phase4.py
    python src/scripts/run_phase4.py --input output/notes/pulse_2026-05-15.md
    python src/scripts/run_phase4.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import importlib.util as _ilu

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MCP_DIR = PROJECT_ROOT / "src" / "Phase4-mcp"


def _load(module_name: str, file_path: Path, package_name: Optional[str] = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.modules["Phase4_mcp"] = type(sys)("Phase4_mcp")
sys.modules["Phase4_mcp"].__path__ = [str(MCP_DIR)]

_load("Phase4_mcp.exceptions", MCP_DIR / "exceptions.py", "Phase4_mcp")
_load("Phase4_mcp.publish_result", MCP_DIR / "publish_result.py", "Phase4_mcp")
_config_mod = _load("Phase4_mcp.config", MCP_DIR / "config.py", "Phase4_mcp")
_http_mod = _load("Phase4_mcp.mcp_http_client", MCP_DIR / "mcp_http_client.py", "Phase4_mcp")
_load("Phase4_mcp.google_docs_client", MCP_DIR / "google_docs_client.py", "Phase4_mcp")
_load("Phase4_mcp.gmail_client", MCP_DIR / "gmail_client.py", "Phase4_mcp")
_publisher_mod = _load("Phase4_mcp.publisher", MCP_DIR / "publisher.py", "Phase4_mcp")

PulsePublisher = _publisher_mod.PulsePublisher
ConfigurationError = _config_mod.ConfigurationError
MCPError = _http_mod.MCPError


def _latest_pulse_md(notes_dir: Path) -> Path:
    candidates = sorted(notes_dir.glob("pulse_*.md"), reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No pulse_*.md files in {notes_dir}. Run Phase 3 first."
        )
    return candidates[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 4 — Append pulse to master Google Doc and create Gmail draft"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        metavar="FILE",
        help="Pulse Markdown file (default: latest output/notes/pulse_*.md)",
    )
    parser.add_argument(
        "--txt",
        type=str,
        default=None,
        metavar="FILE",
        help="Plain-text pulse for email body (default: same stem as --input)",
    )
    parser.add_argument(
        "--notes-dir",
        type=str,
        default="output/notes",
        metavar="DIR",
        help="Directory to search for latest pulse when --input omitted",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    logger = logging.getLogger(__name__)

    notes_dir = PROJECT_ROOT / args.notes_dir
    if args.input:
        md_path = PROJECT_ROOT / args.input
    else:
        md_path = _latest_pulse_md(notes_dir)

    txt_path = PROJECT_ROOT / args.txt if args.txt else None

    logger.info("Publishing from %s", md_path)

    try:
        publisher = PulsePublisher(project_root=PROJECT_ROOT)
        result, log_path = publisher.publish(md_path, txt_path)
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except MCPError as exc:
        logger.error("MCP publish failed: %s", exc)
        if getattr(exc, "details", None):
            logger.error("Details: %s", exc.details)
        logger.error(
            "Local pulse kept at %s. Fix MCP config and re-run Phase 4 only.",
            md_path,
        )
        return 1

    print("\n=== Phase 4 Complete ===")
    print(f"  Pulse input    : {md_path}")
    print(f"  Master doc ID  : {result.document_id}")
    print(f"  Master doc URL : {result.document_url}")
    print(f"  Gmail draft ID : {result.draft_id}")
    print(f"  Publish log    : {log_path}")
    return 0


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        print("\nPublish interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
