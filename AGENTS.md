# Repository Guidelines

## Project Structure & Module Organization
- `bot.py` loads env config, configures logging, and registers all cogs; it's the Discord entrypoint.
- `cogs/` contains slash-command groups (`boards.py`, `tasks.py`, `admin.py`); register new cogs in `bot.py`.
- `utils/` centralizes async helpers (PostgreSQL wrapper, embeds, validators, reminders) for reuse across cogs.
- `web/app.py` hosts the FastAPI landing page and `/status` endpoint used by `distask.service`.
- `data/` and `logs/` are runtime outputs (archives/backups, rotating logs); keep them out of commits.

## Build, Test, and Development Commands
- `python -m venv .venv` followed by `source .venv/bin/activate` prepares an isolated environment.
- `pip install -r requirements.txt` installs Discord bot and web dependencies.
- `python bot.py` starts the bot and ensures the configured PostgreSQL schema + default board columns exist.
- `uvicorn web.app:app --reload` runs the status site locally on `http://127.0.0.1:8000`.
- `tail -f logs/distask.log` streams structured logs for troubleshooting instead of ad-hoc prints.

## Coding Style & Naming Conventions
- Use 4-space indentation, PEP 8 spacing, and keep imports ordered stdlib → third-party → local.
- Annotate new functions with type hints; prefer `async def` for Discord handlers and explicit return types.
- Adopt `snake_case` for modules/functions, `PascalCase` for cogs/classes, and uppercase constants such as `ISO_FORMAT`.
- Slash-command names stay lowercase with hyphens; embed titles use concise sentence case.

## Testing Guidelines
- Automated coverage is pending; add tests under `tests/` and run them via `pytest` (with `pytest-asyncio` for coroutines).
- Point `DATABASE_URL` at a throwaway PostgreSQL database (or schema) when validating database helpers; clean up fixtures after each run.
- Record manual checks (e.g., `/create-board`, `/add-task`) in PRs and reference `logs/distask.log` output.

## Commit & Pull Request Guidelines
- Follow existing history: imperative subjects with optional scopes (`feat:`, `web:`), e.g., `feat: tighten reminders`.
- Keep unrelated changes in separate commits and ship schema updates with the cogs that use them.
- PRs should include a summary, testing notes, linked issue or Discord thread, and visuals for embed/UI tweaks.
- Highlight permission changes or new env vars in the PR title or checklist.

## Security & Configuration Tips
- Copy `.env.example` to `.env`, store secrets outside git, and point systemd units at that file.
- Run services as a non-root user and restrict access to `data/` and `logs/`.
- Update the invite URL in `web/app.py` whenever the `discord_client_id` changes.
- Last updated: $(date) - Verified commit process working correctly.
