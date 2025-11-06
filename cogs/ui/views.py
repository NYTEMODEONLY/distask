from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List, Optional

import discord

if TYPE_CHECKING:
    from utils import Database, EmbedFactory

from .helpers import get_board_choices, get_column_choices, get_task_choices
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
    async def board_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Board Not Found", "That board no longer exists.", emoji="⚠️"
                ),
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
    async def column_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        column_name = select.values[0]
        column = await self.db.get_column_by_name(self.board_id, column_name)
        if not column:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Column Not Found", "That column no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return
        await self.on_select(interaction, column["id"], column)
        self.stop()


class NotificationToggleView(discord.ui.View):
    """View with Enable/Disable buttons for notifications."""

    def __init__(
        self,
        *,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds

    @discord.ui.button(
        label="🔔 Enable Reminders", style=discord.ButtonStyle.green, custom_id="enable"
    )
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.set_notifications(self.guild_id, True)
        await interaction.followup.send(
            embed=self.embeds.message("Reminders", "Digest pings enabled.", emoji="🔔"),
        )
        self.stop()

    @discord.ui.button(
        label="🔕 Disable Reminders",
        style=discord.ButtonStyle.gray,
        custom_id="disable",
    )
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=True)
        await self.db.set_notifications(self.guild_id, False)
        await interaction.followup.send(
            embed=self.embeds.message(
                "Reminders", "Digest pings disabled.", emoji="🔕"
            ),
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

        # Create and add ChannelSelect component
        channel_select = discord.ui.ChannelSelect(
            placeholder="Select a channel for board updates...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )

        # Create wrapper callback - Discord.py only passes interaction when manually set
        async def channel_select_callback_wrapper(
            interaction: discord.Interaction,
        ) -> None:
            # Get the select component from the view
            select_component = None
            for item in self.children:
                if isinstance(item, discord.ui.ChannelSelect) and item.row == 0:
                    select_component = item
                    break
            if select_component:
                await self.channel_select_callback(interaction, select_component)

        channel_select.callback = channel_select_callback_wrapper
        self.add_item(channel_select)

    async def channel_select_callback(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        try:
            channel = select.values[0]

            # ChannelSelect with channel_types=[discord.ChannelType.text] already filters to text channels only
            # Partial channel objects from ChannelSelect may not pass isinstance checks,
            # so we trust the filter and just extract the ID
            # Full validation will happen in the modal when we fetch the complete channel

            # Get channel ID and name safely
            self.selected_channel_id = channel.id

            # Try to get channel name - handle both full and partial channel objects
            if hasattr(channel, "name") and channel.name:
                self.selected_channel_name = channel.name
            else:
                # Try to get from guild cache or use ID as fallback
                try:
                    full_channel = interaction.guild.get_channel(channel.id)
                    if full_channel and hasattr(full_channel, "name"):
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
                )
            self.stop()


class QuickCreateBoardView(discord.ui.View):
    """Simple view with a button to create a board - shown when no boards exist."""

    def __init__(
        self,
        *,
        guild_id: int,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.db = db
        self.embeds = embeds

    @discord.ui.button(
        label="Create Board", style=discord.ButtonStyle.primary, emoji="➕"
    )
    async def create_board_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Launch the board creation flow."""
        # Check if user has manage_guild permission
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Insufficient Permissions",
                    "You need the 'Manage Server' permission to create boards.",
                    emoji="🚫",
                ),
                ephemeral=True,
            )
            return

        # Launch the full board creation flow
        create_view = CreateBoardFlowView(
            guild_id=self.guild_id,
            db=self.db,
            embeds=self.embeds,
        )

        await interaction.response.send_message(
            embed=self.embeds.message(
                "Create Board",
                "Select a channel where board updates will be posted:",
                emoji="📋",
            ),
            view=create_view,
        )
        self.stop()


class AddTaskFlowView(discord.ui.View):
    """View for the /add-task flow: board selector → column selector → modal.

    Shows one step at a time with back/cancel buttons.
    """

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
        self.selected_assignee_ids: List[int] = []  # Support multiple assignees
        self.selected_assignee_names: List[str] = []  # Support multiple assignee names
        self.selected_due_date_preset: Optional[str] = None
        self.current_step: int = 1  # 1=board, 2=column, 3=assignee, 4=due_date, 5=ready

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create column_select manually (Discord requires at least one option even when disabled)
        column_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[
                discord.SelectOption(
                    label="(Select board first)", value="__placeholder__", default=False
                )
            ],
        )
        column_select.callback = self.column_select_callback
        self.add_item(column_select)
        self.column_select = column_select

        # Create user_select for assignee selection (supports multiple users)
        user_select = discord.ui.UserSelect(
            placeholder="3. Assign to user(s) (optional)",
            min_values=0,
            max_values=25,  # Discord limit; support multiple assignees
            disabled=True,
            row=2,
        )

        # Create wrapper callback - Discord.py only passes interaction when manually set
        async def user_select_callback_wrapper(
            interaction: discord.Interaction,
        ) -> None:
            # Get the select component from the view
            select_component = None
            for item in self.children:
                if isinstance(item, discord.ui.UserSelect) and item.row == 2:
                    select_component = item
                    break
            if select_component:
                await self.user_select_callback(interaction, select_component)

        user_select.callback = user_select_callback_wrapper
        self.add_item(user_select)
        self.user_select = user_select

    @discord.ui.select(
        placeholder="1. Select a board...", min_values=1, max_values=1, row=0
    )
    async def board_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Board Not Found", "That board no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        self.selected_board_id = board_id
        self.selected_board_name = board["name"]
        self.current_step = 2

        # Load column options
        column_options = await get_column_choices(self.db, board_id)
        if not column_options:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Columns", "This board has no columns.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        # Show only column select, hide board select
        self.board_select.disabled = True
        self.column_select.options = column_options
        self.column_select.disabled = False
        self.column_select.placeholder = "2. Select a column..."
        if hasattr(self, "due_date_preset_select"):
            self.due_date_preset_select.disabled = True
        if hasattr(self, "continue_button"):
            self.continue_button.disabled = True
        if hasattr(self, "back_button"):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{board['name']}**\n\nNow select a column.",
                emoji="➕",
            ),
            view=self,
        )

    async def column_select_callback(self, interaction: discord.Interaction) -> None:
        # Discord.py passes only interaction when callback is manually set
        # Get values from interaction data
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        column_name = values[0]
        column = await self.db.get_column_by_name(self.selected_board_id, column_name)
        if not column:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Column Not Found", "That column no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        self.selected_column_id = column["id"]
        self.selected_column_name = column["name"]
        self.current_step = 3

        # Show user select, hide column select
        self.board_select.disabled = True
        self.column_select.disabled = True
        self.user_select.disabled = False
        if hasattr(self, "due_date_preset_select"):
            self.due_date_preset_select.disabled = True
        if hasattr(self, "continue_button"):
            self.continue_button.disabled = True
        if hasattr(self, "back_button"):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{self.selected_board_name}**\nColumn: **{column_name}**\n\nOptionally assign to one or more users, then choose a due date preset.",
                emoji="➕",
            ),
            view=self,
        )

    async def user_select_callback(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ) -> None:
        # UserSelect callback receives both interaction and select component
        # Get selected users from select.values (UserSelect returns User objects)
        if not select.values:
            # No users selected (min_values=0 allows this)
            self.selected_assignee_ids = []
            self.selected_assignee_names = []
        else:
            # Support multiple users
            self.selected_assignee_ids = [user.id for user in select.values]
            self.selected_assignee_names = [user.display_name for user in select.values]

        self.current_step = 4

        # Show due date select
        self.board_select.disabled = True
        self.column_select.disabled = True
        self.user_select.disabled = True
        if hasattr(self, "due_date_preset_select"):
            self.due_date_preset_select.disabled = False
        if hasattr(self, "continue_button"):
            self.continue_button.disabled = False

        # Format assignee text for display
        if self.selected_assignee_ids:
            if len(self.selected_assignee_names) == 1:
                assignee_text = f"\nAssignee: **{self.selected_assignee_names[0]}**"
            else:
                assignee_text = (
                    f"\nAssignees: **{', '.join(self.selected_assignee_names[:3])}"
                    + (
                        f" +{len(self.selected_assignee_names) - 3} more**"
                        if len(self.selected_assignee_names) > 3
                        else "**"
                    )
                )
        else:
            assignee_text = ""

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{self.selected_board_name}**\nColumn: **{self.selected_column_name}**{assignee_text}\n\nOptionally choose a due date preset, then click Continue.",
                emoji="➕",
            ),
            view=self,
        )

    @discord.ui.select(
        placeholder="4. Due Date Preset (optional)",
        min_values=0,
        max_values=1,
        disabled=True,
        row=3,
        options=[
            discord.SelectOption(
                label="Today", value="Today", description="Due end of today"
            ),
            discord.SelectOption(
                label="Tomorrow", value="Tomorrow", description="Due end of tomorrow"
            ),
            discord.SelectOption(
                label="3 Days", value="3 Days", description="Due in 3 days"
            ),
            discord.SelectOption(
                label="6 Days", value="6 Days", description="Due in 6 days"
            ),
            discord.SelectOption(
                label="7 Days", value="7 Days", description="Due in 7 days"
            ),
        ],
    )
    async def due_date_preset_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        if select.values:
            self.selected_due_date_preset = select.values[0]
        else:
            self.selected_due_date_preset = None

        preset_text = (
            f"\nDue Date Preset: **{self.selected_due_date_preset}**"
            if self.selected_due_date_preset
            else ""
        )
        # Format assignee text for display
        if self.selected_assignee_ids:
            if len(self.selected_assignee_names) == 1:
                assignee_text = f"\nAssignee: **{self.selected_assignee_names[0]}**"
            else:
                assignee_text = (
                    f"\nAssignees: **{', '.join(self.selected_assignee_names[:3])}"
                    + (
                        f" +{len(self.selected_assignee_names) - 3} more**"
                        if len(self.selected_assignee_names) > 3
                        else "**"
                    )
                )
        else:
            assignee_text = ""
        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Add Task",
                f"Board: **{self.selected_board_name}**\nColumn: **{self.selected_column_name}**{assignee_text}{preset_text}\n\nClick Continue to open the task form.",
                emoji="➕",
            ),
            view=self,
        )

    @discord.ui.button(
        label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=4
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.current_step == 2:
            # Go back to board selection
            self.current_step = 1
            self.selected_board_id = None
            self.selected_board_name = None
            self.board_select.disabled = False
            self.column_select.disabled = True
            self.column_select.placeholder = "Select a board first..."
            self.due_date_preset_select.disabled = True
            self.continue_button.disabled = True
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message(
                    "Add Task", "Select a board to add a task:", emoji="➕"
                ),
                view=self,
            )
        elif self.current_step == 3:
            # Go back to column selection
            self.current_step = 2
            self.selected_column_id = None
            self.selected_column_name = None
            self.board_select.disabled = True
            self.column_select.disabled = False
            self.user_select.disabled = True
            if hasattr(self, "due_date_preset_select"):
                self.due_date_preset_select.disabled = True
            if hasattr(self, "continue_button"):
                self.continue_button.disabled = True
            if hasattr(self, "back_button"):
                self.back_button.disabled = False

            await interaction.response.edit_message(
                embed=self.embeds.message(
                    "Add Task",
                    f"Board: **{self.selected_board_name}**\n\nNow select a column.",
                    emoji="➕",
                ),
                view=self,
            )
        elif self.current_step == 4:
            # Go back to user selection
            self.current_step = 3
            self.selected_assignee_ids = []
            self.selected_assignee_names = []
            self.board_select.disabled = True
            self.column_select.disabled = True
            self.user_select.disabled = False
            if hasattr(self, "due_date_preset_select"):
                self.due_date_preset_select.disabled = True
            if hasattr(self, "continue_button"):
                self.continue_button.disabled = True
            if hasattr(self, "back_button"):
                self.back_button.disabled = False

            await interaction.response.edit_message(
                embed=self.embeds.message(
                    "Add Task",
                    f"Board: **{self.selected_board_name}**\nColumn: **{self.selected_column_name}**\n\nOptionally assign to one or more users, then choose a due date preset.",
                    emoji="➕",
                ),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=4)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Cancelled", "Task creation cancelled.", emoji="❌"
            ),
            view=None,
        )
        self.stop()

    @discord.ui.button(
        label="Continue", style=discord.ButtonStyle.primary, disabled=True, row=4
    )
    async def continue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.selected_board_id or not self.selected_column_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Selection Required",
                    "Please select both board and column first.",
                    emoji="⚠️",
                ),
            )
            return

        modal = AddTaskModal(
            board_id=self.selected_board_id,
            board_name=self.selected_board_name,
            column_id=self.selected_column_id,
            column_name=self.selected_column_name,
            db=self.db,
            embeds=self.embeds,
            assignee_ids=self.selected_assignee_ids,  # Pass multiple assignees
            due_date_preset=self.selected_due_date_preset,
        )
        await interaction.response.send_modal(modal)
        self.stop()


class EditTaskFlowView(discord.ui.View):
    """View for the /edit-task flow: board selector → task selector → edit modal.

    Shows one step at a time with back/cancel buttons.
    Only shows tasks created by the user (or all tasks if admin).
    """

    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
        is_admin: bool,
        db: "Database",
        embeds: "EmbedFactory",
        initial_board_options: list,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.is_admin = is_admin
        self.db = db
        self.embeds = embeds
        self.selected_board_id: Optional[int] = None
        self.selected_board_name: Optional[str] = None
        self.selected_task_id: Optional[int] = None
        self.selected_task: Optional[dict] = None
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create task_select manually (Discord requires at least one option even when disabled)
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[
                discord.SelectOption(
                    label="(Select board first)", value="__placeholder__", default=False
                )
            ],
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

    @discord.ui.select(
        placeholder="1. Select a board...", min_values=1, max_values=1, row=0
    )
    async def board_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Board Not Found", "That board no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        self.selected_board_id = board_id
        self.selected_board_name = board["name"]
        self.current_step = 2

        # Load task options (filtered by creator unless admin)
        task_options = await get_task_choices(
            self.db, board_id, self.user_id, self.is_admin
        )
        if not task_options:
            filter_msg = "that you created" if not self.is_admin else ""
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Tasks Found",
                    f"This board has no tasks{filter_msg} that you can edit.",
                    emoji="⚠️",
                ),
            )
            self.stop()
            return

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task to edit..."
        if hasattr(self, "back_button"):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Edit Task",
                f"Board: **{board['name']}**\n\nSelect a task to edit.",
                emoji="✏️",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        # Discord.py passes only interaction when callback is manually set
        # Get values from interaction data
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Task Not Found", "That task no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        # Verify task belongs to selected board
        if task.get("board_id") != self.selected_board_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Task", "Task doesn't belong to selected board.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        # Verify permissions: user created it OR is admin
        if not self.is_admin and task.get("created_by") != self.user_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Permission Denied",
                    "You can only edit tasks that you created. Server admins can edit any task.",
                    emoji="🚫",
                ),
            )
            self.stop()
            return

        self.selected_task_id = task_id
        self.selected_task = task

        # Show edit modal
        from .modals import EditTaskModal

        edit_modal = EditTaskModal(
            task_id=task_id,
            task=task,
            db=self.db,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(edit_modal)
        self.stop()

    @discord.ui.button(
        label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=2
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.current_step == 2:
            # Go back to board selection
            self.current_step = 1
            self.selected_board_id = None
            self.selected_board_name = None
            self.selected_task_id = None
            self.selected_task = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message(
                    "Edit Task", "Select a board to edit a task:", emoji="✏️"
                ),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Cancelled", "Task editing cancelled.", emoji="❌"
            ),
            view=None,
        )
        self.stop()


class EditTaskButtonView(discord.ui.View):
    """View with a button to open the edit task modal (legacy - kept for compatibility)."""

    def __init__(
        self,
        *,
        task_id: int,
        task: dict,
        db: "Database",
        embeds: "EmbedFactory",
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.task = task
        self.db = db
        self.embeds = embeds

    @discord.ui.button(label="✏️ Edit Task", style=discord.ButtonStyle.primary)
    async def edit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from .modals import EditTaskModal

        edit_modal = EditTaskModal(
            task_id=self.task_id,
            task=self.task,
            db=self.db,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(edit_modal)
        self.stop()


class CompleteTaskFlowView(discord.ui.View):
    """View for the /complete-task flow: board selector → task selector → action buttons.

    Shows one step at a time with back/cancel buttons.
    Shows all tasks (no creator filter for completion).
    """

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
        self.selected_task_id: Optional[int] = None
        self.selected_task: Optional[dict] = None
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options (after super().__init__() creates components from decorators)
        # Find board_select component and set options
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.row == 0:
                item.options = initial_board_options
                self.board_select = item
                break

        # Create task_select manually (Discord requires at least one option even when disabled)
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[
                discord.SelectOption(
                    label="(Select board first)", value="__placeholder__", default=False
                )
            ],
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

    @discord.ui.select(
        placeholder="1. Select a board...", min_values=1, max_values=1, row=0
    )
    async def board_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        board_id = int(select.values[0])
        board = await self.db.get_board(self.guild_id, board_id)
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Board Not Found", "That board no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        self.selected_board_id = board_id
        self.selected_board_name = board["name"]
        self.current_step = 2

        # Load task options (show all tasks - no creator filter for completion)
        task_options = await get_task_choices(
            self.db, board_id, 0, True
        )  # Pass dummy user_id, is_admin=True to show all
        if not task_options:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Tasks Found",
                    "This board has no tasks.",
                    emoji="⚠️",
                ),
            )
            self.stop()
            return

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task..."
        if hasattr(self, "back_button"):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Complete Task",
                f"Board: **{board['name']}**\n\nSelect a task to mark complete/incomplete.",
                emoji="✅",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        # Discord.py passes only interaction when callback is manually set
        # Get values from interaction data
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Task Not Found", "That task no longer exists.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        # Verify task belongs to selected board
        if task.get("board_id") != self.selected_board_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Task", "Task doesn't belong to selected board.", emoji="⚠️"
                ),
            )
            self.stop()
            return

        self.selected_task_id = task_id
        self.selected_task = task

        # Show task actions view with Complete/Incomplete/Delete buttons
        view = TaskActionsView(
            task_id=task_id,
            task=task,
            db=self.db,
            embeds=self.embeds,
        )
        task_embed = self.embeds.task_detail(task, task.get("column_name", "Unknown"))
        await interaction.response.edit_message(embed=task_embed, view=view)
        self.stop()

    @discord.ui.button(
        label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=2
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.current_step == 2:
            # Go back to board selection
            self.current_step = 1
            self.selected_board_id = None
            self.selected_board_name = None
            self.selected_task_id = None
            self.selected_task = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message(
                    "Complete Task",
                    "Select a board to mark a task complete/incomplete:",
                    emoji="✅",
                ),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Cancelled", "Task completion cancelled.", emoji="❌"
            ),
            view=None,
        )
        self.stop()


class SelfAssignTaskView(discord.ui.View):
    """Simple view with a button to self-assign to a task."""

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

    @discord.ui.button(
        label="Assign to Me", style=discord.ButtonStyle.primary, emoji="👤"
    )
    async def assign_to_me_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Assign the current user to this task."""
        await interaction.response.defer(thinking=True)

        # Check if already assigned
        assignee_ids = self.task.get("assignee_ids", [])
        if interaction.user.id in assignee_ids:
            await interaction.followup.send(
                embed=self.embeds.message(
                    "Already Assigned",
                    f"You're already assigned to task #{self.task_id}.",
                    emoji="ℹ️",
                ),
                ephemeral=True,
            )
            return

        # Assign user to task
        await self.db.add_task_assignees(self.task_id, [interaction.user.id])

        # Send notifications if event notifier is available
        if hasattr(interaction.client, "event_notifier"):
            try:
                await interaction.client.event_notifier.notify_task_assigned(
                    task_id=self.task_id,
                    assignee_ids=[interaction.user.id],
                    assigned_by_id=interaction.user.id,
                )
            except Exception:
                # Don't fail the operation if notifications fail
                pass

        await interaction.followup.send(
            embed=self.embeds.message(
                "Self-Assigned",
                f"You've been assigned to task #{self.task_id}.",
                emoji="✅",
            ),
        )
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

    @discord.ui.button(
        label="✅ Mark Complete", style=discord.ButtonStyle.green, custom_id="complete"
    )
    async def complete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        new_status = not self.task.get("completed", False)
        
        # If marking complete, show notes modal; if marking incomplete, just toggle
        if new_status:
            from .modals import CompletionNotesModal
            
            async def on_complete(interaction: discord.Interaction, notes: Optional[str]) -> None:
                await interaction.response.defer(thinking=True)
                await self.db.toggle_complete(self.task_id, True, completion_notes=notes)
                status_msg = f"Task #{self.task_id} completed."
                if notes:
                    status_msg += f"\n\n📝 Notes: {notes}"
                await interaction.followup.send(
                    embed=self.embeds.message("Task Completed", status_msg, emoji="✅"),
                )
                self.stop()
            
            modal = CompletionNotesModal(
                task_id=self.task_id,
                db=self.db,
                embeds=self.embeds,
                on_complete=on_complete,
            )
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer(thinking=True)
            await self.db.toggle_complete(self.task_id, False)
            await interaction.followup.send(
                embed=self.embeds.message("Task Status", f"Task #{self.task_id} reopened.", emoji="↩️"),
            )
            self.stop()

    @discord.ui.button(label="👤 Self Assign", style=discord.ButtonStyle.primary, custom_id="self_assign", row=1)
    async def self_assign_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user_id = interaction.user.id
        await interaction.response.defer(thinking=True)
        
        # Get current assignees
        current_assignees = self.task.get("assignee_ids", [])
        if not isinstance(current_assignees, list):
            current_assignees = []
        
        # Check if already assigned
        if user_id in current_assignees:
            await interaction.followup.send(
                embed=self.embeds.message("Already Assigned", f"You are already assigned to task #{self.task_id}.", emoji="ℹ️"),
            )
            return
        
        # Add user as assignee
        await self.db.add_task_assignees(self.task_id, [user_id])
        await interaction.followup.send(
            embed=self.embeds.message("Self Assigned", f"You have been assigned to task #{self.task_id}.", emoji="👤"),
        )
        self.stop()

    @discord.ui.button(
        label="🗑️ Delete Task", style=discord.ButtonStyle.danger, custom_id="delete"
    )
    async def delete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
            embed=self.embeds.message(
                "Task Deleted", f"Removed task #{self.task_id}.", emoji="🗑️"
            ),
        )
        if self.on_delete_confirmed:
            await self.on_delete_confirmed(interaction, self.task_id)


class MoveTaskFlowView(discord.ui.View):
    """View for the /move-task flow: board selector → task selector → column selector."""

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
        self.selected_task_id: Optional[int] = None
        self.selected_task: Optional[dict] = None
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create task_select manually
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[discord.SelectOption(label="(Select board first)", value="__placeholder__", default=False)]
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

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
        self.current_step = 2

        # Load task options (show all non-completed tasks)
        task_options = await get_task_choices(self.db, board_id, 0, True)
        # Filter out completed tasks manually
        task_options = [opt for opt in task_options if not opt.label.startswith("✅")]
        if not task_options:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "No Tasks Found",
                    "This board has no active tasks to move.",
                    emoji="⚠️",
                ),
            )
            self.stop()
            return

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task to move..."
        if hasattr(self, 'back_button'):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Move Task",
                f"Board: **{board['name']}**\n\nSelect a task to move.",
                emoji="🧭",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message("Task Not Found", "That task no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return

        if task.get("board_id") != self.selected_board_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Task", "Task doesn't belong to selected board.", emoji="⚠️"),
            )
            self.stop()
            return

        self.selected_task_id = task_id
        self.selected_task = task

        # Get column options for the task's board
        from .helpers import get_column_choices
        column_options = await get_column_choices(self.db, task["board_id"])
        if not column_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Columns", "This board has no columns.", emoji="⚠️"),
            )
            self.stop()
            return

        # Show column selector
        async def on_column_selected(col_inter: discord.Interaction, column_id: int, column: dict) -> None:
            await col_inter.response.defer(thinking=True)
            
            # Get original column name for notification
            old_column = await self.db.get_column_by_id(task["column_id"])
            old_column_name = old_column["name"] if old_column else "Unknown"
            
            # Move task
            await self.db.move_task(task_id, column_id)
            
            # Send event notification if available
            if hasattr(col_inter.client, "event_notifier") and col_inter.guild_id:
                try:
                    # Get updated task data
                    updated_task = await self.db.fetch_task(task_id)
                    board = await self.db.get_board(col_inter.guild_id, task["board_id"])
                    if updated_task and board:
                        await col_inter.client.event_notifier.notify_task_moved(
                            task=updated_task,
                            from_column=old_column_name,
                            to_column=column["name"],
                            mover_id=col_inter.user.id,
                            guild_id=col_inter.guild_id,
                            channel_id=board["channel_id"],
                        )
                except Exception:
                    # Don't fail the operation if notifications fail
                    pass
            
            await col_inter.followup.send(
                embed=self.embeds.message("Task Moved", f"Task #{task_id} → **{column['name']}**", emoji="🧭"),
            )

        column_view = ColumnSelectorView(
            board_id=task["board_id"],
            db=self.db,
            embeds=self.embeds,
            on_select=on_column_selected,
            placeholder="Select target column...",
            initial_options=column_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Move Task", f"Select a column to move task #{task_id} to:", emoji="🧭"),
            view=column_view,
        )
        self.stop()

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_step == 2:
            self.current_step = 1
            self.selected_board_id = None
            self.selected_task_id = None
            self.selected_task = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message("Move Task", "Select a board to move a task:", emoji="🧭"),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message("Cancelled", "Task move cancelled.", emoji="❌"),
            view=None,
        )
        self.stop()


