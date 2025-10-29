from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp

from utils import Database, EmbedFactory, Validator
from utils.github_utils import export_to_github

GITHUB_LINK = "https://github.com/NYTEMODEONLY/distask/blob/main/feature_requests.md"
THUMBS_UP = "👍"
THUMBS_DOWN = "👎"
DUPLICATE_EMOJI = "🔁"


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
        community_guild_id: Optional[int],
        community_channel_id: Optional[int],
        community_webhook_url: Optional[str],
    ) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.logger = logging.getLogger("distask.features")
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.community_guild_id = community_guild_id
        self.community_channel_id = community_channel_id
        self.community_webhook_url = community_webhook_url

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
                f"🔗 View all requests: {GITHUB_LINK}"
            ),
            emoji="✨",
        )
        embed.add_field(name="📋 Request ID", value=f"**#{request_id}**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._announce_to_community(
            feature_id=request_id,
            guild=interaction.guild,
            requester=interaction.user,
            title=clean_title,
            suggestion=clean_suggestion,
            suggested_priority=clean_priority,
        )

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

    async def _announce_to_community(
        self,
        *,
        feature_id: int,
        guild: Optional[discord.Guild],
        requester: discord.abc.User,
        title: str,
        suggestion: str,
        suggested_priority: Optional[str],
    ) -> None:
        if not self.community_webhook_url or not self.community_channel_id:
            return
        # Build enhanced title with emoji
        title_text = f"✨ Feature Request #{feature_id}: {title}"
        
        # Build description with suggestion
        description = suggestion or "—"
        
        embed = discord.Embed(
            title=title_text,
            description=description,
            color=discord.Color.blurple(),
        )
        
        # Add metadata line
        guild_name = guild.name if guild else "Unknown Server"
        metadata_parts = [
            f"👤 <@{requester.id}>",
            f"🏠 {guild_name}",
        ]
        if suggested_priority:
            priority_emoji = "🔴" if suggested_priority.lower() == "high" else "🟡" if suggested_priority.lower() == "medium" else "🟢"
            metadata_parts.append(f"{priority_emoji} {suggested_priority.capitalize()}")
        
        embed.description += "\n\n" + " • ".join(metadata_parts)
        
        # Add fields with emoji indicators
        embed.add_field(
            name="👤 Requested By",
            value=f"<@{requester.id}>",
            inline=True,
        )
        embed.add_field(
            name="🏠 Origin Server",
            value=guild_name,
            inline=True,
        )
        if suggested_priority:
            priority_emoji = "🔴" if suggested_priority.lower() == "high" else "🟡" if suggested_priority.lower() == "medium" else "🟢"
            embed.add_field(
                name="📊 Suggested Priority",
                value=f"{priority_emoji} {suggested_priority.capitalize()}",
                inline=True,
            )
        embed.add_field(
            name="🔗 Public Backlog",
            value=f"[View on GitHub]({GITHUB_LINK})",
            inline=False,
        )
        embed.set_footer(text="👍 / 👎 / 🔁 Vote to influence priority and duplicate detection.")

        message_id: Optional[int] = None
        try:
            avatar_url = self.bot.user.display_avatar.url if self.bot.user else None
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(self.community_webhook_url, session=session)
                webhook_message = await webhook.send(
                    embed=embed,
                    wait=True,
                    username="DisTask Feature Requests",
                    avatar_url=avatar_url,
                )
                if isinstance(webhook_message, discord.WebhookMessage):
                    message_id = webhook_message.id
        except Exception as exc:
            self.logger.exception("Failed to post feature request %s to community webhook: %s", feature_id, exc)
            return

        if not message_id:
            return

        try:
            channel = await self.bot.fetch_channel(self.community_channel_id)
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(message_id)
                for emoji in (THUMBS_UP, THUMBS_DOWN, DUPLICATE_EMOJI):
                    await message.add_reaction(emoji)
                await self.db.set_feature_request_message(feature_id, message_id=message.id, channel_id=channel.id)
        except Exception as exc:
            self.logger.exception("Failed to finalize community announcement for feature %s: %s", feature_id, exc)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction_event(payload, delta=1)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction_event(payload, delta=-1)

    async def _handle_reaction_event(self, payload: discord.RawReactionActionEvent, *, delta: int) -> None:
        if payload.user_id == (self.bot.user.id if self.bot.user else None):
            return
        if self.community_guild_id and payload.guild_id != self.community_guild_id:
            return
        if payload.channel_id != self.community_channel_id:
            return
        emoji = str(payload.emoji)
        if emoji not in {THUMBS_UP, THUMBS_DOWN, DUPLICATE_EMOJI}:
            return
        feature = await self.db.get_feature_by_message(payload.message_id)
        if not feature:
            return
        up_delta = down_delta = dup_delta = 0
        if emoji == THUMBS_UP:
            up_delta = delta
        elif emoji == THUMBS_DOWN:
            down_delta = delta
        elif emoji == DUPLICATE_EMOJI:
            dup_delta = delta
        if up_delta == down_delta == dup_delta == 0:
            return
        await self.db.adjust_feature_votes(feature["id"], up_delta=up_delta, down_delta=down_delta, duplicate_delta=dup_delta)
