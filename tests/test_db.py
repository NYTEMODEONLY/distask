"""Tests for database operations (requires test database)."""

import pytest
import asyncio
from utils import Database


@pytest.mark.asyncio
async def test_database_init(test_db_url):
    """Test database initialization."""
    db = Database(test_db_url)
    try:
        await db.init()
        # Verify connection works
        result = await db._execute("SELECT 1 as test", fetchone=True)
        assert result is not None
        assert result["test"] == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_ensure_guild(test_db_url, sample_guild_id):
    """Test guild creation."""
    db = Database(test_db_url)
    try:
        await db.init()
        await db.ensure_guild(sample_guild_id)
        
        # Verify guild exists
        settings = await db.get_guild_settings(sample_guild_id)
        assert settings is not None
        assert settings["guild_id"] == sample_guild_id
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_board_creation(test_db_url, sample_guild_id, sample_user_id):
    """Test board creation."""
    db = Database(test_db_url)
    try:
        await db.init()
        await db.ensure_guild(sample_guild_id)
        
        board_id = await db.create_board(
            guild_id=sample_guild_id,
            channel_id=111111111111111111,
            name="Test Board",
            description="Test description",
            created_by=sample_user_id,
        )
        
        assert board_id > 0
        
        # Verify board exists
        board = await db.get_board(sample_guild_id, board_id)
        assert board is not None
        assert board["name"] == "Test Board"
        assert board["description"] == "Test description"
        
        # Verify default columns created
        columns = await db.fetch_columns(board_id)
        assert len(columns) >= 3  # To Do, In Progress, Done
    finally:
        await db.close()

