from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import sys
import math

import aiohttp
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import Database
from utils.github_utils import export_to_github
STATE_PATH = ROOT_DIR / "data" / "feature_agent_state.json"
OUTPUT_DIR = ROOT_DIR / "automation"
OUTPUT_JSON = OUTPUT_DIR / "feature_queue.json"
OUTPUT_MD = OUTPUT_DIR / "feature_queue.md"

DUPLICATE_THRESHOLD = 90.0
SIMILAR_THRESHOLD = 78.0

COMMIT_PATTERNS = [
    re.compile(r"FR-(\d+)", re.IGNORECASE),
    re.compile(r"feature-request[^\d]*(\d+)", re.IGNORECASE),
    re.compile(r"feature[/_-](\d+)", re.IGNORECASE),
]


@dataclass
class FeatureRequest:
    id: int
    title: str
    suggestion: str
    status: str
    priority: Optional[int]
    ease: Optional[int]
    created_at: Optional[datetime]
    duplicate_of: Optional[int]
    last_analyzed_at: Optional[datetime]
    community_message_id: Optional[int]
    community_channel_id: Optional[int]
    community_upvotes: int
    community_downvotes: int
    community_duplicate_votes: int

    @property
    def combined_text(self) -> str:
        return f"{self.title.strip()} {self.suggestion.strip()}".strip()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def load_feature_requests(db: Optional[Database]) -> List[Dict[str, object]]:
    if db is not None:
        try:
            rows = await db.fetch_feature_requests()
            if rows:
                return rows
        except Exception as exc:
            logging.error("Failed to fetch feature requests from DB: %s", exc)
    markdown_path = ROOT_DIR / "feature_requests.md"
    if not markdown_path.exists():
        raise RuntimeError("No feature request data available (DB unavailable and feature_requests.md missing).")
    logging.info("Falling back to reading %s", markdown_path)
    return parse_markdown(markdown_path.read_text())


def parse_markdown(content: str) -> List[Dict[str, object]]:
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("| ---")]
    rows: List[Dict[str, object]] = []
    if not lines:
        return rows
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]
    for raw in lines[1:]:
        parts = [part.strip() or None for part in raw.split("|")]
        if len(parts) < len(headers):
            continue
        record = dict(zip(headers, parts))
        try:
            record["id"] = int(record.get("ID") or record.get("Id") or record.get("id"))
        except (TypeError, ValueError):
            continue
        rows.append(record)
    return rows


def to_model(rows: Iterable[Dict[str, object]]) -> List[FeatureRequest]:
    models: List[FeatureRequest] = []
    for row in rows:
        models.append(
            FeatureRequest(
                id=int(row["id"]),
                title=str(row.get("title") or row.get("Title") or ""),
                suggestion=str(row.get("suggestion") or row.get("Suggestion") or ""),
                status=str(row.get("status") or row.get("Status") or "pending"),
                priority=_safe_int(row.get("priority")),
                ease=_safe_int(row.get("ease_of_implementation") or row.get("Ease")),
                created_at=_safe_datetime(row.get("created_at") or row.get("Created At")),
                duplicate_of=_safe_int(row.get("duplicate_of") or row.get("Duplicate Of")),
                last_analyzed_at=_safe_datetime(row.get("last_analyzed_at") or row.get("Last Analyzed")),
                community_message_id=_safe_int(row.get("community_message_id") or row.get("Community Message Id")),
                community_channel_id=_safe_int(row.get("community_channel_id") or row.get("Community Channel Id")),
                community_upvotes=_safe_int(row.get("community_upvotes") or row.get("Community Upvotes")) or 0,
                community_downvotes=_safe_int(row.get("community_downvotes") or row.get("Community Downvotes")) or 0,
                community_duplicate_votes=_safe_int(row.get("community_duplicate_votes") or row.get("Community Duplicate Votes")) or 0,
            )
        )
    return models


