from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory


class InfoCog(commands.Cog):
    """Cog for informational and meta commands about the bot."""

    def __init__(self, bot: commands.Bot, db: Database, embeds: EmbedFactory) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.logger = logging.getLogger("distask.info")

    def _read_version(self) -> str:
        """Read version from VERSION file."""
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning("Failed to read VERSION file: %s", e)
            return "unknown"

    def _calculate_uptime(self) -> str:
        """Calculate bot uptime in human-readable format."""
        if not hasattr(self.bot, "start_time"):
            return "unknown"

        uptime_seconds = (
            datetime.now(timezone.utc) - self.bot.start_time
        ).total_seconds()
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        if days > 0:
            return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
        elif hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"

    @app_commands.command(
        name="version", description="[Global] View bot version and release information"
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def version(self, interaction: discord.Interaction) -> None:
        """Display bot version, uptime, and links to releases."""
        version = self._read_version()
        uptime = self._calculate_uptime()

        # Get repo info from bot config
        repo_owner = getattr(self.bot, "config", {}).get("repo_owner", "NYTEMODEONLY")
        repo_name = getattr(self.bot, "config", {}).get("repo_name", "distask")
        releases_url = f"https://github.com/{repo_owner}/{repo_name}/releases"

        embed = discord.Embed(
            title=f"DisTask v{version}",
            description="Task management, simplified.",
            color=0x5865F2,  # Discord brand blue
        )

        embed.add_field(name="📦 Version", value=version, inline=True)
        embed.add_field(name="⏱️ Uptime", value=uptime, inline=True)
        embed.add_field(
            name="📋 Changelog", value=f"[View releases]({releases_url})", inline=False
        )
        embed.add_field(
            name="💡 Feature Requests",
            value="Have an idea? Use `/request-feature`",
            inline=False,
        )

        embed.set_footer(text="Crafted with intention")

        await interaction.response.send_message(embed=embed)
        self.logger.info("User %s viewed version info", interaction.user.id)

    @app_commands.command(
        name="support",
        description="[Global] Support DisTask and contribute to the project",
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def support(self, interaction: discord.Interaction) -> None:
        """Display support and contribution information."""
        # Get repo info from bot config
        repo_owner = getattr(self.bot, "config", {}).get("repo_owner", "NYTEMODEONLY")
        repo_name = getattr(self.bot, "config", {}).get("repo_name", "distask")
        repo_url = f"https://github.com/{repo_owner}/{repo_name}"

        embed = discord.Embed(
            title="Support DisTask ❤️",
            description="This bot is free and open source. Your support keeps it alive.",
            color=0xF1C40F,  # Warm gold
        )

        # Payment options
        payment_links = []
        payment_links.append(
            f"[GitHub Sponsors](https://github.com/sponsors/{repo_owner})"
        )
        payment_links.append("[PayPal](https://paypal.me/lobostylez)")
        embed.add_field(
            name="💝 Donate",
            value=" • ".join(payment_links),
            inline=False,
        )

        # Contribution pathways
        embed.add_field(
            name="🛠️ Contribute",
            value=f"Submit PRs or report issues on [GitHub]({repo_url})",
            inline=False,
        )

        embed.add_field(
            name="⭐ Star the Project",
            value=f"[{repo_owner}/{repo_name}]({repo_url})",
            inline=False,
        )

        embed.add_field(
            name="💡 Share Ideas",
            value="Use `/request-feature` to suggest improvements",
            inline=False,
        )

        embed.set_footer(text="Every contribution matters")

        await interaction.response.send_message(embed=embed)
        self.logger.info("User %s viewed support info", interaction.user.id)


async def setup(bot: commands.Bot) -> None:
    """Load the InfoCog."""
    db = getattr(bot, "db", None)
    embeds = getattr(bot, "embeds", None)

    if not db or not embeds:
        raise RuntimeError("InfoCog requires DisTaskBot with db and embeds attributes")

    await bot.add_cog(InfoCog(bot, db, embeds))