class AssignTaskFlowView(discord.ui.View):
    """View for the /assign-task flow: board selector → task selector → user selector."""

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
        self.selected_task_id: Optional[int] = None
        self.selected_task: Optional[dict] = None
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create task_select manually
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[discord.SelectOption(label="(Select board first)", value="__placeholder__", default=False)]
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

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
        self.current_step = 2

        # Load task options (show all tasks)
        task_options = await get_task_choices(self.db, board_id, 0, True)
        if not task_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Tasks Found", "This board has no tasks.", emoji="⚠️"),
            )
            self.stop()
            return

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task to assign..."
        if hasattr(self, 'back_button'):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Assign Task",
                f"Board: **{board['name']}**\n\nSelect a task to assign.",
                emoji="👥",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message("Task Not Found", "That task no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return

        if task.get("board_id") != self.selected_board_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Task", "Task doesn't belong to selected board.", emoji="⚠️"),
            )
            self.stop()
            return

        self.selected_task_id = task_id
        self.selected_task = task

        # Show user select for assigning
        from .helpers import parse_user_mention_or_id
        
        # Create user select
        user_select = discord.ui.UserSelect(
            placeholder="Select user(s) to assign...",
            min_values=1,
            max_values=10,
            row=2,
        )
        
        async def on_user_selected(user_inter: discord.Interaction) -> None:
            # UserSelect callbacks only receive the interaction
            # Access selected users via interaction.data['values'] or the select component
            if not user_inter.data or "values" not in user_inter.data:
                await user_inter.response.send_message(
                    embed=self.embeds.message("No Users Selected", "Please select at least one user.", emoji="⚠️"),
                )
                return
            
            # Get selected user IDs from interaction data
            selected_user_ids = [int(uid) for uid in user_inter.data.get("values", [])]
            if not selected_user_ids:
                await user_inter.response.send_message(
                    embed=self.embeds.message("No Users Selected", "Please select at least one user.", emoji="⚠️"),
                )
                return
            
            await user_inter.response.defer(thinking=True)
            
            # Add assignees (they'll be added to existing ones)
            await self.db.add_task_assignees(task_id, selected_user_ids)
            
            # Send event notification if available
            if hasattr(user_inter.client, "event_notifier") and user_inter.guild_id:
                try:
                    await user_inter.client.event_notifier.notify_task_assigned(
                        task_id=task_id,
                        assignee_ids=selected_user_ids,
                        assigned_by_id=user_inter.user.id,
                    )
                except Exception:
                    # Don't fail the operation if notifications fail
                    pass
            
            # Format success message
            if len(selected_user_ids) == 1:
                message = f"Task #{task_id} now includes <@{selected_user_ids[0]}> as an assignee."
            else:
                mentions = ", ".join([f"<@{uid}>" for uid in selected_user_ids])
                message = f"Task #{task_id} now includes {mentions} as assignees."
            
            await user_inter.followup.send(
                embed=self.embeds.message("Task Assigned", message, emoji="👥"),
            )
        
        user_select.callback = on_user_selected
        
        view = discord.ui.View(timeout=300.0)
        view.add_item(user_select)
        
        await interaction.response.send_message(
            embed=self.embeds.message("Assign Task", f"Select user(s) to assign to task #{task_id}:", emoji="👥"),
            view=view,
        )
        self.stop()

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=3)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_step == 2:
            self.current_step = 1
            self.selected_board_id = None
            self.selected_task_id = None
            self.selected_task = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message("Assign Task", "Select a board to assign a task:", emoji="👥"),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=3)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message("Cancelled", "Task assignment cancelled.", emoji="❌"),
            view=None,
        )
        self.stop()


