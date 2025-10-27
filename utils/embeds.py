from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import discord

DATE_FORMAT = "%b %d, %Y %H:%M UTC"
FOOTER_TEXT = "distask.xyz"
DEFAULT_COLOR = discord.Color.from_rgb(118, 75, 162)


def _format_time(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime(DATE_FORMAT)
    except ValueError:
        return value


class EmbedFactory:
    def __init__(self, color: Optional[discord.Color] = None) -> None:
        self.color = color or DEFAULT_COLOR

    def _finalize(self, embed: discord.Embed) -> discord.Embed:
        embed.timestamp = datetime.now(timezone.utc)
        embed.set_footer(text=FOOTER_TEXT)
        return embed

    def message(
        self,
        title: str,
        description: str,
        *,
        emoji: Optional[str] = None,
        color: Optional[discord.Color] = None,
    ) -> discord.Embed:
        heading = f"{emoji} {title}" if emoji else title
        embed = discord.Embed(title=heading, description=description, color=color or self.color)
        return self._finalize(embed)

    def board_list(self, guild_name: str, boards: Iterable[Dict[str, Any]]) -> discord.Embed:
        embed = discord.Embed(
            title=f"Boards in {guild_name}",
            color=self.color,
            description="Use /view-board for details",
        )
        for board in boards:
            field_value = board.get("description") or "No description provided"
            embed.add_field(
                name=f"{board['name']} (ID {board['id']})",
                value=field_value[:500],
                inline=False,
            )
        if not embed.fields:
            embed.description = "No boards yet. Use /create-board to start."
        return self._finalize(embed)

    def board_detail(
        self,
        board: Dict[str, Any],
        columns: List[Dict[str, Any]],
        stats: Dict[str, int],
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{board['name']} (ID {board['id']})",
            description=board.get("description") or "—",
            color=self.color,
        )
        embed.add_field(
            name="Columns",
            value=", ".join(col["name"] for col in columns) or "No columns",
            inline=False,
        )
        embed.add_field(
            name="Stats",
            value=(
                f"Total Tasks: {stats.get('total', 0)}\n"
                f"Completed: {stats.get('completed', 0)}\n"
                f"Overdue: {stats.get('overdue', 0)}"
            ),
            inline=False,
        )
        return self._finalize(embed)

    def task_detail(
        self,
        task: Dict[str, Any],
        column_name: str,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Task #{task['id']}: {task['title']}",
            description=task.get("description") or "—",
            color=self.color,
        )
        embed.add_field(name="Column", value=column_name, inline=True)
        embed.add_field(name="Assignee", value=f"<@{task['assignee_id']}>" if task.get("assignee_id") else "Unassigned", inline=True)
        embed.add_field(name="Due", value=_format_time(task.get("due_date")), inline=True)
        embed.add_field(name="Completed", value="✅" if task.get("completed") else "❌", inline=True)
        return self._finalize(embed)

    def search_results(self, query: str, tasks: List[Dict[str, Any]]) -> discord.Embed:
        embed = discord.Embed(
            title=f"Search results for '{query}'",
            color=self.color,
        )
        for task in tasks:
            assignee = f"<@{task['assignee_id']}>" if task.get("assignee_id") else "—"
            embed.add_field(
                name=f"#{task['id']} · {task['title']} (Board {task['board_name']})",
                value=(
                    f"Column ID: {task['column_id']}\n"
                    f"Due: {_format_time(task.get('due_date'))}\n"
                    f"Assignee: {assignee}"
                ),
                inline=False,
            )
        if not tasks:
            embed.description = "No matches."
        return self._finalize(embed)

    def reminder_digest(self, guild_name: str, tasks: List[Dict[str, Any]]) -> discord.Embed:
        embed = discord.Embed(
            title=f"DisTask reminders · {guild_name}",
            color=discord.Color.orange(),
        )
        for task in tasks:
            assignee = f"<@{task['assignee_id']}>" if task.get("assignee_id") else "—"
            embed.add_field(
                name=f"#{task['id']} in {task['board_name']}",
                value=(
                    f"Title: {task['title']}\n"
                    f"Due: {_format_time(task.get('due_date'))}\n"
                    f"Assignee: {assignee}"
                ),
                inline=False,
            )
        if not tasks:
            embed.description = "All caught up!"
        return self._finalize(embed)
