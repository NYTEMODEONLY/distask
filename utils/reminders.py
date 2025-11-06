from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import discord

from .embeds import EmbedFactory
from .db import Database, ISO_FORMAT


class ReminderScheduler:
    """Runs a lightweight daily reminder loop."""

    def __init__(
        self,
        bot: discord.Client,
        db: Database,
        embed_factory: EmbedFactory,
        logger,
        interval: int = 60,
    ) -> None:
        self.bot = bot
        self.db = db
        self.embed_factory = embed_factory
        self.logger = logger
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_run: Dict[int, str] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="distask-reminder-loop")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.exception("Reminder tick failed: %s", exc)
            sleep_task = asyncio.create_task(asyncio.sleep(self.interval))
            stop_task = asyncio.create_task(self._stop.wait())
            done, pending = await asyncio.wait({sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if stop_task in done:
                break

    async def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        guilds = await self.db.list_guilds()
        horizon = (now + timedelta(days=1)).strftime(ISO_FORMAT)
        due_tasks = await self.db.fetch_due_tasks(horizon)
        for guild in guilds:
            if not guild.get("notify_enabled"):
                continue
            should_run = self._should_run_today(now, guild["reminder_time"], guild["guild_id"])
            if not should_run:
                continue
            try:
                await self._dispatch_guild(guild["guild_id"], due_tasks)
                self._last_run[guild["guild_id"]] = now.date().isoformat()
            except discord.HTTPException as exc:
                self.logger.warning("Failed sending reminders for guild %s: %s", guild["guild_id"], exc)

    def _should_run_today(self, now: datetime, reminder_time: str, guild_id: int) -> bool:
        hour, minute = map(int, reminder_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return False
        last_run = self._last_run.get(guild_id)
        return last_run != now.date().isoformat()

    async def _dispatch_guild(self, guild_id: int, tasks: List[Dict[str, Any]]) -> None:
        # Group tasks by channel_id to respect privacy boundaries
        # Each board's tasks should only be sent to that board's channel
        # This prevents private board tasks from leaking to public channels
        grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for task in tasks:
            if task["guild_id"] != guild_id:
                continue
            grouped[task["channel_id"]].append(task)
        
        if not grouped:
            return
        
        # Get the guild object to get the guild name
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            self.logger.warning("Cannot access guild %s for reminders", guild_id)
            return
        
        # Send one digest per channel (respecting privacy boundaries)
        # This ensures private board tasks don't leak to public channels
        for channel_id, channel_tasks in grouped.items():
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    self.logger.warning("Cannot access channel %s for reminders", channel_id)
                    continue
            
            if not isinstance(channel, discord.abc.Messageable):
                continue
            
            # Send a single digest for this channel's tasks
            try:
                embed = self.embed_factory.reminder_digest(guild.name, channel_tasks)
                await channel.send(embed=embed)
            except discord.HTTPException as exc:
                self.logger.warning("Failed to send reminder to channel %s: %s", channel_id, exc)
