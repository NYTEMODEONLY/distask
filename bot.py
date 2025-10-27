from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils import Database, EmbedFactory, ReminderScheduler

BASE_DIR = Path(__file__).parent


def load_config() -> Dict[str, Any]:
    load_dotenv()
    token = os.getenv("TOKEN") or os.getenv("token")
    if not token:
        raise RuntimeError("Discord token missing. Provide TOKEN in the environment or .env file.")
    db_path = os.getenv("DATABASE_PATH") or os.getenv("database_path") or BASE_DIR / "data" / "distask.db"
    log_file = os.getenv("LOG_FILE") or os.getenv("log_file") or BASE_DIR / "logs" / "distask.log"
    reminder_time = os.getenv("REMINDER_TIME") or os.getenv("reminder_time") or "09:00"
    config = {
        "token": token,
        "database_path": str(db_path),
        "log_file": str(log_file),
        "reminder_time": reminder_time,
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
        self.db = Database(config["database_path"], default_reminder=config["reminder_time"])
        self.embeds = EmbedFactory()
        self.reminders = ReminderScheduler(self, self.db, self.embeds, logging.getLogger("distask.reminders"))
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.db.init()
        await self.add_cog(self._build_boards_cog())
        await self.add_cog(self._build_tasks_cog())
        await self.add_cog(self._build_admin_cog())
        await self.tree.sync()
        await self.reminders.start()
        self.logger.info("Slash commands synced.")

    async def on_ready(self) -> None:
        self.logger.info("Logged in as %s (%s)", self.user, self.user and self.user.id)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.db.ensure_guild(guild.id, reminder_time=self.config["reminder_time"])
        await self.db.set_reminder_time(guild.id, self.config["reminder_time"])

    async def close(self) -> None:
        await self.reminders.stop()
        await super().close()

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            sender = interaction.followup
            kwargs = {"ephemeral": True}
            send = sender.send
        else:
            send = interaction.response.send_message
            kwargs = {"ephemeral": True}
        if isinstance(error, app_commands.CommandOnCooldown):
            await send(f"Slow down! Try again in {error.retry_after:.1f}s.", **kwargs)
            return
        if isinstance(error, app_commands.MissingPermissions):
            await send("You lack the required permissions for this command.", **kwargs)
            return
        if isinstance(error, app_commands.AppCommandError) and not isinstance(error, app_commands.CommandInvokeError):
            await send(str(error), **kwargs)
            return
        await send("Something went wrong while running that command.", **kwargs)
        self.logger.exception("App command error: %s", error)

    def _build_boards_cog(self) -> commands.Cog:
        from cogs.boards import BoardsCog

        return BoardsCog(self, self.db, self.embeds)

    def _build_tasks_cog(self) -> commands.Cog:
        from cogs.tasks import TasksCog

        return TasksCog(self, self.db, self.embeds)

    def _build_admin_cog(self) -> commands.Cog:
        from cogs.admin import AdminCog

        return AdminCog(self, self.db)


def main() -> None:
    config = load_config()
    setup_logging(config["log_file"])
    bot = DisTaskBot(config)
    bot.run(config["token"])


if __name__ == "__main__":
    main()
