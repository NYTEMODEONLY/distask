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

    @app_commands.command(name="create-board", description="Create a new task board")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def create_board(self, interaction: discord.Interaction) -> None:
        from .ui import CreateBoardModal

        modal = CreateBoardModal(cog=self, db=self.db, embeds=self.embeds)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="list-boards", description="List all boards in this server")
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

    @app_commands.command(name="delete-board", description="Delete a board and all its tasks")
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

    @app_commands.command(name="view-board", description="View a board's configuration")
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
            stats = await self.db.board_stats(board_id)
            embed = self.embeds.board_detail(board, columns, stats)
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

    @app_commands.command(name="board-stats", description="Show quick stats for a board")
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
            embed = self.embeds.message(
                "Board Pulse",
                (
                    f"**{board['name']}**\n"
                    f"• Total: {stats['total']}\n"
                    f"• Complete: {stats['completed']}\n"
                    f"• Overdue: {stats['overdue']}"
                ),
                emoji="📊",
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
