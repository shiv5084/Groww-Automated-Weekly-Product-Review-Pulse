"""
local_scheduler.py — Local test script to simulate the GitHub Actions cron job.

This script allows you to:
1. Run the entire pipeline immediately to test the workflow.
2. Schedule the pipeline to run at a specific time (simulating cron).

Usage:
    python src/scripts/local_scheduler.py --run-now
    python src/scripts/local_scheduler.py --run-now --no-dry-run
    python src/scripts/local_scheduler.py --test-cron "09:20" --day "Monday"
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def run_pipeline(dry_run=True):
    """Execute the main pipeline using the same logic as the GHA workflow."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting local pipeline run...")
    
    # Try to find the correct virtual environment
    python_exe = sys.executable
    venv_python = PROJECT_ROOT / "langgraph_env" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python)
        print(f"Using virtual environment: {venv_python}")
    
    # We use the same command as the GHA workflow
    cmd = [
        python_exe, 
        str(PROJECT_ROOT / "src" / "main.py"),
        "--scrape",
        "--weeks", "12"
    ]
    
    if dry_run:
        cmd.append("--dry-run")
        print("Dry run mode: active (will skip Google Docs / Gmail publishing)")
    
    try:
        # Run and stream output
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        for line in process.stdout:
            print(line, end="")
            
        process.wait()
        
        if process.returncode == 0:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline completed successfully.")
        else:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline failed with return code {process.returncode}.")
            
    except Exception as e:
        print(f"Error executing pipeline: {e}")

def start_scheduler(target_time: str, target_day: str, dry_run=True):
    """Simple loop to wait for the next scheduled time."""
    print(f"Local scheduler started. Target: Every {target_day} at {target_time}")
    print(f"Dry run mode: {dry_run}")
    print("Press Ctrl+C to stop.")
    
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%A")
        
        if current_day == target_day and current_time == target_time:
            run_pipeline(dry_run=dry_run)
            # Sleep for 61 seconds to avoid multiple triggers in the same minute
            time.sleep(61)
        
        # Check every 30 seconds
        time.sleep(30)

def main():
    parser = argparse.ArgumentParser(description="Local scheduler test script")
    parser.add_argument("--run-now", action="store_true", help="Run the pipeline immediately and exit")
    parser.add_argument("--no-dry-run", action="store_true", help="Disable dry run (will attempt to publish)")
    parser.add_argument("--test-cron", type=str, default=None, metavar="HH:MM", help="Schedule time (e.g. 09:20)")
    parser.add_argument("--day", type=str, default="Monday", help="Day of the week (default: Monday)")
    
    args = parser.parse_args()
    
    if args.run_now:
        run_pipeline(dry_run=not args.no_dry_run)
        return

    if args.test_cron:
        start_scheduler(args.test_cron, args.day, dry_run=not args.no_dry_run)
    else:
        print("Please specify --run-now or --test-cron HH:MM")
        parser.print_help()

if __name__ == "__main__":
    main()