class DeleteTaskFlowView(discord.ui.View):
    """View for the /delete-task flow: board selector → task selector → confirmation."""

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
        self.selected_task_id: Optional[int] = None
        self.selected_task: Optional[dict] = None
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create task_select manually
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[discord.SelectOption(label="(Select board first)", value="__placeholder__", default=False)]
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

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
        self.current_step = 2

        # Load task options (show all tasks)
        task_options = await get_task_choices(self.db, board_id, 0, True)
        if not task_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Tasks Found", "This board has no tasks.", emoji="⚠️"),
            )
            self.stop()
            return

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task to delete..."
        if hasattr(self, 'back_button'):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Delete Task",
                f"Board: **{board['name']}**\n\nSelect a task to delete.",
                emoji="🗑️",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message("Task Not Found", "That task no longer exists.", emoji="⚠️"),
            )
            self.stop()
            return

        if task.get("board_id") != self.selected_board_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Task", "Task doesn't belong to selected board.", emoji="⚠️"),
            )
            self.stop()
            return

        self.selected_task_id = task_id
        self.selected_task = task

        # Show confirmation view
        task_embed = self.embeds.task_detail(task, task.get("column_name", "Unknown"))
        confirm_view = DeleteTaskConfirmationView(
            task_id=task_id,
            task=task,
            db=self.db,
            embeds=self.embeds,
        )
        await interaction.response.send_message(
            embed=task_embed,
            view=confirm_view,
        )
        self.stop()

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_step == 2:
            self.current_step = 1
            self.selected_board_id = None
            self.selected_task_id = None
            self.selected_task = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message("Delete Task", "Select a board to delete a task:", emoji="🗑️"),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message("Cancelled", "Task deletion cancelled.", emoji="❌"),
            view=None,
        )
        self.stop()


