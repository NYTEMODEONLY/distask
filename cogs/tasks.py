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

    @app_commands.command(name="add-task", description="Create a new task on a board")
    @app_commands.autocomplete(board=board_autocomplete, column=column_autocomplete)
    @app_commands.describe(
        board="Board to use",
        title="Short task title",
        description="Optional description",
        column="Column name (defaults to first column)",
        assignee="Member responsible",
        due_date="Due date (e.g. 2024-07-04 17:00 UTC)",
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def add_task(
        self,
        interaction: discord.Interaction,
        board: str,
        title: str,
        description: Optional[str] = None,
        column: Optional[str] = None,
        assignee: Optional[discord.Member] = None,
        due_date: Optional[str] = None,
    ) -> None:
        board_data = await self._resolve_board(interaction, board)
        validation = Validator.task_title(title)
        if not validation.ok:
            await interaction.response.send_message(
                embed=self.embeds.message("Invalid Title", validation.message, emoji="⚠️"),
            )
            return
        await interaction.response.defer(thinking=True)
        columns = await self.db.fetch_columns(board_data["id"])
        target_column = await self._resolve_column(board_data["id"], columns, column)
        due_iso = None
        if due_date:
            try:
                due_iso = Validator.parse_due_date(due_date)
            except ValueError as exc:
                await interaction.followup.send(
                    embed=self.embeds.message("Invalid Due Date", str(exc), emoji="⚠️"),
                )
                return
        task_id = await self.db.create_task(
            board_id=board_data["id"],
            column_id=target_column["id"],
            title=title.strip(),
            description=description,
            assignee_id=assignee.id if assignee else None,
            due_date=due_iso,
            created_by=interaction.user.id,
        )
        task = await self.db.fetch_task(task_id)
        embed = self.embeds.task_detail(task, target_column["name"])
        embed.add_field(name="Board", value=board_data["name"], inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="list-tasks", description="List tasks on a board")
    @app_commands.autocomplete(board=board_autocomplete, column=column_autocomplete)
    @app_commands.describe(
        board="Board to inspect",
        column="Optional column filter",
        assignee="Filter by assignee",
        include_completed="Include completed tasks",
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def list_tasks(
        self,
        interaction: discord.Interaction,
        board: str,
        column: Optional[str] = None,
        assignee: Optional[discord.Member] = None,
        include_completed: bool = False,
    ) -> None:
        board_data = await self._resolve_board(interaction, board)
        column_data = None
        if column:
            column_data = await self.db.get_column_by_name(board_data["id"], column)
            if not column_data:
                await interaction.response.send_message(
                    embed=self.embeds.message("Column Missing", "That column does not exist on this board.", emoji="⚠️"),
                )
                return
        column_id = column_data["id"] if column_data else None
        tasks = await self.db.fetch_tasks(
            board_id=board_data["id"],
            column_id=column_id,
            assignee_id=assignee.id if assignee else None,
            include_completed=include_completed,
        )
        if not tasks:
            await interaction.response.send_message(
                embed=self.embeds.message("No Tasks", "Nothing matches those filters just yet.", emoji="📭"),
            )
            return
        lines = [self._format_task_line(task) for task in tasks[:20]]
        content = "\n".join(lines)
        if len(tasks) > 20:
            content += f"\n…and {len(tasks) - 20} more"
        embed = self.embeds.message(
            f"Tasks · {board_data['name']}",
            content,
            emoji="🗂️",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="move-task", description="Move a task to another column")
    @app_commands.autocomplete(column=column_autocomplete)
    @app_commands.checks.cooldown(1, 3.0)
    async def move_task(self, interaction: discord.Interaction, task_id: int, column: str) -> None:
        task = await self._require_task(interaction, task_id)
        columns = await self.db.fetch_columns(task["board_id"])
        target_column = await self._resolve_column(task["board_id"], columns, column)
        await self.db.move_task(task_id, target_column["id"])
        await interaction.response.send_message(
            embed=self.embeds.message("Task Moved", f"#{task_id} → **{target_column['name']}**", emoji="🧭"),
        )

    @app_commands.command(name="assign-task", description="Assign a task to a member")
    @app_commands.checks.cooldown(1, 3.0)
    async def assign_task(self, interaction: discord.Interaction, task_id: int, member: discord.Member) -> None:
        await self._require_task(interaction, task_id)
        await self.db.update_task(task_id, assignee_id=member.id)
        await interaction.response.send_message(
            embed=self.embeds.message("Task Assigned", f"#{task_id} now belongs to {member.mention}", emoji="👥"),
        )

    @app_commands.command(name="edit-task", description="Update details for a task")
    @app_commands.autocomplete(column=column_autocomplete)
    @app_commands.describe(
        title="New title",
        description="New description",
        column="Move to column",
        assignee="Reassign member",
        due_date="New due date",
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def edit_task(
        self,
        interaction: discord.Interaction,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        column: Optional[str] = None,
        assignee: Optional[discord.Member] = None,
        due_date: Optional[str] = None,
    ) -> None:
        task = await self._require_task(interaction, task_id)
        updates = {}
        if title:
            validation = Validator.task_title(title)
            if not validation.ok:
                await interaction.response.send_message(
                    embed=self.embeds.message("Invalid Title", validation.message, emoji="⚠️"),
                )
                return
            updates["title"] = title.strip()
        if description is not None:
            updates["description"] = description
        if assignee is not None:
            updates["assignee_id"] = assignee.id
        if due_date is not None:
            if due_date:
                try:
                    updates["due_date"] = Validator.parse_due_date(due_date)
                except ValueError as exc:
                    await interaction.response.send_message(
                        embed=self.embeds.message("Invalid Due Date", str(exc), emoji="⚠️"),
                    )
                    return
            else:
                updates["due_date"] = None
        if column:
            columns = await self.db.fetch_columns(task["board_id"])
            target_column = await self._resolve_column(task["board_id"], columns, column)
            updates["column_id"] = target_column["id"]
        if not updates:
            await interaction.response.send_message(
                embed=self.embeds.message("No Changes", "Provide at least one field to update.", emoji="⚠️"),
            )
            return
        await self.db.update_task(task_id, **updates)
        await interaction.response.send_message(
            embed=self.embeds.message("Task Updated", f"Edits applied to task #{task_id}.", emoji="✨"),
        )

    @app_commands.command(name="complete-task", description="Mark a task complete/incomplete")
    @app_commands.checks.cooldown(1, 3.0)
    async def complete_task(self, interaction: discord.Interaction, task_id: int, completed: bool = True) -> None:
        await self._require_task(interaction, task_id)
        await self.db.toggle_complete(task_id, completed)
        status = "completed" if completed else "reopened"
        emoji = "✅" if completed else "↩️"
        await interaction.response.send_message(
            embed=self.embeds.message("Task Status", f"Task #{task_id} {status}.", emoji=emoji),
        )

    @app_commands.command(name="delete-task", description="Remove a task")
    @app_commands.checks.cooldown(1, 3.0)
    async def delete_task(self, interaction: discord.Interaction, task_id: int) -> None:
        await self._require_task(interaction, task_id)
        await self.db.delete_task(task_id)
        await interaction.response.send_message(
            embed=self.embeds.message("Task Deleted", f"Removed task #{task_id}.", emoji="🗑️"),
        )

    @app_commands.command(name="search-task", description="Full-text search across tasks")
    @app_commands.describe(query="Keywords to search")
    @app_commands.checks.cooldown(1, 10.0)
    async def search_task(self, interaction: discord.Interaction, query: str) -> None:
        validation = Validator.search_query(query)
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
        results = await self.db.search_tasks(interaction.guild_id, query)
        embed = self.embeds.search_results(query, results)
        await interaction.followup.send(embed=embed)

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
        assignee = f"<@{task['assignee_id']}>" if task.get("assignee_id") else "—"
        status = "✅" if task.get("completed") else "❌"
        due = task.get("due_date") or "—"
        return f"#{task['id']} [{status}] {task['title']} · Due: {due} · Assignee: {assignee}"
