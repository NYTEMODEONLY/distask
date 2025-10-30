from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

import discord

if TYPE_CHECKING:
    from utils import Database, EmbedFactory


class ConfirmationModal(discord.ui.Modal):
    """Generic confirmation modal that requires user to type a specific value."""

    def __init__(
        self,
        *,
        title: str,
        label: str,
        expected_value: str,
        placeholder: str,
        on_confirm: Callable,
        embeds: "EmbedFactory",
    ) -> None:
        super().__init__(title=title, timeout=300)
        self.expected_value = expected_value.lower()
        self.on_confirm = on_confirm
        self.embeds = embeds
        self.confirmation_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            style=discord.TextStyle.short,
            max_length=100,
        )
        self.add_item(self.confirmation_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.confirmation_input.value.strip().lower() != self.expected_value:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Confirmation Failed",
                    "The value you entered doesn't match. Action cancelled.",
                    emoji="⚠️",
                ),
            )
            return
        await self.on_confirm(interaction)


class TaskIDInputModal(discord.ui.Modal):
    """Modal to input a task ID."""

    def __init__(
        self,
        *,
        title: str,
        on_submit_callback: Callable,
        embeds: "EmbedFactory",
    ) -> None:
        super().__init__(title=title, timeout=300)
        self.on_submit_callback = on_submit_callback
        self.embeds = embeds
        self.task_id_input = discord.ui.TextInput(
            label="Task ID",
            placeholder="Enter the task ID number",
            required=True,
            style=discord.TextStyle.short,
            max_length=20,
        )
        self.add_item(self.task_id_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            task_id = int(self.task_id_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Task ID",
                    "Please enter a valid numeric task ID.",
                    emoji="⚠️",
                ),
            )
            return
        await self.on_submit_callback(interaction, task_id)


class CreateBoardModal(discord.ui.Modal):
    """Modal for creating a new board."""

    def __init__(
        self,
        cog,
        db: "Database",
        embeds: "EmbedFactory",
        *,
        channel_id: Optional[int] = None,
        channel_name: Optional[str] = None,
    ) -> None:
        super().__init__(title="Create New Board", timeout=300)
        self.cog = cog
        self.db = db
        self.embeds = embeds
        self.channel_id = channel_id
        self.channel_name = channel_name

        self.board_name = discord.ui.TextInput(
            label="Board Name",
            placeholder="e.g., Sprint 2024-Q1",
            max_length=100,
            required=True,
            style=discord.TextStyle.short,
        )
        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Optional description of this board",
            max_length=500,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.board_name)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator

        validation = Validator.board_name(self.board_name.value)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Board Name", validation.message, emoji="⚠️"),
            )
            return

        cleaned_name = self.board_name.value.strip()
        desc = self.description.value.strip() if self.description.value else None

        # Use pre-selected channel if available
        if not self.channel_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Channel Required",
                    "Please select a channel first.",
                    emoji="⚠️",
                ),
            )
            return
        
        # Verify channel exists and is accessible
        try:
            channel = await interaction.guild.fetch_channel(self.channel_id)
            
            # Check channel type - more flexible check
            if channel.type != discord.ChannelType.text:
                await interaction.response.send_message(
                    embed=self.embeds.message(
                        "Invalid Channel",
                        "The selected channel is not a text channel.",
                        emoji="⚠️",
                    ),
                )
                return
            
            # Ensure it's messageable
            if not isinstance(channel, discord.abc.Messageable):
                await interaction.response.send_message(
                    embed=self.embeds.message(
                        "Invalid Channel",
                        "Selected channel cannot receive messages.",
                        emoji="⚠️",
                    ),
                )
                return
                
        except discord.NotFound:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Channel Not Found",
                    "I couldn't find that channel. It may have been deleted.",
                    emoji="⚠️",
                ),
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Access Denied",
                    "I don't have permission to access that channel.",
                    emoji="⚠️",
                ),
            )
            return
        except Exception as e:
            logger = logging.getLogger("distask.create_board")
            logger.exception("Error fetching channel %s: %s", self.channel_id, e)
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Channel Error",
                    "An error occurred while accessing the channel. Please try again.",
                    emoji="🔥",
                ),
            )
            return

        await interaction.response.defer(thinking=True)

        # Check for duplicate
        existing = await self.db.get_board_by_name(interaction.guild_id, cleaned_name)
        if existing:
            await interaction.followup.send(
                embed=self.embeds.message("Duplicate Board", "Choose a unique board name for this server.", emoji="🛑"),
            )
            return

        # Create board
        board_id = await self.db.create_board(
            interaction.guild_id,
            channel.id,
            cleaned_name,
            desc,
            interaction.user.id,
        )
        board = await self.db.get_board(interaction.guild_id, board_id)
        columns = await self.db.fetch_columns(board_id)
        stats = await self.db.board_stats_detailed(board_id)

        # Get creator and channel mentions
        creator_mention = f"<@{interaction.user.id}>"
        channel_mention = channel.mention

        embed = self.embeds.board_detail(
            board,
            columns,
            stats,
            channel_mention=channel_mention,
            creator_mention=creator_mention,
        )
        await interaction.followup.send(embed=embed)


