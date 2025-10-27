#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.db import Database


def _load_sqlite_rows(sqlite_path: Path) -> Dict[str, List[Dict[str, object]]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {}
        for table in ("guilds", "boards", "columns", "tasks"):
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            tables[table] = [dict(row) for row in rows]
        return tables
    finally:
        conn.close()


async def _ensure_schema(dsn: str) -> None:
    db = Database(dsn)
    await db.init()
    await db.close()


async def _migrate(sqlite_path: Path, dsn: str, force: bool) -> Tuple[int, int, int, int]:
    data = _load_sqlite_rows(sqlite_path)
    await _ensure_schema(dsn)

    pool = await asyncpg.create_pool(dsn=dsn)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                if not force:
                    counts = await conn.fetchrow(
                        """
                        SELECT
                            (SELECT COUNT(1) FROM guilds) AS guilds,
                            (SELECT COUNT(1) FROM boards) AS boards,
                            (SELECT COUNT(1) FROM columns) AS columns,
                            (SELECT COUNT(1) FROM tasks) AS tasks
                        """
                    )
                    if any(counts.values()):
                        raise RuntimeError(
                            "Target PostgreSQL database is not empty. Pass --force to overwrite existing data."
                        )

                await conn.execute("TRUNCATE TABLE tasks, columns, boards, guilds RESTART IDENTITY CASCADE")

                guild_rows = [
                    (row["guild_id"], bool(row["notify_enabled"]), row["reminder_time"])
                    for row in data["guilds"]
                ]
                if guild_rows:
                    await conn.executemany(
                        "INSERT INTO guilds (guild_id, notify_enabled, reminder_time) VALUES ($1, $2, $3)",
                        guild_rows,
                    )

                board_rows = [
                    (
                        row["id"],
                        row["guild_id"],
                        row["channel_id"],
                        row["name"],
                        row["description"],
                        row["created_by"],
                        row["created_at"],
                    )
                    for row in data["boards"]
                ]
                if board_rows:
                    await conn.executemany(
                        """
                        INSERT INTO boards (id, guild_id, channel_id, name, description, created_by, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        board_rows,
                    )
                    max_board_id = max(row[0] for row in board_rows)
                    await conn.execute("SELECT setval('boards_id_seq', $1, true)", max_board_id)

                column_rows = [
                    (
                        row["id"],
                        row["board_id"],
                        row["name"],
                        row["position"],
                    )
                    for row in data["columns"]
                ]
                if column_rows:
                    await conn.executemany(
                        "INSERT INTO columns (id, board_id, name, position) VALUES ($1, $2, $3, $4)",
                        column_rows,
                    )
                    max_column_id = max(row[0] for row in column_rows)
                    await conn.execute("SELECT setval('columns_id_seq', $1, true)", max_column_id)

                task_rows = [
                    (
                        row["id"],
                        row["board_id"],
                        row["column_id"],
                        row["title"],
                        row["description"],
                        row["assignee_id"],
                        row["due_date"],
                        row["created_by"],
                        row["created_at"],
                        bool(row["completed"]),
                    )
                    for row in data["tasks"]
                ]
                if task_rows:
                    await conn.executemany(
                        """
                        INSERT INTO tasks (
                            id,
                            board_id,
                            column_id,
                            title,
                            description,
                            assignee_id,
                            due_date,
                            created_by,
                            created_at,
                            completed
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        """,
                        task_rows,
                    )
                    max_task_id = max(row[0] for row in task_rows)
                    await conn.execute("SELECT setval('tasks_id_seq', $1, true)", max_task_id)

        return (
            len(guild_rows),
            len(board_rows),
            len(column_rows),
            len(task_rows),
        )
    finally:
        await pool.close()


async def _run(sqlite_path: Path, dsn: str, force: bool) -> None:
    guilds, boards, columns, tasks = await _migrate(sqlite_path, dsn, force)
    print(f"Migrated {guilds} guilds, {boards} boards, {columns} columns, {tasks} tasks.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate DisTask data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--sqlite",
        default="data/distask.db",
        help="Path to the existing SQLite database (default: data/distask.db).",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN. Defaults to DATABASE_URL env var or postgresql://distask:distaskpass@localhost:5432/distask",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing PostgreSQL data even if tables are not empty.",
    )
    args = parser.parse_args()

    dsn = args.dsn or os.getenv("DATABASE_URL") or "postgresql://distask:distaskpass@localhost:5432/distask"
    sqlite_path = Path(args.sqlite).expanduser().resolve()

    asyncio.run(_run(sqlite_path, dsn, args.force))


if __name__ == "__main__":
    main()
