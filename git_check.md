# Git Check & Sync Guide for DisTask VPS

This document provides step-by-step instructions for AI assistants to properly sync the VPS workspace with the GitHub repository and manage services.

## Overview
This guide ensures the VPS workspace matches the latest GitHub version while preserving any local changes by pushing them first, then pulling updates, and restarting services as needed.

## Step-by-Step Process

### 1. Check Current Status
```bash
cd /root/distask
git status
git fetch origin
```

**What to look for:**
- Working tree should be clean (no uncommitted changes)
- Check if local branch is ahead, behind, or diverged from origin/main

### 2. Handle Local Changes (if any)
If there are uncommitted changes:
```bash
# Stage all changes
git add .

# Commit with descriptive message
git commit -m "feat: describe the changes made on VPS"
```

### 3. Check for Remote Updates
```bash
git log --oneline HEAD..origin/main
```

**If there are remote commits:**
- Note the number and type of changes
- Proceed to step 4

**If no remote commits:**
- VPS is up to date, skip to step 6

### 4. Handle Diverged Branches
If branches have diverged (local ahead + remote ahead):

**Option A: Push local changes first, then pull**
```bash
# Push local commits to GitHub
git push origin main

# Pull remote changes
git pull origin main --no-rebase
```

**Option B: If push fails (remote has newer commits)**
```bash
# Pull with merge strategy
git pull origin main --no-rebase
```

### 5. Verify Sync
```bash
git status
git log --oneline -3
```

**Expected result:**
- "Your branch is up to date with 'origin/main'"
- Latest commits should include both local and remote changes

### 6. Restart Services (if updates were pulled)
If any code changes were pulled, restart the services:

```bash
# Restart Discord bot
systemctl restart distask.service

# Restart web interface
systemctl restart distask-web.service

# Note: Feature agent timer doesn't need restart (runs on schedule)
```

### 7. Verify Services
```bash
# Check service status
systemctl status distask.service distask-web.service distask-feature-agent.timer

# Check if services are running
systemctl is-active distask.service distask-web.service distask-feature-agent.timer
```

**Expected results:**
- All services should show "active (running)" or "active (waiting)" for timer
- No error messages in status output

## Service Management Commands

### Check Service Status
```bash
systemctl status distask.service distask-feature-agent.timer distask-web.service
```

### Restart Services
```bash
# Restart bot only
systemctl restart distask.service

# Restart web interface only
systemctl restart distask-web.service

# Restart all services
systemctl restart distask.service distask-web.service
```

### Enable/Disable Services
```bash
# Enable services to start on boot
systemctl enable distask.service distask-feature-agent.timer distask-web.service

# Disable services
systemctl disable distask.service distask-feature-agent.timer distask-web.service
```

## Troubleshooting

### If Git Pull Fails
```bash
# Check for merge conflicts
git status

# If conflicts exist, resolve them manually, then:
git add .
git commit -m "resolve: merge conflicts"

# Continue with normal flow
```

### If Services Won't Start
```bash
# Check service logs
journalctl -u distask.service -f
journalctl -u distask-web.service -f

# Check for Python errors
cd /root/distask
python bot.py  # Test bot manually
```

### If Working Tree is Dirty
```bash
# Stash changes temporarily
git stash

# Pull updates
git pull origin main --no-rebase

# Apply stashed changes
git stash pop

# Resolve any conflicts and commit
```

## Important Notes

1. **Always check status first** - Don't assume the state of the repository
2. **Preserve local changes** - Push them to GitHub before pulling updates
3. **Use merge strategy** - `--no-rebase` prevents history rewriting
4. **Restart after code changes** - Services need restart to load new code
5. **Verify everything works** - Check service status after restart
6. **Feature agent timer** - Runs automatically, no manual restart needed

## Quick Reference

```bash
# Complete sync process
cd /root/distask
git status
git fetch origin
git add . && git commit -m "feat: VPS changes" 2>/dev/null || true
git push origin main 2>/dev/null || git pull origin main --no-rebase
systemctl restart distask.service distask-web.service
systemctl status distask.service distask-web.service
```

## File Locations
- **Project root**: `/root/distask`
- **Service files**: `/etc/systemd/system/distask*.service`
- **Logs**: `journalctl -u distask.service`
- **Git hooks**: `/root/distask/.git/hooks/`

---
*This document should be updated if the sync process changes or new services are added.*