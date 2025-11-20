"""Enhanced notification scheduler with multiple specialized engines.

This module provides:
- DueDateReminderEngine: Sends reminders before/at due dates
- DigestEngine: Generates daily/weekly task digests
- EscalationEngine: Increases frequency for overdue tasks
- SnoozedReminderEngine: Processes snoozed reminders
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord
import pytz

from utils.db import Database, ISO_FORMAT
from utils.notifications import NotificationRouter
from utils.preference_manager import PreferenceManager

if TYPE_CHECKING:
    from discord.ext import commands

logger = logging.getLogger(__name__)


class DueDateReminderEngine:
    """Handles due date reminders with timezone awareness and pre-warnings."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        router: NotificationRouter,
        pref_manager: PreferenceManager,
    ) -> None:
        self.bot = bot
        self.db = db
        self.router = router
        self.pref_manager = pref_manager

    async def run(self) -> None:
        """Check for tasks approaching their due dates and send reminders."""
        logger.debug("DueDateReminderEngine: Checking for upcoming due dates")

        # Get all tasks with due dates that aren't completed
        now = datetime.now(timezone.utc)

        # Check tasks due in the next 7 days
        future_window = (now + timedelta(days=7)).strftime(ISO_FORMAT)
        tasks = await self.db.fetch_due_tasks(future_window)

        for task in tasks:
            assignee_ids = task.get("assignee_ids", [])
            if not assignee_ids:
                continue

            task_due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            time_until_due = task_due_date - now

            for assignee_id in assignee_ids:
                # Get user's preferred advance reminder days
                advance_days = await self.pref_manager.get_due_date_advance_days(
                    assignee_id,
                    task["guild_id"],
                )

                # Check if we should send a reminder based on advance days
                days_until_due = time_until_due.days
                hours_until_due = time_until_due.total_seconds() / 3600

                should_remind = False
                reminder_message = ""

                if days_until_due in advance_days:
                    should_remind = True
                    reminder_message = f"Due in {days_until_due} day{'s' if days_until_due != 1 else ''}"
                elif days_until_due == 0 and hours_until_due > 0 and hours_until_due < 24:
                    should_remind = True
                    reminder_message = f"Due today (<t:{int(task_due_date.timestamp())}:R>)"
                elif time_until_due.total_seconds() < 0:
                    # Task is overdue - let EscalationEngine handle this
                    continue

                if should_remind:
                    # Check if we already sent this reminder
                    if await self.db.check_notification_sent(
                        assignee_id,
                        task["id"],
                        "due_date",
                        within_hours=12,
                    ):
                        continue

                    # Create reminder embed
                    embed = discord.Embed(
                        title="🔔 Task Due Soon",
                        description=reminder_message,
                        color=discord.Color.orange(),
                    )
                    embed.add_field(
                        name="Task",
                        value=task.get("title", "Unknown"),
                        inline=False,
                    )

                    if task.get("description"):
                        desc = task["description"][:100] + "..." if len(task["description"]) > 100 else task["description"]
                        embed.add_field(name="Description", value=desc, inline=False)

                    embed.add_field(
                        name="Due Date",
                        value=f"<t:{int(task_due_date.timestamp())}:F>",
                        inline=True,
                    )
                    embed.add_field(
                        name="Board",
                        value=task.get("board_name", "Unknown"),
                        inline=True,
                    )

                    # Add action buttons
                    from cogs.ui.views import NotificationActionView
                    view = NotificationActionView(
                        task_id=task["id"],
                        notification_type="due_date",
                    )

                    # Send reminder
                    await self.router.send_notification(
                        user_id=assignee_id,
                        guild_id=task["guild_id"],
                        embed=embed,
                        notification_type="due_date",
                        task_id=task["id"],
                        channel_id=task.get("channel_id"),
                        view=view,
                    )


