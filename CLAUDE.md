# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

DisTask is a production Discord bot providing kanban-style task boards via slash commands. It uses async PostgreSQL, daily reminder digests, a feature request system with community voting, and automated backlog management.

## Development Commands

### Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Bot
```bash
python bot.py  # Starts bot and ensures DB schema exists
```

### Running the Web Landing Page
```bash
uvicorn web.app:app --reload  # Dev server on http://127.0.0.1:8000
```

### Running the Feature Agent
```bash
python scripts/feature_agent.py  # Dedupe, score, sync git commits
```

### Logs
```bash
tail -f logs/distask.log  # Stream structured logs
```

## Architecture

### Entry Point & Configuration
- `bot.py` is the main entry point. It loads `.env` config, sets up logging (console + rotating file), initializes the `Database` wrapper, registers all cogs, and starts the reminder scheduler.
- Environment variables are case-insensitive (checks both uppercase and lowercase). Critical vars: `token`, `database_url`, `github_token`, `repo_owner`, `repo_name`, `community_guild_id`, `community_channel_id`, `community_feature_webhook`.

### Database Layer (`utils/db.py`)
- `Database` class wraps `asyncpg.Pool` and provides async helpers for all CRUD operations.
- Schema has cascading foreign keys: `guilds` → `boards` → `columns`/`tasks` and `guilds` → `feature_requests`.
- Tables: `guilds`, `boards`, `columns`, `tasks`, `feature_requests`.
- Methods follow pattern: `create_*`, `get_*`, `update_*`, `delete_*`, `list_*`.
- `ensure_guild()` creates a guild row if missing; called on bot startup and guild join.
- Default columns (To Do, In Progress, Done) are created with each new board.

### Cogs (Slash Command Groups)
Cogs are loaded in `bot.py` via `_build_*_cog()` methods:

- **`cogs/boards.py`** (`BoardsCog`): Board lifecycle commands
  - `/create-board`, `/list-boards`, `/view-board`, `/delete-board`, `/board-stats`
  - Enforces `Manage Guild` permission for create/delete

- **`cogs/tasks.py`** (`TasksCog`): Task CRUD and management
  - `/add-task`, `/list-tasks`, `/move-task`, `/assign-task`, `/edit-task`, `/complete-task`, `/delete-task`, `/search-task`
  - Supports due dates, assignees, full-text search, filtering by column/assignee/completion

- **`cogs/admin.py`** (`AdminCog`): Guild and board administration
  - `/add-column`, `/remove-column`, `/toggle-notifications`, `/set-reminder`, `/distask-help`
  - Enforces `Manage Channels` for column ops, `Manage Guild` for notification/reminder config

- **`cogs/features.py`** (`FeaturesCog`): Feature request system
  - `/request-feature` modal captures title, suggestion, priority
  - Posts to community channel via webhook with 👍/👎/🔁 reactions
  - On reaction events, updates `community_upvotes`, `community_downvotes`, `community_duplicate_signals` in DB
  - Triggers GitHub export of `feature_requests.md` when credentials are configured

### Utilities (`utils/`)
- **`db.py`**: PostgreSQL wrapper, schema management, all database operations
- **`embeds.py`**: `EmbedFactory` builds consistent Discord embeds (message, board, task, stats)
- **`validators.py`**: Input validation (names, due dates, reminder times)
- **`reminders.py`**: `ReminderScheduler` background task runs every ~60s, checks if guilds have passed their reminder time, sends daily digest (overdue + next 24h tasks) to board channels
- **`github_utils.py`**: `export_to_github()` updates `feature_requests.md` via GitHub Contents API

### Feature Automation (`scripts/feature_agent.py`)
Four-pass pipeline for managing the feature backlog:

1. **Ingest**: Loads feature requests from PostgreSQL
2. **Dedupe**: Fuzzy-matches titles/suggestions using `SequenceMatcher`
   - ≥90% similarity → auto-marks as duplicate
   - 78-90% → logs as "similar" for manual review