def _safe_int(value: object) -> Optional[int]:
    if value is None or value == "-" or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime(value: object) -> Optional[datetime]:
    if not value or value == "-":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def find_duplicate_candidates(requests: List[FeatureRequest]) -> Tuple[List[Tuple[FeatureRequest, FeatureRequest, float]], Dict[int, List[int]]]:
    duplicates: List[Tuple[FeatureRequest, FeatureRequest, float]] = []
    similar_map: Dict[int, List[int]] = {}
    active = [req for req in requests if req.status in {"pending", "in_progress"}]
    for idx, left in enumerate(active):
        for right in active[idx + 1 :]:
            if left.duplicate_of or right.duplicate_of:
                continue
            if left.id == right.id:
                continue
            score = similarity_score(left.combined_text, right.combined_text)
            if score >= DUPLICATE_THRESHOLD:
                older, newer = (left, right) if _is_older(left, right) else (right, left)
                duplicates.append((newer, older, score))
            elif score >= SIMILAR_THRESHOLD:
                similar_map.setdefault(left.id, []).append(right.id)
                similar_map.setdefault(right.id, []).append(left.id)
    return duplicates, similar_map


def _is_older(a: FeatureRequest, b: FeatureRequest) -> bool:
    if a.created_at and b.created_at:
        return a.created_at <= b.created_at
    return a.id <= b.id


def compute_priority_score(req: FeatureRequest) -> Tuple[float, Dict[str, float]]:
    priority = req.priority if req.priority is not None else 5
    ease = req.ease if req.ease is not None else 5
    net_votes = max(req.community_upvotes - req.community_downvotes, 0)
    vote_bonus = math.log1p(net_votes) * 2.0
    duplicate_penalty = math.log1p(max(req.community_duplicate_votes, 0)) * 1.5
    score = float(priority + ease + vote_bonus - duplicate_penalty)
    return score, {
        "priority": float(priority),
        "ease": float(ease),
        "vote_bonus": vote_bonus,
        "duplicate_penalty": duplicate_penalty,
        "net_votes": float(net_votes),
        "upvotes": float(req.community_upvotes),
        "downvotes": float(req.community_downvotes),
        "dup_votes": float(req.community_duplicate_votes),
    }


def build_queue_from_models(models: Iterable[FeatureRequest]) -> List[Dict[str, object]]:
    queue: List[Dict[str, object]] = []
    for model in models:
        score, components = compute_priority_score(model)
        if model.status not in {"pending", "in_progress"} or model.duplicate_of:
            continue
        notes_parts = []
        if components["vote_bonus"] > 0:
            notes_parts.append(f"votes +{components['vote_bonus']:.2f}")
        if components["duplicate_penalty"] > 0:
            notes_parts.append(f"dup -{components['duplicate_penalty']:.2f}")
        notes = ", ".join(notes_parts) if notes_parts else None
        queue.append(
            {
                "id": model.id,
                "title": model.title,
                "score": score,
                "priority": components["priority"],
                "ease": components["ease"],
                "status": model.status,
                "duplicate_of": model.duplicate_of,
                "votes": {
                    "up": model.community_upvotes,
                    "down": model.community_downvotes,
                    "duplicate": model.community_duplicate_votes,
                    "net": int(components["net_votes"]),
                },
                "components": components,
                "notes": notes,
            }
        )
    queue.sort(key=lambda item: (-item["score"], item["id"]))
    return queue


def similarity_score(left: str, right: str) -> float:
    left_tokens = " ".join(sorted(set(left.lower().split())))
    right_tokens = " ".join(sorted(set(right.lower().split())))
    return SequenceMatcher(None, left_tokens, right_tokens).ratio() * 100.0


def load_state() -> Dict[str, object]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            logging.warning("State file %s is invalid JSON, ignoring.", STATE_PATH)
    return {}


def save_state(data: Dict[str, object]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2))


