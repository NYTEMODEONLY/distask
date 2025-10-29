# VPS Setup Guide for Feature Agent Automation

Complete guide for setting up the DisTask feature agent on your VPS to run 24/7 with PR scanning and automation.

## Prerequisites

- VPS with root/sudo access
- DisTask repository cloned on the VPS
- PostgreSQL database configured and accessible
- GitHub Personal Access Token (PAT) with `repo` scope

## Step 1: Update Codebase

First, ensure your VPS has the latest code:

```bash
cd /root/distask  # or wherever your repo is located
git fetch origin
git checkout main
git pull origin main
```

Verify the new files exist:
```bash
ls -la scripts/setup-git-hooks.sh
ls -la scripts/feature_agent.py
ls -la docs/FEATURE_REQUEST_WORKFLOW.md
```

## Step 2: Update Python Dependencies

Ensure all required packages are installed:

```bash
cd /root/distask
source .venv/bin/activate
pip install -r requirements.txt
```

The feature agent requires `aiohttp` which should already be in `requirements.txt`. Verify:
```bash
pip list | grep aiohttp
```

## Step 3: Configure Environment Variables

Edit your `.env` file (usually at `/root/distask/.env`):

```bash
nano /root/distask/.env
```

Ensure these variables are set (required for PR scanning):

```env
# Database (required)
DATABASE_URL=postgresql://user:password@localhost:5432/distask

# GitHub API (required for PR scanning and feature request export)
GITHUB_TOKEN=ghp_your_personal_access_token_here
REPO_OWNER=NYTEMODEONLY
REPO_NAME=distask

# Optional: Community voting (if configured)
COMMUNITY_GUILD_ID=your_guild_id
COMMUNITY_CHANNEL_ID=your_channel_id
COMMUNITY_FEATURE_WEBHOOK=https://discord.com/api/webhooks/...
```

**GitHub Token Requirements:**
- Create a Personal Access Token (PAT) at: https://github.com/settings/tokens
- Select `repo` scope (for private repos) or `public_repo` (for public repos)
- The token needs permissions to:
  - Read merged pull requests
  - Update `feature_requests.md` file via Contents API

## Step 4: Verify Git Configuration

The agent uses git to scan commits. Ensure git is configured:

```bash
cd /root/distask
git config --global user.name "DisTask Bot"
git config --global user.email "bot@distask.xyz"
```

Verify git can access the repository:
```bash
git log --oneline -5
```

## Step 5: Install/Update Systemd Service Files

Copy the systemd unit files to the system directory:

```bash
cd /root/distask
sudo cp distask-feature-agent.service /etc/systemd/system/
sudo cp distask-feature-agent.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

**Note:** Update the paths in `distask-feature-agent.service` if your repo is not at `/root/distask`:
- `WorkingDirectory`: Change to your actual repo path
- `EnvironmentFile`: Change to your actual `.env` file path
- `ExecStart`: Update Python path if using a different venv location

Example for different locations:
```ini
[Service]
Type=oneshot
WorkingDirectory=/home/username/distask
EnvironmentFile=/home/username/distask/.env
ExecStart=/home/username/distask/.venv/bin/python /home/username/distask/scripts/feature_agent.py
```

## Step 6: Enable and Start the Timer

Enable the timer to run nightly at 03:30 CST (08:30 UTC):

```bash
sudo systemctl enable distask-feature-agent.timer
sudo systemctl start distask-feature-agent.timer
```

Verify the timer is active:
```bash
sudo systemctl status distask-feature-agent.timer
```

Expected output should show:
- `Active: active (waiting)` - Timer is scheduled
- `Trigger: ...` - Next run time

## Step 7: Test the Agent Manually

Before relying on the timer, test the agent manually:

```bash
cd /root/distask
source .venv/bin/activate
python scripts/feature_agent.py
```

**What to check:**
1. Database connection successful
2. Feature requests loaded from database
3. GitHub API connection (if credentials configured)
4. PR scanning runs without errors
5. Commit scanning works
6. Output files generated:
   ```bash
   ls -la automation/feature_queue.json
   ls -la automation/feature_queue.md
   ls -la data/feature_agent_state.json
   ```

**Common Issues:**

- **Database connection failed**: Check `DATABASE_URL` in `.env`, verify PostgreSQL is running
- **GitHub API error**: Verify `GITHUB_TOKEN` is valid and has correct permissions
- **Rate limit hit**: GitHub API has rate limits; agent will skip PR scan if hit (check logs)
- **Git errors**: Ensure git repository is initialized and accessible

## Step 8: Verify Timer Execution

After the timer runs (or trigger manually), check logs:

```bash
# View recent logs
sudo journalctl -u distask-feature-agent.service --since "1 hour ago"

# View all logs
sudo journalctl -u distask-feature-agent.service -n 100

