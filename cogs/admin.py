from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory
from utils.validators import Validator


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, embeds: EmbedFactory) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.logger = logging.getLogger("distask.admin")

    async def board_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        boards = await self.db.fetch_boards(interaction.guild_id)
        needle = current.lower()
        results: List[app_commands.Choice[str]] = []
        for board in boards:
            if needle and needle not in board["name"].lower():
                continue
            results.append(app_commands.Choice(name=f"{board['name']} · {board['id']}", value=str(board["id"])))
            if len(results) >= 25:
                break
        if not results:
            for board in boards[:25]:
                results.append(app_commands.Choice(name=f"{board['name']} · {board['id']}", value=str(board["id"])))
        return results[:25]

    async def column_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        board_value = getattr(interaction.namespace, "board", None)
        if not board_value:
            return []
        try:
            board_id = int(board_value)
        except (TypeError, ValueError):
            return []
        columns = await self.db.fetch_columns(board_id)
        needle = current.lower()
        results: List[app_commands.Choice[str]] = []
        for column in columns:
            if needle and needle not in column["name"].lower():
                continue
            results.append(app_commands.Choice(name=column["name"], value=column["name"]))
        return results[:25]

    @app_commands.command(name="add-column", description="Add a column to a board")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def add_column(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView, AddColumnModal
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        # Check if there are any boards first
        board_options = await get_board_choices(self.db, interaction.guild_id)
        if not board_options:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Boards",
                    "This server has no boards yet. Create one with `/create-board`.",
                    emoji="📭",
                ),
            )
            return

        async def on_board_selected(inter: discord.Interaction, board_id: int, board: dict) -> None:
            # Show modal to enter column name
            modal = AddColumnModal(
                board_id=board_id,
                board_name=board["name"],
                db=self.db,
                embeds=self.embeds,
            )
            await inter.response.send_modal(modal)

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Add Column", "Select a board to add a column to:", emoji="➕"),
            view=view,
        )

    @app_commands.command(name="remove-column", description="Remove a column (must be empty)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def remove_column(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView, ColumnSelectorView, RemoveColumnConfirmationView
        from .ui.helpers import get_board_choices, get_column_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        # Check if there are any boards first
        board_options = await get_board_choices(self.db, interaction.guild_id)
        if not board_options:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Boards",
                    "This server has no boards yet. Create one with `/create-board`.",
                    emoji="📭",
                ),
            )
            return

        async def on_board_selected(inter: discord.Interaction, board_id: int, board: dict) -> None:
            # Get column options
            column_options = await get_column_choices(self.db, board_id)
            if not column_options:
                await inter.response.send_message(
                    embed=self.embeds.message(
                        "No Columns",
                        "This board has no columns.",
                        emoji="⚠️",
                    ),
                )
                return

            # Show column selector
            async def on_column_selected(col_inter: discord.Interaction, column_id: int, column: dict) -> None:
                # Show confirmation view
                confirm_view = RemoveColumnConfirmationView(
                    board_id=board_id,
                    column_name=column["name"],
                    db=self.db,
                    embeds=self.embeds,
                )
                await col_inter.response.send_message(
                    embed=self.embeds.message(
                        "Confirm Removal",
                        f"Are you sure you want to remove column **{column['name']}** from **{board['name']}**? The column must be empty.",
                        emoji="⚠️",
                    ),
                    view=confirm_view,
                )

            column_view = ColumnSelectorView(
                board_id=board_id,
                db=self.db,
                embeds=self.embeds,
                on_select=on_column_selected,
                placeholder="Select a column to remove...",
                initial_options=column_options,
            )
            await inter.response.send_message(
                embed=self.embeds.message("Remove Column", f"Select a column from **{board['name']}** to remove:", emoji="🗑️"),
                view=column_view,
            )

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Remove Column", "Select a board:", emoji="🗑️"),
            view=view,
        )

    @app_commands.command(name="toggle-notifications", description="Enable or disable due reminders for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def toggle_notifications(self, interaction: discord.Interaction) -> None:
        from .ui import NotificationToggleView

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        view = NotificationToggleView(guild_id=interaction.guild_id, db=self.db, embeds=self.embeds)
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Notification Settings",
                "Choose whether to enable or disable reminder digests for this server.",
                emoji="🔔",
            ),
            view=view,
        )

    @app_commands.command(name="set-reminder", description="Set the daily reminder time (UTC)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def set_reminder(self, interaction: discord.Interaction) -> None:
        from .ui import ReminderTimeModal

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        modal = ReminderTimeModal(db=self.db, embeds=self.embeds)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="mark-feature-completed", description="Manually mark a feature request as completed (admin only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    @app_commands.describe(feature_id="The feature request ID to mark as completed", commit_hash="Optional: commit hash that completed this feature")
    async def mark_feature_completed(
        self,
        interaction: discord.Interaction,
        feature_id: int,
        commit_hash: str | None = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        # Check if feature request exists
        try:
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

            # Check if already completed
            if feature.get("status") == "completed":
                await interaction.response.send_message(
                    embed=self.embeds.message(
                        "Already Completed",
                        f"Feature request #{feature_id} is already marked as completed.",
                        emoji="✅",
                    ),
                )
                return

            # Mark as completed
            commit_message = f"Manually marked completed via /mark-feature-completed by {interaction.user.display_name}"
            if commit_hash:
                commit_message = f"{commit_message} (commit: {commit_hash})"

            await self.db.mark_feature_completed(
                feature_id,
                commit_hash=commit_hash,
                commit_message=commit_message,
            )

            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Feature Marked Completed",
                    f"Feature request **#{feature_id}** has been marked as completed.\n\n"
                    f"**Title:** {feature.get('title', 'N/A')}\n"
                    f"**Status:** completed\n"
                    + (f"**Commit:** `{commit_hash}`\n" if commit_hash else ""),
                    emoji="✅",
                ),
            )
        except Exception as exc:
            self.logger.exception("Failed to mark feature completed: %s", exc)
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Error",
                    f"Failed to mark feature request #{feature_id} as completed: {exc}",
                    emoji="🔥",
                ),
            )

    @app_commands.command(name="distask-help", description="Show help for DisTask")
    @app_commands.checks.cooldown(1, 3.0)
    async def distask_help(self, interaction: discord.Interaction) -> None:
        # Create a rich embed with sections
        embed = discord.Embed(
            title="📚 Command Guide",
            description="DisTask Command Groups",
            color=discord.Color.from_rgb(118, 75, 162),  # Default blue-purple
        )
        
        # Boards section
        boards_commands = (
            "`/create-board` - Create a new task board\n"
            "`/list-boards` - List all boards in this server\n"
            "`/view-board` - View a board's configuration\n"
            "`/delete-board` - Delete a board and all its tasks\n"
            "`/board-stats` - Show quick stats for a board"
        )
        embed.add_field(
            name="📋 Boards",
            value=boards_commands,
            inline=False,
        )
        
        # Tasks section
        tasks_commands = (
            "`/add-task` - Create a new task on a board\n"
            "`/list-tasks` - List tasks on a board\n"
            "`/move-task` - Move a task to another column\n"
            "`/assign-task` - Assign a task to a member\n"
            "`/edit-task` - Update details for a task\n"
            "`/complete-task` - Mark a task complete/incomplete\n"
            "`/delete-task` - Remove a task\n"
            "`/search-task` - Full-text search across tasks"
        )
        embed.add_field(
            name="📝 Tasks",
            value=tasks_commands,
            inline=False,
        )
        
        # Admin section
        admin_commands = (
            "`/add-column` - Add a column to a board\n"
            "`/remove-column` - Remove a column (must be empty)\n"
            "`/toggle-notifications` - Enable or disable due reminders for this server\n"
            "`/set-reminder` - Set the daily reminder time (UTC)\n"
            "`/mark-feature-completed` - Manually mark a feature request as completed"
        )
        embed.add_field(
            name="⚙️ Admin",
            value=admin_commands,
            inline=False,
        )
        
        # Features section
        features_commands = (
            "`/request-feature` - Suggest a new feature for DisTask"
        )
        embed.add_field(
            name="✨ Features",
            value=features_commands,
            inline=False,
        )
        
        # Footer note
        embed.set_footer(text="Need more? Check the README bundled with the bot. • distask.xyz")
        embed.timestamp = datetime.now(timezone.utc)
        
        await interaction.response.send_message(embed=embed)

    async def _resolve_board(self, interaction: discord.Interaction, board_value: str):
        if not interaction.guild_id:
            raise app_commands.AppCommandError("Guild-only command.")
        try:
            board_id = int(board_value)
        except (TypeError, ValueError):
            raise app_commands.AppCommandError("Invalid board selection.")
        board = await self.db.get_board(interaction.guild_id, board_id)
        if not board:
            raise app_commands.AppCommandError("Board not found.")
        return board