class AddTaskModal(discord.ui.Modal):
    """Modal for adding a task."""

    def __init__(
        self,
        *,
        board_id: int,
        board_name: str,
        column_id: int,
        column_name: str,
        db: "Database",
        embeds: "EmbedFactory",
        assignee_id: Optional[int] = None,
        due_date_preset: Optional[str] = None,
    ) -> None:
        super().__init__(title=f"Add Task to {board_name}", timeout=300)
        self.board_id = board_id
        self.board_name = board_name
        self.column_id = column_id
        self.column_name = column_name
        self.db = db
        self.embeds = embeds
        self.assignee_id = assignee_id  # Store pre-selected assignee

        self.title_input = discord.ui.TextInput(
            label="Task Title",
            placeholder="Short description of the task",
            max_length=200,
            required=True,
            style=discord.TextStyle.short,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Optional detailed description",
            max_length=2000,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        # If assignee_id provided from user selector, pre-fill it
        assignee_placeholder = f"Selected: {assignee_id}" if assignee_id else "@user or user ID (optional)"
        self.assignee_input = discord.ui.TextInput(
            label="Assignee (optional)",
            placeholder=assignee_placeholder,
            default=str(assignee_id) if assignee_id else "",
            required=False,
            style=discord.TextStyle.short,
            max_length=100,
        )
        self.due_date_input = discord.ui.TextInput(
            label="Due Date (optional)",
            placeholder="Today, Tomorrow, 3 Days, 6 Days, 7 Days, or YYYY-MM-DD HH:MM UTC",
            default=due_date_preset or "",
            required=False,
            style=discord.TextStyle.short,
            max_length=50,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.assignee_input)
        self.add_item(self.due_date_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator
        from .helpers import parse_user_mention_or_id

        validation = Validator.task_title(self.title_input.value)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Title", validation.message, emoji="⚠️"),
            )
            return

        title = self.title_input.value.strip()
        description = self.description_input.value.strip() if self.description_input.value else None

        # Parse assignee - use pre-selected assignee_id if available, otherwise parse from input
        assignee_id = None
        if self.assignee_id:  # Use pre-selected assignee from user selector
            assignee_id = self.assignee_id
        elif self.assignee_input.value and self.assignee_input.value.strip():
            # User typed in assignee field, parse it
            assignee_id = parse_user_mention_or_id(self.assignee_input.value)
            if not assignee_id:
                await interaction.response.send_message(
                    embed=self.embeds.message(
                        "Invalid Assignee",
                        "Please provide a valid user mention (@user) or user ID.",
                        emoji="⚠️",
                    ),
                )
                return

        # Parse due date
        due_iso = None
        if self.due_date_input.value:
            try:
                due_iso = Validator.parse_due_date(self.due_date_input.value)
            except ValueError as exc:
                await interaction.response.send_message(
                    embed=self.embeds.message("Invalid Due Date", str(exc), emoji="⚠️"),
                )
                return

        await interaction.response.defer(thinking=True)

        task_id = await self.db.create_task(
            board_id=self.board_id,
            column_id=self.column_id,
            title=title,
            description=description,
            assignee_id=assignee_id,
            due_date=due_iso,
            created_by=interaction.user.id,
        )

        task = await self.db.fetch_task(task_id)
        embed = self.embeds.task_detail(task, self.column_name)
        embed.add_field(name="Board", value=self.board_name, inline=False)
        await interaction.followup.send(embed=embed)


class EditTaskModal(discord.ui.Modal):
    """Modal for editing a task."""

    def __init__(
        self,
        *,
        task_id: int,
        task: dict,
        db: "Database",
        embeds: "EmbedFactory",
    ) -> None:
        super().__init__(title=f"Edit Task #{task_id}", timeout=300)
        self.task_id = task_id
        self.task = task
        self.db = db
        self.embeds = embeds

        self.title_input = discord.ui.TextInput(
            label="Task Title",
            placeholder="Leave empty to keep current",
            default=task.get("title", ""),
            max_length=200,
            required=False,
            style=discord.TextStyle.short,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Leave empty to keep current",
            default=task.get("description") or "",
            max_length=2000,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.assignee_input = discord.ui.TextInput(
            label="Assignee (optional)",
            placeholder="@user, user ID, or empty to unassign",
            required=False,
            style=discord.TextStyle.short,
            max_length=100,
        )
        self.due_date_input = discord.ui.TextInput(
            label="Due Date (optional)",
            placeholder="Today, Tomorrow, 3 Days, 6 Days, 7 Days, or YYYY-MM-DD HH:MM UTC (empty to clear)",
            default=task.get("due_date") or "",
            required=False,
            style=discord.TextStyle.short,
            max_length=50,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.assignee_input)
        self.add_item(self.due_date_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator
        from .helpers import parse_user_mention_or_id

        updates = {}

        # Handle title
        if self.title_input.value and self.title_input.value.strip():
            validation = Validator.task_title(self.title_input.value)
            if not validation.ok:
                await interaction.response.send_message(
                    embed=self.embeds.message("Invalid Title", validation.message, emoji="⚠️"),
                )
                return
            updates["title"] = self.title_input.value.strip()

        # Handle description
        if self.description_input.value is not None:
            desc = self.description_input.value.strip()
            updates["description"] = desc if desc else None

        # Handle assignee
        if self.assignee_input.value:
            assignee_text = self.assignee_input.value.strip()
            if assignee_text:
                assignee_id = parse_user_mention_or_id(assignee_text)
                if not assignee_id:
                    await interaction.response.send_message(
                        embed=self.embeds.message(
                            "Invalid Assignee",
                            "Please provide a valid user mention (@user) or user ID.",
                            emoji="⚠️",
                        ),
                    )
                    return
                updates["assignee_id"] = assignee_id
            else:
                updates["assignee_id"] = None

        # Handle due date
        if self.due_date_input.value is not None:
            due_text = self.due_date_input.value.strip()
            if due_text:
                try:
                    updates["due_date"] = Validator.parse_due_date(due_text)
                except ValueError as exc:
                    await interaction.response.send_message(
                        embed=self.embeds.message("Invalid Due Date", str(exc), emoji="⚠️"),
                    )
                    return
            else:
                updates["due_date"] = None

        if not updates:
            await interaction.response.send_message(
                embed=self.embeds.message("No Changes", "Provide at least one field to update.", emoji="⚠️"),
            )
            return

        await interaction.response.defer(thinking=True)
        await self.db.update_task(self.task_id, **updates)
        await interaction.followup.send(
            embed=self.embeds.message("Task Updated", f"Edits applied to task #{self.task_id}.", emoji="✨"),
        )


class SearchTaskModal(discord.ui.Modal):
    """Modal for searching tasks."""

    def __init__(self, *, db: "Database", embeds: "EmbedFactory") -> None:
        super().__init__(title="Search Tasks", timeout=300)
        self.db = db
        self.embeds = embeds

        self.query_input = discord.ui.TextInput(
            label="Search Query",
            placeholder="Enter keywords to search",
            min_length=2,
            max_length=200,
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator

        validation = Validator.search_query(self.query_input.value)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Search", validation.message, emoji="⚠️"),
            )
            return

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Search must be run inside a server.", emoji="⚠️"),
            )
            return

        await interaction.response.defer(thinking=True)
        results = await self.db.search_tasks(interaction.guild_id, self.query_input.value)
        embed = self.embeds.search_results(self.query_input.value, results)
        await interaction.followup.send(embed=embed)


class AddColumnModal(discord.ui.Modal):
    """Modal for adding a column to a board."""

    def __init__(
        self,
        *,
        board_id: int,
        board_name: str,
        db: "Database",
        embeds: "EmbedFactory",
    ) -> None:
        super().__init__(title=f"Add Column to {board_name}", timeout=300)
        self.board_id = board_id
        self.board_name = board_name
        self.db = db
        self.embeds = embeds

        self.column_name = discord.ui.TextInput(
            label="Column Name",
            placeholder="e.g., In Review",
            max_length=100,
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.column_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator

        validation = Validator.column_name(self.column_name.value)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Column", validation.message, emoji="⚠️"),
            )
            return

        await interaction.response.defer(thinking=True)
        await self.db.add_column(self.board_id, self.column_name.value.strip())
        await interaction.followup.send(
            embed=self.embeds.message("Column Added", f"**{self.column_name.value.strip()}** is now live.", emoji="➕"),
        )


class ReminderTimeModal(discord.ui.Modal):
    """Modal for setting reminder time."""

    def __init__(self, *, db: "Database", embeds: "EmbedFactory") -> None:
        super().__init__(title="Set Reminder Time", timeout=300)
        self.db = db
        self.embeds = embeds

        self.time_input = discord.ui.TextInput(
            label="Reminder Time (UTC)",
            placeholder="HH:MM (24-hour format, e.g., 09:00)",
            max_length=5,
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.validators import Validator

        validation = Validator.reminder_time(self.time_input.value)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Time", validation.message, emoji="⚠️"),
            )
            return

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Run this inside a server.", emoji="⚠️"),
            )
            return

        await interaction.response.defer(thinking=True)
        await self.db.set_reminder_time(interaction.guild_id, self.time_input.value)
        await interaction.followup.send(
            embed=self.embeds.message("Reminder Updated", f"Daily digest scheduled for {self.time_input.value} UTC.", emoji="⏰"),
        )


class AssignTaskModal(discord.ui.Modal):
    """Modal for assigning a task."""

    def __init__(self, *, db: "Database", embeds: "EmbedFactory") -> None:
        super().__init__(title="Assign Task", timeout=300)
        self.db = db
        self.embeds = embeds

        self.task_id_input = discord.ui.TextInput(
            label="Task ID",
            placeholder="Enter the task ID number",
            required=True,
            style=discord.TextStyle.short,
            max_length=20,
        )
        self.assignee_input = discord.ui.TextInput(
            label="Assignee",
            placeholder="@user or user ID",
            required=True,
            style=discord.TextStyle.short,
            max_length=100,
        )
        self.add_item(self.task_id_input)
        self.add_item(self.assignee_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from .helpers import parse_user_mention_or_id

        # Parse task ID
        try:
            task_id = int(self.task_id_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Task ID",
                    "Please enter a valid numeric task ID.",
                    emoji="⚠️",
                ),
            )
            return

        # Parse assignee
        assignee_id = parse_user_mention_or_id(self.assignee_input.value)
        if not assignee_id:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Assignee",
                    "Please provide a valid user mention (@user) or user ID.",
                    emoji="⚠️",
                ),
            )
            return

        # Verify task exists and belongs to this guild
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return

        await interaction.response.defer(thinking=True)

        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.followup.send(
                embed=self.embeds.message("Task Not Found", f"Task #{task_id} does not exist.", emoji="⚠️"),
            )
            return

        board = await self.db.get_board(interaction.guild_id, task["board_id"])
        if not board:
            await interaction.followup.send(
                embed=self.embeds.message("Task Not Found", "Task not part of this guild.", emoji="⚠️"),
            )
            return

        # Assign the task
        await self.db.update_task(task_id, assignee_id=assignee_id)
        await interaction.followup.send(
            embed=self.embeds.message("Task Assigned", f"#{task_id} now belongs to <@{assignee_id}>", emoji="👥"),
        )