def get_commit_range(last_commit: Optional[str]) -> List[Dict[str, str]]:
    args = ["git", "log", "--pretty=format:%H%x1f%ct%x1f%s"]
    if last_commit:
        args.insert(2, f"{last_commit}..HEAD")
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logging.error("git log failed: %s", result.stderr)
        return []
    commits: List[Dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        commit_hash, timestamp, message = parts
        commits.append({"hash": commit_hash, "timestamp": timestamp, "message": message})
    commits.reverse()
    return commits


def extract_feature_ids(message: str) -> List[int]:
    ids: List[int] = []
    for pattern in COMMIT_PATTERNS:
        for match in pattern.findall(message):
            try:
                ids.append(int(match))
            except ValueError:
                continue
    return list(sorted(set(ids)))


async def scan_github_prs(
    token: str,
    owner: str,
    repo: str,
    last_pr_number: Optional[int],
) -> List[Dict[str, str]]:
    """
    Scan merged GitHub PRs for FR markers.
    Returns list of PRs with extracted feature IDs.
    """
    prs: List[Dict[str, str]] = []
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DisTask-Feature-Agent",
    }
    params: Dict[str, str] = {
        "state": "closed",
        "sort": "updated",
        "direction": "desc",
        "per_page": "100",
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            page = 1
            while True:
                params["page"] = str(page)
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 403:
                        logging.warning("GitHub API rate limit hit; skipping PR scan")
                        break
                    if response.status != 200:
                        text = await response.text()
                        logging.error("Failed to fetch PRs from GitHub (%s): %s", response.status, text)
                        break
                    
                    pr_list = await response.json()
                    if not pr_list:
                        break
                    
                    for pr in pr_list:
                        # Only process merged PRs
                        if not pr.get("merged_at"):
                            continue
                        
                        pr_number = pr.get("number")
                        if pr_number is None:
                            continue
                        
                        # Stop if we've reached PRs we've already processed
                        if last_pr_number and pr_number <= last_pr_number:
                            return prs
                        
                        # Extract feature IDs from title and body
                        title = pr.get("title", "")
                        body = pr.get("body", "") or ""
                        merge_commit_sha = pr.get("merge_commit_sha")
                        
                        # Combine title and body for scanning
                        combined_text = f"{title}\n{body}"
                        feature_ids = extract_feature_ids(combined_text)
                        
                        if feature_ids:
                            prs.append({
                                "number": str(pr_number),
                                "title": title,
                                "merge_commit_sha": merge_commit_sha or "",
                                "merged_at": pr.get("merged_at", ""),
                                "feature_ids": ",".join(str(fid) for fid in feature_ids),
                            })
                    
                    # If we got fewer than per_page, we're done
                    if len(pr_list) < 100:
                        break
                    page += 1
                    
        except aiohttp.ClientError as exc:
            logging.error("GitHub API error while scanning PRs: %s", exc)
    
    return prs


def write_outputs(queue: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({"generated_at": utcnow_iso(), "items": queue}, indent=2))
    OUTPUT_MD.write_text(build_markdown(queue))


def build_markdown(queue: List[Dict[str, object]]) -> str:
    header = (
        "| Rank | ID | Title | Score | Priority | Ease | Net Votes | Status | Duplicate Of | Notes |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    lines = []
    for idx, item in enumerate(queue, start=1):
        votes = item.get("votes") or {}
        net_votes = votes.get("net", 0)
        lines.append(
            "| {rank} | {id} | {title} | {score} | {priority} | {ease} | {net} | {status} | {duplicate} | {notes} |".format(
                rank=idx,
                id=item["id"],
                title=_escape_markdown(item["title"]),
                score=item["score"],
                priority=item["priority"],
                ease=item["ease"],
                net=net_votes,
                status=item["status"],
                duplicate=item.get("duplicate_of") or "-",
                notes=_escape_markdown(item.get("notes") or "-"),
            )
        )
    if not lines:
        lines.append("| - | - | No feature requests | - | - | - | - | - | - | - |")
    return header + "\n".join(lines) + "\n"


def _escape_markdown(text: str) -> str:
    text = text.replace("|", "\\|")
    return text.replace("\n", "<br>")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    load_dotenv()

    database_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("database_url")
        or "postgresql://distask:distaskpass@localhost:5432/distask"
    )
    db: Optional[Database] = None
    db_ready = False
    try:
        db = Database(database_url)
        await db.init()
        db_ready = True
    except Exception as exc:
        logging.error("Database initialisation failed: %s", exc)

    try:
        try:
            raw_rows = await load_feature_requests(db if db_ready else None)
        except RuntimeError as exc:
            logging.error("%s", exc)
            return

        requests = to_model(raw_rows)

        if not db_ready or db is None:
            queue = build_queue_from_models(requests)
            write_outputs(queue)
            save_state(
                {
                    "last_commit": _get_head_commit(),
                    "last_run_at": utcnow_iso(),
                    "queue_count": len(queue),
                    "db_connected": False,
                }
            )
            logging.warning("Database unavailable; generated local queue only.")
            return

        duplicates, similar_map = find_duplicate_candidates(requests)
        logging.info("Identified %d exact duplicates and %d requests with similar candidates.", len(duplicates), len(similar_map))

        for duplicate, parent, score in duplicates:
            if duplicate.duplicate_of == parent.id:
                continue
            logging.info("Marking #%s as duplicate of #%s (score %.1f)", duplicate.id, parent.id, score)
            await db.mark_feature_duplicate(
                duplicate.id,
                parent_id=parent.id,
                confidence=score,
                note=f"Auto-detected duplicate of {parent.id} (score {score:.1f})",
            )

        for request_id, candidate_ids in similar_map.items():
            logging.info("Logging similar candidates for #%s -> %s", request_id, candidate_ids)
            await db.set_similar_candidates(request_id, candidate_ids)

        # Refresh state after updates
        refreshed_rows = await db.fetch_feature_requests()
        refreshed_models = to_model(refreshed_rows)

        queue = build_queue_from_models(refreshed_models)
        for item in queue:
            components = item.get("components") or {}
            votes = item.get("votes") or {}
            await db.set_feature_score(
                item["id"],
                score=item["score"],
                priority_value=item["priority"],
                ease_value=item["ease"],
                vote_bonus=components.get("vote_bonus"),
                duplicate_penalty=components.get("duplicate_penalty"),
                net_votes=int(components.get("net_votes", 0)),
                upvotes=votes.get("up"),
                downvotes=votes.get("down"),
                duplicate_votes=votes.get("duplicate"),
            )

        write_outputs(queue)

        # Sync with git history and GitHub PRs
        state = load_state()
        last_commit = state.get("last_commit")
        last_pr_number = state.get("last_pr_number")
        
        completed_ids: List[int] = []
        
        # Process commits
        commits = get_commit_range(last_commit)
        for commit in commits:
            commit_ids = extract_feature_ids(commit["message"])
            if not commit_ids:
                continue
            for feature_id in commit_ids:
                logging.info("Marking feature #%s as completed via commit %s", feature_id, commit["hash"])
                await db.mark_feature_completed(
                    feature_id,
                    commit_hash=commit["hash"],
                    commit_message=commit["message"],
                )
                completed_ids.append(feature_id)
        
        # Process merged PRs (if GitHub credentials available)
        github_token = os.getenv("GITHUB_TOKEN") or os.getenv("github_token")
        repo_owner = os.getenv("REPO_OWNER") or os.getenv("repo_owner")
        repo_name = os.getenv("REPO_NAME") or os.getenv("repo_name")
        
        if github_token and repo_owner and repo_name:
            try:
                prs = await scan_github_prs(github_token, repo_owner, repo_name, last_pr_number)
                max_pr_number = last_pr_number or 0
                
                for pr in prs:
                    pr_number = int(pr["number"])
                    if pr_number > max_pr_number:
                        max_pr_number = pr_number
                    
                    feature_ids_str = pr.get("feature_ids", "")
                    if not feature_ids_str:
                        continue
                    
                    feature_ids = [int(fid.strip()) for fid in feature_ids_str.split(",") if fid.strip().isdigit()]
                    merge_commit_sha = pr.get("merge_commit_sha", "")
                    pr_title = pr.get("title", "")
                    
                    for feature_id in feature_ids:
                        # Check if already marked via commit scan
                        if feature_id not in completed_ids:
                            logging.info("Marking feature #%s as completed via PR #%s (%s)", feature_id, pr_number, merge_commit_sha)
                            await db.mark_feature_completed(
                                feature_id,
                                commit_hash=merge_commit_sha,
                                commit_message=f"PR #{pr_number}: {pr_title}",
                            )
                            completed_ids.append(feature_id)
                        else:
                            logging.debug("Feature #%s already marked via commit, skipping PR #%s", feature_id, pr_number)
                
                last_pr_number = max_pr_number
            except Exception as exc:
                logging.error("Failed to scan GitHub PRs: %s", exc)
        else:
            logging.debug("GitHub credentials not configured; skipping PR scan")

        head_commit = _get_head_commit()
        save_state(
            {
                "last_commit": head_commit,
                "last_pr_number": last_pr_number,
                "last_run_at": utcnow_iso(),
                "completed_ids": completed_ids,
                "queue_count": len(queue),
            }
        )

        # Export feature requests to GitHub (reuse credentials from PR scan)
        if github_token and repo_owner and repo_name:
            await export_to_github(
                db,
                token=github_token,
                owner=repo_owner,
                repo=repo_name,
            )
    finally:
        if db_ready and db is not None:
            await db.close()


def _get_head_commit() -> Optional[str]:
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logging.error("git rev-parse failed: %s", result.stderr)
        return None
    return result.stdout.strip()


if __name__ == "__main__":
    asyncio.run(main())
