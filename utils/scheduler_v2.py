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
    """Generates daily and weekly task digests for users."""

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
        """Generate and send daily/weekly digests to users."""
        logger.debug("DigestEngine: Generating digests")

        # Get all guilds
        guilds = await self.db.list_guilds()

        for guild_data in guilds:
            guild_id = guild_data["guild_id"]

            # Get all boards in this guild
            boards = await self.db.fetch_boards(guild_id)

            # Collect all unique user IDs from tasks in this guild
            user_tasks_map: Dict[int, List[Dict[str, Any]]] = {}

            for board in boards:
                tasks = await self.db.fetch_tasks(board["id"], include_completed=False)

                for task in tasks:
                    assignee_ids = task.get("assignee_ids", [])
                    for assignee_id in assignee_ids:
                        if assignee_id not in user_tasks_map:
                            user_tasks_map[assignee_id] = []
                        user_tasks_map[assignee_id].append({**task, "board_name": board["name"], "board_id": board["id"]})

            # Send digests to each user
            for user_id, user_tasks in user_tasks_map.items():
                # Check if it's time for daily digest
                if await self.pref_manager.should_send_digest_now(user_id, guild_id, "daily"):
                    # Check if we already sent today's digest (use task_id=None for digests)
                    if not await self.db.check_notification_sent(user_id, None, "daily_digest", within_hours=23):
                        await self._send_daily_digest(user_id, guild_id, user_tasks)

                # Check if it's time for weekly digest
                if await self.pref_manager.should_send_digest_now(user_id, guild_id, "weekly"):
                    # Check if we already sent this week's digest (use task_id=None for digests)
                    if not await self.db.check_notification_sent(user_id, None, "weekly_digest", within_hours=167):  # 7 days
                        await self._send_weekly_digest(user_id, guild_id, user_tasks)

    async def _send_daily_digest(
        self,
        user_id: int,
        guild_id: int,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """Send daily digest to a user."""
        if not tasks:
            return

        now = datetime.now(timezone.utc)

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

        # Create digest embed
        embed = discord.Embed(
            title="📊 Daily Task Digest",
            description=f"You have {len(tasks)} active task{'s' if len(tasks) != 1 else ''}",
            color=discord.Color.blue(),
            timestamp=now,
        )

        if overdue:
            overdue_list = "\n".join([f"• **{t['title']}** (Board: {t['board_name']})" for t in overdue[:5]])
            if len(overdue) > 5:
                overdue_list += f"\n... and {len(overdue) - 5} more"
            embed.add_field(
                name=f"🚨 Overdue ({len(overdue)})",
                value=overdue_list,
                inline=False,
            )

        if due_today:
            today_list = "\n".join([f"• **{t['title']}** (Board: {t['board_name']})" for t in due_today[:5]])
            if len(due_today) > 5:
                today_list += f"\n... and {len(due_today) - 5} more"
            embed.add_field(
                name=f"📅 Due Today ({len(due_today)})",
                value=today_list,
                inline=False,
            )

        if due_soon:
            soon_list = "\n".join([f"• **{t['title']}** (Board: {t['board_name']})" for t in due_soon[:5]])
            if len(due_soon) > 5:
                soon_list += f"\n... and {len(due_soon) - 5} more"
            embed.add_field(
                name=f"⏰ Due This Week ({len(due_soon)})",
                value=soon_list,
                inline=False,
            )

        # Find a channel to send to (use first board's channel)
        channel_id = tasks[0].get("channel_id") if tasks else None

        # Use task_id=None for digest tracking (digests are not tied to specific tasks)
        await self.router.send_notification(
            user_id=user_id,
            guild_id=guild_id,
            embed=embed,
            notification_type="daily_digest",
            task_id=None,  # NULL value - digests are not task-specific
            channel_id=channel_id,
        )

    async def _send_weekly_digest(
        self,
        user_id: int,
        guild_id: int,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """Send weekly digest to a user."""
        if not tasks:
            return

        now = datetime.now(timezone.utc)

        embed = discord.Embed(
            title="📈 Weekly Task Summary",
            description=f"You have {len(tasks)} active task{'s' if len(tasks) != 1 else ''}",
            color=discord.Color.purple(),
            timestamp=now,
        )

        # Group by board
        board_tasks: Dict[str, List[Dict[str, Any]]] = {}
        for task in tasks:
            board_name = task.get("board_name", "Unknown")
            if board_name not in board_tasks:
                board_tasks[board_name] = []
            board_tasks[board_name].append(task)

        for board_name, board_task_list in list(board_tasks.items())[:5]:  # Limit to 5 boards
            task_summary = f"{len(board_task_list)} task{'s' if len(board_task_list) != 1 else ''}"

            # Count overdue
            overdue_count = sum(
                1
                for t in board_task_list
                if t.get("due_date")
                and datetime.fromisoformat(t["due_date"].replace("Z", "+00:00")) < now
            )
            if overdue_count > 0:
                task_summary += f" ({overdue_count} overdue)"

            embed.add_field(
                name=f"📁 {board_name}",
                value=task_summary,
                inline=True,
            )

        # Find a channel to send to
        channel_id = tasks[0].get("channel_id") if tasks else None

        # Use task_id=None for digest tracking (digests are not tied to specific tasks)
        await self.router.send_notification(
            user_id=user_id,
            guild_id=guild_id,
            embed=embed,
            notification_type="weekly_digest",
            task_id=None,  # NULL value - digests are not task-specific
            channel_id=channel_id,
        )


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
