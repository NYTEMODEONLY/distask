from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory, Validator
from utils.github_utils import export_to_github

GITHUB_LINK = "https://github.com/NYTEMODEONLY/distask/blob/main/feature_requests.md"


class FeatureRequestModal(discord.ui.Modal):
    def __init__(self, cog: "FeaturesCog") -> None:
        super().__init__(title="Request a Feature")
        self.cog = cog
        self.feature_title = discord.ui.TextInput(
            label="Feature Title",
            placeholder="Short summary",
            max_length=100,
            required=True,
            style=discord.TextStyle.short,
        )
        self.detailed_suggestion = discord.ui.TextInput(
            label="Detailed Suggestion",
            placeholder="Describe the use-case or pain point.",
            max_length=2000,
            required=True,
            style=discord.TextStyle.paragraph,
        )
        self.suggested_priority = discord.ui.TextInput(
            label="Suggested Priority",
            placeholder="low · medium · high (optional)",
            max_length=100,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.feature_title)
        self.add_item(self.detailed_suggestion)
        self.add_item(self.suggested_priority)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.process_submission(
            interaction,
            title=self.feature_title.value,
            suggestion=self.detailed_suggestion.value,
            suggested_priority=self.suggested_priority.value,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        self.cog.logger.exception("Modal submission failed: %s", error)
        if interaction.response.is_done():
            sender = interaction.followup
            send = sender.send
        else:
            send = interaction.response.send_message
        await send(
            embed=self.cog.embeds.message(
                "Submission Error",
                "Something went wrong while processing your feature request. Please try again later.",
                emoji="🔥",
            ),
        )


class FeaturesCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        embeds: EmbedFactory,
        *,
        github_token: Optional[str],
        repo_owner: Optional[str],
        repo_name: Optional[str],
    ) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.logger = logging.getLogger("distask.features")
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name

    @app_commands.command(name="request-feature", description="Suggest a new feature for DisTask")
    @app_commands.checks.cooldown(1, 10.0)
    async def request_feature(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Guild Only",
                    "Please run /request-feature inside a Discord server.",
                    emoji="🏠",
                ),
            )
            return
        await interaction.response.send_modal(FeatureRequestModal(self))

    async def process_submission(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        suggestion: str,
        suggested_priority: Optional[str],
    ) -> None:
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Guild Missing",
                    "Feature requests must be submitted from a server context.",
                    emoji="🏠",
                ),
            )
            return

        clean_title = title.strip()
        clean_suggestion = suggestion.strip()
        clean_priority = Validator.sanitize(suggested_priority) or None

        if not clean_title or not clean_suggestion:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Input",
                    "Both the feature title and detailed suggestion are required.",
                    emoji="⚠️",
                ),
            )
            return

        try:
            request_id = await self.db.create_feature_request(
                user_id=interaction.user.id,
                guild_id=guild_id,
                title=clean_title,
                suggestion=clean_suggestion,
                suggested_priority=clean_priority,
            )
        except Exception as exc:
            self.logger.exception("Failed to store feature request: %s", exc)
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Database Error",
                    "Couldn't record your feature request right now. Please try again later.",
                    emoji="🔥",
                ),
            )
            return

        embed = self.embeds.message(
            "Feature Request Logged",
            (
                "Thank you! Your feature request has been logged and will be reviewed for prioritization.\n\n"
                f"You can view all requests at {GITHUB_LINK}"
            ),
            emoji="✨",
        )
        embed.add_field(name="Request ID", value=str(request_id), inline=False)
        await interaction.response.send_message(embed=embed)

        await self._export_feature_requests()

    async def _export_feature_requests(self) -> None:
        try:
            await export_to_github(
                self.db,
                token=self.github_token,
                owner=self.repo_owner,
                repo=self.repo_name,
            )
        except Exception as exc:
            self.logger.exception("Failed to export feature requests to GitHub: %s", exc)
