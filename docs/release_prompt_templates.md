# Universal AI/IDE Prompt Templates for DisTask

This document provides LLM-agnostic prompt templates for implementing features in DisTask. These templates are designed to work with any AI coding assistant (Cursor, Claude, GitHub Copilot, Codex, etc.) using plain English and structured instructions.

## Template Structure

All templates follow this structure:
- **Feature Description**: What needs to be implemented
- **Existing Code Context**: Relevant files and patterns
- **Implementation Guidelines**: Project-specific rules
- **Output Format**: What code/artifacts to produce

## Template 1: Feature Implementation

### Basic Feature Implementation

```
Implement Feature Request: [FR-XXX] [Feature Title]

Description:
[Full feature description from feature request]

Score: [X.XX] (Priority: [Y], Ease: [Z], Net Votes: [N])

Existing Code Context:
- Project structure: DisTask Discord bot for task management
- Main entry: bot.py (loads env, logging, registers cogs)
- Commands: cogs/boards.py, cogs/tasks.py, cogs/admin.py, cogs/features.py
- Utilities: utils/db.py (Database wrapper), utils/embeds.py (EmbedFactory), utils/validators.py
- Database: PostgreSQL with asyncpg, tables: guilds, boards, columns, tasks, feature_requests
- UI: cogs/ui/modals.py (Modals), cogs/ui/views.py (Views with buttons/select menus)
- Validation: utils/validators.py (Validator class with input checks)

Implementation Guidelines:
1. Follow existing patterns in cogs/ directory
2. Use Database methods from utils/db.py for data operations
3. Use EmbedFactory from utils/embeds.py for Discord embeds
4. Use Validator class for input validation
5. Follow snake_case for functions/modules, PascalCase for classes
6. Use async/await for all database operations
7. Add cooldowns using @app_commands.checks.cooldown() decorators
8. Use Modals for text input, Views for interactive components
9. All command responses should be public (not ephemeral) for team visibility
10. Include type hints on all new functions

Output Format:
Provide only the Python code changes needed. Include:
- Modified files with line numbers or full context
- New functions/classes with complete implementation
- Import statements if adding new dependencies
- Brief comments explaining key logic

Compatibility Requirements:
- Must work with existing Database schema
- Must not break existing slash commands
- Must follow Discord.py 2.3+ patterns
- Must be compatible with PostgreSQL asyncpg
```

### Example Usage

```
Implement Feature Request: FR-123 Add task due date reminders

Description:
Users want to receive DM reminders when tasks are approaching their due dates. 
The bot should send a DM 24 hours before the due date and another reminder 1 hour before.

Score: 85.50 (Priority: 8, Ease: 7, Net Votes: 12)

Existing Code Context:
- Reminder system exists in utils/reminders.py (ReminderScheduler)
- Tasks have due_date field stored as ISO format string
- Current reminders only send daily digests to board channels
- Database: tasks table has due_date TEXT field

Implementation Guidelines:
[Same as above]

Output Format:
[Same as above]
```

## Template 2: Database Schema Changes

```
Implement Database Schema Change: [Description]

Change Required:
[Describe the schema change: new table, column, index, etc.]

Affected Tables:
- [Table name]: [Current structure]
- [Add/modify]: [What needs to change]

Migration Strategy:
1. Add column/table with ALTER TABLE IF NOT EXISTS or CREATE TABLE IF NOT EXISTS
2. Ensure backward compatibility (new columns nullable or with defaults)
3. Update Database class in utils/db.py with new methods
4. No data migration needed: [Yes/No]

Database Helper Methods Needed:
- [Method name]: [Purpose]
- Returns: [Return type]

Implementation Guidelines:
1. Follow existing patterns in utils/db.py
2. Use asyncpg connection pool from Database._pool
3. Add schema changes in Database.init() method
4. Use ALTER TABLE ADD COLUMN IF NOT EXISTS for safety
5. Add helper methods following create_*/get_*/update_*/delete_* patterns
6. Include proper error handling

Output Format:
- Updated Database.init() schema statements
- New Database class methods with type hints
- Updated docstrings
```

## Template 3: New Slash Command

```
Implement New Slash Command: /[command-name]

Command Purpose:
[What the command does]

Parameters:
- [param1]: [Type] - [Description]
- [param2]: [Type] - [Description]

Permissions Required:
- [Manage Guild / Manage Channels / None]

Interaction Flow:
1. User runs /[command-name]
2. [What happens: Modal opens / Select menu appears / Direct response]
3. [Final step: What user sees]

Existing Patterns:
- See cogs/boards.py for board commands
- See cogs/tasks.py for task commands
- See cogs/admin.py for admin commands
- Use cogs/ui/modals.py for text input
- Use cogs/ui/views.py for buttons/select menus

Database Operations:
- Reads: [Which tables/fields]
- Writes: [Which tables/fields]

Implementation Guidelines:
1. Create command in appropriate cog file
2. Use @app_commands.command() decorator
3. Add cooldown: @app_commands.checks.cooldown(1, 3.0) for normal, 10.0 for heavy ops
4. Use Database methods for data access
5. Use EmbedFactory for response embeds
6. Use Validator for input validation
7. Handle errors gracefully with try/except
8. Return public response (not ephemeral)

Output Format:
- Complete command handler function
- Required imports
- Modal/View classes if needed
- Error handling code
```

## Template 4: Code Review Checklist

