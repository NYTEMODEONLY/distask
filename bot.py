from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils import Database, EmbedFactory, ReminderScheduler
from utils.preference_manager import PreferenceManager
from utils.notifications import NotificationRouter, EventNotifier
from utils.scheduler_v2 import EnhancedScheduler

BASE_DIR = Path(__file__).parent


def _maybe_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_config() -> Dict[str, Any]:
    load_dotenv()
    token = os.getenv("TOKEN") or os.getenv("token")
    if not token:
        raise RuntimeError(
            "Discord token missing. Provide TOKEN in the environment or .env file."
        )
    db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("database_url")
        or "postgresql://distask:distaskpass@localhost:5432/distask"
    )
    log_file = (
        os.getenv("LOG_FILE")
        or os.getenv("log_file")
        or BASE_DIR / "logs" / "distask.log"
    )
    reminder_time = os.getenv("REMINDER_TIME") or os.getenv("reminder_time") or "09:00"
    config = {
        "token": token,
        "database_url": str(db_url),
        "log_file": str(log_file),
        "reminder_time": reminder_time,
        "github_token": os.getenv("GITHUB_TOKEN") or os.getenv("github_token"),
        "repo_owner": os.getenv("REPO_OWNER")
        or os.getenv("repo_owner")
        or "NYTEMODEONLY",
        "repo_name": os.getenv("REPO_NAME") or os.getenv("repo_name") or "distask",
        "community_guild_id": _maybe_int(
            os.getenv("COMMUNITY_GUILD_ID") or os.getenv("community_guild_id")
        ),
        "community_channel_id": _maybe_int(
            os.getenv("COMMUNITY_CHANNEL_ID") or os.getenv("community_channel_id")
        ),
        "community_feature_webhook": os.getenv("COMMUNITY_FEATURE_WEBHOOK")
        or os.getenv("community_feature_webhook"),
    }
    return config


def setup_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


class DisTaskBot(commands.Bot):
    def __init__(self, config: Dict[str, Any]) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="/", intents=intents)
        self.config = config
        self.logger = logging.getLogger("distask.bot")
        self.db = Database(
            config["database_url"], default_reminder=config["reminder_time"]
        )
        self.embeds = EmbedFactory()
        self.start_time = datetime.now(
            timezone.utc
        )  # Track bot start time for uptime calculation
        # Legacy reminder system - disabled in favor of EnhancedScheduler
        # self.reminders = ReminderScheduler(self, self.db, self.embeds, logging.getLogger("distask.reminders"))

        # Initialize enhanced notification system
        self.pref_manager = PreferenceManager(self.db)
        self.notification_router = NotificationRouter(self, self.db, self.pref_manager)
        self.event_notifier = EventNotifier(self, self.db, self.notification_router)
        self.enhanced_scheduler = EnhancedScheduler(self, self.db)

        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.db.init()

        # Register persistent views for notification buttons
        from cogs.ui.views import NotificationActionView

        # Add a persistent view with dummy values - the custom_id parsing handles actual task_id
        self.add_view(NotificationActionView(task_id=0, notification_type="persistent"))

        await self.add_cog(self._build_boards_cog())
        await self.add_cog(self._build_tasks_cog())
        await self.add_cog(self._build_features_cog())
        await self.add_cog(self._build_admin_cog())
        await self.add_cog(self._build_notifications_cog())
        await self.add_cog(self._build_info_cog())
        await self.tree.sync()
        # await self.reminders.start()  # Disabled - using EnhancedScheduler instead
        await self.enhanced_scheduler.start()
        self.logger.info("Slash commands synced.")
        self.logger.info("Enhanced notification system started.")

    async def on_ready(self) -> None:
        self.logger.info("Logged in as %s (%s)", self.user, self.user and self.user.id)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.db.ensure_guild(guild.id, reminder_time=self.config["reminder_time"])
        await self.db.set_reminder_time(guild.id, self.config["reminder_time"])

    async def close(self) -> None:
        # await self.reminders.stop()  # Disabled - using EnhancedScheduler instead
        await self.enhanced_scheduler.stop()
        await self.db.close()
        await super().close()

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if interaction.response.is_done():
            send = interaction.followup.send
        else:
            send = interaction.response.send_message

        if isinstance(error, app_commands.CommandOnCooldown):
            embed = self.embeds.message(
                "Cooldown", f"Try again in {error.retry_after:.1f}s.", emoji="⏳"
            )
            await send(embed=embed)
            return
        if isinstance(error, app_commands.MissingPermissions):
            embed = self.embeds.message(
                "Insufficient Permissions",
                "You don't have the required Discord permissions.",
                emoji="🚫",
            )
            await send(embed=embed)
            return
        if isinstance(error, app_commands.AppCommandError) and not isinstance(
            error, app_commands.CommandInvokeError
        ):
            embed = self.embeds.message("Command Error", str(error), emoji="⚠️")
            await send(embed=embed)
            return
        embed = self.embeds.message(
            "Unexpected Error",
            "Something went wrong while running that command.",
            emoji="🔥",
        )
        await send(embed=embed)
        self.logger.exception("App command error: %s", error)

    def _build_boards_cog(self) -> commands.Cog:
        from cogs.boards import BoardsCog

        return BoardsCog(self, self.db, self.embeds)

    def _build_tasks_cog(self) -> commands.Cog:
        from cogs.tasks import TasksCog

        return TasksCog(self, self.db, self.embeds)

    def _build_admin_cog(self) -> commands.Cog:
        from cogs.admin import AdminCog

        return AdminCog(self, self.db, self.embeds)

    def _build_features_cog(self) -> commands.Cog:
        from cogs.features import FeaturesCog

        return FeaturesCog(
            self,
            self.db,
            self.embeds,
            github_token=self.config.get("github_token"),
            repo_owner=self.config.get("repo_owner"),
            repo_name=self.config.get("repo_name"),
            community_guild_id=self.config.get("community_guild_id"),
            community_channel_id=self.config.get("community_channel_id"),
            community_webhook_url=self.config.get("community_feature_webhook"),
        )

    def _build_notifications_cog(self) -> commands.Cog:
        from cogs.notifications import NotificationsCog

        return NotificationsCog(self, self.db, self.embeds)

    def _build_info_cog(self) -> commands.Cog:
        from cogs.info import InfoCog

        return InfoCog(self, self.db, self.embeds)


def main() -> None:
    config = load_config()
    setup_logging(config["log_file"])
    bot = DisTaskBot(config)
    bot.run(config["token"])


if __name__ == "__main__":
    main()
