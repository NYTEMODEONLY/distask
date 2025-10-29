# Setup Guide for New Feature Request Workflow Features

Quick setup guide for the newly added PR-first workflow features on your VPS.

## What's New

1. **Git Hooks** - Auto-validate and inject FR markers in commit messages
2. **PR Scanning** - Automation now scans merged GitHub PRs for FR markers
3. **Admin Command** - `/mark-feature-completed` for manual completion
4. **Workflow Documentation** - Complete PR-first workflow guide

## Step 1: Update Codebase

Pull the latest changes:

```bash
cd /root/distask  # or your repo path
git pull origin main
```

Verify new files exist:
```bash
ls -la scripts/setup-git-hooks.sh
ls -la git-hooks/commit-msg
ls -la docs/FEATURE_REQUEST_WORKFLOW.md
```

## Step 2: Configure GitHub API Credentials (Required for PR Scanning)

The enhanced automation now scans GitHub PRs. Ensure your `.env` has:

```bash
nano /root/distask/.env
```

Add/verify these variables:
```env
GITHUB_TOKEN=ghp_your_personal_access_token_here
REPO_OWNER=NYTEMODEONLY
REPO_NAME=distask
```

**Creating GitHub Token:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select `repo` scope (for private repos) or `public_repo` (for public repos)
4. Copy token and add to `.env` as `GITHUB_TOKEN`

**Why needed:** PR scanning uses GitHub API to check merged PRs for FR markers, providing redundancy if commit markers are missed.

## Step 3: (Optional) Install Git Hooks on VPS

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

## Step 4: Restart Feature Agent (Load New Code)

After updating code and configuring GitHub credentials:

```bash
# Restart the service to load new code
sudo systemctl restart distask-feature-agent.service

# Or if timer isn't running yet, enable it
sudo systemctl enable --now distask-feature-agent.timer
```

## Step 5: Test PR Scanning

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

## Step 6: Verify PR Scanning Works

Check the state file to see if PR scanning is tracking:

```bash
cat /root/distask/data/feature_agent_state.json
```

Should show:
```json
{
  "last_commit": "abc123...",
  "last_pr_number": 123,
  "last_run_at": "2025-01-XX...",
  ...
}
```

If `last_pr_number` is present, PR scanning is working.

## Step 7: Test Admin Command (Discord Bot)

The new `/mark-feature-completed` command is available in Discord:

1. **Permissions:** Requires `Manage Guild` permission
2. **Usage:** `/mark-feature-completed feature_id:123 [commit_hash:abc123]`
3. **Purpose:** Manually mark features as completed if automation misses them

**Test it:**
- Go to your Discord server
- Run `/mark-feature-completed feature_id:1` (use a test feature ID)
- Should mark the feature as completed immediately

**Note:** The bot service doesn't need restart - new commands load automatically on bot restart (or use hot-reload if configured).

## Step 8: Review Workflow Documentation

Read the complete workflow guide:

```bash
cat /root/distask/docs/FEATURE_REQUEST_WORKFLOW.md
```

Or view on GitHub: `docs/FEATURE_REQUEST_WORKFLOW.md`

## What Changed in Automation

### Before
- Only scanned git commits for FR markers
- Manual markdown edits could be overwritten
- Easy to miss completion if commit message forgot FR marker

### After
- **Scans both commits AND merged PRs** for FR markers
- PR title/description provides redundancy
- Incremental processing (tracks last PR number)
- Better tracking and completion detection

## Usage Going Forward

### For Feature Requests

**When implementing a feature:**

1. **Create PR first** (before coding):
   ```bash
   git checkout -b feature/123-short-description
   git commit --allow-empty -m "WIP: Feature request #123"
   git push origin feature/123-short-description
   # Then create PR on GitHub
   ```

2. **PR Title must include FR marker:**
   ```
   feat: Add modal export FR-123
   ```

3. **Get code review**, then implement

4. **Commit with FR markers** (hooks auto-add if branch matches):
   ```bash
   git commit -m "feat: implement export FR-123"
   ```

5. **Merge PR** - Automation detects completion via:
   - PR title: `FR-123`
   - PR description: `feature-request #123`
   - Commit messages: `FR-123`

### Verification

After merging, check completion:

```bash
# View agent logs
sudo journalctl -u distask-feature-agent.service --since "1 hour ago"

# Check feature_requests.md on GitHub
# Or query database
```

## Troubleshooting

### PR Scanning Not Working

**Check GitHub credentials:**
```bash
cd /root/distask
source .venv/bin/activate
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Token:', 'SET' if os.getenv('GITHUB_TOKEN') else 'MISSING')"
```

**Test GitHub API access:**
```bash
TOKEN=$(grep GITHUB_TOKEN /root/distask/.env | cut -d '=' -f2)
curl -H "Authorization: token $TOKEN" \
  https://api.github.com/repos/NYTEMODEONLY/distask/pulls?state=closed&per_page=1
```

**Check logs for errors:**
```bash
sudo journalctl -u distask-feature-agent.service | grep -i "github\|pr\|error"
```

### Git Hooks Not Working

**Reinstall hooks:**
```bash
cd /root/distask
./scripts/setup-git-hooks.sh
```

**Verify hooks are executable:**
```bash
chmod +x .git/hooks/commit-msg .git/hooks/prepare-commit-msg
```

**Test hook manually:**
```bash
echo "test commit" | .git/hooks/commit-msg /tmp/test-msg
```

### Admin Command Not Appearing

**Restart bot service:**
```bash
sudo systemctl restart distask.service
```

**Check bot logs:**
```bash
sudo journalctl -u distask.service | grep -i "mark-feature-completed"
```

**Verify permissions:** You need `Manage Guild` permission in Discord.

## Quick Verification Checklist

- [ ] Code updated (`git pull origin main`)
- [ ] GitHub token configured in `.env`
- [ ] Feature agent restarted
- [ ] PR scanning works (check logs)
- [ ] State file shows `last_pr_number`
- [ ] Admin command available in Discord
- [ ] Workflow documentation reviewed

## Files Changed

```
git-hooks/
  ├── commit-msg              # Validation hook
  └── prepare-commit-msg      # Auto-injection hook

scripts/
  └── setup-git-hooks.sh      # Hook installation script

docs/
  └── FEATURE_REQUEST_WORKFLOW.md  # Complete workflow guide

cogs/
  └── admin.py                # Added /mark-feature-completed command

scripts/
  └── feature_agent.py        # Enhanced with PR scanning

utils/
  └── db.py                   # Added get_feature_request() method
```

## Next Steps

1. **Test the workflow** with a real feature request
2. **Create PR first** before implementing
3. **Use git hooks locally** (install with `./scripts/setup-git-hooks.sh`)
4. **Monitor automation** via logs to ensure PR scanning works

The automation runs nightly at 03:30 CST. Check logs the next day to verify everything is working!

