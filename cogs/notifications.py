"""Notification preferences management cog.

Provides slash commands for users and admins to configure notification preferences.
"""

from __future__ import annotations

import json
import logging
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory
from utils.preference_manager import PreferenceManager


class NotificationsCog(commands.Cog):
    """Cog for managing notification preferences."""

    def __init__(self, bot: commands.Bot, db: Database, embeds: EmbedFactory) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.pref_manager = PreferenceManager(db)
        self.logger = logging.getLogger("distask.notifications")

    @app_commands.command(name="notification-preferences", description="Configure your notification preferences")
    @app_commands.checks.cooldown(1, 3.0)
    async def notification_preferences(self, interaction: discord.Interaction) -> None:
        """Open modal to configure notification preferences."""
        from .ui.modals import NotificationPreferencesModal

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Get current preferences
        current_prefs = await self.pref_manager.get_effective_preferences(
            interaction.user.id,
            interaction.guild_id,
        )

        # Show modal
        modal = NotificationPreferencesModal(
            db=self.db,
            embeds=self.embeds,
            pref_manager=self.pref_manager,
            current_prefs=current_prefs,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="set-timezone", description="Set your timezone for notifications")
    @app_commands.describe(timezone="Your timezone (e.g., America/New_York, Europe/London, UTC)")
    @app_commands.checks.cooldown(1, 3.0)
    async def set_timezone(self, interaction: discord.Interaction, timezone: str) -> None:
        """Set user's timezone for notification timing."""
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Validate timezone
        import pytz
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Timezone",
                    f"Unknown timezone: `{timezone}`\n\nExamples:\n• America/New_York\n• Europe/London\n• Asia/Tokyo\n• UTC",
                    emoji="⚠️",
                ),
                ephemeral=True,
            )
            return

        # Save timezone
        await self.db.set_user_notification_prefs(
            interaction.user.id,
            interaction.guild_id,
            timezone=timezone,
        )

        await interaction.response.send_message(
            embed=self.embeds.message(
                "Timezone Updated",
                f"Your timezone has been set to **{timezone}**\n\nNotifications will be sent according to your local time.",
                emoji="🌍",
            ),
        )

    @app_commands.command(name="set-quiet-hours", description="Set hours when you don't want notifications")
    @app_commands.describe(
        start_time="Start time in HH:MM format (e.g., 22:00)",
        end_time="End time in HH:MM format (e.g., 08:00)",
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def set_quiet_hours(
        self,
        interaction: discord.Interaction,
        start_time: str,
        end_time: str,
    ) -> None:
        """Set quiet hours during which notifications are suppressed."""
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Validate time format
        from datetime import datetime
        time_format = "%H:%M"

        try:
            datetime.strptime(start_time, time_format)
            datetime.strptime(end_time, time_format)
        except ValueError:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Time Format",
                    "Please use HH:MM format (e.g., 22:00 for 10 PM, 08:00 for 8 AM)",
                    emoji="⚠️",
                ),
                ephemeral=True,
            )
            return

        # Save quiet hours
        await self.db.set_user_notification_prefs(
            interaction.user.id,
            interaction.guild_id,
            quiet_hours_start=start_time,
            quiet_hours_end=end_time,
        )

        await interaction.response.send_message(
            embed=self.embeds.message(
                "Quiet Hours Set",
                f"Notifications will be suppressed between **{start_time}** and **{end_time}** (your local time)",
                emoji="🌙",
            ),
        )

    @app_commands.command(name="set-delivery-method", description="Choose how you want to receive notifications")
    @app_commands.describe(
        method="Delivery method: channel (no mention), channel_mention (@mention in channel), or dm (direct message)"
    )
    @app_commands.choices(method=[
        app_commands.Choice(name="Channel (no mention)", value="channel"),
        app_commands.Choice(name="Channel with @mention", value="channel_mention"),
        app_commands.Choice(name="Direct Message", value="dm"),
    ])
    @app_commands.checks.cooldown(1, 3.0)
    async def set_delivery_method(
        self,
        interaction: discord.Interaction,
        method: app_commands.Choice[str],
    ) -> None:
        """Set preferred notification delivery method."""
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        await self.db.set_user_notification_prefs(
            interaction.user.id,
            interaction.guild_id,
            delivery_method=method.value,
        )

        method_descriptions = {
            "channel": "Notifications will be posted in board channels without mentioning you",
            "channel_mention": "Notifications will be posted in board channels and you'll be @mentioned",
            "dm": "Notifications will be sent to you via direct message",
        }

        await interaction.response.send_message(
            embed=self.embeds.message(
                "Delivery Method Updated",
                method_descriptions.get(method.value, "Delivery method updated successfully"),
                emoji="📬",
            ),
        )

    @app_commands.command(name="toggle-notification-type", description="Enable or disable specific notification types")
    @app_commands.describe(
        notification_type="Type of notification to toggle",
        enabled="Enable or disable this notification type",
    )
    @app_commands.choices(notification_type=[
        app_commands.Choice(name="Due Date Reminders", value="due_date"),
        app_commands.Choice(name="Event Alerts (assignments, updates)", value="event"),
        app_commands.Choice(name="Daily Digest", value="daily_digest"),
        app_commands.Choice(name="Weekly Digest", value="weekly_digest"),
    ])
    @app_commands.checks.cooldown(1, 3.0)
    async def toggle_notification_type(
        self,
        interaction: discord.Interaction,
        notification_type: app_commands.Choice[str],
        enabled: bool,
    ) -> None:
        """Enable or disable specific notification types."""
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Map notification types to database fields
        type_field_map = {
            "due_date": "enable_due_date_reminders",
            "event": "enable_event_alerts",
            "daily_digest": "enable_daily_digest",
            "weekly_digest": "enable_weekly_digest",
        }

        field_name = type_field_map.get(notification_type.value)
        if not field_name:
            await interaction.response.send_message(
                embed=self.embeds.message("Error", "Invalid notification type", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Update preference
        await self.db.set_user_notification_prefs(
            interaction.user.id,
            interaction.guild_id,
            **{field_name: enabled},
        )

        status = "enabled" if enabled else "disabled"
        emoji = "✅" if enabled else "🔕"

        await interaction.response.send_message(
            embed=self.embeds.message(
                "Notification Type Updated",
                f"**{notification_type.name}** have been {status}",
                emoji=emoji,
            ),
        )

    @app_commands.command(name="view-notification-preferences", description="View your current notification preferences")
    @app_commands.checks.cooldown(1, 3.0)
    async def view_notification_preferences(self, interaction: discord.Interaction) -> None:
        """View current notification preferences."""
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        prefs = await self.pref_manager.get_effective_preferences(
            interaction.user.id,
            interaction.guild_id,
        )

        embed = discord.Embed(
            title="🔔 Your Notification Preferences",
            description="Current notification settings for this server",
            color=discord.Color.blue(),
        )

        # Delivery method
        method_names = {
            "channel": "Channel (no mention)",
            "channel_mention": "Channel with @mention",
            "dm": "Direct Message",
        }
        embed.add_field(
            name="📬 Delivery Method",
            value=method_names.get(prefs.get("delivery_method", "channel"), "Channel"),
            inline=True,
        )

        # Timezone
        embed.add_field(
            name="🌍 Timezone",
            value=prefs.get("timezone", "UTC"),
            inline=True,
        )

        # Quiet hours
        quiet_start = prefs.get("quiet_hours_start")
        quiet_end = prefs.get("quiet_hours_end")
        if quiet_start and quiet_end:
            embed.add_field(
                name="🌙 Quiet Hours",
                value=f"{quiet_start} - {quiet_end}",
                inline=True,
            )

        # Enabled notification types
        enabled_types = []
        if prefs.get("enable_due_date_reminders"):
            enabled_types.append("✅ Due Date Reminders")
        if prefs.get("enable_event_alerts"):
            enabled_types.append("✅ Event Alerts")
        if prefs.get("enable_daily_digest"):
            enabled_types.append("✅ Daily Digest")
        if prefs.get("enable_weekly_digest"):
            enabled_types.append("✅ Weekly Digest")

        if enabled_types:
            embed.add_field(
                name="📋 Enabled Notifications",
                value="\n".join(enabled_types),
                inline=False,
            )

        # Digest times
        daily_time = prefs.get("daily_digest_time")
        if daily_time and prefs.get("enable_daily_digest"):
            embed.add_field(
                name="⏰ Daily Digest Time",
                value=daily_time,
                inline=True,
            )

        weekly_time = prefs.get("weekly_digest_time")
        weekly_day = prefs.get("weekly_digest_day", 1)
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if weekly_time and prefs.get("enable_weekly_digest"):
            embed.add_field(
                name="📅 Weekly Digest",
                value=f"{days[weekly_day]} at {weekly_time}",
                inline=True,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="guild-notification-defaults", description="[Admin] Set guild-wide notification defaults")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def guild_notification_defaults(self, interaction: discord.Interaction) -> None:
        """Set guild-wide notification defaults (admin only)."""
        from .ui.modals import GuildNotificationDefaultsModal

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return

        # Get current guild defaults
        guild_defaults = await self.db.get_guild_notification_defaults(interaction.guild_id)
        if not guild_defaults:
            guild_defaults = self.pref_manager.DEFAULT_PREFS

        # Show modal
        modal = GuildNotificationDefaultsModal(
            db=self.db,
            embeds=self.embeds,
            current_defaults=guild_defaults,
        )
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    """Load the NotificationsCog."""
    db = getattr(bot, "db", None)
    embeds = getattr(bot, "embeds", None)

    if not db or not embeds:
        raise RuntimeError("Bot must have 'db' and 'embeds' attributes")

    await bot.add_cog(NotificationsCog(bot, db, embeds))
