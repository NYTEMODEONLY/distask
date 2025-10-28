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


def _format_relative_time(iso_timestamp: Optional[str]) -> str:
    """Format timestamp as relative time (e.g., '3 days ago')."""
    if not iso_timestamp:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt

        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "just now"
    except (ValueError, AttributeError):
        return "Unknown"


def _create_progress_bar(current: int, total: int, length: int = 16) -> str:
    """Create a Unicode progress bar."""
    if total == 0:
        return "░" * length

    filled_length = int(length * current / total)
    bar = "█" * filled_length + "░" * (length - filled_length)
    return bar


def _get_column_emoji(column_name: str) -> str:
    """Get emoji for common column names."""
    name_lower = column_name.lower()
    emoji_map = {
        "to do": "📝",
        "todo": "📝",
        "backlog": "📋",
        "in progress": "⚙️",
        "in-progress": "⚙️",
        "doing": "⚙️",
        "working": "⚙️",
        "done": "✅",
        "complete": "✅",
        "completed": "✅",
        "finished": "✅",
        "review": "👀",
        "testing": "🧪",
        "blocked": "🚫",
        "on hold": "⏸️",
        "waiting": "⏳",
    }
    return emoji_map.get(name_lower, "📌")


def _calculate_board_health_color(stats: Dict[str, int]) -> discord.Color:
    """Determine embed color based on board health."""
    total = stats.get("total", 0)
    overdue = stats.get("overdue", 0)

    if total == 0:
        return discord.Color.from_rgb(118, 75, 162)  # Default blue-purple

    if overdue == 0:
        return discord.Color.from_rgb(46, 204, 113)  # Green - healthy
    elif overdue <= 5:
        return discord.Color.from_rgb(243, 156, 18)  # Yellow - some overdue
    elif overdue <= 10:
        return discord.Color.from_rgb(230, 126, 34)  # Orange - multiple overdue
    else:
        return discord.Color.from_rgb(231, 76, 60)  # Red - critical


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
        *,
        channel_mention: Optional[str] = None,
        creator_mention: Optional[str] = None,
    ) -> discord.Embed:
        """Create an enhanced, visually rich board detail embed."""
        # Determine embed color based on board health
        embed_color = _calculate_board_health_color(stats)

        # Create title with emoji
        title = f"📋 {board['name']} · #{board['id']}"

        # Build description with metadata
        description_parts = []
        if board.get("description"):
            description_parts.append(board["description"])

        # Add metadata line
        metadata = []
        if creator_mention:
            metadata.append(f"👤 {creator_mention}")
        if board.get("created_at"):
            time_ago = _format_relative_time(board["created_at"])
            metadata.append(f"📅 Created {time_ago}")
        if channel_mention:
            metadata.append(f"📢 {channel_mention}")

        if metadata:
            description_parts.append("\n" + " • ".join(metadata))

        description = "\n".join(description_parts) if description_parts else "No description"

        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color,
        )

        # Columns field with emojis and task counts
        if columns:
            column_breakdown = stats.get("column_breakdown", [])
            column_display = []

            for col in columns:
                emoji = _get_column_emoji(col["name"])
                # Find task count for this column
                task_count = 0
                for breakdown in column_breakdown:
                    if breakdown["name"] == col["name"]:
                        task_count = breakdown.get("task_count", 0)
                        break

                column_display.append(f"{emoji} **{col['name']}** ({task_count})")

            columns_value = "  •  ".join(column_display)
        else:
            columns_value = "No columns configured"

        embed.add_field(
            name="📋 Columns",
            value=columns_value,
            inline=False,
        )

        # Progress Overview
        total = stats.get("total", 0)
        completed = stats.get("completed", 0)
        active = stats.get("active", 0)
        overdue = stats.get("overdue", 0)

        if total > 0:
            # Progress bar
            percentage = int((completed / total) * 100)
            progress_bar = _create_progress_bar(completed, total, length=16)
            progress_text = f"{progress_bar} {percentage}% complete\n\n"

            # Stats line
            stats_parts = []
            if completed > 0:
                stats_parts.append(f"✅ **{completed}** completed")
            if active > 0:
                stats_parts.append(f"⏳ **{active}** active")
            if overdue > 0:
                stats_parts.append(f"🔴 **{overdue}** overdue")

            progress_text += "  •  ".join(stats_parts) if stats_parts else "No tasks"

            # Add activity indicator
            due_this_week = stats.get("due_this_week", 0)
            if due_this_week > 0:
                progress_text += f"\n⚡ **{due_this_week}** task{'s' if due_this_week != 1 else ''} due this week"

            embed.add_field(
                name="📊 Progress Overview",
                value=progress_text,
                inline=False,
            )

            # Task Distribution by column (if there are active tasks)
            if active > 0 and column_breakdown:
                distribution_lines = []
                for breakdown in column_breakdown:
                    col_name = breakdown["name"]
                    task_count = breakdown.get("task_count", 0)

                    if task_count > 0:
                        emoji = _get_column_emoji(col_name)
                        # Calculate percentage for this column
                        col_percentage = int((task_count / active) * 100) if active > 0 else 0
                        mini_bar = _create_progress_bar(task_count, active, length=8)
                        distribution_lines.append(
                            f"{emoji} {col_name:<12} {mini_bar} {col_percentage}% ({task_count})"
                        )

                if distribution_lines:
                    embed.add_field(
                        name="📌 Task Distribution",
                        value="\n".join(distribution_lines),
                        inline=False,
                    )
        else:
            # Empty board
            embed.add_field(
                name="📊 Progress Overview",
                value="No tasks yet. Use `/add-task` to create your first task!",
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
