# DisTask – Discord Task Boards

DisTask is a production-ready Discord bot that provides lightweight kanban boards and task management powered by slash commands. It ships with async SQLite storage, reminder digests, rich embeds, and deployment tooling so you can keep projects moving without leaving Discord.

## Features

- ✅ **Slash commands for boards and tasks** with cooldowns (3s default, 10s for heavy ops) to prevent spam
- ✅ **Async SQLite** backend with guild/board/column/task tables and cascade cleanup
- ✅ **Custom columns** beyond the To Do / In Progress / Done defaults
- ✅ **Task lifecycle tools**: assign, move, edit, complete, delete, and full-text search
- ✅ **Due dates + reminders**: background worker posts daily digests to board channels
- ✅ **Permission-aware administration** (`Manage Guild`/`Manage Channels` checks where appropriate)
- ✅ **Structured embeds & logging** (console + rotating file target)
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
│   └── admin.py         # /add-column, /toggle-notifications, ...
├── utils/               # Shared helpers
│   ├── db.py            # Async SQLite wrapper + schema
│   ├── embeds.py        # Embed builders
│   ├── validators.py    # Input validation + parsing
│   └── reminders.py     # Background reminder scheduler
├── LICENSE              # MIT
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
   - Adjust `database_path`, `log_file`, or `reminder_time` if desired.

3. **Run the bot locally**:

   ```bash
   python bot.py
   ```

   The first startup will create `data/distask.db` and `logs/distask.log` automatically.

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

Additional behavior:

- Default rate limit is 1 call / 3s per user. Heavy commands (`/create-board`, `/add-task`, `/search-task`, `/edit-task`) use 10s cooldowns.
- Reminder digests run roughly once per minute and deliver a daily summary (overdue + next 24h) to each board channel when the guild's scheduled time passes. Use `/toggle-notifications` + `/set-reminder` to control behavior per guild.

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

- **Database**: SQLite is stored wherever `database_path` points. Each guild can host multiple boards; deleting a board cascades to columns/tasks.
- **Logging**: Both stdout and the configured file receive structured logs. Adjust `setup_logging` in `bot.py` if you prefer RotatingFileHandler, etc.
- **Extensibility**: New slash commands can be added in the existing cogs or by creating additional cogs and registering them in `bot.py`.
- **Token Handling**: Never commit `.env` with your production token. Keep secrets in deployment-specific files or environment variables.

## License

Released under the [MIT License](LICENSE).

<sub>This project is [built by nytemode](https://nytemode.com).</sub>
