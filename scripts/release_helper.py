from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import scripts.validate as validate
from scripts.feature_agent import (
    FeatureRequest,
    build_queue_from_models,
    compute_priority_score,
    to_model,
)
from utils.db import Database

logger = logging.getLogger("distask.release")

VERSION_FILE = ROOT_DIR / "VERSION"
CHANGELOG_FILE = ROOT_DIR / "CHANGELOG.md"
FEATURE_QUEUE_JSON = ROOT_DIR / "automation" / "feature_queue.json"
FEATURE_QUEUE_MD = ROOT_DIR / "automation" / "feature_queue.md"


@dataclass
class ReleaseCandidate:
    """A feature request candidate for release."""
    id: int
    title: str
    suggestion: Optional[str]
    score: float
    priority: float
    ease: float
    net_votes: int
    status: str
    rationale: str


def load_version() -> str:
    """Load current version from VERSION file or git tag."""
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text().strip()
        if version:
            return version
    
    # Try to get latest git tag
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            tag = result.stdout.strip()
            # Remove 'v' prefix if present
            return tag.lstrip("v")
    except Exception:
        pass
    
    return "1.0.0"


def save_version(version: str) -> None:
    """Save version to VERSION file."""
    VERSION_FILE.write_text(f"{version}\n")


def bump_version(current: str, bump_type: str = "patch") -> str:
    """Bump version following semantic versioning."""
    parts = current.split(".")
    if len(parts) != 3:
        parts = ["1", "0", "0"]
    
    major, minor, patch = map(int, parts)
    
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    
    return f"{major}.{minor}.{patch}"


def parse_feature_queue() -> List[Dict]:
    """Parse feature queue from JSON file."""
    if not FEATURE_QUEUE_JSON.exists():
        logger.warning("feature_queue.json not found, running feature_agent first...")
        return []
    
    try:
        with open(FEATURE_QUEUE_JSON, "r") as f:
            data = json.load(f)
        return data.get("items", [])
    except Exception as e:
        logger.error("Error parsing feature_queue.json: %s", e)
        return []


async def load_features_from_db(db: Database) -> List[FeatureRequest]:
    """Load feature requests from database."""
    try:
        rows = await db.fetch_feature_requests()
        return to_model(rows)
    except Exception as e:
        logger.error("Error loading features from DB: %s", e)
        return []


def suggest_release_batch(
    queue: List[Dict],
    threshold: float = 80.0,
    max_items: int = 5,
) -> List[ReleaseCandidate]:
    """Suggest features for release based on score threshold."""
    candidates: List[ReleaseCandidate] = []
    
    # Filter by threshold and status
    eligible = [
        item for item in queue
        if item.get("score", 0) >= threshold
        and item.get("status") in ("pending", "in_progress")
        and not item.get("duplicate_of")
    ]
    
    # Sort by score descending
    eligible.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # Take top N
    for item in eligible[:max_items]:
        score = item.get("score", 0)
        priority = item.get("priority", 5)
        ease = item.get("ease", 5)
        votes = item.get("votes", {})
        net_votes = votes.get("net", 0)
        
        # Build rationale
        rationale_parts = []
        if priority > 5:
            rationale_parts.append(f"high priority ({priority})")
        if ease > 5:
            rationale_parts.append(f"easy to implement ({ease})")
        if net_votes > 0:
            rationale_parts.append(f"community support (+{net_votes} votes)")
        if score > threshold + 10:
            rationale_parts.append("high overall score")
        
        rationale = ", ".join(rationale_parts) if rationale_parts else "meets threshold criteria"
        
        candidates.append(
            ReleaseCandidate(
                id=item["id"],
                title=item["title"],
                suggestion=item.get("suggestion") or None,  # Queue JSON may not have full suggestion
                score=score,
                priority=priority,
                ease=ease,
                net_votes=net_votes,
                status=item.get("status", "pending"),
                rationale=rationale,
            )
        )
    
    return candidates