class RecoverTaskFlowView(discord.ui.View):
    """View for the /recover-task flow: board selector → deleted task selector → recovery."""

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
        self.current_step: int = 1  # 1=board, 2=task

        # Set initial board options
        self.board_select.options = initial_board_options

        # Create task_select manually
        task_select = discord.ui.Select(
            placeholder="Select a board first...",
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
            options=[discord.SelectOption(label="(Select board first)", value="__placeholder__", default=False)]
        )
        task_select.callback = self.task_select_callback
        self.add_item(task_select)
        self.task_select = task_select

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
        self.current_step = 2

        # Load deleted task options
        deleted_tasks = await self.db.fetch_deleted_tasks(self.guild_id, board_id)
        if not deleted_tasks:
            await interaction.response.send_message(
                embed=self.embeds.message("No Deleted Tasks", "This board has no deleted tasks to recover.", emoji="ℹ️"),
            )
            self.stop()
            return

        # Create task options from deleted tasks
        task_options = []
        for task in deleted_tasks[:25]:  # Limit to 25
            title = task.get("title", "Untitled")[:50]
            deleted_at = task.get("deleted_at", "")
            task_options.append(
                discord.SelectOption(
                    label=f"#{task['id']}: {title}",
                    value=str(task["id"]),
                    description=f"Deleted {deleted_at[:10] if deleted_at else 'recently'}"[:100],
                )
            )

        # Show only task select, hide board select
        self.board_select.disabled = True
        self.task_select.options = task_options
        self.task_select.disabled = False
        self.task_select.placeholder = "2. Select a task to recover..."
        if hasattr(self, 'back_button'):
            self.back_button.disabled = False

        await interaction.response.edit_message(
            embed=self.embeds.message(
                "Recover Task",
                f"Board: **{board['name']}**\n\nSelect a deleted task to recover.",
                emoji="♻️",
            ),
            view=self,
        )

    async def task_select_callback(self, interaction: discord.Interaction) -> None:
        if not interaction.data or "values" not in interaction.data:
            return

        values = interaction.data.get("values", [])
        if not values or values[0] == "__placeholder__":
            return

        task_id = int(values[0])
        await interaction.response.defer(thinking=True)

        # Recover the task
        recovered = await self.db.recover_task(task_id)
        if not recovered:
            await interaction.followup.send(
                embed=self.embeds.message("Recovery Failed", f"Task #{task_id} could not be recovered. It may not be deleted.", emoji="⚠️"),
            )
            self.stop()
            return

        # Fetch the recovered task to show details
        task = await self.db.fetch_task(task_id)
        if task:
            task_embed = self.embeds.task_detail(task, task.get("column_name", "Unknown"))
            await interaction.followup.send(
                embed=task_embed,
            )
            await interaction.followup.send(
                embed=self.embeds.message("Task Recovered", f"Task #{task_id} has been recovered successfully.", emoji="♻️"),
            )
        else:
            await interaction.followup.send(
                embed=self.embeds.message("Task Recovered", f"Task #{task_id} has been recovered successfully.", emoji="♻️"),
            )
        self.stop()

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True, row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_step == 2:
            self.current_step = 1
            self.selected_board_id = None
            self.board_select.disabled = False
            self.task_select.disabled = True
            self.task_select.placeholder = "Select a board first..."
            self.back_button.disabled = True

            await interaction.response.edit_message(
                embed=self.embeds.message("Recover Task", "Select a board to recover a deleted task:", emoji="♻️"),
                view=self,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.embeds.message("Cancelled", "Task recovery cancelled.", emoji="❌"),
            view=None,
        )
        self.stop()


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

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel"
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Cancelled", "Board deletion cancelled.", emoji="✅"
            ),
        )
        self.stop()

    @discord.ui.button(
        label="🗑️ Delete Board", style=discord.ButtonStyle.danger, custom_id="delete"
    )
    async def delete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
                embed=self.embeds.message(
                    "Board Deleted",
                    f"**{self.board_name}** has been archived.",
                    emoji="🗑️",
                ),
            )
        else:
            await interaction.followup.send(
                embed=self.embeds.message(
                    "Not Found", "Unable to locate that board.", emoji="⚠️"
                ),
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

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel"
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Cancelled", "Column removal cancelled.", emoji="✅"
            ),
        )
        self.stop()

    @discord.ui.button(
        label="🗑️ Remove Column", style=discord.ButtonStyle.danger, custom_id="remove"
    )
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
                embed=self.embeds.message(
                    "Not Found", "That column does not exist.", emoji="⚠️"
                ),
            )
            return

        await interaction.followup.send(
            embed=self.embeds.message(
                "Column Removed",
                f"Deleted **{self.column_name}** from the board.",
                emoji="🗑️",
            ),
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

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel"
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Cancelled", "Task deletion cancelled.", emoji="✅"
            ),
        )
        self.stop()

    @discord.ui.button(
        label="🗑️ Delete Task", style=discord.ButtonStyle.danger, custom_id="delete"
    )
    async def delete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
            embed=self.embeds.message(
                "Task Deleted", f"Removed task #{self.task_id}.", emoji="🗑️"
            ),
        )


