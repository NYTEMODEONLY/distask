# DisTask Embed Standardization Guide

This document defines the standardized visual style for all Discord embeds in DisTask, ensuring consistency, visual appeal, and information density across all commands.

## Core Principles

1. **Emoji-First Titles**: All embeds should have contextual emojis in titles
2. **Rich Metadata**: Include relevant metadata (creator, timestamps, counts) using emoji indicators
3. **Visual Progress Indicators**: Use Unicode progress bars and color-coding where applicable
4. **Health-Based Colors**: Use semantic colors (green/yellow/orange/red) based on status/health
5. **Information Density**: Pack maximum useful information with clear visual hierarchy

## Standard Format Patterns

### 1. Title Format
```
{emoji} {Title} · #{ID or identifier}
```
Example: `📋 Test board · #9`

### 2. Metadata Line Format
```
👤 {creator} • 📅 {relative_time} • 📢 {channel}
```
Example: `👤 @username • 📅 3 days ago • 📢 #task-updates`

### 3. Status Indicators
- ✅ Completed/Done
- ⏳ Active/In Progress
- 🔴 Overdue/Critical
- ⚡ Upcoming deadlines
- 📝 To Do/Backlog
- ⚙️ In Progress/Working
- ✅ Done/Complete

### 4. Progress Bar Format
```
████████░░░░░░░░ {percentage}% complete
```
Use `_create_progress_bar()` helper function with 16-character default length.

### 5. Color Coding Standards

#### Board Health Colors
- 🟢 **Green** (`rgb(46, 204, 113)`): All tasks on track, no overdue
- 🟡 **Yellow** (`rgb(243, 156, 18)`): 1-5 overdue tasks
- 🟠 **Orange** (`rgb(230, 126, 34)`): 6-10 overdue tasks
- 🔴 **Red** (`rgb(231, 76, 60)`): 10+ overdue (critical)
- 🔵 **Blue** (`rgb(118, 75, 162)`): Default/No tasks yet

#### Task Status Colors
- 🟢 **Green**: Completed, success states
- 🟡 **Yellow**: Warning, pending, needs attention
- 🔴 **Red**: Error, critical, overdue
- 🔵 **Blue**: Info, neutral states

## Embed Type Specifications

### Message Embeds (Success/Error/Info)
**Format:**
- Title: `{emoji} {Title}`
- Description: Clear, concise message
- Color: Based on message type (success = green, error = red, info = default)

**Example:**
```
✅ Task Created
Task #42 has been successfully added to the board.
```

### Board List Embed
**Format:**
- Title: `📋 Boards in {guild_name}`
- Description: Brief instruction or empty state message
- Fields: Each board as a field with emoji indicator, name, ID, and description preview
- Show board count summary

**Pattern:**
```
📋 Boards in My Server

📋 Board Name · #1
Brief description or preview...

📋 Another Board · #2
Another description...
```

### Board Detail Embed (Already Standardized ✅)
Follows the enhanced format with:
- Title with emoji and ID
- Metadata line (creator, creation time, channel)
- Column breakdown with emoji indicators and task counts
- Progress overview with progress bar
- Task distribution with mini progress bars
- Health-based color coding

### Task Detail Embed
**Format:**
- Title: `📋 Task #{id}: {title}`
- Description: Task description or "—"
- Fields:
  - Column with emoji indicator
  - Assignee with user mention or "Unassigned"
  - Due date with relative time if available
  - Status with emoji (✅ Completed / ❌ Not Completed)
  - Board name if applicable
- Color: Based on task status (green if completed, yellow if due soon, red if overdue)

### Search Results Embed
**Format:**
- Title: `🔍 Search Results · '{query}'`
- Description: Result count summary
- Fields: Each task with:
  - Task ID and title with emoji
  - Column name with emoji
  - Board name
  - Due date and assignee
  - Status indicator
- Show "No matches" state with helpful message

### Reminder Digest Embed
**Format:**
- Title: `⏰ Daily Reminders · {guild_name}`
- Description: Summary count (e.g., "5 tasks need attention")
- Fields: Grouped by urgency:
  - 🔴 Overdue (if any)
  - ⚡ Due Today
  - 📅 Due This Week
- Each task shows: ID, title, board, due date, assignee, column
- Color: Orange for reminders

### Feature Request Embeds
**Format:**
- Title: `✨ Feature Request #{id}: {title}`
- Description: Detailed suggestion
- Fields:
  - 👤 Requested By: {user mention}
  - 🏠 Origin Server: {guild name}
  - 📊 Suggested Priority: {priority}
  - 🔗 Public Backlog: {GitHub link}
- Footer: Vote instructions
- Color: Blurple for community features

## Implementation Guidelines

### Helper Functions
Use existing helpers from `utils/embeds.py`:
- `_format_relative_time()`: Converts ISO timestamps to "X days ago"
- `_create_progress_bar()`: Creates Unicode progress bars
- `_get_column_emoji()`: Maps column names to emojis
- `_calculate_board_health_color()`: Determines color based on board health

### Field Naming Convention
Use emoji prefixes for field names:
- `📋 Columns`
- `📊 Progress Overview`
- `📌 Task Distribution`
- `⏰ Reminders`
- `👤 Assignee`
- `📅 Due Date`

### Empty States
Always provide helpful empty state messages:
- "No boards yet. Use `/create-board` to start."
- "No tasks found. Use `/add-task` to create your first task!"
- "All caught up! 🎉"

### Consistency Checks
Before committing, verify:
- ✅ All embeds use emoji in titles
- ✅ Metadata lines follow format (emoji • separator • emoji)
- ✅ Progress bars use consistent length (16 for main, 8 for mini)
- ✅ Colors match semantic meaning
- ✅ Empty states are helpful and actionable
- ✅ Footer includes "distask.xyz" and timestamp

## Migration Checklist

When updating existing embeds:
1. Add emoji to title
2. Add metadata line if applicable
3. Replace plain text with emoji indicators
4. Add progress bars where numeric progress is shown
5. Apply appropriate color coding
6. Ensure empty states are friendly
7. Test visual appearance in Discord
8. Verify information density is optimal

## Examples Reference

See `utils/embeds.py` → `board_detail()` method for the gold standard implementation that all other embeds should match in visual quality and information density.