async def show_completed_features(db: Optional[Database] = None, limit: int = 10) -> None:
    """Show recently completed features."""
    print("\n" + "=" * 70)
    print("RECENTLY COMPLETED FEATURES")
    print("=" * 70)
    
    completed: List[Dict] = []
    
    if db:
        try:
            rows = await db.fetch_feature_requests()
            for row in rows:
                if row.get("status") == "completed":
                    completed.append(row)
            # Sort by completed_at descending
            completed.sort(
                key=lambda x: x.get("completed_at") or "",
                reverse=True,
            )
        except Exception as e:
            logger.error("Error loading completed features from DB: %s", e)
    
    if not completed:
        print("No completed features found.")
        print("=" * 70 + "\n")
        return
    
    for idx, feature in enumerate(completed[:limit], 1):
        feature_id = feature.get("id")
        title = feature.get("title", "Unknown")
        completed_at = feature.get("completed_at", "")
        analysis = feature.get("analysis_data", {})
        commit_hash = analysis.get("commit_hash", "") if isinstance(analysis, dict) else ""
        commit_message = analysis.get("commit_message", "") if isinstance(analysis, dict) else ""
        
        print(f"\n{idx}. FR-{feature_id}: {title}")
        if completed_at:
            print(f"   Completed: {completed_at}")
        if commit_hash:
            print(f"   Commit: {commit_hash[:8]} - {commit_message[:60]}")
    
    print("\n" + "=" * 70)
    print(f"Total: {len(completed)} completed feature(s)")
    print("=" * 70 + "\n")


def print_release_suggestion(candidates: List[ReleaseCandidate], threshold: float) -> None:
    """Print formatted release suggestion."""
    print("\n" + "=" * 70)
    print(f"RELEASE BATCH SUGGESTION (Score Threshold: {threshold})")
    print("=" * 70)
    
    if not candidates:
        print("No features meet the score threshold.")
        print("=" * 70 + "\n")
        return
    
    for idx, candidate in enumerate(candidates, 1):
        print(f"\n{idx}. FR-{candidate.id}: {candidate.title}")
        print(f"   Score: {candidate.score:.2f} (Priority: {candidate.priority}, Ease: {candidate.ease})")
        print(f"   Net Votes: {candidate.net_votes}")
        print(f"   Status: {candidate.status}")
        print(f"   Rationale: {candidate.rationale}")
        if candidate.suggestion:
            desc = candidate.suggestion[:100] + "..." if len(candidate.suggestion) > 100 else candidate.suggestion
            print(f"   Description: {desc}")
    
    print("\n" + "=" * 70)
    print(f"Total: {len(candidates)} feature(s) suggested for release")
    print("=" * 70 + "\n")


