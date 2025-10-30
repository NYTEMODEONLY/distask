# Quick Start: Rapid Release Flow

## 🚀 How to Use the Release Helper (Yourself)

### Step 1: Connect to VPS

```bash
ssh root@178.156.192.132
# Password: Icbktw135!
```

### Step 2: Navigate & Activate

```bash
cd /root/distask
source .venv/bin/activate
```

### Step 3: Pull Latest Code

```bash
git pull origin main
```

### Step 4: Check What's Ready to Release

```bash
python scripts/release_helper.py --suggest --threshold 80
```

**This shows you:**
- Which features have scores ≥ 80
- Why they were selected (high priority, easy, community votes)
- How many features are ready

### Step 5: Validate Before Release

```bash
python scripts/release_helper.py --validate
```

**Checks:**
- ✅ Code formatting
- ✅ Code style  
- ✅ Tests (if any)
- ✅ Git state
- ✅ Feature queue consistency

### Step 6: Dry-Run First (Always!)

```bash
python scripts/release_helper.py --full-cycle --dry-run --threshold 80
```

**Shows you:**
- What version will be created
- What changelog will be generated
- What git tag will be created
- What GitHub release will be made

**DOESN'T MAKE ANY CHANGES** - safe to run anytime!

### Step 7: Execute Release

```bash
python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80
```

**This:**
- ✅ Selects top-scoring features automatically
- ✅ Validates everything first
- ✅ Bumps version (e.g., 1.0.0 → 1.1.0)
- ✅ Generates changelog
- ✅ Creates git tag
- ✅ Creates GitHub release
- ✅ Marks features as shipped

### Step 8: Restart Services (If Needed)

```bash
sudo systemctl restart distask.service distask-web.service
```

## 📋 Common Commands Cheat Sheet

```bash
# 1. Check what's ready
python scripts/release_helper.py --suggest --threshold 80

# 2. Validate
python scripts/release_helper.py --validate

# 3. Dry-run
python scripts/release_helper.py --full-cycle --dry-run --threshold 80

# 4. Release
python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80

# 5. Check version
cat VERSION

# 6. View changelog
cat CHANGELOG.md
```

## ⚙️ Configuration

Add to `/root/distask/.env`:

```env
RELEASE_THRESHOLD=80.0
```

## 🎯 Typical Workflow

1. **Morning**: Check what's ready
   ```bash
   python scripts/release_helper.py --suggest --threshold 80
   ```

2. **Before Release**: Validate
   ```bash
   python scripts/release_helper.py --validate
   ```

3. **Test Release**: Dry-run
   ```bash
   python scripts/release_helper.py --full-cycle --dry-run --threshold 80
   ```

4. **Ship It**: Execute
   ```bash
   python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80
   ```

5. **Restart**: Services (if needed)
   ```bash
   sudo systemctl restart distask.service
   ```

## 📚 Full Documentation

- **Complete Guide**: `docs/RELEASE_FLOW.md`
- **VPS Setup**: `docs/VPS_RELEASE_SETUP.md`
- **AI Templates**: `docs/release_prompt_templates.md`
- **Feature Workflow**: `docs/FEATURE_REQUEST_WORKFLOW.md`

## ❓ Troubleshooting

**No features suggested?**
- Lower threshold: `--threshold 50`
- Update queue: `python scripts/feature_agent.py`

**Validation fails?**
- Fix formatting: `black .`
- Fix style: Check flake8 output
- Clean git: `git status`

**GitHub release fails?**
- Check `GITHUB_TOKEN` in `.env`
- Verify token has `repo` scope

## 🎉 That's It!

The release helper does everything automatically:
- ✅ Score-based selection
- ✅ Comprehensive validation
- ✅ Version bumping
- ✅ Changelog generation
- ✅ GitHub releases
- ✅ Git tagging

You just run 3 commands: `--suggest`, `--validate`, `--full-cycle`!

