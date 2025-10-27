from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import asyncpg

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def _parse_command_tag(tag: str) -> int:
    try:
        return int(tag.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0


class Database:
    """Async wrapper around PostgreSQL with helper methods for DisTask."""

    def __init__(self, dsn: str, *, default_reminder: str = "09:00") -> None:
        self.dsn = dsn
        self.default_reminder = default_reminder
        self._pool: Optional[asyncpg.Pool] = None

    async def init(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            schema_statements = [
                """
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id BIGINT PRIMARY KEY,
                    notify_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    reminder_time TEXT NOT NULL DEFAULT '09:00'
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS boards (
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
                    channel_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_by BIGINT,
                    created_at TEXT NOT NULL,
                    UNIQUE (guild_id, name)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS columns (
                    id BIGSERIAL PRIMARY KEY,
                    board_id BIGINT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    UNIQUE (board_id, name)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id BIGSERIAL PRIMARY KEY,
                    board_id BIGINT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                    column_id BIGINT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    description TEXT,
                    assignee_id BIGINT,
                    due_date TEXT,
                    created_by BIGINT,
                    created_at TEXT NOT NULL,
                    completed BOOLEAN NOT NULL DEFAULT FALSE
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board_id)",
                "CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)",
                """
                CREATE TABLE IF NOT EXISTS feature_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    suggestion TEXT NOT NULL,
                    suggested_priority TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER,
                    ease_of_implementation INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_feature_requests_guild ON feature_requests(guild_id)",
            ]
            for statement in schema_statements:
                await conn.execute(statement)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def ensure_guild(self, guild_id: int, *, reminder_time: Optional[str] = None) -> None:
        await self._execute(
            "INSERT INTO guilds (guild_id, reminder_time) VALUES ($1, $2) ON CONFLICT(guild_id) DO NOTHING",
            (guild_id, reminder_time or self.default_reminder),
        )

    async def set_notifications(self, guild_id: int, enabled: bool) -> None:
        await self.ensure_guild(guild_id)
        await self._execute(
            "UPDATE guilds SET notify_enabled = $1 WHERE guild_id = $2",
            (enabled, guild_id),
        )

    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        await self.ensure_guild(guild_id)
        row = await self._execute(
            "SELECT * FROM guilds WHERE guild_id = $1",
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
            "UPDATE guilds SET reminder_time = $1 WHERE guild_id = $2",
            (reminder_time, guild_id),
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
        board_row = await self._execute(
            """
            INSERT INTO boards (guild_id, channel_id, name, description, created_by, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            (guild_id, channel_id, name, description, created_by, _utcnow()),
            fetchone=True,
        )
        if not board_row:
            raise RuntimeError("Failed to create board")
        board_id = board_row["id"]
        await self._add_default_columns(board_id)
        return board_id

    async def delete_board(self, guild_id: int, board_id: int) -> bool:
        result = await self._execute(
            "DELETE FROM boards WHERE guild_id = $1 AND id = $2",
            (guild_id, board_id),
            rowcount=True,
        )
        return bool(result)

    async def fetch_boards(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM boards WHERE guild_id = $1 ORDER BY created_at DESC",
            (guild_id,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def get_board(self, guild_id: int, board_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM boards WHERE guild_id = $1 AND id = $2",
            (guild_id, board_id),
            fetchone=True,
        )
        return dict(row) if row else None

    async def get_board_by_name(self, guild_id: int, name: str) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM boards WHERE guild_id = $1 AND name = $2",
            (guild_id, name),
            fetchone=True,
        )
        return dict(row) if row else None

    async def fetch_columns(self, board_id: int) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM columns WHERE board_id = $1 ORDER BY position",
            (board_id,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def add_column(self, board_id: int, name: str) -> int:
        columns = await self.fetch_columns(board_id)
        position = (columns[-1]["position"] + 1) if columns else 0
        column_row = await self._execute(
            """
            INSERT INTO columns (board_id, name, position)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            (board_id, name, position),
            fetchone=True,
        )
        if not column_row:
            raise RuntimeError("Failed to add column")
        return column_row["id"]

    async def remove_column(self, board_id: int, name: str) -> bool:
        column = await self._execute(
            "SELECT id FROM columns WHERE board_id = $1 AND name = $2",
            (board_id, name),
            fetchone=True,
        )
        if not column:
            return False
        tasks = await self._execute(
            "SELECT COUNT(1) as c FROM tasks WHERE column_id = $1",
            (column["id"],),
            fetchone=True,
        )
        if tasks and tasks["c"]:
            raise ValueError("Column still has tasks. Move them before deleting.")
        await self._execute(
            "DELETE FROM columns WHERE id = $1",
            (column["id"],),
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
        task_row = await self._execute(
            """
            INSERT INTO tasks (board_id, column_id, title, description, assignee_id, due_date, created_by, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            (board_id, column_id, title, description, assignee_id, due_date, created_by, _utcnow()),
            fetchone=True,
        )
        if not task_row:
            raise RuntimeError("Failed to create task")
        return task_row["id"]

    async def fetch_tasks(
        self,
        board_id: int,
        *,
        column_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        include_completed: bool = True,
    ) -> List[Dict[str, Any]]:
        query = ["SELECT * FROM tasks WHERE board_id = $1"]
        params: List[Any] = [board_id]
        if column_id is not None:
            params.append(column_id)
            query.append(f"AND column_id = ${len(params)}")
        if assignee_id is not None:
            params.append(assignee_id)
            query.append(f"AND assignee_id = ${len(params)}")
        if not include_completed:
            query.append("AND completed = FALSE")
        query.append("ORDER BY created_at DESC")
        rows = await self._execute(" ".join(query), tuple(params), fetchall=True)
        return [dict(row) for row in rows or []]

    async def fetch_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM tasks WHERE id = $1",
            (task_id,),
            fetchone=True,
        )
        return dict(row) if row else None

    async def update_task(self, task_id: int, **fields: Any) -> bool:
        if not fields:
            return False
        assignments = []
        params: List[Any] = []
        for idx, (key, value) in enumerate(fields.items(), start=1):
            assignments.append(f"{key} = ${idx}")
            params.append(value)
        params.append(task_id)
        result = await self._execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ${len(params)}",
            tuple(params),
            rowcount=True,
        )
        return bool(result)

    async def delete_task(self, task_id: int) -> bool:
        result = await self._execute(
            "DELETE FROM tasks WHERE id = $1",
            (task_id,),
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
            WHERE boards.guild_id = $1
              AND (
                  tasks.title ILIKE $2 OR
                  COALESCE(tasks.description, '') ILIKE $3
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
            """
            SELECT
                COUNT(1) AS total,
                SUM(CASE WHEN completed THEN 1 ELSE 0 END) AS completed
            FROM tasks
            WHERE board_id = $1
            """,
            (board_id,),
            fetchone=True,
        )
        overdue = await self._execute(
            """
            SELECT COUNT(1) AS overdue
            FROM tasks
            WHERE board_id = $1 AND completed = FALSE AND due_date IS NOT NULL AND due_date < $2
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
            WHERE tasks.completed = FALSE AND tasks.due_date IS NOT NULL AND tasks.due_date <= $1
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
                """
                INSERT INTO columns (board_id, name, position)
                VALUES ($1, $2, $3)
                ON CONFLICT (board_id, name) DO NOTHING
                """,
                (board_id, name, position),
            )

    async def get_column_by_name(self, board_id: int, name: str) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM columns WHERE board_id = $1 AND LOWER(name) = LOWER($2)",
            (board_id, name),
            fetchone=True,
        )
        return dict(row) if row else None

    async def get_column_by_id(self, column_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM columns WHERE id = $1",
            (column_id,),
            fetchone=True,
        )
        return dict(row) if row else None

    async def move_task(self, task_id: int, column_id: int) -> bool:
        return await self.update_task(task_id, column_id=column_id)

    async def toggle_complete(self, task_id: int, completed: bool) -> bool:
        return await self.update_task(task_id, completed=completed)

    async def create_feature_request(
        self,
        *,
        user_id: int,
        guild_id: int,
        title: str,
        suggestion: str,
        suggested_priority: Optional[str],
    ) -> int:
        await self.ensure_guild(guild_id)
        row = await self._execute(
            """
            INSERT INTO feature_requests (user_id, guild_id, title, suggestion, suggested_priority)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            (user_id, guild_id, title, suggestion, suggested_priority),
            fetchone=True,
        )
        if not row:
            raise RuntimeError("Failed to store feature request")
        return row["id"]

    async def fetch_feature_requests(self) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM feature_requests ORDER BY created_at DESC",
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def _execute(
        self,
        query: str,
        params: Iterable[Any] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        rowcount: bool = False,
    ) -> Any:
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        params_seq: Sequence[Any] = tuple(params)
        async with self._pool.acquire() as conn:
            if fetchone:
                return await conn.fetchrow(query, *params_seq)
            if fetchall:
                return await conn.fetch(query, *params_seq)
            status = await conn.execute(query, *params_seq)
            if rowcount:
                return _parse_command_tag(status)
            return status