def generate_changelog(
    candidates: List[ReleaseCandidate],
    version: str,
    previous_version: str,
    repo_owner: str = "NYTEMODEONLY",
    repo_name: str = "distask",
) -> str:
    """Generate changelog entry for release candidates."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    lines = [
        f"## [{version}] - {date}",
        "",
    ]
    
    if candidates:
        lines.append("### Added")
        for candidate in candidates:
            lines.append(f"- FR-{candidate.id}: {candidate.title}")
            if candidate.suggestion:
                desc = candidate.suggestion[:200] + "..." if len(candidate.suggestion) > 200 else candidate.suggestion
                lines.append(f"  - {desc}")
            lines.append("")
    else:
        lines.append("### Changed")
        lines.append("- Maintenance release")
        lines.append("")
    
    lines.append(f"[Full Changelog](https://github.com/{repo_owner}/{repo_name}/compare/v{previous_version}...v{version})")
    lines.append("")
    
    return "\n".join(lines)


def update_changelog(new_entry: str) -> None:
    """Prepend new changelog entry to CHANGELOG.md."""
    if CHANGELOG_FILE.exists():
        existing = CHANGELOG_FILE.read_text()
        content = new_entry + "\n" + existing
    else:
        content = new_entry + "\n"
    
    CHANGELOG_FILE.write_text(content)


async def create_github_release(
    version: str,
    changelog_entry: str,
    github_token: str,
    repo_owner: str,
    repo_name: str,
) -> bool:
    """Create GitHub release via API."""
    import aiohttp  # noqa: E402
    
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DisTask-Release-Helper",
    }
    
    tag_name = f"v{version}"
    release_name = f"Release {version}"
    
    body = {
        "tag_name": tag_name,
        "name": release_name,
        "body": changelog_entry,
        "draft": False,
        "prerelease": False,
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=body) as response:
                if response.status in (200, 201):
                    logger.info("GitHub release created: %s", tag_name)
                    return True
                else:
                    text = await response.text()
                    logger.error("Failed to create GitHub release (%s): %s", response.status, text)
                    return False
    except Exception as e:
        logger.error("Error creating GitHub release: %s", e)
        return False


def create_git_tag(version: str, dry_run: bool = False) -> bool:
    """Create git tag for version."""
    tag_name = f"v{version}"
    
    if dry_run:
        logger.info("[DRY RUN] Would create git tag: %s", tag_name)
        return True
    
    try:
        result = subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Release {version}"],
            cwd=ROOT_DIR,
            check=False,
        )
        if result.returncode == 0:
            logger.info("Created git tag: %s", tag_name)
            return True
        else:
            logger.error("Failed to create git tag")
            return False
    except Exception as e:
        logger.error("Error creating git tag: %s", e)
        return False


def restart_services(dry_run: bool = False) -> bool:
    """Restart systemd services."""
    services = ["distask.service", "distask-web.service"]
    
    if dry_run:
        logger.info("[DRY RUN] Would restart services: %s", ", ".join(services))
        return True
    
    for service in services:
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Restarted %s", service)
            else:
                logger.warning("Failed to restart %s: %s", service, result.stderr)
        except Exception as e:
            logger.error("Error restarting %s: %s", service, e)
            return False
    
    return True


async def mark_features_shipped(
    db: Database,
    candidates: List[ReleaseCandidate],
    version: str,
    dry_run: bool = False,
) -> None:
    """Mark features as shipped in database."""
    if dry_run:
        logger.info("[DRY RUN] Would mark %d features as shipped", len(candidates))
        return
    
    for candidate in candidates:
        try:
            # Update feature status to indicate it's been shipped
            # Note: We don't mark as 'completed' here since that's for implementation
            # Instead, we could add a 'shipped_in_version' field or similar
            # For now, we'll just log it
            logger.info("Feature FR-%d included in release %s", candidate.id, version)
        except Exception as e:
            logger.error("Error marking feature FR-%d as shipped: %s", candidate.id, e)


async def full_release_cycle(
    threshold: float,
    max_items: int,
    auto_select: bool,
    dry_run: bool,
    yes: bool,
    db_url: Optional[str],
    github_token: Optional[str],
    repo_owner: Optional[str],
    repo_name: Optional[str],
    bump_type: str = "minor",
) -> bool:
    """Execute full release cycle."""
    logger.info("Starting release cycle (threshold=%.1f, max_items=%d, dry_run=%s)", threshold, max_items, dry_run)
    
    # Step 1: Parse feature queue
    queue = parse_feature_queue()
    if not queue:
        logger.error("No feature queue found. Run feature_agent.py first.")
        return False
    
    # Step 2: Suggest release batch
    candidates = suggest_release_batch(queue, threshold, max_items)
    print_release_suggestion(candidates, threshold)
    
    if not candidates:
        logger.info("No candidates for release")
        return False
    
    # Step 3: Confirm selection (unless auto-select)
    if not auto_select and not dry_run:
        if not yes:
            response = input(f"Proceed with releasing {len(candidates)} feature(s)? [y/N]: ")
            if response.lower() != "y":
                logger.info("Release cancelled by user")
                return False
    
    # Step 4: Validate
    logger.info("Running validation checks...")
    results, validation_passed = validate.run_all_validations(db_url=db_url)
    validate.print_validation_summary(results, validation_passed)
    
    if not validation_passed and not dry_run:
        logger.error("Validation failed. Aborting release.")
        return False
    
    # Step 5: Bump version
    current_version = load_version()
    new_version = bump_version(current_version, bump_type)
    logger.info("Bumping version: %s -> %s", current_version, new_version)
    
    if not dry_run:
        save_version(new_version)
    
    # Step 6: Generate changelog
    changelog_entry = generate_changelog(
        candidates,
        new_version,
        current_version,
        repo_owner=repo_owner or "NYTEMODEONLY",
        repo_name=repo_name or "distask",
    )
    logger.info("Generated changelog entry")
    
    if not dry_run:
        update_changelog(changelog_entry)
    
    # Step 7: Create git tag
    create_git_tag(new_version, dry_run=dry_run)
    
    # Step 8: Create GitHub release (if credentials available)
    if github_token and repo_owner and repo_name and not dry_run:
        logger.info("Creating GitHub release...")
        await create_github_release(new_version, changelog_entry, github_token, repo_owner, repo_name)
    
    # Step 9: Mark features as shipped (if DB available)
    if db_url:
        db = Database(db_url)
        try:
            await db.init()
            await mark_features_shipped(db, candidates, new_version, dry_run=dry_run)
        finally:
            await db.close()
    
    # Step 10: Restart services (optional, user-triggered)
    if not dry_run:
        logger.info("Release cycle complete. Services not automatically restarted.")
        logger.info("To restart services, run: sudo systemctl restart distask.service distask-web.service")
    
    logger.info("Release cycle completed successfully")
    return True


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="DisTask Rapid Release Helper - Score-based release automation"
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Suggest release batch based on score threshold",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run all validation checks",
    )
    parser.add_argument(
        "--full-cycle",
        action="store_true",
        help="Execute full release cycle",
    )
    parser.add_argument(
        "--show-completed",
        action="store_true",
        help="Show recently completed features",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Score threshold for release selection (default: from .env or 80.0)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of features to include in release batch (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate release without making changes",
    )
    parser.add_argument(
        "--auto-select",
        action="store_true",
        help="Automatically select top-scoring features without prompts",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    parser.add_argument(
        "--bump-type",
        choices=["major", "minor", "patch"],
        default="minor",
        help="Version bump type (default: minor)",
    )
    parser.add_argument(
        "--db-url",
        help="Database URL (default: from .env)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test execution during validation",
    )
    
    args = parser.parse_args()
    
    # Load environment
    load_dotenv()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    
    # Get threshold from args or env
    threshold = args.threshold
    if threshold is None:
        threshold_str = os.getenv("RELEASE_THRESHOLD") or os.getenv("release_threshold") or "80.0"
        try:
            threshold = float(threshold_str)
        except ValueError:
            threshold = 80.0
    
    # Get database URL
    db_url = args.db_url or os.getenv("DATABASE_URL") or os.getenv("database_url")
    
    # Get GitHub credentials
    github_token = os.getenv("GITHUB_TOKEN") or os.getenv("github_token")
    repo_owner = os.getenv("REPO_OWNER") or os.getenv("repo_owner") or "NYTEMODEONLY"
    repo_name = os.getenv("REPO_NAME") or os.getenv("repo_name") or "distask"
    
    # Execute requested action
    if args.show_completed:
        db = None
        if db_url:
            db = Database(db_url)
            try:
                await db.init()
                await show_completed_features(db, limit=10)
            except Exception as e:
                logger.error("Error showing completed features: %s", e)
            finally:
                if db:
                    await db.close()
        else:
            logger.warning("No database URL provided; cannot load completed features")
            await show_completed_features(None, limit=10)
        return 0
    
    elif args.suggest:
        queue = parse_feature_queue()
        candidates = suggest_release_batch(queue, threshold, args.max_items)
        print_release_suggestion(candidates, threshold)
        return 0
    
    elif args.validate:
        results, success = validate.run_all_validations(
            db_url=db_url,
            skip_tests=args.skip_tests,
        )
        validate.print_validation_summary(results, success)
        return 0 if success else 1
    
    elif args.full_cycle:
        success = await full_release_cycle(
            threshold=threshold,
            max_items=args.max_items,
            auto_select=args.auto_select,
            dry_run=args.dry_run,
            yes=args.yes,
            db_url=db_url,
            github_token=github_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
            bump_type=args.bump_type,
        )
        return 0 if success else 1
    
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

