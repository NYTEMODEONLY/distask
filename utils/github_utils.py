from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

import aiohttp

if TYPE_CHECKING:
    from .db import Database

LOGGER = logging.getLogger("distask.github")
GITHUB_API_BASE = "https://api.github.com"
FEATURE_REQUESTS_PATH = "feature_requests.md"


def _format_markdown(rows: Iterable[Dict[str, Any]]) -> str:
    header = (
        "| ID | User ID | Guild ID | Title | Suggestion | Suggested Priority | Status | Priority | Ease | Score | Upvotes | Downvotes | Duplicate Votes | Duplicate Of | Last Analyzed | Created At | Completed At |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    lines: List[str] = []
    for row in rows:
        lines.append(
            "| {id} | {user_id} | {guild_id} | {title} | {suggestion} | {suggested_priority} | {status} | {priority} | {ease} | {score} | {upvotes} | {downvotes} | {dup_votes} | {duplicate_of} | {last_analyzed} | {created_at} | {completed_at} |".format(
                id=_format_cell(row.get("id")),
                user_id=_format_cell(row.get("user_id")),
                guild_id=_format_cell(row.get("guild_id")),
                title=_format_cell(row.get("title")),
                suggestion=_format_cell(row.get("suggestion")),
                suggested_priority=_format_cell(row.get("suggested_priority")),
                status=_format_cell(row.get("status")),
                priority=_format_cell(row.get("priority")),
                ease=_format_cell(row.get("ease_of_implementation")),
                score=_format_cell(row.get("score")),
                upvotes=_format_cell(row.get("community_upvotes")),
                downvotes=_format_cell(row.get("community_downvotes")),
                dup_votes=_format_cell(row.get("community_duplicate_votes")),
                duplicate_of=_format_cell(row.get("duplicate_of")),
                last_analyzed=_format_cell(row.get("last_analyzed_at")),
                created_at=_format_cell(row.get("created_at")),
                completed_at=_format_cell(row.get("completed_at")),
            )
        )
    if not lines:
        lines.append("| - | - | - | No feature requests yet | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    return header + "\n".join(lines) + "\n"


def _format_cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = str(value)
    text = text.replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text if text else "-"


async def export_to_github(
    db: "Database",
    *,
    token: Optional[str],
    owner: Optional[str],
    repo: Optional[str],
) -> None:
    """Export feature requests to GitHub as a Markdown file."""
    if not token or not owner or not repo:
        LOGGER.warning("Missing GitHub configuration; skipping feature request export.")
        return

    rows = await db.fetch_feature_requests()
    content = _format_markdown(rows)
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{FEATURE_REQUESTS_PATH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DisTask-Bot",
    }

    sha: Optional[str] = None
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    payload = await response.json()
                    sha = payload.get("sha")
                elif response.status == 404:
                    sha = None
                else:
                    text = await response.text()
                    LOGGER.error("Failed to fetch %s from GitHub (%s): %s", FEATURE_REQUESTS_PATH, response.status, text)
                    return

            commit_message = f"Update feature requests [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}]"
            body: Dict[str, Any] = {
                "message": commit_message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            }
            if sha:
                body["sha"] = sha

            async with session.put(url, headers=headers, json=body) as response:
                if response.status not in (200, 201):
                    text = await response.text()
                    LOGGER.error("Failed to upsert %s on GitHub (%s): %s", FEATURE_REQUESTS_PATH, response.status, text)
        except aiohttp.ClientError as exc:
            LOGGER.error("GitHub export failed: %s", exc)