```
Review Code Changes for Feature Request: [FR-XXX]

Review Checklist:

Code Quality:
- [ ] Follows PEP 8 style guidelines
- [ ] Uses 4-space indentation
- [ ] Imports ordered: stdlib → third-party → local
- [ ] Type hints on all functions
- [ ] Docstrings on public functions/classes

Project Standards:
- [ ] Uses existing Database methods (no raw SQL unless necessary)
- [ ] Uses EmbedFactory for Discord embeds
- [ ] Uses Validator for input validation
- [ ] Follows snake_case/PascalCase naming conventions
- [ ] Commands have appropriate cooldowns

Functionality:
- [ ] Handles edge cases (None values, empty strings, etc.)
- [ ] Proper error handling with try/except
- [ ] Database operations use async/await
- [ ] No blocking operations in async functions
- [ ] Command responses are public (team visibility)

Testing:
- [ ] Manual testing performed
- [ ] Database operations tested
- [ ] Error cases tested
- [ ] Works with existing features

Documentation:
- [ ] PR description includes FR marker (FR-XXX)
- [ ] Code comments explain complex logic
- [ ] No hardcoded values (use config/env)

Output Format:
Provide review feedback as:
- [ ] Checklist items with status
- Specific code suggestions with line numbers
- Potential issues or improvements
- Approval status
```

## Template 5: Pre-Commit Validation

```
Validate Code Changes Before Commit

Validation Checks Required:

1. Code Formatting:
   - Run: black --check .
   - Expected: No formatting changes needed

2. Code Style:
   - Run: flake8 . --exclude=.venv,venv,__pycache__,.git
   - Expected: No style violations

3. Type Checking (optional):
   - Run: mypy . --ignore-missing-imports
   - Expected: No type errors (warnings acceptable)

4. Tests:
   - Run: pytest tests/ (if tests exist)
   - Expected: All tests pass

5. Git State:
   - Check: git status --porcelain
   - Expected: Clean working tree (or staged changes ready to commit)

6. Feature Queue Consistency:
   - Check: automation/feature_queue.json matches automation/feature_queue.md
   - Expected: Consistent feature IDs

7. Database Schema:
   - Verify: No breaking schema changes
   - Expected: New columns nullable or with defaults

8. FR Marker:
   - Check: Commit message includes FR-XXX or feature-request #XXX
   - Expected: Marker present for feature implementation

Output Format:
Report validation results:
- [✓/✗] Check name: Status (PASS/FAIL)
- Issues found: [List any failures]
- Warnings: [List any warnings]
- Overall: PASS/FAIL
```

## Template 6: Release Batch Implementation

```
Implement Release Batch: [Version] [Date]

Features in This Release:
1. FR-XXX: [Title] - [Brief description]
2. FR-YYY: [Title] - [Brief description]
3. FR-ZZZ: [Title] - [Brief description]

Implementation Order:
1. [FR-XXX] - [Rationale: e.g., "High priority, low complexity"]
2. [FR-YYY] - [Rationale]
3. [FR-ZZZ] - [Rationale]

Per-Feature Implementation:
For each feature, use Template 1 (Feature Implementation) and:
- Create PR first on branch feature/XXX-short-slug
- Get code review
- Implement with FR markers in commits
- Merge PR

Validation:
- Run: python scripts/release_helper.py --validate
- All checks must pass before merging PRs

Version Bump:
- Current: [X.Y.Z]
- New: [X.Y+1.Z] (minor bump for feature release)

Changelog:
- Auto-generated by release_helper.py
- Includes all FR-XXX entries

Output Format:
- Implementation status for each feature
- PR links
- Validation results
- Final release tag
```

## Template 7: AI-Assisted Feature Implementation

```
You are helping implement a feature for DisTask, a Discord bot for task management.

Feature Request: FR-[ID]
Title: [Title]
Score: [X.XX]
Description: [Full description]

Context:
- This is a Python Discord bot using discord.py 2.3+
- Database: PostgreSQL with asyncpg (async operations)
- Project structure: bot.py → cogs/ → utils/
- Commands use slash commands with Modals/Views for UI
- All responses are public (not ephemeral)

Task:
Implement this feature following existing patterns. Keep it simple, use existing utilities.

Output:
Provide only the code changes needed. No explanations unless the approach is non-obvious.

Key Files to Modify:
- [List relevant files based on feature type]

Key Utilities to Use:
- Database: utils/db.py
- Embeds: utils/embeds.py
- Validators: utils/validators.py

Patterns to Follow:
- See [similar existing command] in cogs/[file].py
- Use async/await for DB operations
- Add cooldowns for rate limiting
- Validate inputs with Validator class
```

## Usage Instructions

### For Cursor AI
1. Copy the relevant template
2. Fill in bracketed placeholders `[XXX]`
3. Paste into Cursor chat
4. Cursor will generate code following the template

### For Claude (Claude.ai)
1. Use Template 7 for general assistance
2. Use Template 1 for specific feature implementation
3. Use Template 4 for code review

### For GitHub Copilot
1. Use Template 7 as a comment block above code
2. Copilot will use context to suggest implementations

### For Other AI Tools
- All templates use plain English
- No proprietary syntax required
- Structured format works with any LLM
- Adapt placeholders to your tool's format

## Best Practices

1. **Always fill in placeholders**: Replace `[XXX]` with actual values
2. **Include score context**: Helps AI prioritize implementation approach
3. **Reference existing code**: Point to similar features for pattern matching
4. **Specify output format**: Tell AI exactly what you need
5. **Iterate**: Use Template 4 to review and refine

## Examples

See `docs/RELEASE_FLOW.md` for complete workflow examples using these templates.

