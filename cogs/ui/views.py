from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

import discord

if TYPE_CHECKING:
    from utils import Database, EmbedFactory

from .helpers import get_board_choices, get_column_choices
from .modals import (
    AddColumnModal,
    AddTaskModal,
    ConfirmationModal,
    TaskIDInputModal,
)


class BoardSelectorView(discord.ui.View):
    """View with a select menu for choosing a board."""

    def __init__(
        self,
        *,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        on_select: Callable,
        placeholder: str = "Select a board...",
        initial_options: list = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds
        self.on_select = on_select
        self.placeholder = placeholder

        # Set initial options if provided
        if initial_options:
            self.board_select.options = initial_options

    @discord.ui.select(placeholder="Select a board...", min_values=1, max_values=1)
    async def board_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message("Board Not Found", "That board no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return
        await self.on_select(interaction, board_id, board)
        self.stop()


class ColumnSelectorView(discord.ui.View):
    """View with a select menu for choosing a column."""

    def __init__(
        self,
        *,
        board_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        on_select: Callable,
        placeholder: str = "Select a column...",
        initial_options: list = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.board_id = board_id
        self.db = db
        self.embeds = embeds
        self.on_select = on_select
        self.placeholder = placeholder

        # Set initial options if provided
        if initial_options:
            self.column_select.options = initial_options

    @discord.ui.select(placeholder="Select a column...", min_values=1, max_values=1)
    async def column_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        column_name = select.values[0]
        column = await self.db.get_column_by_name(self.board_id, column_name)
        if not column:
            await interaction.response.send_message(
                embed=self.embeds.message("Column Not Found", "That column no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return
        await self.on_select(interaction, column["id"], column)
        self.stop()


class NotificationToggleView(discord.ui.View):
    """View with Enable/Disable buttons for notifications."""

    def __init__(self, *, guild_id: int, db: "Database", embeds: "EmbedFactory", timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds

    @discord.ui.button(label="🔔 Enable Reminders", style=discord.ButtonStyle.green, custom_id="enable")
    async def enable_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.set_notifications(self.guild_id, True)
        await interaction.followup.send(
            embed=self.embeds.message("Reminders", "Digest pings enabled.", emoji="🔔"),
        )
        self.stop()

    @discord.ui.button(label="🔕 Disable Reminders", style=discord.ButtonStyle.gray, custom_id="disable")
    async def disable_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.set_notifications(self.guild_id, False)
        await interaction.followup.send(
            embed=self.embeds.message("Reminders", "Digest pings disabled.", emoji="🔕"),
        )
        self.stop()


class CreateBoardFlowView(discord.ui.View):
    """View for the /create-board flow: channel selector → modal."""

    def __init__(
        self,
        *,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds
        self.selected_channel_id: Optional[int] = None
        self.selected_channel_name: Optional[str] = None

    @discord.ui.channel_select(
        placeholder="Select a channel for board updates...",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
        row=0,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
        try:
            channel = select.values[0]
            
            # ChannelSelect with channel_types=[discord.ChannelType.text] already filters to text channels only
            # Partial channel objects from ChannelSelect may not pass isinstance checks,
            # so we trust the filter and just extract the ID
            # Full validation will happen in the modal when we fetch the complete channel
            
            # Get channel ID and name safely
            self.selected_channel_id = channel.id
            
            # Try to get channel name - handle both full and partial channel objects
            if hasattr(channel, 'name') and channel.name:
                self.selected_channel_name = channel.name
            else:
                # Try to get from guild cache or use ID as fallback
                try:
                    full_channel = interaction.guild.get_channel(channel.id)
                    if full_channel and hasattr(full_channel, 'name'):
                        self.selected_channel_name = full_channel.name
                    else:
                        self.selected_channel_name = f"Channel {channel.id}"
                except Exception:
                    self.selected_channel_name = f"Channel {channel.id}"

            # Show modal for board name and description
            from .modals import CreateBoardModal
            
            modal = CreateBoardModal(
                cog=None,  # Not needed since we're handling channel separately
                db=self.db,
                embeds=self.embeds,
                channel_id=self.selected_channel_id,
                channel_name=self.selected_channel_name,
            )
            await interaction.response.send_modal(modal)
            self.stop()
        except Exception as e:
            logger = logging.getLogger("distask.create_board")
            logger.exception("Error in channel_select: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=self.embeds.message(
                        "Unexpected Error",
                        "Something went wrong while processing your channel selection. Please try again.",
                        emoji="🔥",
                    ),
                    ephemeral=True,
                )
            self.stop()


class AddTaskFlowView(discord.ui.View):
    """View for the /add-task flow: board selector → column selector → modal."""

    def __init__(
        self,
        *,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        initial_board_options: list,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds
        self.selected_board_id: Optional[int] = None
        self.selected_board_name: Optional[str] = None
        self.selected_column_id: Optional[int] = None
        self.selected_column_name: Optional[str] = None
        self.selected_due_date_preset: Optional[str] = None

        # Set initial board options
        self.board_select.options = initial_board_options

    @discord.ui.select(placeholder="1. Select a board...", min_values=1, max_values=1, row=0)
    async def board_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message("Board Not Found", "That board no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return

        self.selected_board_id = board_id
        self.selected_board_name = board["name"]

        # Load column options
        column_options = await get_column_choices(self.db, board_id)
        if not column_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Columns", "This board has no columns.", emoji="⚠️"),
            )
            self.stop()
            return

        self.column_select.options = column_options
        self.column_select.disabled = False
        self.due_date_preset_select.disabled = False
        self.continue_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{board['name']}**\n\nNow select a column and optionally choose a due date preset, then click Continue.",
                emoji="➕",
            ),
            view=self,
        )

    @discord.ui.select(placeholder="2. Select a column...", min_values=1, max_values=1, disabled=True, row=1)
    async def column_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        column_name = select.values[0]
        column = await self.db.get_column_by_name(self.selected_board_id, column_name)
        if not column:
            await interaction.response.send_message(
                embed=self.embeds.message("Column Not Found", "That column no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return

        self.selected_column_id = column["id"]
        self.selected_column_name = column["name"]

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{self.selected_board_name}**\nColumn: **{column_name}**\n\nOptionally choose a due date preset, then click Continue to open the task form.",
                emoji="➕",
            ),
            view=self,
        )

    @discord.ui.select(
        placeholder="3. Due Date Preset (optional)",
        min_values=0,
        max_values=1,
        disabled=True,
        row=2,
        options=[
            discord.SelectOption(label="Today", value="Today", description="Due end of today"),
            discord.SelectOption(label="Tomorrow", value="Tomorrow", description="Due end of tomorrow"),
            discord.SelectOption(label="3 Days", value="3 Days", description="Due in 3 days"),
            discord.SelectOption(label="6 Days", value="6 Days", description="Due in 6 days"),
            discord.SelectOption(label="7 Days", value="7 Days", description="Due in 7 days"),
        ],
    )
    async def due_date_preset_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if select.values:
            self.selected_due_date_preset = select.values[0]
        else:
            self.selected_due_date_preset = None
        
        preset_text = f"\nDue Date Preset: **{self.selected_due_date_preset}**" if self.selected_due_date_preset else ""
        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{self.selected_board_name}**\nColumn: **{self.selected_column_name}**{preset_text}\n\nClick Continue to open the task form.",
                emoji="➕",
            ),
            view=self,
        )

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary, disabled=True, row=3)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.selected_board_id or not self.selected_column_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Selection Required", "Please select both board and column first.", emoji="⚠️"),
            )
            return

        modal = AddTaskModal(
            board_id=self.selected_board_id,
            board_name=self.selected_board_name,
            column_id=self.selected_column_id,
            column_name=self.selected_column_name,
            db=self.db,
            embeds=self.embeds,
            due_date_preset=self.selected_due_date_preset,
        )
        await interaction.response.send_modal(modal)
        self.stop()


class TaskActionsView(discord.ui.View):
    """View with Complete/Incomplete/Delete buttons for a task."""

    def __init__(
        self,
        *,
        task_id: int,
        task: dict,
        db: "Database",
        embeds: "EmbedFactory",
        on_delete_confirmed: Optional[Callable] = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.task = task
        self.db = db
        self.embeds = embeds
        self.on_delete_confirmed = on_delete_confirmed

        # Adjust button labels based on current state
        if task.get("completed"):
            self.complete_button.label = "↩️ Mark Incomplete"
            self.complete_button.style = discord.ButtonStyle.secondary
        else:
            self.complete_button.label = "✅ Mark Complete"
            self.complete_button.style = discord.ButtonStyle.green

    @discord.ui.button(label="✅ Mark Complete", style=discord.ButtonStyle.green, custom_id="complete")
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        new_status = not self.task.get("completed", False)
        await interaction.response.defer(thinking=True)
        await self.db.toggle_complete(self.task_id, new_status)
        status = "completed" if new_status else "reopened"
        emoji = "✅" if new_status else "↩️"
        await interaction.followup.send(
            embed=self.embeds.message("Task Status", f"Task #{self.task_id} {status}.", emoji=emoji),
        )
        self.stop()

    @discord.ui.button(label="🗑️ Delete Task", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Show confirmation modal
        modal = ConfirmationModal(
            title="Confirm Task Deletion",
            label="Type the task ID to confirm",
            expected_value=str(self.task_id),
            placeholder=f"Type {self.task_id} to confirm",
            on_confirm=self._handle_delete_confirmed,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)
        self.stop()

    async def _handle_delete_confirmed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.delete_task(self.task_id)
        await interaction.followup.send(
            embed=self.embeds.message("Task Deleted", f"Removed task #{self.task_id}.", emoji="🗑️"),
        )
        if self.on_delete_confirmed:
            await self.on_delete_confirmed(interaction, self.task_id)


class DeleteBoardConfirmationView(discord.ui.View):
    """View with Cancel/Delete buttons for board deletion."""

    def __init__(
        self,
        *,
        board_id: int,
        board_name: str,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.board_id = board_id
        self.board_name = board_name
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message("Cancelled", "Board deletion cancelled.", emoji="✅"),
        )
        self.stop()

    @discord.ui.button(label="🗑️ Delete Board", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Show confirmation modal
        modal = ConfirmationModal(
            title="Confirm Board Deletion",
            label="Type the board name to confirm",
            expected_value=self.board_name,
            placeholder=f"Type '{self.board_name}' to confirm",
            on_confirm=self._handle_delete_confirmed,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)
        self.stop()

    async def _handle_delete_confirmed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        deleted = await self.db.delete_board(self.guild_id, self.board_id)
        if deleted:
            await interaction.followup.send(
                embed=self.embeds.message("Board Deleted", f"**{self.board_name}** has been archived.", emoji="🗑️"),
            )
        else:
            await interaction.followup.send(
                embed=self.embeds.message("Not Found", "Unable to locate that board.", emoji="⚠️"),
            )


class RemoveColumnConfirmationView(discord.ui.View):
    """View with Cancel/Remove buttons for column removal."""

    def __init__(
        self,
        *,
        board_id: int,
        column_name: str,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.board_id = board_id
        self.column_name = column_name
        self.db = db
        self.embeds = embeds

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message("Cancelled", "Column removal cancelled.", emoji="✅"),
        )
        self.stop()

    @discord.ui.button(label="🗑️ Remove Column", style=discord.ButtonStyle.danger, custom_id="remove")
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Show confirmation modal
        modal = ConfirmationModal(
            title="Confirm Column Removal",
            label="Type the column name to confirm",
            expected_value=self.column_name,
            placeholder=f"Type '{self.column_name}' to confirm",
            on_confirm=self._handle_remove_confirmed,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)
        self.stop()

    async def _handle_remove_confirmed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            removed = await self.db.remove_column(self.board_id, self.column_name)
        except ValueError as exc:
            await interaction.followup.send(
                embed=self.embeds.message("Column Busy", str(exc), emoji="⚠️"),
            )
            return

        if not removed:
            await interaction.followup.send(
                embed=self.embeds.message("Not Found", "That column does not exist.", emoji="⚠️"),
            )
            return

        await interaction.followup.send(
            embed=self.embeds.message("Column Removed", f"Deleted **{self.column_name}** from the board.", emoji="🗑️"),
        )


class DeleteTaskConfirmationView(discord.ui.View):
    """View specifically for delete task confirmation."""

    def __init__(
        self,
        *,
        task_id: int,
        task: dict,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.task = task
        self.db = db
        self.embeds = embeds

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message("Cancelled", "Task deletion cancelled.", emoji="✅"),
        )
        self.stop()

    @discord.ui.button(label="🗑️ Delete Task", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Show confirmation modal
        modal = ConfirmationModal(
            title="Confirm Task Deletion",
            label="Type the task ID to confirm",
            expected_value=str(self.task_id),
            placeholder=f"Type {self.task_id} to confirm",
            on_confirm=self._handle_delete_confirmed,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)
        self.stop()

    async def _handle_delete_confirmed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.delete_task(self.task_id)
        await interaction.followup.send(
            embed=self.embeds.message("Task Deleted", f"Removed task #{self.task_id}.", emoji="🗑️"),
        )
