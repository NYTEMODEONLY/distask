"""Notification routing and delivery system.

This module provides:
- NotificationRouter: Delivers notifications via channel, mention, or DM
- EventNotifier: Handles event-based alerts (assignments, updates, etc.)
- Notification embeds with interactive buttons
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord

from utils.db import Database
from utils.preference_manager import PreferenceManager

if TYPE_CHECKING:
    from discord.ext import commands

logger = logging.getLogger(__name__)


class NotificationRouter:
    """Routes and delivers notifications based on user preferences."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        pref_manager: PreferenceManager,
    ) -> None:
        self.bot = bot
        self.db = db
        self.pref_manager = pref_manager

    async def send_notification(
        self,
        user_id: int,
        guild_id: int,
        embed: discord.Embed,
        *,
        notification_type: str,
        task_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        view: Optional[discord.ui.View] = None,
    ) -> bool:
        """Send a notification to a user based on their preferences.

        Args:
            user_id: Discord user ID to notify
            guild_id: Guild context for the notification
            embed: Discord embed to send
            notification_type: Type of notification (due_date, assignment, etc.)
            task_id: Optional task ID associated with notification
            channel_id: Channel ID for channel-based notifications
            view: Optional view with interactive buttons

        Returns:
            True if notification was sent successfully, False otherwise
        """
        # Check if user wants this type of notification
        if not await self.pref_manager.should_notify(user_id, guild_id, notification_type):
            logger.debug(f"User {user_id} has disabled {notification_type} notifications")
            return False

        # Check quiet hours
        if await self.pref_manager.is_quiet_hours(user_id, guild_id):
            logger.debug(f"User {user_id} is in quiet hours, skipping notification")
            return False

        # Check for duplicate notifications
        if task_id and await self.db.check_notification_sent(
            user_id, task_id, notification_type, within_hours=24
        ):
            logger.debug(f"Duplicate notification suppressed for user {user_id}, task {task_id}")
            return False

        # Get preferred delivery method
        delivery_method = await self.pref_manager.get_preferred_delivery_method(user_id, guild_id)

        # Attempt delivery
        success = False
        if delivery_method == "dm":
            success = await self._send_dm(user_id, embed, view)
        elif delivery_method == "channel_mention":
            success = await self._send_channel_mention(user_id, guild_id, channel_id, embed, view)
        else:  # channel
            success = await self._send_channel(guild_id, channel_id, embed, view)

        # Record notification in history if successful
        if success and task_id:
            await self.db.record_notification(
                user_id=user_id,
                guild_id=guild_id,
                notification_type=notification_type,
                task_id=task_id,
                delivery_method=delivery_method,
            )

        return success

    async def _send_dm(
        self,
        user_id: int,
        embed: discord.Embed,
        view: Optional[discord.ui.View] = None,
    ) -> bool:
        """Send notification via direct message."""
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                await user.send(embed=embed, view=view)
                logger.info(f"Sent DM notification to user {user_id}")
                return True
        except discord.Forbidden:
            logger.warning(f"Cannot send DM to user {user_id} (DMs disabled)")
        except discord.HTTPException as e:
            logger.error(f"Failed to send DM to user {user_id}: {e}")
        return False

    async def _send_channel(
        self,
        guild_id: int,
        channel_id: Optional[int],
        embed: discord.Embed,
        view: Optional[discord.ui.View] = None,
    ) -> bool:
        """Send notification to a channel without mentioning user."""
        if not channel_id:
            logger.warning("No channel_id provided for channel notification")
            return False

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)

            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(embed=embed, view=view)
                logger.info(f"Sent channel notification to channel {channel_id}")
                return True
        except discord.Forbidden:
            logger.warning(f"No permission to send to channel {channel_id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}")
        return False

    async def _send_channel_mention(
        self,
        user_id: int,
        guild_id: int,
        channel_id: Optional[int],
        embed: discord.Embed,
        view: Optional[discord.ui.View] = None,
    ) -> bool:
        """Send notification to a channel with user mention."""
        if not channel_id:
            logger.warning("No channel_id provided for channel mention notification")
            return False

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)

            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(f"<@{user_id}>", embed=embed, view=view)
                logger.info(f"Sent channel mention notification to channel {channel_id}")
                return True
        except discord.Forbidden:
            logger.warning(f"No permission to send to channel {channel_id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}")
        return False

    async def send_bulk_notification(
        self,
        user_ids: List[int],
        guild_id: int,
        embed: discord.Embed,
        *,
        notification_type: str,
        task_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        view: Optional[discord.ui.View] = None,
    ) -> int:
        """Send notifications to multiple users.

        Returns:
            Number of successfully sent notifications
        """
        sent_count = 0
        for user_id in user_ids:
            if await self.send_notification(
                user_id=user_id,
                guild_id=guild_id,
                embed=embed,
                notification_type=notification_type,
                task_id=task_id,
                channel_id=channel_id,
                view=view,
            ):
                sent_count += 1
        return sent_count


