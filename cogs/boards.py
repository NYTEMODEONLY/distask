from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory
from utils.validators import Validator


class BoardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, embeds: EmbedFactory) -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds

    async def board_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        boards = await self.db.fetch_boards(interaction.guild_id)
        results: List[app_commands.Choice[str]] = []
        needle = current.lower()
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

    @app_commands.command(name="create-board", description="[Server] Create a new task board")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def create_board(self, interaction: discord.Interaction) -> None:
        from .ui import CreateBoardFlowView

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to create boards.", emoji="⚠️"),
            )
            return

        view = CreateBoardFlowView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
        )
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Create Board",
                "Select a channel where board updates and reminders will be posted:",
                emoji="📋",
            ),
            view=view,
        )

    @app_commands.command(name="list-boards", description="[Server] List all boards in this server")
    @app_commands.checks.cooldown(1, 3.0)
    async def list_boards(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to manage boards.", emoji="⚠️"),
            )
            return
        boards = await self.db.fetch_boards(interaction.guild_id)
        embed = self.embeds.board_list(interaction.guild.name, boards)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="delete-board", description="[Server] Delete a board and all its tasks")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def delete_board(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView, DeleteBoardConfirmationView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to manage boards.", emoji="⚠️"),
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
            # Show confirmation view
            confirm_view = DeleteBoardConfirmationView(
                board_id=board_id,
                board_name=board["name"],
                guild_id=inter.guild_id,
                db=self.db,
                embeds=self.embeds,
            )
            await inter.response.send_message(
                embed=self.embeds.message(
                    "Confirm Deletion",
                    f"Are you sure you want to delete **{board['name']}**? This will remove all tasks and columns.",
                    emoji="⚠️",
                ),
                view=confirm_view,
            )

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board to delete...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Delete Board", "Select a board to delete:", emoji="🗑️"),
            view=view,
        )

    @app_commands.command(name="recover-board", description="[Server] Recover a deleted board")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def recover_board(self, interaction: discord.Interaction) -> None:
        from .ui import RecoverBoardFlowView

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to recover boards.", emoji="⚠️"),
            )
            return

        # Check if there are any deleted boards
        deleted_boards = await self.db.fetch_deleted_boards(interaction.guild_id)
        if not deleted_boards:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Deleted Boards",
                    "This server has no deleted boards to recover.",
                    emoji="ℹ️",
                ),
            )
            return

        view = RecoverBoardFlowView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            deleted_boards=deleted_boards,
        )

        await interaction.response.send_message(
            embed=self.embeds.message("Recover Board", "Select a deleted board to recover:", emoji="♻️"),
            view=view,
        )

    @app_commands.command(name="view-board", description="[Server] View a board's configuration")
    @app_commands.checks.cooldown(1, 3.0)
    async def view_board(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to manage boards.", emoji="⚠️"),
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
            await inter.response.defer(thinking=True)
            columns = await self.db.fetch_columns(board_id)
            stats = await self.db.board_stats_detailed(board_id)

            # Fetch channel mention if available
            channel_mention = None
            if board.get("channel_id"):
                try:
                    channel = inter.guild.get_channel(board["channel_id"])
                    if channel:
                        channel_mention = channel.mention
                except Exception:
                    pass

            # Get creator mention if available
            creator_mention = None
            if board.get("created_by"):
                creator_mention = f"<@{board['created_by']}>"

            embed = self.embeds.board_detail(
                board,
                columns,
                stats,
                channel_mention=channel_mention,
                creator_mention=creator_mention,
            )
            await inter.followup.send(embed=embed)

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board to view...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("View Board", "Select a board to view its configuration:", emoji="📋"),
            view=view,
        )

    @app_commands.command(name="board-stats", description="[Server] Show quick stats for a board")
    @app_commands.checks.cooldown(1, 3.0)
    async def board_stats(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Join a server to manage boards.", emoji="⚠️"),
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
            await inter.response.defer(thinking=True)
            stats = await self.db.board_stats(board_id)
            
            # Calculate health-based color
            total = stats.get("total", 0)
            overdue = stats.get("overdue", 0)
            completed = stats.get("completed", 0)
            active = total - completed
            
            # Determine color
            if total == 0:
                color = discord.Color.from_rgb(118, 75, 162)  # Default blue-purple
            elif overdue == 0:
                color = discord.Color.from_rgb(46, 204, 113)  # Green - healthy
            elif overdue <= 5:
                color = discord.Color.from_rgb(243, 156, 18)  # Yellow - some overdue
            elif overdue <= 10:
                color = discord.Color.from_rgb(230, 126, 34)  # Orange - multiple overdue
            else:
                color = discord.Color.from_rgb(231, 76, 60)  # Red - critical
            
            # Build enhanced description with visual indicators
            description_parts = [f"📋 **{board['name']}** · #{board_id}"]
            
            # Stats with emojis
            stats_parts = []
            if total > 0:
                stats_parts.append(f"📊 **{total}** total")
            if completed > 0:
                stats_parts.append(f"✅ **{completed}** completed")
            if active > 0:
                stats_parts.append(f"⏳ **{active}** active")
            if overdue > 0:
                stats_parts.append(f"🔴 **{overdue}** overdue")
            
            if stats_parts:
                description_parts.append("\n" + "  •  ".join(stats_parts))
            
            # Add progress bar if there are tasks
            if total > 0:
                from utils.embeds import _create_progress_bar
                percentage = int((completed / total) * 100)
                progress_bar = _create_progress_bar(completed, total, length=16)
                description_parts.append(f"\n\n{progress_bar} {percentage}% complete")
            
            embed = self.embeds.message(
                "Board Pulse",
                "\n".join(description_parts),
                emoji="📊",
                color=color,
            )
            await inter.followup.send(embed=embed)

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board to view stats...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Board Stats", "Select a board to view its stats:", emoji="📊"),
            view=view,
        )

    async def _resolve_board(self, interaction: discord.Interaction, board_value: str):
        if not interaction.guild_id:
            raise app_commands.AppCommandError("This command must be used in a guild.")
        try:
            board_id = int(board_value)
        except (TypeError, ValueError):
            raise app_commands.AppCommandError("Invalid board selection.")
        board = await self.db.get_board(interaction.guild_id, board_id)
        if not board:
            raise app_commands.AppCommandError("Board not found.")
        return board