class PastDueDateConfirmationView(discord.ui.View):
    """View with confirmation buttons for editing a task to a past due date."""

    def __init__(
        self,
        *,
        task_id: int,
        updates: dict,
        assignee_ids_to_set: Optional[List[int]],
        db: "Database",
        embeds: "EmbedFactory",
        past_date_str: str,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.updates = updates
        self.assignee_ids_to_set = assignee_ids_to_set
        self.db = db
        self.embeds = embeds
        self.past_date_str = past_date_str

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel"
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Cancelled", "Task update cancelled.", emoji="✅"
            ),
        )
        self.stop()

    @discord.ui.button(
        label="Yes, Continue", style=discord.ButtonStyle.danger, custom_id="confirm"
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=True)

        # Apply assignee changes (if any)
        if self.assignee_ids_to_set is not None:
            await self.db.set_task_assignees(self.task_id, self.assignee_ids_to_set)

        # Apply other field updates
        if self.updates:
            await self.db.update_task(self.task_id, **self.updates)

        await interaction.followup.send(
            embed=self.embeds.message(
                "Task Updated",
                f"Edits applied to task #{self.task_id}.\n⚠️ **Note:** Due date is in the past.",
                emoji="✨",
            ),
        )
        self.stop()


class NotificationActionView(discord.ui.View):
    """View with interactive buttons for notification actions.

    This view is persistent (no timeout) so buttons work indefinitely.
    Custom IDs encode task_id for proper state reconstruction.
    """

    def __init__(
        self,
        *,
        task_id: int,
        notification_type: str,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.notification_type = notification_type

        # Update button custom_ids to include task info for persistence
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if hasattr(item, "custom_id") and item.custom_id:
                    # Encode task_id and type into custom_id
                    item.custom_id = (
                        f"{item.custom_id.split(':')[0]}:{task_id}:{notification_type}"
                    )

    @discord.ui.button(
        label="Snooze 1h",
        style=discord.ButtonStyle.secondary,
        emoji="⏰",
        custom_id="snooze_1h",
    )
    async def snooze_1h_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Snooze notification for 1 hour."""
        from datetime import datetime, timedelta, timezone as dt_timezone
        from utils.db import ISO_FORMAT

        # Parse task_id from custom_id
        task_id, notification_type = self._parse_custom_id(button.custom_id)

        # Calculate snooze_until time
        snooze_until = (datetime.now(dt_timezone.utc) + timedelta(hours=1)).strftime(
            ISO_FORMAT
        )

        # Get database from bot
        db = interaction.client.db

        # Create snooze record
        await db.snooze_reminder(
            user_id=interaction.user.id,
            task_id=task_id,
            notification_type=notification_type,
            snooze_until=snooze_until,
        )

        await interaction.response.send_message(
            content="✅ Reminder snoozed for 1 hour",
            ephemeral=True,
        )
        self.stop()

    @discord.ui.button(
        label="Snooze 1d",
        style=discord.ButtonStyle.secondary,
        emoji="💤",
        custom_id="snooze_1d",
    )
    async def snooze_1d_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Snooze notification for 1 day."""
        from datetime import datetime, timedelta, timezone as dt_timezone
        from utils.db import ISO_FORMAT

        # Parse task_id from custom_id
        task_id, notification_type = self._parse_custom_id(button.custom_id)

        # Calculate snooze_until time
        snooze_until = (datetime.now(dt_timezone.utc) + timedelta(days=1)).strftime(
            ISO_FORMAT
        )

        # Get database from bot
        db = interaction.client.db

        # Create snooze record
        await db.snooze_reminder(
            user_id=interaction.user.id,
            task_id=task_id,
            notification_type=notification_type,
            snooze_until=snooze_until,
        )

        await interaction.response.send_message(
            content="✅ Reminder snoozed for 1 day",
            ephemeral=True,
        )
        self.stop()

    @discord.ui.button(
        label="Mark as Read",
        style=discord.ButtonStyle.primary,
        emoji="✅",
        custom_id="mark_read",
    )
    async def mark_read_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Mark notification as read/acknowledged."""
        await interaction.response.send_message(
            content="✅ Notification marked as read",
            ephemeral=True,
        )
        self.stop()

    def _parse_custom_id(self, custom_id: str) -> tuple[int, str]:
        """Parse task_id and notification_type from custom_id.

        Format: action:task_id:notification_type
        """
        parts = custom_id.split(":")
        if len(parts) >= 3:
            return int(parts[1]), parts[2]
        # Fallback to instance variables
        return self.task_id, self.notification_type
