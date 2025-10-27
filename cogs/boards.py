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
    @app_commands.describe(
        name="Board name",
        description="Optional description",
        channel="Channel where board updates and reminders post",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def create_board(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel,
        description: str | None = None,
    ) -> None:
        validation = Validator.board_name(name)
        if not validation.ok:
            await interaction.response.send_message(validation.message, ephemeral=True)
            return
        existing = await self.db.get_board_by_name(interaction.guild_id, name.strip())
        if existing:
            await interaction.response.send_message("A board with that name already exists.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        board_id = await self.db.create_board(interaction.guild_id, channel.id, name.strip(), description, interaction.user.id)
        board = await self.db.get_board(interaction.guild_id, board_id)
        columns = await self.db.fetch_columns(board_id)
        stats = await self.db.board_stats(board_id)
        embed = self.embeds.board_detail(board, columns, stats)
        await interaction.followup.send(f"Board created in {channel.mention}", embed=embed, ephemeral=True)

    @app_commands.command(name="list-boards", description="List all boards in this server")
    @app_commands.checks.cooldown(1, 3.0)
    async def list_boards(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in servers.", ephemeral=True)
            return
        boards = await self.db.fetch_boards(interaction.guild_id)
        embed = self.embeds.board_list(interaction.guild.name, boards)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delete-board", description="Delete a board and all its tasks")
    @app_commands.autocomplete(board=board_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def delete_board(self, interaction: discord.Interaction, board: str) -> None:
        board_data = await self._resolve_board(interaction, board)
        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = await self.db.delete_board(interaction.guild_id, board_data["id"])
        if deleted:
            await interaction.followup.send(f"Deleted board **{board_data['name']}**", ephemeral=True)
        else:
            await interaction.followup.send("Board not found.", ephemeral=True)

    @app_commands.command(name="view-board", description="View a board's configuration")
    @app_commands.autocomplete(board=board_autocomplete)
    @app_commands.checks.cooldown(1, 3.0)
    async def view_board(self, interaction: discord.Interaction, board: str) -> None:
        board_data = await self._resolve_board(interaction, board)
        columns = await self.db.fetch_columns(board_data["id"])
        stats = await self.db.board_stats(board_data["id"])
        embed = self.embeds.board_detail(board_data, columns, stats)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="board-stats", description="Show quick stats for a board")
    @app_commands.autocomplete(board=board_autocomplete)
    @app_commands.checks.cooldown(1, 3.0)
    async def board_stats(self, interaction: discord.Interaction, board: str) -> None:
        board_data = await self._resolve_board(interaction, board)
        stats = await self.db.board_stats(board_data["id"])
        message = (
            f"**{board_data['name']}**\n"
            f"Total tasks: {stats['total']}\n"
            f"Complete: {stats['completed']}\n"
            f"Overdue: {stats['overdue']}"
        )
        await interaction.response.send_message(message, ephemeral=True)

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