# Follow logs in real-time
sudo journalctl -u distask-feature-agent.service -f
```

**Expected log output:**
```
INFO | Identified X exact duplicates and Y requests with similar candidates.
INFO | Marking feature #123 as completed via PR #456 (abc123def)
INFO | Marking feature #789 as completed via commit def456abc
```

## Step 9: (Optional) Install Git Hooks on VPS

If you want git hooks for validation when making commits directly on the VPS:

```bash
cd /root/distask
./scripts/setup-git-hooks.sh
```

Verify hooks installed:
```bash
ls -la .git/hooks/commit-msg .git/hooks/prepare-commit-msg
```

**Note:** Hooks are optional on VPS since most development happens locally. They're mainly useful if you make commits directly on the server.

## Step 10: Test PR Scanning

To verify PR scanning works:

1. **Check state file** (tracks last processed PR):
   ```bash
   cat data/feature_agent_state.json
   ```
   Should show `last_pr_number` if PR scanning has run.

2. **Trigger manual run**:
   ```bash
   sudo systemctl start distask-feature-agent.service
   ```

3. **Check logs for PR processing**:
   ```bash
   sudo journalctl -u distask-feature-agent.service --since "5 minutes ago" | grep -i "pr\|pull"
   ```

4. **Verify feature requests marked completed**:
   Check the database or `feature_requests.md` on GitHub for status updates.

## Maintenance

### Rotating GitHub Token

When your GitHub PAT expires:

1. Generate new token at https://github.com/settings/tokens
2. Update `.env`:
   ```bash
   nano /root/distask/.env
   # Update GITHUB_TOKEN value
   ```
3. Restart service (no need to restart timer):
   ```bash
   sudo systemctl restart distask-feature-agent.service
   ```

### Manual Trigger

Run the agent on-demand:
```bash
sudo systemctl start distask-feature-agent.service
```

### Check Timer Schedule

View when the timer will run next:
```bash
sudo systemctl list-timers distask-feature-agent.timer
```

### Disable Timer

To temporarily disable automation:
```bash
sudo systemctl stop distask-feature-agent.timer
sudo systemctl disable distask-feature-agent.timer
```

To re-enable:
```bash
sudo systemctl enable distask-feature-agent.timer
sudo systemctl start distask-feature-agent.timer
```

## Troubleshooting

### Agent Not Running

**Check timer status:**
```bash
sudo systemctl status distask-feature-agent.timer
```

**Check service logs:**
```bash
sudo journalctl -u distask-feature-agent.service -n 50
```

**Verify paths in service file:**
```bash
cat /etc/systemd/system/distask-feature-agent.service
```

### PR Scanning Not Working

**Verify GitHub credentials:**
```bash
cd /root/distask
source .venv/bin/activate
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Token:', 'SET' if os.getenv('GITHUB_TOKEN') else 'MISSING'); print('Owner:', os.getenv('REPO_OWNER')); print('Repo:', os.getenv('REPO_NAME'))"
```

**Test GitHub API access:**
```bash
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/repos/NYTEMODEONLY/distask/pulls?state=closed&per_page=1
```

### Database Connection Issues

**Test PostgreSQL connection:**
```bash
PGPASSWORD=yourpass psql -h localhost -U distask -d distask -c "SELECT COUNT(*) FROM feature_requests;"
```

**Verify DATABASE_URL format:**
```bash
grep DATABASE_URL /root/distask/.env
```

### State File Issues

If state file gets corrupted, delete it and let agent recreate:
```bash
rm /root/distask/data/feature_agent_state.json
sudo systemctl start distask-feature-agent.service
```

The agent will start from the beginning (may reprocess old commits/PRs).

## Verification Checklist

- [ ] Codebase updated with latest changes
- [ ] Python dependencies installed (`aiohttp` present)
- [ ] `.env` file configured with all required variables
- [ ] Git configured and repository accessible
- [ ] Systemd service files installed and paths correct
- [ ] Timer enabled and scheduled
- [ ] Manual test run successful
- [ ] Logs show successful execution
- [ ] PR scanning works (if GitHub credentials configured)
- [ ] Feature requests being marked as completed
- [ ] `feature_requests.md` updated on GitHub

## Quick Reference

```bash
# Update code
cd /root/distask && git pull origin main

# Test manually
cd /root/distask && source .venv/bin/activate && python scripts/feature_agent.py

# Check timer status
sudo systemctl status distask-feature-agent.timer

# View logs
sudo journalctl -u distask-feature-agent.service --since "1 day ago"

# Trigger manual run
sudo systemctl start distask-feature-agent.service

# Check next run time
sudo systemctl list-timers distask-feature-agent.timer
```

## Related Documentation

- [Feature Request Workflow](FEATURE_REQUEST_WORKFLOW.md) - Development workflow guide
- [README.md](../README.md) - General project documentation
- [CLAUDE.md](../CLAUDE.md) - Development guidelines

