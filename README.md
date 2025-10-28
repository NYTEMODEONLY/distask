# DisTask – Discord Task Boards

DisTask is a production-ready Discord bot that provides lightweight kanban boards and task management powered by slash commands. It ships with an async PostgreSQL backend, reminder digests, rich embeds, and deployment tooling so you can keep projects moving without leaving Discord.

## Features

- ✅ **Slash commands for boards and tasks** with cooldowns (3s default, 10s for heavy ops) to prevent spam
- ✅ **Async PostgreSQL** backend with guild/board/column/task tables and cascade cleanup
- ✅ **Custom columns** beyond the To Do / In Progress / Done defaults
- ✅ **Task lifecycle tools**: assign, move, edit, complete, delete, and full-text search
- ✅ **Due dates + reminders**: background worker posts daily digests to board channels
- ✅ **Feature requests**: `/request-feature` modal logs ideas and syncs them to GitHub
- ✅ **Community voting**: submissions auto-post to the DisTask community server with 👍 / 👎 / 🔁 reactions to drive prioritisation
- ✅ **Automation agent**: deduplicates, scores, and syncs shipping status from git history
- ✅ **Permission-aware administration** (`Manage Guild`/`Manage Channels` checks where appropriate)
- ✅ **Structured embeds & logging** (console + rotating file target)
- ✅ **Channel-visible responses** so the entire team sees board & task activity (no ephemeral hides)
- ✅ **Systemd unit** for 24/7 hosting on Linux

## Project Layout

```
distask/
├── bot.py               # Entry point (loads env, logging, cogs)
├── requirements.txt     # Python dependencies
├── .env.example         # Sample environment configuration
├── distask.service      # Systemd service template
├── cogs/                # Slash command groups
│   ├── boards.py        # /create-board, /list-boards, etc.
│   ├── tasks.py         # /add-task, /move-task, /search-task, ...
│   ├── admin.py         # /add-column, /toggle-notifications, ...
│   └── features.py      # /request-feature modal + GitHub export trigger
├── utils/               # Shared helpers
│   ├── db.py            # Async PostgreSQL wrapper + schema management
│   ├── embeds.py        # Embed builders
│   ├── validators.py    # Input validation + parsing
│   ├── reminders.py     # Background reminder scheduler
│   └── github_utils.py  # GitHub Markdown export helper
├── LICENSE              # MIT
├── scripts/             # Operational tooling & automation
│   ├── feature_agent.py # Duplicate detection, scoring, git integration
│   └── migrate_sqlite_to_postgres.py  # One-time migration helper
└── README.md            # You are here
```

## Getting Started

1. **Create a virtual environment** (Python 3.11+ recommended):

   ```bash
   cd distask
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:

   - Copy `.env.example` → `.env`.
   - Fill in `token` with your bot token (keep it private!).
   - Add `discord_client_id` (used for invite URLs) and, if you plan to run OAuth flows, `discord_client_secret`. These are optional but keep the landing-page CTA up to date.
   - Configure `github_token`, `repo_owner`, and `repo_name` so feature requests can be published to your GitHub repo. The token needs `repo` scope.
   - Set `community_guild_id`, `community_channel_id`, and `community_feature_webhook` if you want requests mirrored into the public DisTask community (or your own community server) for voting.
   - Adjust `database_url`, `log_file`, or `reminder_time` if desired. The URL should follow the PostgreSQL DSN format (`postgresql://user:password@host:port/database`).

3. **Run the bot locally**:

   ```bash
   python bot.py
   ```

   The first startup will ensure the configured PostgreSQL database has the necessary tables and will create `logs/distask.log` automatically.

4. **Invite the bot** with the `applications.commands` scope (and `bot` scope if you want reminder messages). Make sure the bot has access to the channels you plan to use for boards.

## Commands Overview

