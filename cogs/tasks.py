from __future__ import annotations

from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import Database, EmbedFactory
from utils.validators import Validator


class TasksCog(commands.Cog):
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
        board_id: Optional[int] = None
        if board_value:
            try:
                board_id = int(board_value)
            except (TypeError, ValueError):
                board_id = None
        if board_id is None:
            task_id = getattr(interaction.namespace, "task_id", None)
            if task_id:
                task = await self.db.fetch_task(task_id)
                if task:
                    board_id = task["board_id"]
        if board_id is None:
            return []
        columns = await self.db.fetch_columns(board_id)
        needle = current.lower()
        results: List[app_commands.Choice[str]] = []
        for column in columns:
            if needle and needle not in column["name"].lower():
                continue
            results.append(app_commands.Choice(name=column["name"], value=column["name"]))
        return results[:25]

    @app_commands.command(name="add-task", description="[Server] Create a new task on a board")
    @app_commands.checks.cooldown(1, 10.0)
    async def add_task(self, interaction: discord.Interaction) -> None:
        from .ui import AddTaskFlowView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
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

        view = AddTaskFlowView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            initial_board_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("Add Task", "Select a board and column to add a task:", emoji="➕"),
            view=view,
        )

    @app_commands.command(name="list-tasks", description="[Server] List tasks on a board")
    @app_commands.checks.cooldown(1, 3.0)
    async def list_tasks(self, interaction: discord.Interaction) -> None:
        from .ui import BoardSelectorView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
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
            # Fetch all non-completed tasks by default
            tasks = await self.db.fetch_tasks(
                board_id=board_id,
                column_id=None,
                assignee_id=None,
                include_completed=False,
            )
            if not tasks:
                await inter.followup.send(
                    embed=self.embeds.message("No Tasks", "This board has no active tasks.", emoji="📭"),
                )
                return

            lines = [self._format_task_line(task) for task in tasks[:20]]
            content = "\n".join(lines)
            if len(tasks) > 20:
                content += f"\n…and {len(tasks) - 20} more"
            embed = self.embeds.message(
                f"Tasks · {board['name']}",
                content,
                emoji="🗂️",
            )
            await inter.followup.send(embed=embed)

        view = BoardSelectorView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            on_select=on_board_selected,
            placeholder="Select a board to list tasks...",
            initial_options=board_options,
        )
        await interaction.response.send_message(
            embed=self.embeds.message("List Tasks", "Select a board to view its tasks:", emoji="🗂️"),
            view=view,
        )

    @app_commands.command(name="move-task", description="[Server] Move a task to another column")
    @app_commands.checks.cooldown(1, 3.0)
    async def move_task(self, interaction: discord.Interaction) -> None:
        from .ui import MoveTaskModal, ColumnSelectorView
        from .ui.helpers import get_column_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return

        async def on_task_validated(inter: discord.Interaction, task_id: int, task: dict) -> None:
            # Get column options for the task's board
            column_options = await get_column_choices(self.db, task["board_id"])
            if not column_options:
                await inter.response.send_message(
                    embed=self.embeds.message(
                        "No Columns",
                        "This board has no columns.",
                        emoji="⚠️",
                    ),
                )
                return

            # Show column selector for the task's board
            async def on_column_selected(col_inter: discord.Interaction, column_id: int, column: dict) -> None:
                await col_inter.response.defer(thinking=True)

                # Get original column name for notification
                old_column = await self.db.get_column_by_id(task["column_id"])
                old_column_name = old_column["name"] if old_column else "Unknown"

                # Move task
                await self.db.move_task(task_id, column_id)

                # Send event notification
                if hasattr(self.bot, "event_notifier") and col_inter.guild_id:
                    # Get updated task data
                    updated_task = await self.db.fetch_task(task_id)
                    board = await self.db.get_board(col_inter.guild_id, task["board_id"])
                    if updated_task and board:
                        await self.bot.event_notifier.notify_task_moved(
                            task=updated_task,
                            from_column=old_column_name,
                            to_column=column["name"],
                            mover_id=col_inter.user.id,
                            guild_id=col_inter.guild_id,
                            channel_id=board["channel_id"],
                        )

                await col_inter.followup.send(
                    embed=self.embeds.message("Task Moved", f"#{task_id} → **{column['name']}**", emoji="🧭"),
                )

            column_view = ColumnSelectorView(
                board_id=task["board_id"],
                db=self.db,
                embeds=self.embeds,
                on_select=on_column_selected,
                placeholder="Select target column...",
                initial_options=column_options,
            )
            await inter.response.send_message(
                embed=self.embeds.message("Move Task", f"Select a column to move task #{task_id} to:", emoji="🧭"),
                view=column_view,
            )

        modal = MoveTaskModal(
            on_task_validated=on_task_validated,
            db=self.db,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="assign-task", description="[Server] Assign a task to a member")
    @app_commands.checks.cooldown(1, 3.0)
    async def assign_task(self, interaction: discord.Interaction) -> None:
        from .ui import AssignTaskModal

        modal = AssignTaskModal(db=self.db, embeds=self.embeds)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="edit-task", description="[Server] Update details for a task")
    @app_commands.checks.cooldown(1, 10.0)
    async def edit_task(self, interaction: discord.Interaction) -> None:
        from .ui import EditTaskFlowView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return
        
        # Check if user is admin (has Manage Guild permission)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.user else False
        
        # Get board options
        board_options = await get_board_choices(self.db, interaction.guild_id)
        if not board_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Boards", "There are no boards in this server.", emoji="⚠️"),
            )
            return
        
        view = EditTaskFlowView(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            is_admin=is_admin,
            db=self.db,
            embeds=self.embeds,
            initial_board_options=board_options,
        )
        
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Edit Task",
                "Select a board, then choose a task to edit.\n\nYou can only edit tasks you created, unless you're a server admin.",
                emoji="✏️",
            ),
            view=view,
        )

    @app_commands.command(name="complete-task", description="[Server] Mark a task complete/incomplete")
    @app_commands.checks.cooldown(1, 3.0)
    async def complete_task(self, interaction: discord.Interaction) -> None:
        from .ui import CompleteTaskFlowView
        from .ui.helpers import get_board_choices

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return
        
        # Get board options
        board_options = await get_board_choices(self.db, interaction.guild_id)
        if not board_options:
            await interaction.response.send_message(
                embed=self.embeds.message("No Boards", "There are no boards in this server.", emoji="⚠️"),
            )
            return
        
        view = CompleteTaskFlowView(
            guild_id=interaction.guild_id,
            db=self.db,
            embeds=self.embeds,
            initial_board_options=board_options,
        )
        
        await interaction.response.send_message(
            embed=self.embeds.message(
                "Complete Task",
                "Select a board, then choose a task to mark complete or incomplete.",
                emoji="✅",
            ),
            view=view,
        )

    @app_commands.command(name="delete-task", description="[Server] Remove a task")
    @app_commands.checks.cooldown(1, 3.0)
    async def delete_task(self, interaction: discord.Interaction) -> None:
        from .ui import TaskIDInputModal, DeleteTaskConfirmationView

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "This command must be used in a guild.", emoji="⚠️"),
            )
            return

        async def on_task_validated(inter: discord.Interaction, task_id: int) -> None:
            # Verify task belongs to this guild
            task = await self.db.fetch_task(task_id)
            if not task:
                await inter.response.send_message(
                    embed=self.embeds.message("Task Not Found", f"Task #{task_id} does not exist.", emoji="⚠️"),
                )
                return

            board = await self.db.get_board(inter.guild_id, task["board_id"])
            if not board:
                await inter.response.send_message(
                    embed=self.embeds.message("Task Not Found", "Task not part of this guild.", emoji="⚠️"),
                )
                return

            # Show confirmation view with task details
            task_embed = self.embeds.task_detail(task, task.get("column_name", "Unknown"))
            confirm_view = DeleteTaskConfirmationView(
                task_id=task_id,
                task=task,
                db=self.db,
                embeds=self.embeds,
            )
            await inter.response.send_message(
                embed=task_embed,
                view=confirm_view,
            )

        modal = TaskIDInputModal(
            title="Delete Task",
            on_submit_callback=on_task_validated,
            embeds=self.embeds,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="search-task", description="[Server] Full-text search across tasks")
    @app_commands.checks.cooldown(1, 10.0)
    async def search_task(self, interaction: discord.Interaction) -> None:
        from .ui import SearchTaskModal

        if not interaction.guild_id:
            await interaction.response.send_message(
                embed=self.embeds.message("Guild Only", "Search must be run inside a server.", emoji="⚠️"),
            )
            return

        modal = SearchTaskModal(db=self.db, embeds=self.embeds)
        await interaction.response.send_modal(modal)

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

    async def _resolve_column(self, board_id: int, columns, name: Optional[str]):
        if name:
            column = next((col for col in columns if col["name"].lower() == name.lower()), None)
            if not column:
                raise app_commands.AppCommandError("Column not found.")
            return column
        if not columns:
            raise app_commands.AppCommandError("Board has no columns configured.")
        return columns[0]

    async def _require_task(self, interaction: discord.Interaction, task_id: int):
        if not interaction.guild_id:
            raise app_commands.AppCommandError("Guild-only command.")
        task = await self.db.fetch_task(task_id)
        if not task:
            raise app_commands.AppCommandError("Task not found.")
        board = await self.db.get_board(interaction.guild_id, task["board_id"])
        if not board:
            raise app_commands.AppCommandError("Task not part of this guild.")
        return task

    def _format_task_line(self, task) -> str:
        from utils.embeds import _format_assignees
        assignee = _format_assignees(task).replace("👤 ", "").replace("👥 ", "")
        status = "✅" if task.get("completed") else "❌"
        due = task.get("due_date") or "—"
        return f"#{task['id']} [{status}] {task['title']} · Due: {due} · Assignee: {assignee}"
