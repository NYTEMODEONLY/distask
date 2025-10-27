from __future__ import annotations

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
    @app_commands.autocomplete(board=board_autocomplete)
    @app_commands.describe(board="Board", name="Column name")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def add_column(self, interaction: discord.Interaction, board: str, name: str) -> None:
        board_data = await self._resolve_board(interaction, board)
        validation = Validator.column_name(name)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Column", validation.message, emoji="⚠️"),
                ephemeral=True,
            )
            return
        await self.db.add_column(board_data["id"], name.strip())
        await interaction.response.send_message(
            embed=self.embeds.message("Column Added", f"**{name.strip()}** is now live.", emoji="➕"),
            ephemeral=True,
        )

    @app_commands.command(name="remove-column", description="Remove a column (must be empty)")
    @app_commands.autocomplete(board=board_autocomplete, name=column_autocomplete)
    @app_commands.describe(board="Board", name="Column name")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def remove_column(self, interaction: discord.Interaction, board: str, name: str) -> None:
        board_data = await self._resolve_board(interaction, board)
        try:
            removed = await self.db.remove_column(board_data["id"], name)
        except ValueError as exc:
            await interaction.response.send_message(
                embed=self.embeds.message("Column Busy", str(exc), emoji="⚠️"),
                ephemeral=True,
            )
            return
        if not removed:
            await interaction.response.send_message(
                embed=self.embeds.message("Not Found", "That column does not exist.", emoji="⚠️"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=self.embeds.message("Column Removed", f"Deleted **{name}** from the board.", emoji="🗑️"),
            ephemeral=True,
        )

    @app_commands.command(name="toggle-notifications", description="Enable or disable due reminders for this server")
    @app_commands.describe(enabled="Enable reminders?")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def toggle_notifications(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return
        await self.db.set_notifications(interaction.guild_id, enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=self.embeds.message("Reminders", f"Digest pings {status}.", emoji="🔔"),
            ephemeral=True,
        )

    @app_commands.command(name="set-reminder", description="Set the daily reminder time (UTC)")
    @app_commands.describe(time="HH:MM 24h format")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def set_reminder(self, interaction: discord.Interaction, time: str) -> None:
        validation = Validator.reminder_time(time)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Time", validation.message, emoji="⚠️"),
                ephemeral=True,
            )
            return
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
                ephemeral=True,
            )
            return
        await self.db.set_reminder_time(interaction.guild_id, time)
        await interaction.response.send_message(
            embed=self.embeds.message("Reminder Updated", f"Daily digest scheduled for {time} UTC.", emoji="⏰"),
            ephemeral=True,
        )

    @app_commands.command(name="distask-help", description="Show help for DisTask")
    @app_commands.checks.cooldown(1, 3.0)
    async def distask_help(self, interaction: discord.Interaction) -> None:
        message = (
            "**DisTask Command Groups**\n"
            "• Boards: /create-board, /list-boards, /view-board, /delete-board, /board-stats\n"
            "• Tasks: /add-task, /list-tasks, /move-task, /assign-task, /edit-task, /complete-task, /delete-task, /search-task\n"
            "• Admin: /add-column, /remove-column, /toggle-notifications, /set-reminder\n\n"
            "Need more? Check the README bundled with the bot."
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Command Guide", message, emoji="📚"),
            ephemeral=True,
        )

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