| Group  | Command | Description | Permissions |
|--------|---------|-------------|-------------|
| Boards | `/create-board` | Create a board bound to a text channel | Manage Guild |
|        | `/list-boards` | List all boards in the guild | — |
|        | `/view-board` | View board config + stats | — |
|        | `/delete-board` | Remove a board and its data | Manage Guild |
|        | `/board-stats` | Quick stats for a board | — |
| Tasks  | `/add-task` | Create a task with optional due date + assignee | — |
|        | `/list-tasks` | Filter tasks by column/assignee/completion | — |
|        | `/move-task` | Move a task between columns | — |
|        | `/assign-task` | Assign to a member | — |
|        | `/edit-task` | Update title/description/due/column/assignee | — |
|        | `/complete-task` | Mark complete/incomplete | — |
|        | `/delete-task` | Remove a task | — |
|        | `/search-task` | Full-text search across tasks | — |
| Admin  | `/add-column` | Append a column (board must exist) | Manage Channels |
|        | `/remove-column` | Remove an empty column | Manage Channels |
|        | `/toggle-notifications` | Enable/disable reminder digests | Manage Guild |
|        | `/set-reminder` | Set daily reminder time (HH:MM UTC) | Manage Guild |
|        | `/distask-help` | Summary of commands | — |
| Feedback | `/request-feature` | Submit feature ideas via modal; syncs to GitHub | — |

Additional behavior:

- Default rate limit is 1 call / 3s per user. Heavy commands (`/create-board`, `/add-task`, `/search-task`, `/edit-task`) use 10s cooldowns.
- All command responses are posted to the channel so admins and teammates can review changes later.
- Reminder digests run roughly once per minute and deliver a daily summary (overdue + next 24h) to each board channel when the guild's scheduled time passes. Use `/toggle-notifications` + `/set-reminder` to control behavior per guild.
- Feature requests persist to the `feature_requests` table. When GitHub credentials are configured, the bot publishes the backlog to `feature_requests.md` via the GitHub Contents API.
- Community announcements add 👍 / 👎 / 🔁 reactions automatically; these votes feed nightly scoring (support adds weight, duplicate signals subtract) so the most demanded ideas float to the top.

## Feature Automation Pipeline

`scripts/feature_agent.py` keeps the public backlog clean and in sync with production deployments. It runs four passes:

1. **Ingest & normalise** – fetches the latest rows from PostgreSQL (or falls back to `feature_requests.md`) so the workload survives restarts.
2. **Detect duplicates** – uses fuzzy matching on title + suggestion, automatically tagging high-confidence duplicates and logging near-matches for triage.
3. **Score & queue** – combines `priority + ease + vote_bonus - duplicate_penalty` (defaults to `5` when unset; vote bonus is derived from 👍/👎 reaction counts and duplicate penalty from 🔁 reactions), storing results on the request and emitting a prioritised queue at `automation/feature_queue.{json,md}`.
4. **Sync completion** – scans new git commits for tokens such as `FR-123` or `feature-request #123`, then marks matching feature requests as completed (with commit metadata and timestamps).

Run it manually or from CI/cron:

```bash
source .venv/bin/activate
python scripts/feature_agent.py
```

The agent maintains its own cursor (`data/feature_agent_state.json`, ignored by git) and reuses the same GitHub credentials as the bot to publish the refreshed `feature_requests.md`.

### Implementation Workflow

- Start implementation work on a branch named `feature/<id>-short-slug` (e.g. `feature/123-modal-export`).
- Include `FR-123` (or `feature-request #123`) in at least one commit message; the automation uses these markers to move the request to `completed`.
- Post-deploy, re-run the agent to confirm the request is marked as live and the queue reflects the next priority item.
- The VPS now runs the automation nightly at 03:30 CST via `distask-feature-agent.timer`. Manually trigger a run any time with `sudo systemctl start distask-feature-agent.service`.

### Installing the Timer on a Fresh Host

