"""
Test suite for FR-17: Multiple Assignees feature.

Run with: pytest tests/test_multiple_assignees.py -v
"""

import pytest
from typing import Dict, List, Any

# Import the function to test formatting
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.embeds import _format_assignees


class TestAssigneeFormatting:
    """Test the _format_assignees helper function."""
    
    def test_single_assignee_new_format(self):
        """Test formatting with single assignee using new assignee_ids format."""
        task = {'assignee_ids': [123456789]}
        result = _format_assignees(task)
        assert result.startswith('👤'), 'Should start with 👤 emoji'
        assert '<@123456789>' in result, 'Should contain user mention'
        assert result == '👤 <@123456789>', 'Should match expected format'
    
    def test_multiple_assignees_three_or_less(self):
        """Test formatting with 2-3 assignees."""
        task = {'assignee_ids': [123456789, 987654321, 111222333]}
        result = _format_assignees(task)
        assert result.startswith('👥'), 'Should start with 👥 emoji for multiple'
        assert '<@123456789>' in result, 'Should contain first user'
        assert '<@987654321>' in result, 'Should contain second user'
        assert '<@111222333>' in result, 'Should contain third user'
        assert ', ' in result, 'Should separate with commas'
    
    def test_many_assignees_more_than_three(self):
        """Test formatting with more than 3 assignees shows truncation."""
        task = {'assignee_ids': [123456789, 987654321, 111222333, 444555666, 777888999]}
        result = _format_assignees(task)
        assert result.startswith('👥'), 'Should start with 👥 emoji'
        assert '+2 more' in result, 'Should show "+2 more" for 5 assignees'
        assert '<@123456789>' in result, 'Should show first user'
        assert '<@777888999>' not in result, 'Should not show 5th user directly'
    
    def test_backwards_compatibility_legacy(self):
        """Test backwards compatibility with legacy assignee_id field."""
        task = {'assignee_id': 123456789}
        result = _format_assignees(task)
        assert result.startswith('👤'), 'Should start with 👤 emoji'
        assert '<@123456789>' in result, 'Should contain user mention'
        assert result == '👤 <@123456789>', 'Should match expected format'
    
    def test_no_assignees(self):
        """Test formatting when no assignees are present."""
        task = {}
        result = _format_assignees(task)
        assert 'Unassigned' in result, 'Should show Unassigned'
        assert result == '👤 Unassigned', 'Should match expected format'
    
    def test_prefers_new_format_over_legacy(self):
        """Test that new assignee_ids format is preferred over legacy."""
        task = {'assignee_id': 999999999, 'assignee_ids': [123456789]}
        result = _format_assignees(task)
        # Should use assignee_ids, not assignee_id
        assert '<@123456789>' in result, 'Should use assignee_ids'
        assert '<@999999999>' not in result, 'Should not use legacy assignee_id'


@pytest.mark.asyncio
async def test_database_migration_integration():
    """
    Integration test for database migration.
    
    NOTE: This requires a live database connection.
    Run with: pytest tests/test_multiple_assignees.py::test_database_migration_integration -v
    """
    from utils.db import Database
    import os
    
    # Get database URL from environment or use default
    db_url = os.getenv('DATABASE_URL', 'postgresql://distask:distaskpass@localhost:5432/distask')
    db = Database(db_url)
    await db.init()
    
    try:
        # Test 1: Check if task_assignees table exists
        result = await db._execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'task_assignees')",
            (),
            fetchone=True
        )
        assert result['exists'], 'task_assignees table should exist after init()'
        
        # Test 2: Verify migration is idempotent
        count_before = await db._execute(
            'SELECT COUNT(*) as count FROM task_assignees',
            (),
            fetchone=True
        )
        
        # Run migration again (should be safe)
        await db._execute(
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
            (),
        )
        
        count_after = await db._execute(
            'SELECT COUNT(*) as count FROM task_assignees',
            (),
            fetchone=True
        )
        
        assert count_before['count'] == count_after['count'], 'Migration should be idempotent'
        
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_multiple_assignees_crud():
    """
    Test CRUD operations for multiple assignees.
    
    NOTE: This requires a live database connection and a test guild/board.
    """
    from utils.db import Database
    import os
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://distask:distaskpass@localhost:5432/distask')
    db = Database(db_url)
    await db.init()
    
    try:
        # Get a test board (adjust guild_id as needed)
        guild_id = 1432217453370413118  # From environment
        boards = await db.fetch_boards(guild_id)
        if not boards:
            pytest.skip('No test boards available')
        
        board_id = boards[0]['id']
        columns = await db.fetch_columns(board_id)
        if not columns:
            pytest.skip('No test columns available')
        
        column_id = columns[0]['id']
        test_user_id = 536648724244332544
        
        # Test: Create task with multiple assignees
        task_id = await db.create_task(
            board_id=board_id,
            column_id=column_id,
            title='[TEST] Multiple Assignees',
            description='Test task',
            assignee_id=None,
            assignee_ids=[test_user_id, 85711387883499520],
            due_date=None,
            created_by=test_user_id
        )
        
        # Verify task has assignees
        task = await db.fetch_task(task_id)
        assert 'assignee_ids' in task, 'Task should have assignee_ids field'
        assert len(task['assignee_ids']) == 2, 'Should have 2 assignees'
        
        # Test: Add assignee
        await db.add_task_assignees(task_id, [123456789])
        task = await db.fetch_task(task_id)
        assert len(task['assignee_ids']) == 3, 'Should have 3 assignees after adding'
        
        # Test: Remove assignee
        await db.remove_task_assignees(task_id, [123456789])
        task = await db.fetch_task(task_id)
        assert len(task['assignee_ids']) == 2, 'Should have 2 assignees after removing'
        
        # Test: Set assignees (replace all)
        await db.set_task_assignees(task_id, [test_user_id])
        task = await db.fetch_task(task_id)
        assert len(task['assignee_ids']) == 1, 'Should have 1 assignee after setting'
        
        # Cleanup
        await db.delete_task(task_id)
        
    finally:
        await db.close()

