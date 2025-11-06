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
    """Format timestamp as relative time (e.g., '3 days ago' or 'in 3 days')."""
    if not iso_timestamp:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        abs_delta = abs(delta)

        # Handle future dates (negative delta)
        if delta.total_seconds() < 0:
            # Future date - use "in X time"
            if abs_delta.days > 365:
                years = abs_delta.days // 365
                return f"in {years} year{'s' if years != 1 else ''}"
            elif abs_delta.days > 30:
                months = abs_delta.days // 30
                return f"in {months} month{'s' if months != 1 else ''}"
            elif abs_delta.days > 0:
                return f"in {abs_delta.days} day{'s' if abs_delta.days != 1 else ''}"
            elif abs_delta.seconds > 3600:
                hours = abs_delta.seconds // 3600
                return f"in {hours} hour{'s' if hours != 1 else ''}"
            elif abs_delta.seconds > 60:
                minutes = abs_delta.seconds // 60
                return f"in {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                return "soon"
        
        # Handle past dates (positive delta)
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


def _calculate_task_status_color(task: Dict[str, Any]) -> discord.Color:
    """Determine embed color based on task status (completed, due soon, overdue)."""
    if task.get("completed"):
        return discord.Color.from_rgb(46, 204, 113)  # Green - completed
    
    due_date = task.get("due_date")
    if not due_date:
        return discord.Color.from_rgb(118, 75, 162)  # Default blue-purple
    
    try:
        dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = dt - now
        
        if delta.days < 0:
            return discord.Color.from_rgb(231, 76, 60)  # Red - overdue
        elif delta.days <= 1:
            return discord.Color.from_rgb(243, 156, 18)  # Yellow - due soon
        else:
            return discord.Color.from_rgb(118, 75, 162)  # Default blue-purple
    except (ValueError, AttributeError):
        return discord.Color.from_rgb(118, 75, 162)  # Default blue-purple


