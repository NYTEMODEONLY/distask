from __future__ import annotations

import json
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
            self._pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=10, timeout=10.0)
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
                    completed BOOLEAN NOT NULL DEFAULT FALSE,
                    completion_notes TEXT
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS task_assignees (
                    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, user_id)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_task_assignees_task ON task_assignees(task_id)",
                "CREATE INDEX IF NOT EXISTS idx_task_assignees_user ON task_assignees(user_id)",
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
                    completed_at TIMESTAMP,
                    duplicate_of INTEGER REFERENCES feature_requests(id),
                    merge_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                    analysis_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    last_analyzed_at TIMESTAMP,
                    score NUMERIC,
                    community_message_id BIGINT,
                    community_channel_id BIGINT,
                    community_upvotes INTEGER NOT NULL DEFAULT 0,
                    community_downvotes INTEGER NOT NULL DEFAULT 0,
                    community_duplicate_votes INTEGER NOT NULL DEFAULT 0
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_feature_requests_guild ON feature_requests(guild_id)",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS duplicate_of INTEGER REFERENCES feature_requests(id)",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS merge_history JSONB NOT NULL DEFAULT '[]'::jsonb",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS analysis_data JSONB NOT NULL DEFAULT '{}'::jsonb",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS score NUMERIC",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS community_message_id BIGINT",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS community_channel_id BIGINT",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS community_upvotes INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS community_downvotes INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE feature_requests ADD COLUMN IF NOT EXISTS community_duplicate_votes INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completion_notes TEXT",
                # Migrate existing assignee_id values to task_assignees table (one-time migration)
                """
                INSERT INTO task_assignees (task_id, user_id, assigned_at)
                SELECT id, assignee_id, created_at
                FROM tasks
                WHERE assignee_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM task_assignees ta WHERE ta.task_id = tasks.id AND ta.user_id = tasks.assignee_id
                  )
                ON CONFLICT (task_id, user_id) DO NOTHING
                """,
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
        assignee_ids: Optional[List[int]] = None,
    ) -> int:
        """Create a task with optional single assignee (for backwards compat) or multiple assignees."""
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
        task_id = task_row["id"]
        
        # Handle multiple assignees (preferred method)
        if assignee_ids:
            await self.add_task_assignees(task_id, assignee_ids)
        # Backwards compatibility: if single assignee_id provided, add to task_assignees too
        elif assignee_id:
            await self.add_task_assignees(task_id, [assignee_id])
        
        return task_id

    async def fetch_tasks(
        self,
        board_id: int,
        *,
        column_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        include_completed: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch tasks, optionally filtered by column or assignee. Returns tasks with assignee_ids list."""
        query = [
            """
            SELECT t.*, 
                   COALESCE(
                       json_agg(DISTINCT ta.user_id) FILTER (WHERE ta.user_id IS NOT NULL),
                       '[]'::json
                   ) as assignee_ids
            FROM tasks t
            LEFT JOIN task_assignees ta ON t.id = ta.task_id
            WHERE t.board_id = $1
            """
        ]
        params: List[Any] = [board_id]
        if column_id is not None:
            params.append(column_id)
            query.append(f"AND t.column_id = ${len(params)}")
        if assignee_id is not None:
            # Filter by assignee: either in old assignee_id column OR in task_assignees table
            params.append(assignee_id)
            query.append(f"AND (t.assignee_id = ${len(params)} OR EXISTS (SELECT 1 FROM task_assignees ta WHERE ta.task_id = t.id AND ta.user_id = ${len(params)}))")
        if not include_completed:
            query.append("AND t.completed = FALSE")
        query.append("GROUP BY t.id ORDER BY t.created_at DESC")
        rows = await self._execute(" ".join(query), tuple(params), fetchall=True)
        tasks = []
        for row in rows or []:
            task_dict = dict(row)
            # Convert JSON array to Python list
            if isinstance(task_dict.get("assignee_ids"), list):
                task_dict["assignee_ids"] = task_dict["assignee_ids"]
            elif task_dict.get("assignee_ids"):
                import json
                task_dict["assignee_ids"] = json.loads(task_dict["assignee_ids"]) if isinstance(task_dict["assignee_ids"], str) else []
            else:
                task_dict["assignee_ids"] = []
            tasks.append(task_dict)
        return tasks

    async def fetch_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single task with its assignee_ids list."""
        row = await self._execute(
            """
            SELECT t.*,
                   COALESCE(
                       json_agg(DISTINCT ta.user_id) FILTER (WHERE ta.user_id IS NOT NULL),
                       '[]'::json
                   ) as assignee_ids
            FROM tasks t
            LEFT JOIN task_assignees ta ON t.id = ta.task_id
            WHERE t.id = $1
            GROUP BY t.id
            """,
            (task_id,),
            fetchone=True,
        )
        if not row:
            return None
        task_dict = dict(row)
        # Convert JSON array to Python list
        if isinstance(task_dict.get("assignee_ids"), list):
            task_dict["assignee_ids"] = task_dict["assignee_ids"]
        elif task_dict.get("assignee_ids"):
            import json
            task_dict["assignee_ids"] = json.loads(task_dict["assignee_ids"]) if isinstance(task_dict["assignee_ids"], str) else []
        else:
            task_dict["assignee_ids"] = []
        return task_dict

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
    
    # Multiple assignees management methods
    async def add_task_assignees(self, task_id: int, user_ids: List[int]) -> None:
        """Add one or more assignees to a task."""
        if not user_ids:
            return
        now = _utcnow()
        for user_id in user_ids:
            await self._execute(
                """
                INSERT INTO task_assignees (task_id, user_id, assigned_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (task_id, user_id) DO NOTHING
                """,
                (task_id, user_id, now),
            )
        # Also update legacy assignee_id field for backwards compatibility (use first assignee)
        existing = await self._execute(
            "SELECT assignee_id FROM tasks WHERE id = $1",
            (task_id,),
            fetchone=True,
        )
        if existing and not existing.get("assignee_id"):
            await self._execute(
                "UPDATE tasks SET assignee_id = $1 WHERE id = $2",
                (user_ids[0], task_id),
            )
    
    async def remove_task_assignees(self, task_id: int, user_ids: List[int]) -> None:
        """Remove one or more assignees from a task."""
        if not user_ids:
            return
        await self._execute(
            "DELETE FROM task_assignees WHERE task_id = $1 AND user_id = ANY($2::bigint[])",
            (task_id, user_ids),
        )
        # Update legacy assignee_id if we removed the last assignee or the one in assignee_id
        remaining = await self._execute(
            "SELECT user_id FROM task_assignees WHERE task_id = $1 ORDER BY assigned_at LIMIT 1",
            (task_id,),
            fetchone=True,
        )
        if remaining:
            await self._execute(
                "UPDATE tasks SET assignee_id = $1 WHERE id = $2",
                (remaining["user_id"], task_id),
            )
        else:
            await self._execute(
                "UPDATE tasks SET assignee_id = NULL WHERE id = $1",
                (task_id,),
            )
    
    async def set_task_assignees(self, task_id: int, user_ids: List[int]) -> None:
        """Replace all assignees for a task with the given list."""
        # Update legacy assignee_id FIRST to keep it in sync
        # This ensures backwards compatibility even if add_task_assignees doesn't update it
        if user_ids:
            await self._execute(
                "UPDATE tasks SET assignee_id = $1 WHERE id = $2",
                (user_ids[0], task_id),
            )
        else:
            await self._execute(
                "UPDATE tasks SET assignee_id = NULL WHERE id = $1",
                (task_id,),
            )
        
        # Remove all existing assignees
        await self._execute(
            "DELETE FROM task_assignees WHERE task_id = $1",
            (task_id,),
        )
        
        # Add new assignees
        if user_ids:
            await self.add_task_assignees(task_id, user_ids)
    
    async def get_task_assignees(self, task_id: int) -> List[int]:
        """Get list of user IDs assigned to a task."""
        rows = await self._execute(
            "SELECT user_id FROM task_assignees WHERE task_id = $1 ORDER BY assigned_at",
            (task_id,),
            fetchall=True,
        )
        return [row["user_id"] for row in rows or []]

    async def search_tasks(self, guild_id: int, query: str) -> List[Dict[str, Any]]:
        """Search tasks with assignee_ids included."""
        like = f"%{query}%"
        rows = await self._execute(
            """
            SELECT t.*, 
                   boards.name AS board_name, 
                   boards.channel_id,
                   COALESCE(
                       json_agg(DISTINCT ta.user_id) FILTER (WHERE ta.user_id IS NOT NULL),
                       '[]'::json
                   ) as assignee_ids
            FROM tasks t
            JOIN boards ON t.board_id = boards.id
            LEFT JOIN task_assignees ta ON t.id = ta.task_id
            WHERE boards.guild_id = $1
              AND (
                  t.title ILIKE $2 OR
                  COALESCE(t.description, '') ILIKE $3
              )
            GROUP BY t.id, boards.name, boards.channel_id
            ORDER BY t.created_at DESC
            LIMIT 25
            """,
            (guild_id, like, like),
            fetchall=True,
        )
        tasks = []
        for row in rows or []:
            task_dict = dict(row)
            # Convert JSON array to Python list
            if isinstance(task_dict.get("assignee_ids"), list):
                task_dict["assignee_ids"] = task_dict["assignee_ids"]
            elif task_dict.get("assignee_ids"):
                import json
                task_dict["assignee_ids"] = json.loads(task_dict["assignee_ids"]) if isinstance(task_dict["assignee_ids"], str) else []
            else:
                task_dict["assignee_ids"] = []
            tasks.append(task_dict)
        return tasks

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

    async def board_stats_detailed(self, board_id: int) -> Dict[str, Any]:
        """Get detailed board statistics including per-column breakdown."""
        # Get basic totals
        totals = await self._execute(
            """
            SELECT
                COUNT(1) AS total,
                SUM(CASE WHEN completed THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN completed = FALSE THEN 1 ELSE 0 END) AS active
            FROM tasks
            WHERE board_id = $1
            """,
            (board_id,),
            fetchone=True,
        )

        # Get overdue count
        overdue = await self._execute(
            """
            SELECT COUNT(1) AS overdue
            FROM tasks
            WHERE board_id = $1 AND completed = FALSE AND due_date IS NOT NULL AND due_date < $2
            """,
            (board_id, _utcnow()),
            fetchone=True,
        )

        # Get tasks due this week
        from datetime import timedelta
        week_later = datetime.now(timezone.utc) + timedelta(days=7)
        due_this_week = await self._execute(
            """
            SELECT COUNT(1) AS due_soon
            FROM tasks
            WHERE board_id = $1 AND completed = FALSE AND due_date IS NOT NULL
              AND due_date >= $2 AND due_date <= $3
            """,
            (board_id, _utcnow(), week_later.strftime(ISO_FORMAT)),
            fetchone=True,
        )

        # Get per-column task counts
        column_stats = await self._execute(
            """
            SELECT c.id, c.name, COUNT(t.id) AS task_count
            FROM columns c
            LEFT JOIN tasks t ON t.column_id = c.id AND t.completed = FALSE
            WHERE c.board_id = $1
            GROUP BY c.id, c.name
            ORDER BY c.position
            """,
            (board_id,),
            fetchall=True,
        )

        return {
            "total": totals["total"] if totals else 0,
            "completed": totals["completed"] if totals else 0,
            "active": totals["active"] if totals else 0,
            "overdue": overdue["overdue"] if overdue else 0,
            "due_this_week": due_this_week["due_soon"] if due_this_week else 0,
            "column_breakdown": [dict(row) for row in column_stats] if column_stats else [],
        }

    async def fetch_due_tasks(self, before_iso: str) -> List[Dict[str, Any]]:
        """Fetch due tasks with assignee_ids for reminders."""
        rows = await self._execute(
            """
            SELECT t.*, 
                   boards.name AS board_name, 
                   boards.channel_id, 
                   boards.guild_id,
                   COALESCE(
                       json_agg(DISTINCT ta.user_id) FILTER (WHERE ta.user_id IS NOT NULL),
                       '[]'::json
                   ) as assignee_ids
            FROM tasks t
            JOIN boards ON t.board_id = boards.id
            LEFT JOIN task_assignees ta ON t.id = ta.task_id
            WHERE t.completed = FALSE AND t.due_date IS NOT NULL AND t.due_date <= $1
            GROUP BY t.id, boards.name, boards.channel_id, boards.guild_id
            ORDER BY t.due_date ASC
            """,
            (before_iso,),
            fetchall=True,
        )
        tasks = []
        for row in rows or []:
            task_dict = dict(row)
            # Convert JSON array to Python list
            if isinstance(task_dict.get("assignee_ids"), list):
                task_dict["assignee_ids"] = task_dict["assignee_ids"]
            elif task_dict.get("assignee_ids"):
                import json
                task_dict["assignee_ids"] = json.loads(task_dict["assignee_ids"]) if isinstance(task_dict["assignee_ids"], str) else []
            else:
                task_dict["assignee_ids"] = []
            tasks.append(task_dict)
        return tasks

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

    async def toggle_complete(self, task_id: int, completed: bool, completion_notes: Optional[str] = None) -> bool:
        updates = {"completed": completed}
        if completed and completion_notes:
            updates["completion_notes"] = completion_notes
        elif not completed:
            # Clear notes when marking incomplete
            updates["completion_notes"] = None
        return await self.update_task(task_id, **updates)

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

    async def get_feature_request(self, feature_id: int, *, guild_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if guild_id is not None:
            row = await self._execute(
                "SELECT * FROM feature_requests WHERE id = $1 AND guild_id = $2",
                (feature_id, guild_id),
                fetchone=True,
            )
        else:
            row = await self._execute(
                "SELECT * FROM feature_requests WHERE id = $1",
                (feature_id,),
                fetchone=True,
            )
        return dict(row) if row else None

    async def fetch_feature_requests_by_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self._execute(
            "SELECT * FROM feature_requests WHERE guild_id = $1 ORDER BY created_at DESC",
            (guild_id,),
            fetchall=True,
        )
        return [dict(row) for row in rows or []]

    async def set_feature_request_message(
        self,
        feature_id: int,
        *,
        message_id: int,
        channel_id: int,
    ) -> None:
        await self._execute(
            """
            UPDATE feature_requests
            SET community_message_id = $1,
                community_channel_id = $2
            WHERE id = $3
            """,
            (message_id, channel_id, feature_id),
        )

    async def get_feature_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        row = await self._execute(
            "SELECT * FROM feature_requests WHERE community_message_id = $1",
            (message_id,),
            fetchone=True,
        )
        return dict(row) if row else None

    async def adjust_feature_votes(
        self,
        feature_id: int,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
        duplicate_delta: int = 0,
    ) -> None:
        await self._execute(
            """
            UPDATE feature_requests
            SET community_upvotes = GREATEST(community_upvotes + $1, 0),
                community_downvotes = GREATEST(community_downvotes + $2, 0),
                community_duplicate_votes = GREATEST(community_duplicate_votes + $3, 0)
            WHERE id = $4
            """,
            (up_delta, down_delta, duplicate_delta, feature_id),
        )

    async def mark_feature_duplicate(
        self,
        request_id: int,
        *,
        parent_id: int,
        confidence: float,
        note: Optional[str] = None,
    ) -> None:
        payload = {
            "duplicate_parent": parent_id,
            "duplicate_confidence": confidence,
            "duplicate_note": note,
            "duplicate_marked_at": _utcnow(),
        }
        await self._execute(
            """
            UPDATE feature_requests
            SET status = 'duplicate',
                duplicate_of = $1,
                last_analyzed_at = NOW(),
                analysis_data = COALESCE(analysis_data, '{}'::jsonb) || $2::jsonb
            WHERE id = $3
            """,
            (parent_id, json.dumps(payload), request_id),
        )
        history_entry = {
            "timestamp": _utcnow(),
            "action": "marked_duplicate",
            "parent_id": parent_id,
            "confidence": confidence,
            "note": note,
        }
        await self.append_feature_history(request_id, history_entry)
        parent_entry = {
            "timestamp": _utcnow(),
            "action": "duplicate_linked",
            "child_id": request_id,
            "confidence": confidence,
            "note": note,
        }
        await self.append_feature_history(parent_id, parent_entry)

    async def append_feature_history(self, request_id: int, entry: Dict[str, Any]) -> None:
        await self._execute(
            """
            UPDATE feature_requests
            SET merge_history = COALESCE(merge_history, '[]'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            (json.dumps([entry]), request_id),
        )

    async def record_feature_analysis_note(self, request_id: int, note: str, *, tag: Optional[str] = None) -> None:
        payload = {
            "timestamp": _utcnow(),
            "note": note,
        }
        if tag:
            payload["tag"] = tag
        await self.append_feature_history(request_id, {"analysis_note": payload})
        await self._execute(
            """
            UPDATE feature_requests
            SET last_analyzed_at = NOW(),
                analysis_data = COALESCE(analysis_data, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            (json.dumps({f"note_{_utcnow()}": note}), request_id),
        )

    async def set_feature_score(
        self,
        request_id: int,
        *,
        score: float,
        priority_value: Optional[int],
        ease_value: Optional[int],
        vote_bonus: Optional[float] = None,
        duplicate_penalty: Optional[float] = None,
        net_votes: Optional[int] = None,
        upvotes: Optional[int] = None,
        downvotes: Optional[int] = None,
        duplicate_votes: Optional[int] = None,
    ) -> None:
        payload = {
            "score": score,
            "calculated_at": _utcnow(),
            "priority_value": priority_value,
            "ease_value": ease_value,
        }
        if vote_bonus is not None:
            payload["vote_bonus"] = vote_bonus
        if duplicate_penalty is not None:
            payload["duplicate_penalty"] = duplicate_penalty
        if net_votes is not None:
            payload["net_votes"] = net_votes
        if upvotes is not None:
            payload["community_upvotes_snapshot"] = upvotes
        if downvotes is not None:
            payload["community_downvotes_snapshot"] = downvotes
        if duplicate_votes is not None:
            payload["community_duplicate_votes_snapshot"] = duplicate_votes
        await self._execute(
            """
            UPDATE feature_requests
            SET score = $1,
                last_analyzed_at = NOW(),
                analysis_data = COALESCE(analysis_data, '{}'::jsonb) || $2::jsonb
            WHERE id = $3
            """,
            (score, json.dumps(payload), request_id),
        )

    async def set_similar_candidates(self, request_id: int, candidates: List[int]) -> None:
        payload = {
            "similar_candidates": candidates,
            "similar_checked_at": _utcnow(),
        }
        await self._execute(
            """
            UPDATE feature_requests
            SET analysis_data = COALESCE(analysis_data, '{}'::jsonb) || $1::jsonb,
                last_analyzed_at = NOW()
            WHERE id = $2
            """,
            (json.dumps(payload), request_id),
        )

    async def mark_feature_completed(
        self,
        request_id: int,
        *,
        commit_hash: Optional[str],
        commit_message: Optional[str],
    ) -> None:
        payload = {
            "completed_via": "git",
            "commit_hash": commit_hash,
            "commit_message": commit_message,
            "completed_recorded_at": _utcnow(),
        }
        await self._execute(
            """
            UPDATE feature_requests
            SET status = 'completed',
                completed_at = COALESCE(completed_at, NOW()),
                analysis_data = COALESCE(analysis_data, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            (json.dumps(payload), request_id),
        )
        history_entry = {
            "timestamp": _utcnow(),
            "action": "completed",
            "commit_hash": commit_hash,
            "commit_message": commit_message,
        }
        await self.append_feature_history(request_id, history_entry)

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
