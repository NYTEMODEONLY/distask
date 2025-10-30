# FR-17 Testing Summary: Multiple Assignees

## Overview
This document outlines the testing performed for FR-17 (Multiple Assignees feature) and what should be verified after deployment.

## Code Review Verification ✅

### 1. Database Schema Migration
**Status:** ✅ Verified in code

The migration statement in `utils/db.py` (lines 126-136) is:
- **Idempotent**: Uses `ON CONFLICT DO NOTHING` and `NOT EXISTS` check
- **Safe**: Only migrates existing `assignee_id` values, doesn't modify original data
- **Automatic**: Runs during `Database.init()` when bot starts

**Migration Logic:**
```sql
INSERT INTO task_assignees (task_id, user_id, assigned_at)
SELECT id, assignee_id, created_at
FROM tasks
WHERE assignee_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM task_assignees ta 
      WHERE ta.task_id = tasks.id AND ta.user_id = tasks.assignee_id
  )
ON CONFLICT (task_id, user_id) DO NOTHING
```

### 2. Backwards Compatibility
**Status:** ✅ Verified in code

- Legacy `assignee_id` field maintained in `tasks` table
- `create_task()` accepts both `assignee_id` (single) and `assignee_ids` (multiple)
- `_format_assignees()` checks legacy `assignee_id` if `assignee_ids` not present
- All existing single-assignee tasks continue to work

### 3. Display Formatting
**Status:** ✅ Verified in code

The `_format_assignees()` helper function handles:
- Single assignee: `👤 <@user>`
- Multiple (≤3): `👥 <@user1>, <@user2>, <@user3>`
- Many (>3): `👥 <@user1>, <@user2>, <@user3> +2 more`
- Legacy format: Falls back to `assignee_id` if `assignee_ids` not present
- Unassigned: Shows `👤 Unassigned`

## Test Suite Created ✅

Comprehensive test suite added in `tests/test_multiple_assignees.py`:

1. **Unit Tests** (no DB required):
   - Single assignee formatting
   - Multiple assignees formatting (≤3)
   - Many assignees formatting (>3)
   - Backwards compatibility (legacy format)
   - No assignees handling
   - Prefer new format over legacy

2. **Integration Tests** (requires DB):
   - Database migration verification
   - Migration idempotency test
   - CRUD operations for multiple assignees

**Run tests:**
```bash
# Unit tests (no DB needed)
pytest tests/test_multiple_assignees.py::TestAssigneeFormatting -v

# Integration tests (requires DB)
pytest tests/test_multiple_assignees.py::test_database_migration_integration -v
pytest tests/test_multiple_assignees.py::test_multiple_assignees_crud -v
```

## Post-Deployment Testing Checklist

After merging the PR and deploying to VPS, verify:

### Database Migration
- [ ] Bot starts without errors
- [ ] Check logs for migration execution
- [ ] Verify existing tasks with assignees have entries in `task_assignees` table:
  ```sql
  SELECT COUNT(*) FROM tasks WHERE assignee_id IS NOT NULL;
  SELECT COUNT(DISTINCT task_id) FROM task_assignees;
  ```
  (Counts should match or be close)

### UI Functionality
- [ ] `/add-task` - Select multiple users from dropdown
- [ ] `/add-task` - Task shows multiple assignees in embed
- [ ] `/edit-task` - Can edit and set multiple assignees
- [ ] `/assign-task` - Can add multiple assignees (comma-separated)
- [ ] `/assign-task` - Adds to existing assignees (doesn't replace)
- [ ] `/list-tasks` - Shows multiple assignees correctly
- [ ] `/view-board` - Board view shows multiple assignees per task

### Backwards Compatibility
- [ ] Existing single-assignee tasks display correctly
- [ ] Legacy `assignee_id` field still works
- [ ] Creating task with single assignee still works
- [ ] No errors in logs related to missing `assignee_ids`

### Display Formatting
- [ ] Single assignee shows: `👤 <@user>`
- [ ] 2-3 assignees show: `👥 <@user1>, <@user2>, <@user3>`
- [ ] 4+ assignees show: `👥 <@user1>, <@user2>, <@user3> +X more`
- [ ] Field name pluralizes: "Assignee" vs "Assignees"

### Reminders & Filtering
- [ ] Reminder digest includes tasks where user is one of multiple assignees
- [ ] `/list-tasks` filtering by assignee works with multiple assignees
- [ ] Search results show multiple assignees correctly

## Known Limitations

1. **Discord UserSelect Limit**: Maximum 25 users can be selected at once (Discord API limitation)
2. **Display Truncation**: More than 3 assignees are truncated in display (but all are stored)
3. **Legacy Field**: `assignee_id` field kept for backwards compatibility, but new code prefers `assignee_ids`

## Rollback Plan

If issues occur:

1. **Database**: The `task_assignees` table can be ignored - legacy `assignee_id` still works
2. **Code**: Revert to previous commit - existing tasks will continue working
3. **No Data Loss**: All assignee data preserved in both old and new formats

## Notes

- Migration runs automatically on bot startup via `Database.init()`
- Migration is idempotent - safe to run multiple times
- All queries updated to include `assignee_ids` for consistency
- Backwards compatibility maintained throughout

