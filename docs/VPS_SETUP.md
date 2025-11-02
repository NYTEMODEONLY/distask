# Complete VPS Setup Guide for DisTask

Complete guide for setting up and managing DisTask on your VPS, including feature agent automation, git sync, service management, and the PR-first workflow.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Feature Agent Automation](#feature-agent-automation)
4. [Git Sync & Service Management](#git-sync--service-management)
5. [PR-First Workflow Setup](#pr-first-workflow-setup)
6. [Troubleshooting](#troubleshooting)
7. [Quick Reference](#quick-reference)

---

## Prerequisites

- VPS with root/sudo access
- DisTask repository cloned on the VPS
- PostgreSQL database configured and accessible
- GitHub Personal Access Token (PAT) with `repo` scope

---

## Initial Setup

### Step 1: Update Codebase

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

### Step 2: Update Python Dependencies

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

### Step 3: Configure Environment Variables

Edit your `.env` file (usually at `/root/distask/.env`):

```bash
nano /root/distask/.env
```

Ensure these variables are set:

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

# Optional: Git sync (for automated deployments)
GITHUB_WEBHOOK_SECRET=your_random_secret_here
GIT_SYNC_BRANCH=main
GIT_SYNC_ENABLED=true
```

**GitHub Token Requirements:**
- Create a Personal Access Token (PAT) at: https://github.com/settings/tokens
- Select `repo` scope (for private repos) or `public_repo` (for public repos)
- The token needs permissions to:
  - Read merged pull requests
  - Update `feature_requests.md` file via Contents API

**Generate webhook secret:**
```bash
openssl rand -hex 16
```

### Step 4: Verify Git Configuration

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

---

## Feature Agent Automation

### Step 5: Install/Update Systemd Service Files

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

### Step 6: Enable and Start the Timer

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

### Step 7: Test the Agent Manually

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

### Step 8: Verify Timer Execution

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

---

## Git Sync & Service Management

### Automated GitHub Sync via Webhooks

DisTask can automatically sync code changes from GitHub and restart services instantly when you push commits.

#### How It Works

- **Primary Method**: GitHub webhook sends instant push notifications to your VPS
- **Fallback Method**: Systemd timer polls every 2 minutes (only runs if webhook hasn't fired recently)
- **Auto-restart**: Services restart automatically after successful git pull

#### Set Up GitHub Webhook

1. Go to your GitHub repository: `https://github.com/NYTEMODEONLY/distask/settings/hooks`
2. Click **"Add webhook"**
3. Configure:
   - **Payload URL**: `https://distask.xyz/webhooks/github` (or your domain)
   - **Content type**: `application/json`
   - **Secret**: Paste the secret you generated (same as `GITHUB_WEBHOOK_SECRET`)
   - **Events**: Select **"Just the push event"**
   - **Active**: Checked
   - **SSL verification**: Enabled
4. Click **"Add webhook"**

#### Install Fallback Timer (Optional)

Copy the service and timer files:

```bash
cd /root/distask
sudo cp distask-git-sync.service /etc/systemd/system/
sudo cp distask-git-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now distask-git-sync.timer
```

### Manual Git Sync Process

#### Step-by-Step Sync

1. **Check Current Status**
   ```bash
   cd /root/distask
   git status
   git fetch origin
   ```

2. **Handle Local Changes (if any)**
   ```bash
   git add .
   git commit -m "feat: describe the changes made on VPS"
   ```

3. **Check for Remote Updates**
   ```bash
   git log --oneline HEAD..origin/main
   ```

4. **Pull Updates**
   ```bash
   git pull origin main --no-rebase
   ```

5. **Restart Services (if updates were pulled)**
   ```bash
   sudo systemctl restart distask.service distask-web.service
   ```

6. **Verify Services**
   ```bash
   sudo systemctl status distask.service distask-web.service distask-feature-agent.timer
   ```

### Service Management Commands

#### Check Service Status
```bash
sudo systemctl status distask.service distask-feature-agent.timer distask-web.service
```

#### Restart Services
```bash
# Restart bot only
sudo systemctl restart distask.service

# Restart web interface only
sudo systemctl restart distask-web.service

# Restart all services
sudo systemctl restart distask.service distask-web.service
```

#### Enable/Disable Services
```bash
# Enable services to start on boot
sudo systemctl enable distask.service distask-feature-agent.timer distask-web.service

# Disable services
sudo systemctl disable distask.service distask-feature-agent.timer distask-web.service
```

---

## PR-First Workflow Setup

### What's New in PR-First Workflow

1. **Git Hooks** - Auto-validate and inject FR markers in commit messages
2. **PR Scanning** - Automation now scans merged GitHub PRs for FR markers
3. **Admin Command** - `/mark-feature-completed` for manual completion
4. **Workflow Documentation** - Complete PR-first workflow guide

### Install Git Hooks on VPS (Optional)

If you make commits directly on the VPS, install the hooks:

```bash
cd /root/distask
./scripts/setup-git-hooks.sh
```

**What this does:**
- Installs `commit-msg` hook: Validates FR markers match branch names
- Installs `prepare-commit-msg` hook: Auto-injects FR markers from branch names

**Note:** Hooks are optional on VPS. Most development happens locally where hooks are more useful.

**Verify installation:**
```bash
ls -la .git/hooks/commit-msg .git/hooks/prepare-commit-msg
```

Both should be executable (`-rwxr-xr-x`).

### Restart Feature Agent

After updating code and configuring GitHub credentials:

```bash
sudo systemctl restart distask-feature-agent.service
# Or if timer isn't running yet, enable it
sudo systemctl enable --now distask-feature-agent.timer
```

### Test PR Scanning

Manually trigger a run to test PR scanning:

```bash
sudo systemctl start distask-feature-agent.service
```

Check logs for PR scanning:
```bash
sudo journalctl -u distask-feature-agent.service --since "5 minutes ago" | grep -i "pr\|completed"
```

**Expected output:**
```
INFO | Marking feature #123 as completed via PR #456 (abc123def)
INFO | Marking feature #789 as completed via commit def456abc
```

Check the state file to see if PR scanning is tracking:
```bash
cat /root/distask/data/feature_agent_state.json
```

Should show `last_pr_number` if PR scanning has run.

---

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

### Git Sync Issues

**If Git Pull Fails:**
```bash
# Check for merge conflicts
git status

# If conflicts exist, resolve them manually, then:
git add .
git commit -m "resolve: merge conflicts"
```

**If Working Tree is Dirty:**
```bash
# Stash changes temporarily
git stash

# Pull updates
git pull origin main --no-rebase

# Apply stashed changes
git stash pop

# Resolve any conflicts and commit
```

**If Services Won't Start:**
```bash
# Check service logs
journalctl -u distask.service -f
journalctl -u distask-web.service -f

# Check for Python errors
cd /root/distask
python bot.py  # Test bot manually
```

### Webhook Not Triggering

**Check webhook endpoint is accessible:**
```bash
curl -X POST https://distask.xyz/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{"ref":"refs/heads/main"}'
```

**Check webhook secret matches:**
```bash
grep GITHUB_WEBHOOK_SECRET /root/distask/.env
```

**Check webhook delivery logs in GitHub:**
1. Go to repository Settings → Webhooks
2. Click on your webhook
3. View "Recent Deliveries" tab
4. Check if requests are being sent and what responses they receive

### State File Issues

If state file gets corrupted, delete it and let agent recreate:
```bash
rm /root/distask/data/feature_agent_state.json
sudo systemctl start distask-feature-agent.service
```

The agent will start from the beginning (may reprocess old commits/PRs).

---

## Quick Reference

### Complete Sync Process
```bash
cd /root/distask
git status
git fetch origin
git add . && git commit -m "feat: VPS changes" 2>/dev/null || true
git push origin main 2>/dev/null || git pull origin main --no-rebase
sudo systemctl restart distask.service distask-web.service
sudo systemctl status distask.service distask-web.service
```

### Feature Agent Commands
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

### Service Management
```bash
# Restart all services
sudo systemctl restart distask.service distask-web.service

# Check status
sudo systemctl status distask.service distask-web.service distask-feature-agent.timer

# View logs
sudo journalctl -u distask.service -f
sudo journalctl -u distask-web.service -f
```

### Maintenance

**Rotating GitHub Token:**
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

**Manual Trigger:**
```bash
sudo systemctl start distask-feature-agent.service
```

**Disable Timer:**
```bash
sudo systemctl stop distask-feature-agent.timer
sudo systemctl disable distask-feature-agent.timer
```

---

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
- [ ] Git sync working (webhook or timer)
- [ ] Services restarting automatically after git pull

---

## Related Documentation

- [Feature Request Workflow](FEATURE_REQUEST_WORKFLOW.md) - Development workflow guide
- [Release Flow](RELEASE_FLOW.md) - Rapid release flow guide
- [README.md](../README.md) - General project documentation
- [CLAUDE.md](../CLAUDE.md) - Development guidelines
