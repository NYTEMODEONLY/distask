from __future__ import annotations

import re
from typing import Optional

import discord


def parse_user_mention_or_id(value: str) -> Optional[int]:
    """
    Parse a user mention or ID from text input.
    Accepts: @username, <@123456>, 123456
    Returns user ID as int or None if invalid.
    """
    value = value.strip()
    if not value:
        return None

    # Try direct ID
    if value.isdigit():
        return int(value)

    # Try mention format <@123456> or <@!123456>
    match = re.match(r"<@!?(\d+)>", value)
    if match:
        return int(match.group(1))

    return None


def parse_channel_mention_or_id(value: str) -> Optional[int]:
    """
    Parse a channel mention or ID from text input.
    Accepts: #channel-name, <#123456>, 123456
    Returns channel ID as int or None if invalid.
    """
    value = value.strip()
    if not value:
        return None

    # Try direct ID
    if value.isdigit():
        return int(value)

    # Try mention format <#123456>
    match = re.match(r"<#(\d+)>", value)
    if match:
        return int(match.group(1))

    return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


async def get_board_choices(db, guild_id: int, max_choices: int = 25) -> list[discord.SelectOption]:
    """
    Fetch boards for a guild and return as SelectOption list.
    """
    boards = await db.fetch_boards(guild_id)
    options = []
    for board in boards[:max_choices]:
        label = truncate_text(board["name"], 100)
        description = truncate_text(board.get("description") or "No description", 100)
        options.append(
            discord.SelectOption(
                label=label,
                value=str(board["id"]),
                description=description,
            )
        )
    return options


async def get_column_choices(db, board_id: int) -> list[discord.SelectOption]:
    """
    Fetch columns for a board and return as SelectOption list.
    """
    columns = await db.fetch_columns(board_id)
    options = []
    for column in columns:
        options.append(
            discord.SelectOption(
                label=column["name"],
                value=column["name"],
            )
        )
    return options


async def get_task_choices(db, board_id: int, user_id: int, is_admin: bool, max_choices: int = 25) -> list[discord.SelectOption]:
    """
    Fetch tasks for a board and return as SelectOption list.
    If not admin, only returns tasks created by the user.
    If user_id is 0 and is_admin is True, shows all tasks (for completion flow).
    """
    tasks = await db.fetch_tasks(board_id)
    options = []
    count = 0
    
    for task in tasks:
        # Filter: only show tasks created by user, unless admin
        # Special case: if user_id is 0 and is_admin is True, show all (for complete-task)
        if user_id == 0 and is_admin:
            # Show all tasks
            pass
        elif not is_admin and task.get("created_by") != user_id:
            continue
        
        # Format task display
        title = truncate_text(task.get("title", "Untitled"), 80)
        task_id = task.get("id", 0)
        completed_marker = "✅ " if task.get("completed") else ""
        
        options.append(
            discord.SelectOption(
                label=f"{completed_marker}#{task_id}: {title}",
                value=str(task_id),
                description=truncate_text(task.get("description") or "", 100),
            )
        )
        count += 1
        if count >= max_choices:
            break
    
    return options