3. **Score**: Calculates `priority + ease + vote_bonus - duplicate_penalty`
   - vote_bonus: `log1p(👍 - 👎) * 2`
   - duplicate_penalty: `log1p(🔁) * 1.5`
   - Defaults to 5 when unset
4. **Sync Completion**: Scans git commits for `FR-<id>` or `feature-request #<id>` tokens, marks matching requests as completed with commit metadata

Outputs:
- `automation/feature_queue.json`: Full scored + sorted queue
- `automation/feature_queue.md`: Human-readable prioritized backlog
- Publishes `feature_requests.md` to GitHub via Contents API

Maintains cursor in `data/feature_agent_state.json` to track last-scanned commit.

### Web Landing Page (`web/app.py`)
FastAPI app serving:
- `/` - Hero landing page with particle background, CTAs, live status indicator
- `/status` - JSON endpoint polling `systemctl show distask.service` to reflect service state (up/down/transitioning/unknown)

Deployed via `distask-web.service`, proxied by Nginx with TLS.

## Coding Conventions

- **Style**: PEP 8, 4-space indentation, imports ordered (stdlib → third-party → local)
- **Naming**: `snake_case` for functions/modules, `PascalCase` for classes/cogs, `UPPERCASE` for constants
- **Type hints**: Annotate all new functions; use `async def` for Discord handlers
- **Slash commands**: Lowercase with hyphens (`/create-board`)
- **Embeds**: Concise sentence-case titles, use `EmbedFactory` methods

## Rate Limiting

- Default cooldown: 3 seconds per user
- Heavy ops (`/create-board`, `/add-task`, `/search-task`, `/edit-task`): 10 seconds
- Cooldowns defined via `@app_commands.checks.cooldown()` decorators in cogs

## Commit Workflow for Feature Requests

When implementing a feature request:

1. Branch naming: `feature/<id>-short-slug` (e.g., `feature/123-modal-export`)
2. Include `FR-123` or `feature-request #123` in at least one commit message
3. Automation scans commits and marks the request `completed` with commit SHA and timestamp
4. Without the marker, the request stays `pending` and manual edits to `feature_requests.md` will be overwritten

## Deployment

### Bot Service
```bash
sudo cp distask.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now distask.service
journalctl -u distask -f
```

### Feature Agent Timer (nightly at 03:30 CST / 08:30 UTC)
```bash
sudo cp distask-feature-agent.service distask-feature-agent.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now distask-feature-agent.timer
sudo systemctl start distask-feature-agent.service  # Manual trigger
systemctl status distask-feature-agent.timer
journalctl -u distask-feature-agent.service --since "1 day ago"
```

### Web Service
```bash
sudo cp distask-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now distask-web.service
```

Configure Nginx to proxy `distask.xyz` → `http://127.0.0.1:8000`, add TLS with Certbot.

## GitHub Authentication

Store PAT in `.env` under `github_token` (requires `repo` scope).

Persist for git pushes (survives restarts):
```bash
git config --global credential.helper store
git credential approve <<'EOF'
protocol=https
host=github.com
username=YOUR_GITHUB_USERNAME
password=YOUR_PAT
EOF
chmod 600 ~/.git-credentials
```

Rotate PAT: update `.env` + re-run credential helper, then restart services.

## PostgreSQL Connection

- Connection string format: `postgresql://user:password@host:port/database`
- Default: `postgresql://distask:distaskpass@localhost:5432/distask`
- PostgreSQL enforces password auth; use `PGPASSWORD=yourpass psql -h localhost -U youruser -d yourdb -c "select now();"` for manual checks

## Community Voting

Configure in `.env`:
- `community_guild_id`: Discord guild ID for community server
- `community_channel_id`: Channel for feature announcements
- `community_feature_webhook`: Webhook URL for posting announcements

Announcements get 👍/👎/🔁 reactions. Reaction events update DB counters used in scoring.

## Testing

- No automated suite yet; add tests under `tests/` using `pytest` + `pytest-asyncio`
- Point `DATABASE_URL` at throwaway DB for testing DB helpers
- Document manual testing (slash command flows, logs) in PRs
