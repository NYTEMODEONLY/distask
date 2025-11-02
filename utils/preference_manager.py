"""Preference manager for handling user and guild notification preferences.

This module provides utilities for:
- Merging guild defaults with user-specific overrides
- Resolving notification preferences with proper inheritance
- Timezone handling and quiet hours checking
"""

from __future__ import annotations

import json
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional

import pytz

from utils.db import Database


class PreferenceManager:
    """Manages notification preferences with guild defaults and user overrides."""

    # Default preferences when nothing is configured
    DEFAULT_PREFS = {
        "delivery_method": "channel",
        "timezone": "UTC",
        "enable_due_date_reminders": True,
        "enable_event_alerts": True,
        "enable_daily_digest": True,
        "enable_weekly_digest": False,
        "enable_custom_reminders": True,
        "due_date_advance_days": [1],
        "daily_digest_time": "09:00",
        "weekly_digest_day": 1,  # Monday
        "weekly_digest_time": "09:00",
    }

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_effective_preferences(
        self,
        user_id: int,
        guild_id: int,
    ) -> Dict[str, Any]:
        """Get effective preferences for a user by merging guild defaults with user overrides.

        Priority: User preferences > Guild defaults > System defaults
        """
        # Start with system defaults
        prefs = dict(self.DEFAULT_PREFS)

        # Apply guild defaults if they exist
        guild_defaults = await self.db.get_guild_notification_defaults(guild_id)
        if guild_defaults:
            for key, value in guild_defaults.items():
                if key not in ("guild_id", "created_at", "updated_at") and value is not None:
                    # Parse JSON fields
                    if key == "due_date_advance_days" and isinstance(value, str):
                        try:
                            prefs[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    else:
                        prefs[key] = value

        # Apply user overrides if they exist
        user_prefs = await self.db.get_user_notification_prefs(user_id, guild_id)
        if user_prefs:
            for key, value in user_prefs.items():
                if key not in ("user_id", "guild_id", "created_at", "updated_at") and value is not None:
                    # Parse JSON fields
                    if key == "due_date_advance_days" and isinstance(value, str):
                        try:
                            prefs[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    else:
                        prefs[key] = value

        return prefs

    async def should_notify(
        self,
        user_id: int,
        guild_id: int,
        notification_type: str,
    ) -> bool:
        """Check if a notification should be sent based on user preferences.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            notification_type: Type of notification (due_date, event, digest, etc.)

        Returns:
            True if notification should be sent, False otherwise
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)

        # Check if this notification type is enabled
        if notification_type == "due_date":
            return prefs.get("enable_due_date_reminders", True)
        elif notification_type in ("assignment", "update", "move", "complete", "comment"):
            return prefs.get("enable_event_alerts", True)
        elif notification_type == "daily_digest":
            return prefs.get("enable_daily_digest", True)
        elif notification_type == "weekly_digest":
            return prefs.get("enable_weekly_digest", False)
        elif notification_type == "custom":
            return prefs.get("enable_custom_reminders", True)

        # Default to True for unknown types
        return True

    async def is_quiet_hours(
        self,
        user_id: int,
        guild_id: int,
    ) -> bool:
        """Check if current time is within user's quiet hours.

        Returns:
            True if in quiet hours (should suppress notifications), False otherwise
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)

        quiet_start = prefs.get("quiet_hours_start")
        quiet_end = prefs.get("quiet_hours_end")

        if not quiet_start or not quiet_end:
            return False  # No quiet hours configured

        try:
            # Get user's timezone
            tz_name = prefs.get("timezone", "UTC")
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC

            # Get current time in user's timezone
            now_user_tz = datetime.now(tz).time()

            # Parse quiet hours
            start_time = datetime.strptime(quiet_start, "%H:%M").time()
            end_time = datetime.strptime(quiet_end, "%H:%M").time()

            # Check if current time is in quiet hours
            if start_time < end_time:
                # Normal case: 22:00 - 08:00 (not crossing midnight)
                return start_time <= now_user_tz <= end_time
            else:
                # Crosses midnight: 22:00 - 02:00
                return now_user_tz >= start_time or now_user_tz <= end_time

        except (ValueError, TypeError):
            return False  # Invalid time format, don't suppress

    async def get_preferred_delivery_method(
        self,
        user_id: int,
        guild_id: int,
    ) -> str:
        """Get user's preferred notification delivery method.

        Returns:
            One of: 'channel', 'channel_mention', 'dm'
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)
        method = prefs.get("delivery_method", "channel")

        # Validate delivery method
        valid_methods = {"channel", "channel_mention", "dm"}
        if method not in valid_methods:
            return "channel"  # Default fallback

        return method

    async def get_due_date_advance_days(
        self,
        user_id: int,
        guild_id: int,
    ) -> List[int]:
        """Get list of days before due date to send reminders.

        For example: [1, 3, 7] means send reminders 1, 3, and 7 days before due date.
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)
        advance_days = prefs.get("due_date_advance_days", [1])

        if not isinstance(advance_days, list):
            return [1]  # Default fallback

        return [int(d) for d in advance_days if isinstance(d, (int, float, str)) and str(d).isdigit()]

    def convert_to_user_timezone(
        self,
        dt: datetime,
        user_timezone: str,
    ) -> datetime:
        """Convert a UTC datetime to user's timezone.

        Args:
            dt: Datetime in UTC
            user_timezone: Timezone name (e.g., "America/New_York")

        Returns:
            Datetime in user's timezone
        """
        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC

        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(tz)

    def format_time_for_user(
        self,
        dt: datetime,
        user_timezone: str,
    ) -> str:
        """Format a datetime for display to user in their timezone.

        Args:
            dt: Datetime in UTC
            user_timezone: Timezone name

        Returns:
            Formatted string like "2025-11-02 14:30 EST"
        """
        user_dt = self.convert_to_user_timezone(dt, user_timezone)
        return user_dt.strftime("%Y-%m-%d %H:%M %Z")

    async def get_digest_time(
        self,
        user_id: int,
        guild_id: int,
        digest_type: str = "daily",
    ) -> Optional[str]:
        """Get user's preferred time for daily or weekly digest.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            digest_type: "daily" or "weekly"

        Returns:
            Time in HH:MM format, or None if disabled
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)

        if digest_type == "daily":
            if not prefs.get("enable_daily_digest", False):
                return None
            return prefs.get("daily_digest_time", "09:00")
        elif digest_type == "weekly":
            if not prefs.get("enable_weekly_digest", False):
                return None
            return prefs.get("weekly_digest_time", "09:00")

        return None

    async def get_weekly_digest_day(
        self,
        user_id: int,
        guild_id: int,
    ) -> int:
        """Get user's preferred day for weekly digest (0=Monday, 6=Sunday)."""
        prefs = await self.get_effective_preferences(user_id, guild_id)
        day = prefs.get("weekly_digest_day", 1)  # Default: Monday

        # Ensure valid day (0-6)
        if not isinstance(day, int) or day < 0 or day > 6:
            return 1

        return day

    async def should_send_digest_now(
        self,
        user_id: int,
        guild_id: int,
        digest_type: str = "daily",
    ) -> bool:
        """Check if it's time to send a digest to this user.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            digest_type: "daily" or "weekly"

        Returns:
            True if digest should be sent now
        """
        prefs = await self.get_effective_preferences(user_id, guild_id)

        # Get user's timezone
        tz_name = prefs.get("timezone", "UTC")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC

        now_user_tz = datetime.now(tz)

        if digest_type == "daily":
            if not prefs.get("enable_daily_digest", False):
                return False

            digest_time = prefs.get("daily_digest_time", "09:00")
            target_hour, target_minute = map(int, digest_time.split(":"))

            # Check if current time matches digest time (exact minute to prevent duplicates)
            return (
                now_user_tz.hour == target_hour
                and now_user_tz.minute == target_minute
            )

        elif digest_type == "weekly":
            if not prefs.get("enable_weekly_digest", False):
                return False

            digest_day = prefs.get("weekly_digest_day", 1)  # Monday
            digest_time = prefs.get("weekly_digest_time", "09:00")
            target_hour, target_minute = map(int, digest_time.split(":"))

            # Check if current day and time match (exact minute to prevent duplicates)
            return (
                now_user_tz.weekday() == digest_day
                and now_user_tz.hour == target_hour
                and now_user_tz.minute == target_minute
            )

        return False