class DigestEngine:
    """Generates daily and weekly task digests per channel."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        router: NotificationRouter,
        pref_manager: PreferenceManager,
    ) -> None:
        self.bot = bot
        self.db = db
        self.router = router
        self.pref_manager = pref_manager
        self._channel_last_run: Dict[int, str] = {}  # channel_id -> date for daily digests
        self._channel_weekly_last_run: Dict[int, str] = {}  # channel_id -> week for weekly digests

    async def run(self) -> None:
        """Generate and send daily/weekly digests per channel."""
        logger.debug("DigestEngine: Generating digests")

        # Get all guilds
        guilds = await self.db.list_guilds()
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        for guild_data in guilds:
            guild_id = guild_data["guild_id"]

            # Get all boards in this guild
            boards = await self.db.fetch_boards(guild_id)

            # Group tasks by channel_id (one digest per channel)
            channel_tasks_map: Dict[int, List[Dict[str, Any]]] = {}

            for board in boards:
                tasks = await self.db.fetch_tasks(board["id"], include_completed=False)
                channel_id = board["channel_id"]

                if channel_id not in channel_tasks_map:
                    channel_tasks_map[channel_id] = []

                for task in tasks:
                    channel_tasks_map[channel_id].append({
                        **task,
                        "board_name": board["name"],
                        "board_id": board["id"],
                        "channel_id": channel_id,
                        "guild_id": guild_id,
                    })

            # Send one digest per channel
            for channel_id, channel_tasks in channel_tasks_map.items():
                if not channel_tasks:
                    continue

                # Check if any user with tasks in this channel wants daily digest
                # Collect unique user IDs from tasks in this channel
                user_ids_in_channel = set()
                for task in channel_tasks:
                    assignee_ids = task.get("assignee_ids", [])
                    user_ids_in_channel.update(assignee_ids)

                # Check if any user wants daily digest at this time
                should_send_daily = False
                for user_id in user_ids_in_channel:
                    if await self.pref_manager.should_send_digest_now(user_id, guild_id, "daily"):
                        should_send_daily = True
                        break

                # Also check guild-level default if no user preferences found
                if not should_send_daily:
                    guild_prefs = await self.db.get_guild_notification_defaults(guild_id)
                    if guild_prefs and guild_prefs.get("enable_daily_digest", True):
                        # Get guild timezone and convert now to guild timezone
                        guild_tz_name = guild_prefs.get("timezone", "UTC")
                        try:
                            guild_tz = pytz.timezone(guild_tz_name)
                        except pytz.UnknownTimeZoneError:
                            guild_tz = pytz.UTC
                        
                        now_guild_tz = now.astimezone(guild_tz)
                        digest_time = guild_prefs.get("daily_digest_time", "09:00")
                        target_hour, target_minute = map(int, digest_time.split(":"))
                        if now_guild_tz.hour == target_hour and now_guild_tz.minute == target_minute:
                            should_send_daily = True
                    elif not guild_prefs:
                        # No guild prefs, use system default (09:00 UTC)
                        if now.hour == 9 and now.minute == 0:
                            should_send_daily = True

                # Check channel-level deduplication for daily digest
                # Use database-backed check to prevent duplicates across restarts/processes
                if should_send_daily:
                    # Check database first (persists across restarts and works across multiple processes)
                    if not await self.db.check_channel_digest_sent(channel_id, guild_id, "daily_digest", within_hours=23):
                        await self._send_daily_digest(channel_id, guild_id, channel_tasks)
                        # Record in database for future deduplication
                        await self.db.record_channel_digest(channel_id, guild_id, "daily_digest")
                        # Also update in-memory cache for fast lookups
                        guild_prefs = await self.db.get_guild_notification_defaults(guild_id)
                        guild_tz_name = guild_prefs.get("timezone", "UTC") if guild_prefs else "UTC"
                        try:
                            guild_tz = pytz.timezone(guild_tz_name)
                        except pytz.UnknownTimeZoneError:
                            guild_tz = pytz.UTC
                        today_guild_tz = now.astimezone(guild_tz).date().isoformat()
                        self._channel_last_run[channel_id] = today_guild_tz

                # Check if any user wants weekly digest
                should_send_weekly = False
                for user_id in user_ids_in_channel:
                    if await self.pref_manager.should_send_digest_now(user_id, guild_id, "weekly"):
                        should_send_weekly = True
                        break

                # Check guild-level default for weekly
                if not should_send_weekly:
                    guild_prefs = await self.db.get_guild_notification_defaults(guild_id)
                    if guild_prefs and guild_prefs.get("enable_weekly_digest", False):
                        # Get guild timezone and convert now to guild timezone
                        guild_tz_name = guild_prefs.get("timezone", "UTC")
                        try:
                            guild_tz = pytz.timezone(guild_tz_name)
                        except pytz.UnknownTimeZoneError:
                            guild_tz = pytz.UTC
                        
                        now_guild_tz = now.astimezone(guild_tz)
                        digest_day = guild_prefs.get("weekly_digest_day", 1)  # Monday
                        digest_time = guild_prefs.get("weekly_digest_time", "09:00")
                        target_hour, target_minute = map(int, digest_time.split(":"))
                        if (now_guild_tz.weekday() == digest_day and 
                            now_guild_tz.hour == target_hour and now_guild_tz.minute == target_minute):
                            should_send_weekly = True

                # Check channel-level deduplication for weekly digest
                # Use database-backed check to prevent duplicates across restarts/processes
                if should_send_weekly:
                    # Check database first (persists across restarts and works across multiple processes)
                    # Use 167 hours (7 days) window for weekly digests
                    if not await self.db.check_channel_digest_sent(channel_id, guild_id, "weekly_digest", within_hours=167):
                        await self._send_weekly_digest(channel_id, guild_id, channel_tasks)
                        # Record in database for future deduplication
                        await self.db.record_channel_digest(channel_id, guild_id, "weekly_digest")
                        # Also update in-memory cache for fast lookups
                        guild_prefs = await self.db.get_guild_notification_defaults(guild_id)
                        guild_tz_name = guild_prefs.get("timezone", "UTC") if guild_prefs else "UTC"
                        try:
                            guild_tz = pytz.timezone(guild_tz_name)
                        except pytz.UnknownTimeZoneError:
                            guild_tz = pytz.UTC
                        now_guild_tz = now.astimezone(guild_tz)
                        current_week_guild_tz = now_guild_tz.isocalendar()[1]  # Week number in guild timezone
                        self._channel_weekly_last_run[channel_id] = str(current_week_guild_tz)

    async def _check_quiet_hours_for_channel(
        self,
        guild_id: int,
        tasks: List[Dict[str, Any]],
    ) -> bool:
        """Check if any user with tasks in the channel is in quiet hours.
        
        Returns:
            True if any user is in quiet hours (should suppress), False otherwise
        """
        # Collect all unique user IDs from tasks
        user_ids = set()
        for task in tasks:
            assignee_ids = task.get("assignee_ids", [])
            user_ids.update(assignee_ids)
        
        # Check quiet hours for each user
        for user_id in user_ids:
            if await self.pref_manager.is_quiet_hours(user_id, guild_id):
                return True  # At least one user is in quiet hours
        
        return False  # No users in quiet hours

    async def _send_daily_digest(
        self,
        channel_id: int,
        guild_id: int,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """Send daily digest to a channel with all tasks from boards in that channel."""
        if not tasks:
            return

        # Check quiet hours before sending
        if await self._check_quiet_hours_for_channel(guild_id, tasks):
            logger.debug(f"Skipping daily digest for channel {channel_id} - users in quiet hours")
            return

        now = datetime.now(timezone.utc)

        # Group tasks by board
        board_tasks: Dict[str, List[Dict[str, Any]]] = {}
        for task in tasks:
            board_name = task.get("board_name", "Unknown")
            if board_name not in board_tasks:
                board_tasks[board_name] = []
            board_tasks[board_name].append(task)

        # Categorize tasks
        overdue = []
        due_today = []
        due_soon = []
        other = []

        for task in tasks:
            if not task.get("due_date"):
                other.append(task)
                continue

            due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            days_until = (due_date - now).days

            if due_date < now:
                overdue.append(task)
            elif days_until == 0:
                due_today.append(task)
            elif days_until <= 7:
                due_soon.append(task)
            else:
                other.append(task)

        # Get guild name
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Guild"

        # Create digest embed
        total_tasks = len(tasks)
        embed = discord.Embed(
            title="📊 Daily Task Digest",
            description=f"**{guild_name}** • {total_tasks} active task{'s' if total_tasks != 1 else ''} across {len(board_tasks)} board{'s' if len(board_tasks) != 1 else ''}",
            color=discord.Color.blue(),
            timestamp=now,
        )

        # Helper to format task with assignees
        def format_task_with_assignees(task: Dict[str, Any]) -> str:
            title = task.get("title", "Unknown")
            assignee_ids = task.get("assignee_ids", [])
            if assignee_ids:
                mentions = " ".join([f"<@{uid}>" for uid in assignee_ids])
                return f"• **{title}** {mentions}"
            return f"• **{title}** *(unassigned)*"

        # Overdue section
        if overdue:
            overdue_by_board: Dict[str, List[Dict[str, Any]]] = {}
            for task in overdue:
                board_name = task.get("board_name", "Unknown")
                if board_name not in overdue_by_board:
                    overdue_by_board[board_name] = []
                overdue_by_board[board_name].append(task)

            overdue_text = []
            for board_name, board_task_list in list(overdue_by_board.items())[:3]:  # Limit to 3 boards
                board_tasks_str = "\n".join([format_task_with_assignees(t) for t in board_task_list[:5]])
                if len(board_task_list) > 5:
                    board_tasks_str += f"\n... and {len(board_task_list) - 5} more"
                overdue_text.append(f"**{board_name}:**\n{board_tasks_str}")

            if len(overdue_by_board) > 3:
                overdue_text.append(f"\n... and {len(overdue_by_board) - 3} more board{'s' if len(overdue_by_board) - 3 != 1 else ''}")

            embed.add_field(
                name=f"🚨 Overdue ({len(overdue)})",
                value="\n\n".join(overdue_text) if overdue_text else "None",
                inline=False,
            )

        # Due today section
        if due_today:
            today_by_board: Dict[str, List[Dict[str, Any]]] = {}
            for task in due_today:
                board_name = task.get("board_name", "Unknown")
                if board_name not in today_by_board:
                    today_by_board[board_name] = []
                today_by_board[board_name].append(task)

            today_text = []
            for board_name, board_task_list in list(today_by_board.items())[:3]:
                board_tasks_str = "\n".join([format_task_with_assignees(t) for t in board_task_list[:5]])
                if len(board_task_list) > 5:
                    board_tasks_str += f"\n... and {len(board_task_list) - 5} more"
                today_text.append(f"**{board_name}:**\n{board_tasks_str}")

            if len(today_by_board) > 3:
                today_text.append(f"\n... and {len(today_by_board) - 3} more board{'s' if len(today_by_board) - 3 != 1 else ''}")

            embed.add_field(
                name=f"📅 Due Today ({len(due_today)})",
                value="\n\n".join(today_text) if today_text else "None",
                inline=False,
            )

        # Due this week section
        if due_soon:
            soon_by_board: Dict[str, List[Dict[str, Any]]] = {}
            for task in due_soon:
                board_name = task.get("board_name", "Unknown")
                if board_name not in soon_by_board:
                    soon_by_board[board_name] = []
                soon_by_board[board_name].append(task)

            soon_text = []
            for board_name, board_task_list in list(soon_by_board.items())[:3]:
                board_tasks_str = "\n".join([format_task_with_assignees(t) for t in board_task_list[:5]])
                if len(board_task_list) > 5:
                    board_tasks_str += f"\n... and {len(board_task_list) - 5} more"
                soon_text.append(f"**{board_name}:**\n{board_tasks_str}")

            if len(soon_by_board) > 3:
                soon_text.append(f"\n... and {len(soon_by_board) - 3} more board{'s' if len(soon_by_board) - 3 != 1 else ''}")

            embed.add_field(
                name=f"⏰ Due This Week ({len(due_soon)})",
                value="\n\n".join(soon_text) if soon_text else "None",
                inline=False,
            )

        # Other tasks (no due date)
        if other:
            other_by_board: Dict[str, List[Dict[str, Any]]] = {}
            for task in other:
                board_name = task.get("board_name", "Unknown")
                if board_name not in other_by_board:
                    other_by_board[board_name] = []
                other_by_board[board_name].append(task)

            other_text = []
            for board_name, board_task_list in list(other_by_board.items())[:2]:  # Limit to 2 boards for other
                board_tasks_str = "\n".join([format_task_with_assignees(t) for t in board_task_list[:3]])
                if len(board_task_list) > 3:
                    board_tasks_str += f"\n... and {len(board_task_list) - 3} more"
                other_text.append(f"**{board_name}:**\n{board_tasks_str}")

            if len(other_by_board) > 2:
                other_text.append(f"\n... and {len(other_by_board) - 2} more board{'s' if len(other_by_board) - 2 != 1 else ''}")

            embed.add_field(
                name=f"📋 Other Tasks ({len(other)})",
                value="\n\n".join(other_text) if other_text else "None",
                inline=False,
            )

        # Send directly to channel (not through NotificationRouter to avoid user-specific routing)
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)

            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(embed=embed)
                logger.info(f"Sent daily digest to channel {channel_id} ({total_tasks} tasks)")
            else:
                logger.warning(f"Cannot send digest to channel {channel_id} - invalid channel type")
        except Exception as e:
            logger.error(f"Failed to send daily digest to channel {channel_id}: {e}", exc_info=True)

    async def _send_weekly_digest(
        self,
        channel_id: int,
        guild_id: int,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """Send weekly digest to a channel with all tasks from boards in that channel."""
        if not tasks:
            return

        # Check quiet hours before sending
        if await self._check_quiet_hours_for_channel(guild_id, tasks):
            logger.debug(f"Skipping weekly digest for channel {channel_id} - users in quiet hours")
            return

        now = datetime.now(timezone.utc)

        # Get guild name
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Guild"

        # Group by board
        board_tasks: Dict[str, List[Dict[str, Any]]] = {}
        for task in tasks:
            board_name = task.get("board_name", "Unknown")
            if board_name not in board_tasks:
                board_tasks[board_name] = []
            board_tasks[board_name].append(task)

        embed = discord.Embed(
            title="📈 Weekly Task Summary",
            description=f"**{guild_name}** • {len(tasks)} active task{'s' if len(tasks) != 1 else ''} across {len(board_tasks)} board{'s' if len(board_tasks) != 1 else ''}",
            color=discord.Color.purple(),
            timestamp=now,
        )

        # Helper to format assignees
        def format_assignees(task: Dict[str, Any]) -> str:
            assignee_ids = task.get("assignee_ids", [])
            if assignee_ids:
                mentions = " ".join([f"<@{uid}>" for uid in assignee_ids])
                return f" {mentions}"
            return " *(unassigned)*"

        for board_name, board_task_list in list(board_tasks.items())[:10]:  # Limit to 10 boards
            task_summary = f"{len(board_task_list)} task{'s' if len(board_task_list) != 1 else ''}"

            # Count overdue and due soon
            overdue_count = 0
            due_soon_count = 0
            for t in board_task_list:
                if t.get("due_date"):
                    due_date = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                    days_until = (due_date - now).days
                    if due_date < now:
                        overdue_count += 1
                    elif days_until <= 7:
                        due_soon_count += 1

            status_parts = []
            if overdue_count > 0:
                status_parts.append(f"🚨 {overdue_count} overdue")
            if due_soon_count > 0:
                status_parts.append(f"⏰ {due_soon_count} due soon")
            
            if status_parts:
                task_summary += f"\n{', '.join(status_parts)}"

            # Show sample tasks with assignees
            sample_tasks = []
            for t in board_task_list[:3]:  # Show first 3 tasks
                title = t.get("title", "Unknown")
                assignees = format_assignees(t)
                sample_tasks.append(f"• **{title}**{assignees}")
            
            if len(board_task_list) > 3:
                sample_tasks.append(f"... and {len(board_task_list) - 3} more")

            embed.add_field(
                name=f"📁 {board_name}",
                value=f"{task_summary}\n\n" + "\n".join(sample_tasks) if sample_tasks else task_summary,
                inline=False,
            )

        # Send directly to channel
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)

            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(embed=embed)
                logger.info(f"Sent weekly digest to channel {channel_id} ({len(tasks)} tasks)")
            else:
                logger.warning(f"Cannot send weekly digest to channel {channel_id} - invalid channel type")
        except Exception as e:
            logger.error(f"Failed to send weekly digest to channel {channel_id}: {e}", exc_info=True)


class EscalationEngine:
    """Increases reminder frequency for overdue tasks."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        router: NotificationRouter,
        pref_manager: PreferenceManager,
    ) -> None:
        self.bot = bot
        self.db = db
        self.router = router
        self.pref_manager = pref_manager

    async def run(self) -> None:
        """Check for overdue tasks and send escalating reminders."""
        logger.debug("EscalationEngine: Checking for overdue tasks")

        now = datetime.now(timezone.utc)
        now_str = now.strftime(ISO_FORMAT)

        # Get all overdue tasks
        tasks = await self.db.fetch_due_tasks(now_str)

        for task in tasks:
            assignee_ids = task.get("assignee_ids", [])
            if not assignee_ids:
                continue

            due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            days_overdue = (now - due_date).days
            hours_overdue = (now - due_date).total_seconds() / 3600

            # Determine escalation frequency
            reminder_interval_hours = 24  # Default: once per day

            if days_overdue >= 7:
                reminder_interval_hours = 24  # Every day for very overdue
            elif days_overdue >= 3:
                reminder_interval_hours = 12  # Twice a day
            elif days_overdue >= 1:
                reminder_interval_hours = 6   # Every 6 hours

            # Only send if enough time has passed since last reminder
            for assignee_id in assignee_ids:
                if await self.db.check_notification_sent(
                    assignee_id,
                    task["id"],
                    "escalation",
                    within_hours=int(reminder_interval_hours),
                ):
                    continue

                # Create escalation embed
                urgency_color = discord.Color.dark_red() if days_overdue >= 7 else discord.Color.red()

                embed = discord.Embed(
                    title="⚠️ Overdue Task",
                    description=f"This task is {days_overdue} day{'s' if days_overdue != 1 else ''} overdue!",
                    color=urgency_color,
                )
                embed.add_field(
                    name="Task",
                    value=task.get("title", "Unknown"),
                    inline=False,
                )
                embed.add_field(
                    name="Was Due",
                    value=f"<t:{int(due_date.timestamp())}:R>",
                    inline=True,
                )
                embed.add_field(
                    name="Board",
                    value=task.get("board_name", "Unknown"),
                    inline=True,
                )

                # Add action buttons
                from cogs.ui.views import NotificationActionView
                view = NotificationActionView(
                    task_id=task["id"],
                    notification_type="escalation",
                )

                # Send escalation reminder
                await self.router.send_notification(
                    user_id=assignee_id,
                    guild_id=task["guild_id"],
                    embed=embed,
                    notification_type="escalation",
                    task_id=task["id"],
                    channel_id=task.get("channel_id"),
                    view=view,
                )


