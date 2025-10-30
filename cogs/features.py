from __future__ import annotations

import json
import logging
from typing import List, Optional

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
        await interaction.response.send_message(embed=embed)

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

    @app_commands.command(name="check-duplicates", description="Check for duplicate or similar feature requests")
    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.describe(feature_id="Optional: Check duplicates for a specific feature request ID")
    async def check_duplicates(self, interaction: discord.Interaction, feature_id: Optional[int] = None) -> None:
        """Check for duplicate or similar feature requests."""
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Guild Only",
                    "Please run /check-duplicates inside a Discord server.",
                    emoji="🏠",
                ),
            )
            return

        try:
            if feature_id:
                # Check duplicates for specific feature (global - like automation)
                feature = await self.db.get_feature_request(feature_id)
                if not feature:
                    await interaction.response.send_message(
                        embed=self.embeds.message(
                            "Not Found",
                            f"Feature request #{feature_id} does not exist.",
                            emoji="❌",
                        ),
                    )
                    return

                duplicates = await self._find_duplicates_for_feature(feature_id)
                embed = self._build_duplicate_embed(feature, duplicates)
            else:
                # List all duplicates (global - like automation)
                all_duplicates = await self._find_all_duplicates()
                embed = self._build_all_duplicates_embed(all_duplicates)

            await interaction.response.send_message(embed=embed)

        except Exception as exc:
            self.logger.exception("Failed to check duplicates: %s", exc)
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Error",
                    "Failed to check for duplicates. Please try again later.",
                    emoji="🔥",
                ),
            )

    async def _find_duplicates_for_feature(self, feature_id: int) -> List[dict]:
        """Find duplicates for a specific feature request (global across all servers, like automation)."""
        feature = await self.db.get_feature_request(feature_id)
        if not feature:
            return []

        # Fetch ALL features from ALL servers (like automation does)
        all_features = await self.db.fetch_feature_requests()
        duplicates: List[dict] = []

        # Check if marked as duplicate
        if feature.get("duplicate_of"):
            parent = await self.db.get_feature_request(feature["duplicate_of"])
            if parent:
                duplicates.append({
                    "id": parent["id"],
                    "title": parent.get("title", "Unknown"),
                    "relationship": "marked_duplicate_of",
                    "confidence": None,
                })

        # Check analysis_data for similar candidates (from automation, already global)
        analysis_data = feature.get("analysis_data")
        if analysis_data:
            if isinstance(analysis_data, str):
                analysis_data = json.loads(analysis_data)
            similar_ids = analysis_data.get("similar_candidates", [])
            for similar_id in similar_ids:
                similar_feature = await self.db.get_feature_request(similar_id)
                if similar_feature:
                    duplicates.append({
                        "id": similar_id,
                        "title": similar_feature.get("title", "Unknown"),
                        "relationship": "similar",
                        "confidence": None,
                    })

        # Find other features that are duplicates of this one (global)
        for other_feature in all_features:
            if other_feature["id"] == feature_id:
                continue
            if other_feature.get("duplicate_of") == feature_id:
                duplicates.append({
                    "id": other_feature["id"],
                    "title": other_feature.get("title", "Unknown"),
                    "relationship": "duplicate_of_this",
                    "confidence": None,
                })

        return duplicates

    async def _find_all_duplicates(self) -> List[dict]:
        """Find all feature requests marked as duplicates (global across all servers, like automation)."""
        # Fetch ALL features from ALL servers (like automation does)
        all_features = await self.db.fetch_feature_requests()
        duplicates: List[dict] = []

        for feature in all_features:
            if feature.get("duplicate_of"):
                parent_id = feature["duplicate_of"]
                parent = await self.db.get_feature_request(parent_id)
                if parent:
                    duplicates.append({
                        "duplicate_id": feature["id"],
                        "duplicate_title": feature.get("title", "Unknown"),
                        "parent_id": parent_id,
                        "parent_title": parent.get("title", "Unknown"),
                        "status": feature.get("status", "pending"),
                    })

        return duplicates

    def _build_duplicate_embed(self, feature: dict, duplicates: List[dict]) -> discord.Embed:
        """Build embed showing duplicates for a specific feature."""
        title = feature.get("title", "Unknown")
        feature_id = feature.get("id")

        embed = discord.Embed(
            title=f"🔍 Duplicate Check: Feature #{feature_id}",
            description=f"**{title}**",
            color=discord.Color.orange(),
        )

        if not duplicates:
            embed.add_field(
                name="✅ No Duplicates Found",
                value="This feature request appears to be unique.",
                inline=False,
            )
        else:
            grouped = {
                "marked_duplicate_of": [],
                "duplicate_of_this": [],
                "similar": [],
            }
            for dup in duplicates:
                rel = dup.get("relationship", "similar")
                if rel in grouped:
                    grouped[rel].append(dup)

            if grouped["marked_duplicate_of"]:
                dup_info = grouped["marked_duplicate_of"][0]
                embed.add_field(
                    name="📋 Marked as Duplicate Of",
                    value=f"**#{dup_info['id']}**: {dup_info['title']}",
                    inline=False,
                )

            if grouped["duplicate_of_this"]:
                dup_list = "\n".join([
                    f"**#{d['id']}**: {d['title']}"
                    for d in grouped["duplicate_of_this"]
                ])
                embed.add_field(
                    name="🔗 Duplicates of This Feature",
                    value=dup_list or "None",
                    inline=False,
                )

            if grouped["similar"]:
                similar_list = "\n".join([
                    f"**#{d['id']}**: {d['title']}"
                    for d in grouped["similar"][:5]  # Limit to 5
                ])
                if len(grouped["similar"]) > 5:
                    similar_list += f"\n*...and {len(grouped['similar']) - 5} more*"
                embed.add_field(
                    name="🔀 Similar Requests",
                    value=similar_list or "None",
                    inline=False,
                )

        embed.set_footer(text=f"View all requests: {GITHUB_LINK}")
        return embed

    def _build_all_duplicates_embed(self, duplicates: List[dict]) -> discord.Embed:
        """Build embed showing all duplicates."""
        embed = discord.Embed(
            title="🔍 All Duplicate Feature Requests",
            description=f"Found {len(duplicates)} feature request(s) marked as duplicates.",
            color=discord.Color.orange(),
        )

        if not duplicates:
            embed.add_field(
                name="✅ No Duplicates",
                value="No feature requests are currently marked as duplicates.",
                inline=False,
            )
        else:
            # Group by parent
            grouped: dict = {}
            for dup in duplicates:
                parent_id = dup["parent_id"]
                if parent_id not in grouped:
                    grouped[parent_id] = {
                        "parent_title": dup["parent_title"],
                        "duplicates": [],
                    }
                grouped[parent_id]["duplicates"].append({
                    "id": dup["duplicate_id"],
                    "title": dup["duplicate_title"],
                })

            # Display up to 10 groups
            for idx, (parent_id, group) in enumerate(list(grouped.items())[:10]):
                dup_list = "\n".join([
                    f"**#{d['id']}**: {d['title']}"
                    for d in group["duplicates"]
                ])
                embed.add_field(
                    name=f"📋 #{parent_id}: {group['parent_title']}",
                    value=f"Duplicates:\n{dup_list}",
                    inline=False,
                )

            if len(grouped) > 10:
                embed.add_field(
                    name="...",
                    value=f"*And {len(grouped) - 10} more duplicate groups*",
                    inline=False,
                )

        embed.set_footer(text=f"View all requests: {GITHUB_LINK}")
        return embed
