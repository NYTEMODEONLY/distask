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
        self._last_run: Dict[int, str] = {}  # guild_id -> date
        self._channel_last_run: Dict[int, str] = {}  # channel_id -> date
        self._guild_locks: Dict[int, asyncio.Lock] = {}
        self._tick_lock = asyncio.Lock()  # Prevent concurrent ticks

    async def start(self) -> None:
        # Stop any existing task before starting a new one
        if self._task and not self._task.done():
            self.logger.warning("Reminder scheduler already running, stopping existing task")
            await self.stop()
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="distask-reminder-loop")
        self.logger.info("Reminder scheduler started")

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
        # Prevent concurrent ticks entirely
        async with self._tick_lock:
            now = datetime.now(timezone.utc)
            guilds = await self.db.list_guilds()
            horizon = (now + timedelta(days=1)).strftime(ISO_FORMAT)
            due_tasks = await self.db.fetch_due_tasks(horizon)
            for guild in guilds:
                if not guild.get("notify_enabled"):
                    continue
                guild_id = guild["guild_id"]
                should_run = self._should_run_today(now, guild["reminder_time"], guild_id)
                if not should_run:
                    continue
                # Get or create lock for this guild to prevent concurrent execution
                if guild_id not in self._guild_locks:
                    self._guild_locks[guild_id] = asyncio.Lock()
                async with self._guild_locks[guild_id]:
                    # Double-check after acquiring lock (another tick might have already run)
                    if not self._should_run_today(now, guild["reminder_time"], guild_id):
                        continue
                    try:
                        # Dispatch and track success - only mark guild as run if all channels succeed
                        success = await self._dispatch_guild(guild_id, due_tasks, now)
                        if success:
                            # Mark as run AFTER successful dispatch to allow retries on failure
                            self._last_run[guild_id] = now.date().isoformat()
                        else:
                            # Clear guild tracking if dispatch failed so it can retry
                            self._last_run.pop(guild_id, None)
                    except discord.HTTPException as exc:
                        # Clear guild tracking on exception so it can retry
                        self._last_run.pop(guild_id, None)
                        self.logger.warning("Failed sending reminders for guild %s: %s", guild_id, exc)

    def _should_run_today(self, now: datetime, reminder_time: str, guild_id: int) -> bool:
        hour, minute = map(int, reminder_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return False
        last_run = self._last_run.get(guild_id)
        return last_run != now.date().isoformat()

    async def _dispatch_guild(self, guild_id: int, tasks: List[Dict[str, Any]], now: datetime) -> bool:
        """
        Dispatch reminders to all channels in a guild.
        Returns True if all channels were successfully sent, False otherwise.
        """
        # Group tasks by channel_id to respect privacy boundaries
        # Each board's tasks should only be sent to that board's channel
        # This ensures private channel boards don't leak tasks to other channels
        grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for task in tasks:
            if task["guild_id"] != guild_id:
                continue
            grouped[task["channel_id"]].append(task)
        
        if not grouped:
            return True  # No channels to send to, consider it successful
        
        # Get the guild object to get the guild name
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            self.logger.warning("Cannot access guild %s for reminders", guild_id)
            return False
        
        today = now.date().isoformat()
        all_succeeded = True
        
        # Send one digest per channel (respecting privacy boundaries)
        # Each channel receives only tasks from boards in that channel
        # This prevents private board tasks from leaking to public channels
        for channel_id, channel_tasks in grouped.items():
            # Check if we've already sent to this channel today
            if self._channel_last_run.get(channel_id) == today:
                self.logger.debug("Skipping channel %s - already sent digest today", channel_id)
                continue
            
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    self.logger.warning("Cannot access channel %s for reminders", channel_id)
                    all_succeeded = False
                    continue
            
            if not isinstance(channel, discord.abc.Messageable):
                continue
            
            # Send a single digest for this channel's tasks only
            # This ensures privacy: each channel only sees tasks from its own boards
            try:
                # Mark channel as sent BEFORE sending to prevent race conditions
                self._channel_last_run[channel_id] = today
                embed = self.embed_factory.reminder_digest(guild.name, channel_tasks)
                await channel.send(embed=embed)
                self.logger.info("Sent daily digest to channel %s (%s tasks)", channel_id, len(channel_tasks))
            except discord.HTTPException as exc:
                # If send failed, don't mark as sent so it can retry
                self._channel_last_run.pop(channel_id, None)
                all_succeeded = False
                self.logger.warning("Failed to send reminder to channel %s: %s", channel_id, exc)
        
        return all_succeeded
