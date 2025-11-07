from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

import discord

if TYPE_CHECKING:
    from utils import Database, EmbedFactory


class BoardViewUpdater:
    """Service that debounces and updates always-visible board views."""

    def __init__(self, bot: discord.Client, db: "Database", embeds: "EmbedFactory") -> None:
        self.bot = bot
        self.db = db
        self.embeds = embeds
        self.logger = logging.getLogger("distask.board_views")
        self._pending_refreshes: Dict[int, asyncio.Task] = {}
        self._debounce_delay = 5.0  # 5 seconds debounce

    def schedule_refresh(self, board_id: int) -> None:
        """Schedule a debounced refresh for a board view."""
        # Cancel existing pending refresh for this board
        if board_id in self._pending_refreshes:
            task = self._pending_refreshes[board_id]
            if not task.done():
                task.cancel()
        
        # Schedule new refresh
        task = asyncio.create_task(self._debounced_refresh(board_id))
        self._pending_refreshes[board_id] = task

    async def _debounced_refresh(self, board_id: int) -> None:
        """Debounced refresh that waits before actually refreshing."""
        try:
            await asyncio.sleep(self._debounce_delay)
            await self.refresh(board_id)
        except asyncio.CancelledError:
            # Task was cancelled (new change came in), ignore
            pass
        except Exception as exc:
            self.logger.error("Error refreshing board view %s: %s", board_id, exc, exc_info=True)
        finally:
            # Clean up pending task
            if board_id in self._pending_refreshes:
                del self._pending_refreshes[board_id]

    async def refresh(self, board_id: int) -> None:
        """Refresh a board view by updating its message."""
        view_config = await self.db.get_board_view(board_id)
        if not view_config:
            return
        
        # Get board to find guild_id
        boards = await self.db._execute(
            "SELECT * FROM boards WHERE id = $1",
            (board_id,),
            fetchone=True,
        )
        if not boards:
            self.logger.warning("Board %s not found for view refresh", board_id)
            return
        
        board = dict(boards)
        channel_id = view_config["channel_id"]
        message_id = view_config.get("message_id")
        
        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            self.logger.warning("Channel %s not found for board view refresh", channel_id)
            return
        
        # Fetch board data
        columns = await self.db.fetch_columns(board_id)
        tasks = await self.db.fetch_tasks(board_id)
        
        # Group tasks by column
        tasks_by_column: Dict[int, List[Dict]] = {}
        for task in tasks:
            col_id = task["column_id"]
            if col_id not in tasks_by_column:
                tasks_by_column[col_id] = []
            tasks_by_column[col_id].append(task)
        
        # Create embed
        embed = self.embeds.board_snapshot(board, columns, tasks_by_column)
        
        # Update or recreate message
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
                return
            except discord.NotFound:
                # Message was deleted, recreate it
                self.logger.info("Board view message %s was deleted, recreating", message_id)
            except discord.HTTPException as exc:
                self.logger.warning("Failed to edit board view message %s: %s", message_id, exc)
                return
        
        # Create new message
        try:
            message = await channel.send(embed=embed)
            pinned = view_config.get("pinned", False)
            if pinned:
                try:
                    await message.pin()
                except discord.HTTPException:
                    self.logger.warning("Failed to pin board view message")
            
            # Update database with new message_id
            await self.db.update_board_view_message(board_id, message.id)
        except discord.HTTPException as exc:
            self.logger.error("Failed to create board view message: %s", exc, exc_info=True)