class MoveTaskModal(discord.ui.Modal):
    """Modal for entering task ID before moving."""

    def __init__(
        self,
        *,
        on_task_validated: Callable,
        db: "Database",
        embeds: "EmbedFactory",
    ) -> None:
        super().__init__(title="Move Task", timeout=300)
        self.on_task_validated = on_task_validated
        self.db = db
        self.embeds = embeds

        self.task_id_input = discord.ui.TextInput(
            label="Task ID",
            placeholder="Enter the task ID number",
            required=True,
            style=discord.TextStyle.short,
            max_length=20,
        )
        self.add_item(self.task_id_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Parse task ID
        try:
            task_id = int(self.task_id_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                embed=self.embeds.message(
                    "Invalid Task ID",
                    "Please enter a valid numeric task ID.",
                    emoji="⚠️",
                ),
            )
            return

        # Verify task exists and belongs to this guild
        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return

        task = await self.db.fetch_task(task_id)
        if not task:
            await interaction.response.send_message(
                embed=self.embeds.message("Task Not Found", f"Task #{task_id} does not exist.", emoji="⚠️"),
            )
            return

        board = await self.db.get_board(interaction.guild_id, task["board_id"])
        if not board:
            await interaction.response.send_message(
                embed=self.embeds.message("Task Not Found", "Task not part of this guild.", emoji="⚠️"),
            )
            return

        # Task validated, pass to callback
        await self.on_task_validated(interaction, task_id, task)