1. Copy the provided systemd unit files from the repo root:

   ```bash
   sudo cp distask-feature-agent.service /etc/systemd/system/
   sudo cp distask-feature-agent.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

2. Enable the nightly schedule (03:30 CST / 08:30 UTC) and start it immediately:

   ```bash
   sudo systemctl enable --now distask-feature-agent.timer
   ```

3. Kick off an on-demand run whenever needed:

   ```bash
   sudo systemctl start distask-feature-agent.service
   ```

4. Check status or the last execution time:

   ```bash
   systemctl status distask-feature-agent.timer
   journalctl -u distask-feature-agent.service --since "1 day ago"
   ```

Because the agent is idempotent, multiple runs per day simply refresh duplicate detection, recalculate scores, and sync completed requests without disturbing existing data.

## Community Voting Setup

If you want feature requests to appear in a community hub with voting:

1. Create (or reuse) a guild/channel and generate a webhook for the channel.
2. Populate the following `.env` keys:

   ```env
   community_guild_id=YOUR_COMMUNITY_GUILD_ID
   community_channel_id=YOUR_FEATURE_CHANNEL_ID
   community_feature_webhook=https://discord.com/api/webhooks/...
   ```

3. Restart the bot (and feature-agent timer). Every `/request-feature` submission will now:
   - Post a rich embed to the community channel.
   - Automatically add 👍 / 👎 / 🔁 reactions.
   - Track vote counts in the database so nightly automation can use them when scoring.

Votes translate to a score bonus (`log1p(👍 - 👎) * 2`) and duplicate penalty (`log1p(🔁) * 1.5`). A surge of community support will push an item up the queue, while community-marked duplicates drop to the consolidation list.

### GitHub Authentication & PAT Rotation

Both the bot and the automation rely on a Personal Access Token (PAT) with `repo` scope. To keep pushes and Markdown exports working after a reboot:

1. Store the token in `.env` under `github_token` (and ensure `distask.service` / `distask-feature-agent.service` load that file).
2. Configure git to persist the PAT locally so manual `git push` calls and automation commits survive restarts:

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

When the PAT expires (e.g., 30-day tokens), repeat both steps with the new value. Restart the bot and feature-agent timer to pick up the refreshed `.env`.

## Systemd Deployment

A starter service file (`distask.service`) is provided. To use it:

1. Copy the project to the target host (e.g., `/opt/distask`).
2. Update the service file paths (`WorkingDirectory`, `EnvironmentFile`, `ExecStart`) to match your setup; keep the `.env` file outside version control so your Discord token stays private.
3. Install and enable:

   ```bash
   sudo cp distask.service /etc/systemd/system/distask.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now distask.service
   ```

4. View logs with `journalctl -u distask -f` or tail `logs/distask.log`.

## Public Landing Page (distask.xyz)

An always-on landing page lives in `web/app.py`. It renders the non-scrolling hero layout, particle background, CTAs, and a live status indicator that polls `/status` every 10 seconds to mirror the `distask.service` state (`green` = up, `yellow` = transitioning, `red` = down, `gray` = unknown).

Deployment outline:

1. Install the repo requirements so `fastapi` + `uvicorn` are available.
2. Copy `distask-web.service` into `/etc/systemd/system/`, adjust paths if necessary, then `systemctl enable --now distask-web.service`.
3. Install Nginx and create `/etc/nginx/sites-available/distask` that proxies `distask.xyz` → `http://127.0.0.1:8000`, enable it (symlink to `sites-enabled`), remove the default server, and `nginx -t && systemctl reload nginx`.
4. Point the domain’s `A` (and optional `www`) DNS records at this VPS. Add TLS via your preferred method (e.g., `certbot --nginx`) once DNS resolves.
5. Update the “Deploy to Discord” CTA inside `web/app.py` with your live bot client ID before marketing the invite link.

The API simply shells out to `systemctl show distask.service`, so the status badge always reflects the production bot’s service health.

## Development Notes

- **Database**: PostgreSQL is used for multi-guild scalability. Configure the connection string via `DATABASE_URL`. Table relationships enforce cascading deletes so columns/tasks clean up with their parent board.
- **Logging**: Both stdout and the configured file receive structured logs. Adjust `setup_logging` in `bot.py` if you prefer RotatingFileHandler, etc.
- **Credentials**: If you push over HTTPS, configure a credential helper (e.g. `git config credential.helper store`) so Personal Access Tokens persist between sessions and non-interactive pushes continue to work.
- **Extensibility**: New slash commands can be added in the existing cogs or by creating additional cogs and registering them in `bot.py`.
- **Token Handling**: Never commit `.env` with your production token. Keep secrets in deployment-specific files or environment variables.

## License

Released under the [MIT License](LICENSE).

<sub>This project is [built by nytemode](https://nytemode.com).</sub>