def _format_assignees(task: Dict[str, Any]) -> str:
    """Format assignees for display, supporting both single (backwards compat) and multiple assignees."""
    # Check for new assignee_ids list first (preferred)
    assignee_ids = task.get("assignee_ids")
    if assignee_ids and isinstance(assignee_ids, list) and len(assignee_ids) > 0:
        # Multiple assignees
        mentions = [f"<@{user_id}>" for user_id in assignee_ids]
        if len(mentions) == 1:
            return f"👤 {mentions[0]}"
        elif len(mentions) <= 3:
            return f"👥 {', '.join(mentions)}"
        else:
            return f"👥 {', '.join(mentions[:3])} +{len(mentions) - 3} more"
    
    # Backwards compatibility: check legacy assignee_id
    assignee_id = task.get("assignee_id")
    if assignee_id:
        return f"👤 <@{assignee_id}>"
    
    return "👤 Unassigned"


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
        """Create a standardized message embed with emoji title and appropriate color."""
        # Always include emoji in title if provided
        heading = f"{emoji} {title}" if emoji else title
        
        # Determine color based on emoji type if not explicitly provided
        if color is None:
            if emoji:
                if emoji in ["✅", "✨", "🎉", "👍"]:
                    color = discord.Color.from_rgb(46, 204, 113)  # Green - success
                elif emoji in ["⚠️", "🛑", "🔔"]:
                    color = discord.Color.from_rgb(243, 156, 18)  # Yellow - warning
                elif emoji in ["🔥", "❌", "🚫"]:
                    color = discord.Color.from_rgb(231, 76, 60)  # Red - error
                elif emoji in ["📋", "📊", "📌", "📝", "🗂️"]:
                    color = discord.Color.from_rgb(118, 75, 162)  # Default blue-purple
                else:
                    color = self.color
            else:
                color = self.color
        
        embed = discord.Embed(title=heading, description=description, color=color)
        return self._finalize(embed)

    def board_list(self, guild_name: str, boards: Iterable[Dict[str, Any]]) -> discord.Embed:
        """Create an enhanced board list embed with emoji indicators and formatting."""
        boards_list = list(boards)
        board_count = len(boards_list)
        
        embed = discord.Embed(
            title=f"📋 Boards in {guild_name}",
            color=self.color,
            description=f"Found **{board_count}** board{'s' if board_count != 1 else ''}. Use `/view-board` for detailed information.",
        )
        
        for board in boards_list:
            description = board.get("description") or "No description provided"
            # Truncate description for display
            if len(description) > 300:
                description = description[:297] + "..."
            
            # Build field value with metadata
            field_parts = [description]
            
            # Add metadata if available
            metadata_parts = []
            if board.get("created_at"):
                time_ago = _format_relative_time(board["created_at"])
                metadata_parts.append(f"📅 Created {time_ago}")
            
            if metadata_parts:
                field_parts.append("\n" + " • ".join(metadata_parts))
            
            embed.add_field(
                name=f"📋 {board['name']} · #{board['id']}",
                value="\n".join(field_parts),
                inline=False,
            )
        
        if not embed.fields:
            embed.description = "📭 No boards yet. Use `/create-board` to start managing your tasks!"
        
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
        """Create an enhanced task detail embed with visual indicators and status-based coloring."""
        # Determine color based on task status
        embed_color = _calculate_task_status_color(task)
        
        # Build title with emoji and ID
        status_emoji = "✅" if task.get("completed") else "📋"
        title = f"{status_emoji} Task #{task['id']}: {task['title']}"
        
        # Build description with task description
        description = task.get("description") or "—"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color,
        )
        
        # Add metadata line
        metadata_parts = []
        if task.get("created_at"):
            time_ago = _format_relative_time(task["created_at"])
            metadata_parts.append(f"📅 Created {time_ago}")
        if task.get("created_by"):
            metadata_parts.append(f"👤 <@{task['created_by']}>")
        
        if metadata_parts:
            embed.description += "\n\n" + " • ".join(metadata_parts)
        
        # Column with emoji indicator
        column_emoji = _get_column_emoji(column_name)
        embed.add_field(
            name="📋 Column",
            value=f"{column_emoji} {column_name}",
            inline=True,
        )
        
        # Assignee(s) with emoji
        assignee_value = _format_assignees(task)
        assignee_ids = task.get("assignee_ids", [])
        assignee_id = task.get("assignee_id")
        is_multiple = (isinstance(assignee_ids, list) and len(assignee_ids) > 1) or (not assignee_ids and assignee_id)
        embed.add_field(
            name="👥 Assignee" + ("s" if is_multiple else ""),
            value=assignee_value,
            inline=True,
        )
        
        # Due date with emoji and relative time
        due_date = task.get("due_date")
        if due_date:
            formatted_time = _format_time(due_date)
            relative_time = _format_relative_time(due_date)
            # Check if overdue
            try:
                dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                is_overdue = dt < now and not task.get("completed")
                due_emoji = "🔴" if is_overdue else "📅"
                due_value = f"{due_emoji} {formatted_time}\n({relative_time})"
            except (ValueError, AttributeError):
                due_value = f"📅 {formatted_time}"
        else:
            due_value = "📅 No due date"
        
        embed.add_field(
            name="⏰ Due Date",
            value=due_value,
            inline=True,
        )
        
        # Status with emoji
        completed = task.get("completed", False)
        status_value = "✅ Completed" if completed else "⏳ In Progress"
        embed.add_field(
            name="📊 Status",
            value=status_value,
            inline=True,
        )
        
        # Completion notes if task is completed
        completion_notes = task.get("completion_notes")
        if completed and completion_notes:
            embed.add_field(
                name="📝 Completion Notes",
                value=completion_notes,
                inline=False,
            )
        
        return self._finalize(embed)

    def search_results(self, query: str, tasks: List[Dict[str, Any]]) -> discord.Embed:
        """Create an enhanced search results embed with emoji indicators and better formatting."""
        task_count = len(tasks)
        
        embed = discord.Embed(
            title=f"🔍 Search Results · '{query}'",
            description=f"Found **{task_count}** matching task{'s' if task_count != 1 else ''}.",
            color=self.color,
        )
        
        for task in tasks[:10]:  # Limit to 10 results to avoid embed limits
            # Determine status indicators
            completed = task.get("completed", False)
            status_emoji = "✅" if completed else "📋"
            
            # Get column name if available
            column_name = task.get("column_name", f"Column #{task.get('column_id', '?')}")
            column_emoji = _get_column_emoji(column_name)
            
            # Build field name with emoji and board info
            field_name = f"{status_emoji} #{task['id']} · {task['title']}"
            
            # Build field value with structured information
            value_parts = []
            
            # Board and column
            value_parts.append(f"📋 **Board:** {task.get('board_name', 'Unknown')}")
            value_parts.append(f"{column_emoji} **Column:** {column_name}")
            
            # Due date
            due_date = task.get("due_date")
            if due_date:
                formatted_time = _format_time(due_date)
                relative_time = _format_relative_time(due_date)
                # Check if overdue
                try:
                    dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    is_overdue = dt < now and not completed
                    due_emoji = "🔴" if is_overdue else "📅"
                    value_parts.append(f"{due_emoji} **Due:** {formatted_time} ({relative_time})")
                except (ValueError, AttributeError):
                    value_parts.append(f"📅 **Due:** {formatted_time}")
            else:
                value_parts.append("📅 **Due:** No due date")
            
            # Assignee(s)
            assignee = _format_assignees(task)
            value_parts.append(assignee)
            
            embed.add_field(
                name=field_name,
                value="\n".join(value_parts),
                inline=False,
            )
        
        if task_count > 10:
            embed.set_footer(text=f"Showing first 10 of {task_count} results. Refine your search for more specific results.")
        
        if not tasks:
            embed.description = "❌ No matches found. Try a different search query or use `/list-tasks` to browse all tasks."
            embed.color = discord.Color.from_rgb(243, 156, 18)  # Yellow for no results
        
        return self._finalize(embed)

    def reminder_digest(self, guild_name: str, tasks: List[Dict[str, Any]]) -> discord.Embed:
        """Create an enhanced reminder digest embed with urgency grouping and visual indicators."""
        now = datetime.now(timezone.utc)
        overdue_tasks = []
        due_today_tasks = []
        due_this_week_tasks = []
        
        # Categorize tasks by urgency
        for task in tasks:
            due_date = task.get("due_date")
            if not due_date:
                continue
            
            try:
                dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                delta = dt - now
                
                if delta.days < 0:
                    overdue_tasks.append(task)
                elif delta.days == 0:
                    due_today_tasks.append(task)
                elif delta.days <= 7:
                    due_this_week_tasks.append(task)
            except (ValueError, AttributeError):
                # If we can't parse, include in this week's tasks
                due_this_week_tasks.append(task)
        
        total_count = len(tasks)
        overdue_count = len(overdue_tasks)
        today_count = len(due_today_tasks)
        week_count = len(due_this_week_tasks)
        
        # Determine color based on urgency
        if overdue_count > 0:
            embed_color = discord.Color.from_rgb(231, 76, 60)  # Red - critical
        elif today_count > 0:
            embed_color = discord.Color.from_rgb(243, 156, 18)  # Yellow - urgent
        else:
            embed_color = discord.Color.from_rgb(230, 126, 34)  # Orange - reminders
        
        # Build title with summary
        summary_parts = []
        if overdue_count > 0:
            summary_parts.append(f"🔴 {overdue_count} overdue")
        if today_count > 0:
            summary_parts.append(f"⚡ {today_count} due today")
        if week_count > 0:
            summary_parts.append(f"📅 {week_count} due this week")
        
        title = f"⏰ Daily Reminders · {guild_name}"
        if summary_parts:
            title += f"\n{', '.join(summary_parts)}"
        
        embed = discord.Embed(
            title=title,
            description=f"**{total_count}** task{'s' if total_count != 1 else ''} need{'s' if total_count == 1 else ''} your attention.",
            color=embed_color,
        )
        
        # Add overdue tasks first (highest priority)
        if overdue_tasks:
            for task in overdue_tasks[:5]:  # Limit to 5 per category
                task_line = self._format_reminder_task(task, is_overdue=True)
                embed.add_field(
                    name=f"🔴 Overdue · #{task['id']}",
                    value=task_line,
                    inline=False,
                )
            if len(overdue_tasks) > 5:
                embed.add_field(
                    name="🔴 More Overdue Tasks",
                    value=f"...and {len(overdue_tasks) - 5} more overdue task{'s' if len(overdue_tasks) - 5 != 1 else ''}",
                    inline=False,
                )
        
        # Add due today tasks
        if due_today_tasks:
            for task in due_today_tasks[:5]:
                task_line = self._format_reminder_task(task, is_urgent=True)
                embed.add_field(
                    name=f"⚡ Due Today · #{task['id']}",
                    value=task_line,
                    inline=False,
                )
            if len(due_today_tasks) > 5:
                embed.add_field(
                    name="⚡ More Due Today",
                    value=f"...and {len(due_today_tasks) - 5} more task{'s' if len(due_today_tasks) - 5 != 1 else ''}",
                    inline=False,
                )
        
        # Add due this week tasks
        if due_this_week_tasks:
            for task in due_this_week_tasks[:5]:
                task_line = self._format_reminder_task(task)
                embed.add_field(
                    name=f"📅 Due This Week · #{task['id']}",
                    value=task_line,
                    inline=False,
                )
            if len(due_this_week_tasks) > 5:
                embed.add_field(
                    name="📅 More Due This Week",
                    value=f"...and {len(due_this_week_tasks) - 5} more task{'s' if len(due_this_week_tasks) - 5 != 1 else ''}",
                    inline=False,
                )
        
        if not tasks:
            embed.description = "🎉 All caught up! No tasks due right now."
            embed.color = discord.Color.from_rgb(46, 204, 113)  # Green - all good
        
        return self._finalize(embed)
    
    def _format_reminder_task(self, task: Dict[str, Any], *, is_overdue: bool = False, is_urgent: bool = False) -> str:
        """Helper to format a task for reminder digest."""
        parts = []
        
        # Title and board
        parts.append(f"**{task['title']}**")
        parts.append(f"📋 Board: {task.get('board_name', 'Unknown')}")
        
        # Column if available (may not be present in all queries)
        column_name = task.get("column_name")
        if column_name:
            column_emoji = _get_column_emoji(column_name)
            parts.append(f"{column_emoji} Column: {column_name}")
        elif task.get("column_id"):
            # Fallback to column ID if name not available
            parts.append(f"📌 Column ID: {task['column_id']}")
        
        # Due date with relative time
        due_date = task.get("due_date")
        if due_date:
            formatted_time = _format_time(due_date)
            relative_time = _format_relative_time(due_date)
            if is_overdue:
                parts.append(f"🔴 Overdue: {formatted_time} ({relative_time})")
            elif is_urgent:
                parts.append(f"⚡ Due: {formatted_time} ({relative_time})")
            else:
                parts.append(f"📅 Due: {formatted_time} ({relative_time})")
        
        # Assignee(s)
        assignee = _format_assignees(task)
        parts.append(assignee)
        
        return "\n".join(parts)
