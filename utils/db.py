from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import aiosqlite

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


class Database:
    """Async wrapper around SQLite with helper methods for DisTask."""

    def __init__(self, path: str, *, default_reminder: str = "09:00") -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self.default_reminder = default_reminder

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as db:
            await db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id INTEGER PRIMARY KEY,
                    notify_enabled INTEGER NOT NULL DEFAULT 1,
                    reminder_time TEXT NOT NULL DEFAULT '09:00'
                );
                CREATE TABLE IF NOT EXISTS boards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
                    UNIQUE (guild_id, name)
                );
                CREATE TABLE IF NOT EXISTS columns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE,
                    UNIQUE (board_id, name)
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_id INTEGER NOT NULL,
                    column_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    assignee_id INTEGER,
                    due_date TEXT,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE,
                    FOREIGN KEY (column_id) REFERENCES columns(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
                """
            )

    async def ensure_guild(self, guild_id: int, *, reminder_time: Optional[str] = None) -> None:
        await self._execute(
            "INSERT INTO guilds (guild_id, reminder_time) VALUES (?, ?) ON CONFLICT(guild_id) DO NOTHING",
            (guild_id, reminder_time or self.default_reminder),
            commit=True,
        )

    async def set_notifications(self, guild_id: int, enabled: bool) -> None:
        await self.ensure_guild(guild_id)
        await self._execute(
            "UPDATE guilds SET notify_enabled = ? WHERE guild_id = ?",
            (int(enabled), guild_id),
            commit=True,
        )

    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        await self.ensure_guild(guild_id)
        row = await self._execute(
            "SELECT * FROM guilds WHERE guild_id = ?",
            (guild_id,),
            fetchone=True,
        )
        return dict(row) if row else {}

    async def list_guilds(self) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM guilds",
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def set_reminder_time(self, guild_id: int, reminder_time: str) -> None:
        await self.ensure_guild(guild_id)
        await self._execute(
            "UPDATE guilds SET reminder_time = ? WHERE guild_id = ?",
            (reminder_time, guild_id),
            commit=True,
        )

    async def create_board(
        self,
        guild_id: int,
        channel_id: int,
        name: str,
        description: Optional[str],
        created_by: int,
    ) -> int:
        await self.ensure_guild(guild_id)
        board_id = await self._execute(
            """
            INSERT INTO boards (guild_id, channel_id, name, description, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, name, description, created_by, _utcnow()),
            commit=True,
            lastrowid=True,
        )
        await self._add_default_columns(board_id)
        return board_id

    async def delete_board(self, guild_id: int, board_id: int) -> bool:
        result = await self._execute(
            "DELETE FROM boards WHERE guild_id = ? AND id = ?",
            (guild_id, board_id),
            commit=True,
            rowcount=True,
        )
        return bool(result)

    async def fetch_boards(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM boards WHERE guild_id = ? ORDER BY created_at DESC",
            (guild_id,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def get_board(self, guild_id: int, board_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM boards WHERE guild_id = ? AND id = ?",
            (guild_id, board_id),
            fetchone=True,
        )
        return dict(row) if row else None

    async def get_board_by_name(self, guild_id: int, name: str) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM boards WHERE guild_id = ? AND name = ?",
            (guild_id, name),
            fetchone=True,
        )
        return dict(row) if row else None

    async def fetch_columns(self, board_id: int) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM columns WHERE board_id = ? ORDER BY position",
            (board_id,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def add_column(self, board_id: int, name: str) -> int:
        columns = await self.fetch_columns(board_id)
        position = (columns[-1]["position"] + 1) if columns else 0
        return await self._execute(
            "INSERT INTO columns (board_id, name, position) VALUES (?, ?, ?)",
            (board_id, name, position),
            commit=True,
            lastrowid=True,
        )

    async def remove_column(self, board_id: int, name: str) -> bool:
        column = await self._execute(
            "SELECT id FROM columns WHERE board_id = ? AND name = ?",
            (board_id, name),
            fetchone=True,
        )
        if not column:
            return False
        tasks = await self._execute(
            "SELECT COUNT(1) as c FROM tasks WHERE column_id = ?",
            (column["id"],),
            fetchone=True,
        )
        if tasks and tasks["c"]:
            raise ValueError("Column still has tasks. Move them before deleting.")
        await self._execute(
            "DELETE FROM columns WHERE id = ?",
            (column["id"],),
            commit=True,
        )
        return True

    async def create_task(
        self,
        board_id: int,
        column_id: int,
        title: str,
        description: Optional[str],
        assignee_id: Optional[int],
        due_date: Optional[str],
        created_by: int,
    ) -> int:
        return await self._execute(
            """
            INSERT INTO tasks (board_id, column_id, title, description, assignee_id, due_date, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (board_id, column_id, title, description, assignee_id, due_date, created_by, _utcnow()),
            commit=True,
            lastrowid=True,
        )

    async def fetch_tasks(
        self,
        board_id: int,
        *,
        column_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        include_completed: bool = True,
    ) -> List[Dict[str, Any]]:
        query = ["SELECT * FROM tasks WHERE board_id = ?"]
        params: List[Any] = [board_id]
        if column_id:
            query.append("AND column_id = ?")
            params.append(column_id)
        if assignee_id:
            query.append("AND assignee_id = ?")
            params.append(assignee_id)
        if not include_completed:
            query.append("AND completed = 0")
        query.append("ORDER BY created_at DESC")
        rows = await self._execute(" ".join(query), tuple(params), fetchall=True)
        return [dict(row) for row in rows or []]

    async def fetch_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
            fetchone=True,
        )
        return dict(row) if row else None

    async def update_task(self, task_id: int, **fields: Any) -> bool:
        if not fields:
            return False
        columns = ", ".join(f"{key} = ?" for key in fields)
        params = list(fields.values()) + [task_id]
        result = await self._execute(
            f"UPDATE tasks SET {columns} WHERE id = ?",
            tuple(params),
            commit=True,
            rowcount=True,
        )
        return bool(result)

    async def delete_task(self, task_id: int) -> bool:
        result = await self._execute(
            "DELETE FROM tasks WHERE id = ?",
            (task_id,),
            commit=True,
            rowcount=True,
        )
        return bool(result)

    async def search_tasks(self, guild_id: int, query: str) -> List[Dict[str, Any]]:
        like = f"%{query}%"
        rows = await self._execute(
            """
            SELECT tasks.*, boards.name AS board_name, boards.channel_id
            FROM tasks
            JOIN boards ON tasks.board_id = boards.id
            WHERE boards.guild_id = ?
              AND (
                  tasks.title LIKE ? OR
                  IFNULL(tasks.description, '') LIKE ?
              )
            ORDER BY tasks.created_at DESC
            LIMIT 25
            """,
            (guild_id, like, like),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def board_stats(self, board_id: int) -> Dict[str, Any]:
        totals = await self._execute(
            "SELECT COUNT(1) AS total, SUM(completed = 1) AS completed FROM tasks WHERE board_id = ?",
            (board_id,),
            fetchone=True,
        )
        overdue = await self._execute(
            """
            SELECT COUNT(1) AS overdue
            FROM tasks
            WHERE board_id = ? AND completed = 0 AND due_date IS NOT NULL AND due_date < ?
            """,
            (board_id, _utcnow()),
            fetchone=True,
        )
        return {
            "total": totals["total"] if totals else 0,
            "completed": totals["completed"] if totals else 0,
            "overdue": overdue["overdue"] if overdue else 0,
        }

    async def fetch_due_tasks(self, before_iso: str) -> List[Dict[str, Any]]:
        rows = await self._execute(
            """
            SELECT tasks.*, boards.name AS board_name, boards.channel_id, boards.guild_id
            FROM tasks
            JOIN boards ON tasks.board_id = boards.id
            WHERE tasks.completed = 0 AND tasks.due_date IS NOT NULL AND tasks.due_date <= ?
            ORDER BY tasks.due_date ASC
            """,
            (before_iso,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def _add_default_columns(self, board_id: int) -> None:
        defaults = ["To Do", "In Progress", "Done"]
        for position, name in enumerate(defaults):
            await self._execute(
                "INSERT OR IGNORE INTO columns (board_id, name, position) VALUES (?, ?, ?)",
                (board_id, name, position),
                commit=True,
            )

    async def get_column_by_name(self, board_id: int, name: str) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM columns WHERE board_id = ? AND LOWER(name) = LOWER(?)",
            (board_id, name),
            fetchone=True,
        )
        return dict(row) if row else None

    async def get_column_by_id(self, column_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM columns WHERE id = ?",
            (column_id,),
            fetchone=True,
        )
        return dict(row) if row else None

    async def move_task(self, task_id: int, column_id: int) -> bool:
        return await self.update_task(task_id, column_id=column_id)

    async def toggle_complete(self, task_id: int, completed: bool) -> bool:
        return await self.update_task(task_id, completed=int(completed))

    async def _execute(
        self,
        query: str,
        params: Iterable[Any] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        commit: bool = False,
        lastrowid: bool = False,
        rowcount: bool = False,
    ) -> Any:
        async with self._lock:
            async with self._connect() as db:
                cursor = await db.execute(query, tuple(params))
                result = None
                if fetchone:
                    result = await cursor.fetchone()
                elif fetchall:
                    result = await cursor.fetchall()
                if commit:
                    await db.commit()
                if lastrowid:
                    return cursor.lastrowid
                if rowcount:
                    return cursor.rowcount
                return result

    @asynccontextmanager
    async def _connect(self):
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            await conn.close()