class EventNotifier:
    """Handles event-based notifications for task changes."""

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        router: NotificationRouter,
    ) -> None:
        self.bot = bot
        self.db = db
        self.router = router

    async def notify_task_assigned(
        self,
        task: Dict[str, Any],
        assignee_ids: List[int],
        assigner_id: int,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """Notify users when they are assigned to a task."""
        from utils.embeds import EmbedFactory

        for assignee_id in assignee_ids:
            # Don't notify if user assigned themselves
            if assignee_id == assigner_id:
                continue

            # Create notification embed
            embed = discord.Embed(
                title="📌 New Task Assignment",
                description=f"You've been assigned to a new task!",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Task", value=task.get("title", "Unknown"), inline=False)

            if task.get("description"):
                desc = task["description"][:100] + "..." if len(task["description"]) > 100 else task["description"]
                embed.add_field(name="Description", value=desc, inline=False)

            if task.get("due_date"):
                embed.add_field(name="Due Date", value=f"<t:{int(datetime.fromisoformat(task['due_date'].replace('Z', '+00:00')).timestamp())}:R>", inline=True)

            embed.add_field(name="Assigned By", value=f"<@{assigner_id}>", inline=True)

            # Send notification
            await self.router.send_notification(
                user_id=assignee_id,
                guild_id=guild_id,
                embed=embed,
                notification_type="assignment",
                task_id=task.get("id"),
                channel_id=channel_id,
            )

    async def notify_task_updated(
        self,
        task: Dict[str, Any],
        updated_fields: List[str],
        updater_id: int,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """Notify assignees when a task is updated."""
        assignee_ids = task.get("assignee_ids", [])
        if not assignee_ids:
            return

        # Create notification embed
        embed = discord.Embed(
            title="✏️ Task Updated",
            description=f"A task you're assigned to has been updated",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Task", value=task.get("title", "Unknown"), inline=False)
        embed.add_field(name="Updated Fields", value=", ".join(updated_fields), inline=False)
        embed.add_field(name="Updated By", value=f"<@{updater_id}>", inline=True)

        # Send to all assignees except the updater
        for assignee_id in assignee_ids:
            if assignee_id == updater_id:
                continue

            await self.router.send_notification(
                user_id=assignee_id,
                guild_id=guild_id,
                embed=embed,
                notification_type="update",
                task_id=task.get("id"),
                channel_id=channel_id,
            )

    async def notify_task_moved(
        self,
        task: Dict[str, Any],
        from_column: str,
        to_column: str,
        mover_id: int,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """Notify assignees when a task is moved to a different column."""
        assignee_ids = task.get("assignee_ids", [])
        if not assignee_ids:
            return

        # Create notification embed
        embed = discord.Embed(
            title="↔️ Task Moved",
            description=f"A task you're assigned to has been moved",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Task", value=task.get("title", "Unknown"), inline=False)
        embed.add_field(name="From", value=from_column, inline=True)
        embed.add_field(name="To", value=to_column, inline=True)
        embed.add_field(name="Moved By", value=f"<@{mover_id}>", inline=True)

        # Send to all assignees except the mover
        for assignee_id in assignee_ids:
            if assignee_id == mover_id:
                continue

            await self.router.send_notification(
                user_id=assignee_id,
                guild_id=guild_id,
                embed=embed,
                notification_type="move",
                task_id=task.get("id"),
                channel_id=channel_id,
            )

    async def notify_task_completed(
        self,
        task: Dict[str, Any],
        completer_id: int,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """Notify task creator and assignees when a task is completed."""
        # Notify creator if they didn't complete it themselves
        creator_id = task.get("created_by")
        if creator_id and creator_id != completer_id:
            embed = discord.Embed(
                title="✅ Task Completed",
                description=f"A task you created has been completed!",
                color=discord.Color.green(),
            )
            embed.add_field(name="Task", value=task.get("title", "Unknown"), inline=False)
            embed.add_field(name="Completed By", value=f"<@{completer_id}>", inline=True)

            await self.router.send_notification(
                user_id=creator_id,
                guild_id=guild_id,
                embed=embed,
                notification_type="complete",
                task_id=task.get("id"),
                channel_id=channel_id,
            )

        # Notify assignees (except completer)
        assignee_ids = task.get("assignee_ids", [])
        for assignee_id in assignee_ids:
            if assignee_id == completer_id or assignee_id == creator_id:
                continue

            embed = discord.Embed(
                title="✅ Task Completed",
                description=f"A task you're assigned to has been completed!",
                color=discord.Color.green(),
            )
            embed.add_field(name="Task", value=task.get("title", "Unknown"), inline=False)
            embed.add_field(name="Completed By", value=f"<@{completer_id}>", inline=True)

            await self.router.send_notification(
                user_id=assignee_id,
                guild_id=guild_id,
                embed=embed,
                notification_type="complete",
                task_id=task.get("id"),
                channel_id=channel_id,
            )


def create_notification_action_view(
    task_id: int,
    notification_type: str,
) -> discord.ui.View:
    """Create a view with interactive buttons for notifications.

    Buttons:
    - Snooze 1h
    - Snooze 1d
    - Mark as Read
    - View Task
    """
    from cogs.ui.views import NotificationActionView

    return NotificationActionView(task_id=task_id, notification_type=notification_type)