class SnoozedReminderEngine:
    """Processes snoozed reminders that are now due."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        router: NotificationRouter,
    ) -> None:
        self.bot = bot
        self.db = db
        self.router = router

    async def run(self) -> None:
        """Check for snoozed reminders that are now due."""
        logger.debug("SnoozedReminderEngine: Checking snoozed reminders")

        snoozed = await self.db.get_due_snoozed_reminders()

        for item in snoozed:
            task_id = item.get("task_id")
            user_id = item.get("user_id")
            snooze_id = item.get("snooze_id")

            # Get fresh task data
            task = await self.db.fetch_task(task_id)
            if not task or task.get("completed"):
                # Task completed or deleted, remove snooze
                await self.db.delete_snoozed_reminder(snooze_id)
                continue

            # Create reminder embed
            embed = discord.Embed(
                title="⏰ Snoozed Reminder",
                description="You snoozed this reminder. Here it is again!",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Task",
                value=task.get("title", "Unknown"),
                inline=False,
            )

            if task.get("due_date"):
                due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
                embed.add_field(
                    name="Due Date",
                    value=f"<t:{int(due_date.timestamp())}:R>",
                    inline=True,
                )

            # Add action buttons
            from cogs.ui.views import NotificationActionView
            view = NotificationActionView(
                task_id=task_id,
                notification_type=item.get("notification_type", "due_date"),
            )

            # Send reminder
            await self.router.send_notification(
                user_id=user_id,
                guild_id=item.get("guild_id"),
                embed=embed,
                notification_type="snoozed",
                task_id=task_id,
                channel_id=item.get("channel_id"),
                view=view,
            )

            # Remove from snoozed list
            await self.db.delete_snoozed_reminder(snooze_id)


class EnhancedScheduler:
    """Main scheduler that runs all notification engines."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
    ) -> None:
        self.bot = bot
        self.db = db
        self.pref_manager = PreferenceManager(db)
        self.router = NotificationRouter(bot, db, self.pref_manager)

        # Initialize all engines
        self.due_date_engine = DueDateReminderEngine(bot, db, self.router, self.pref_manager)
        self.digest_engine = DigestEngine(bot, db, self.router, self.pref_manager)
        self.escalation_engine = EscalationEngine(bot, db, self.router, self.pref_manager)
        self.snoozed_engine = SnoozedReminderEngine(bot, db, self.router)

        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run())
            logger.info("EnhancedScheduler started")

    async def stop(self) -> None:
        """Stop the scheduler background task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EnhancedScheduler stopped")

    async def _run(self) -> None:
        """Main scheduler loop - runs every minute."""
        await self.bot.wait_until_ready()

        while self._running:
            try:
                # Run all engines
                await self.due_date_engine.run()
                await self.digest_engine.run()
                await self.escalation_engine.run()
                await self.snoozed_engine.run()

            except Exception as e:
                logger.error(f"Error in EnhancedScheduler: {e}", exc_info=True)

            # Wait 60 seconds before next check
            await asyncio.sleep(60)
