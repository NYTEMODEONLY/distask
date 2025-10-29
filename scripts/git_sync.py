#!/usr/bin/env python3
"""
Automated GitHub sync script for DisTask VPS.

This script can be triggered by:
- GitHub webhook (instant updates)
- Systemd timer (fallback polling every 2 minutes)

On successful git pull, restarts DisTask services to apply code changes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT_DIR / "data" / "last_sync.json"
DATA_DIR = ROOT_DIR / "data"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)


def load_env() -> dict[str, Optional[str]]:
    """Load environment variables from .env file."""
    load_dotenv(ROOT_DIR / ".env")
    return {
        "branch": os.getenv("GIT_SYNC_BRANCH", "main"),
        "enabled": os.getenv("GIT_SYNC_ENABLED", "true").lower() == "true",
        "repo_owner": os.getenv("REPO_OWNER", "NYTEMODEONLY"),
        "repo_name": os.getenv("REPO_NAME", "distask"),
    }


def get_last_sync_time() -> Optional[datetime]:
    """Get the timestamp of the last successful sync."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        timestamp_str = data.get("last_sync")
        if timestamp_str:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception as e:
        logger.warning("Failed to read last sync time: %s", e)
    return None


def update_last_sync_time() -> None:
    """Update the last sync timestamp."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        STATE_FILE.write_text(json.dumps({"last_sync": timestamp}, indent=2))
    except Exception as e:
        logger.error("Failed to update last sync time: %s", e)


def check_git_status() -> tuple[bool, Optional[str]]:
    """Check if git working tree is clean."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            return False, result.stdout.strip()
        return True, None
    except subprocess.CalledProcessError as e:
        return False, f"Git status check failed: {e.stderr}"


def fetch_from_remote() -> bool:
    """Fetch latest changes from GitHub."""
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=ROOT_DIR,
            capture_output=True,
            check=True,
            timeout=30,
        )
        return True
    except subprocess.TimeoutExpired:
        logger.error("Git fetch timed out after 30 seconds")
        return False
    except subprocess.CalledProcessError as e:
        logger.error("Git fetch failed: %s", e.stderr.decode() if e.stderr else str(e))
        return False


def check_for_updates(branch: str) -> tuple[bool, Optional[str]]:
    """Check if local branch is behind remote."""
    try:
        # Get local commit (current HEAD)
        local_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        local_commit = local_result.stdout.strip()

        # Get remote commit (origin/branch after fetch)
        remote_result = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        remote_commit = remote_result.stdout.strip()

        if local_commit != remote_commit:
            logger.info("Updates detected: local=%s, remote=%s", local_commit[:8], remote_commit[:8])
            return True, remote_commit
        return False, None
    except subprocess.CalledProcessError as e:
        logger.error("Failed to check for updates: %s", e.stderr.decode() if e.stderr else str(e))
        return False, None


def pull_changes(branch: str) -> bool:
    """Pull latest changes from GitHub."""
    try:
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        logger.info("Git pull successful: %s", result.stdout.strip()[:200])
        return True
    except subprocess.TimeoutExpired:
        logger.error("Git pull timed out after 60 seconds")
        return False
    except subprocess.CalledProcessError as e:
        # Check for merge conflicts
        error_output = e.stderr.decode() if e.stderr and isinstance(e.stderr, bytes) else str(e.stderr) if e.stderr else str(e)
        if "CONFLICT" in error_output or "conflict" in error_output.lower():
            logger.error("Merge conflict detected. Manual intervention required.")
        else:
            logger.error("Git pull failed: %s", error_output)
        return False


def restart_service(service_name: str) -> bool:
    """Restart a systemd service."""
    try:
        result = subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        logger.info("Restarted %s successfully", service_name)
        return True
    except subprocess.TimeoutExpired:
        logger.error("Service restart timed out for %s", service_name)
        return False
    except subprocess.CalledProcessError as e:
        logger.error("Failed to restart %s: %s", service_name, e.stderr.decode() if e.stderr else str(e))
        return False


def should_skip_polling(minutes_threshold: int = 5) -> bool:
    """Check if polling should be skipped (recent sync happened)."""
    last_sync = get_last_sync_time()
    if not last_sync:
        return False
    
    time_diff = (datetime.now(timezone.utc) - last_sync).total_seconds() / 60
    if time_diff < minutes_threshold:
        logger.info("Skipping sync: last sync was %.1f minutes ago (< %d minutes)", time_diff, minutes_threshold)
        return True
    return False


def sync_services() -> None:
    """Restart DisTask services after code update."""
    services = ["distask.service", "distask-web.service"]
    
    # Only restart feature agent if git_sync.py itself changed
    sync_script_path = ROOT_DIR / "scripts" / "git_sync.py"
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD", "--name-only"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        if "scripts/git_sync.py" in result.stdout:
            services.append("distask-feature-agent.service")
            logger.info("Sync script changed, will restart feature agent")
    except Exception as e:
        logger.warning("Could not check if sync script changed: %s", e)
    
    for service in services:
        restart_service(service)


def perform_sync(dry_run: bool = False, poll_mode: bool = False) -> bool:
    """Perform the git sync operation."""
    config = load_env()
    
    if not config["enabled"]:
        logger.info("Git sync is disabled via GIT_SYNC_ENABLED")
        return False
    
    # Skip polling if recent sync happened
    if poll_mode and should_skip_polling():
        return False
    
    branch = config["branch"]
    logger.info("Starting git sync (branch: %s, dry_run: %s, poll_mode: %s)", branch, dry_run, poll_mode)
    
    # Check git status
    is_clean, status_output = check_git_status()
    if not is_clean:
        logger.warning("Working tree is not clean. Skipping sync. Status:\n%s", status_output)
        return False
    
    # Fetch from remote
    if not fetch_from_remote():
        logger.error("Failed to fetch from remote")
        return False
    
    # Check for updates
    has_updates, new_commit = check_for_updates(branch)
    if not has_updates:
        logger.info("No updates available")
        return False
    
    if dry_run:
        logger.info("DRY RUN: Would pull commit %s and restart services", new_commit[:8] if new_commit else "unknown")
        return True
    
    # Pull changes
    if not pull_changes(branch):
        logger.error("Failed to pull changes")
        return False
    
    # Restart services
    sync_services()
    
    # Update last sync time
    update_last_sync_time()
    
    logger.info("Git sync completed successfully")
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync DisTask code from GitHub and restart services")
    parser.add_argument("--dry-run", action="store_true", help="Check for updates without pulling")
    parser.add_argument("--poll", action="store_true", help="Polling mode (checks last sync time)")
    args = parser.parse_args()
    
    try:
        success = perform_sync(dry_run=args.dry_run, poll_mode=args.poll)
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("Sync interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Unexpected error during sync: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

