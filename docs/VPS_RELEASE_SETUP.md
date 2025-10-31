# VPS Release Flow Setup Guide

Complete guide for using the rapid release flow on your VPS.

## Quick Start

### 1. Connect to VPS

```bash
ssh root@YOUR_VPS_IP
# Enter your VPS password when prompted
```

**⚠️ SECURITY NOTE:** Never commit passwords or credentials to git. Use SSH keys or environment variables instead.

### 2. Navigate to Project

```bash
cd /root/distask
```

### 3. Pull Latest Changes

```bash
git pull origin main
```

### 4. Activate Virtual Environment

```bash
source .venv/bin/activate
```

### 5. Install New Dependencies (if needed)

```bash
pip install -r requirements.txt
```

## Using Release Helper

### Suggest Release Batch

See what features are ready for release:

```bash
python scripts/release_helper.py --suggest --threshold 80
```

**Output shows:**
- Feature IDs and titles
- Scores (priority + ease + votes - penalties)
- Rationale for selection
- Number of features suggested

### Validate Everything

Before any release, validate code quality:

```bash
python scripts/release_helper.py --validate
```

**Checks:**
- Code formatting (black)
- Code style (flake8)
- Type hints (mypy, non-blocking)
- Tests (pytest, if tests exist)
- Git state (clean working tree)
- Feature queue consistency
- Database schema compatibility

### Full Release Cycle (Dry Run First)

Always test with dry-run first:

```bash
python scripts/release_helper.py --full-cycle --dry-run --threshold 80
```

This shows what would happen without making changes.

### Execute Release

After validation passes and dry-run looks good:

```bash
python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80
```

**This will:**
- Select top-scoring features automatically
- Skip confirmation prompts (`--yes`)
- Validate before proceeding
- Bump version (from `VERSION` file)
- Generate changelog (`CHANGELOG.md`)
- Create git tag (`v1.2.3`)
- Create GitHub release (if credentials configured)
- Mark features as shipped

## Environment Configuration

Add to `/root/distask/.env`:

```env
# Release threshold (default: 80.0)
RELEASE_THRESHOLD=80.0

# GitHub credentials (for releases)
GITHUB_TOKEN=ghp_your_token_here
REPO_OWNER=NYTEMODEONLY
REPO_NAME=distask

# Database (for schema validation)
DATABASE_URL=postgresql://user:password@localhost:5432/distask
```

## Common Workflows

### Daily Check: What's Ready to Release?

```bash
cd /root/distask
source .venv/bin/activate
python scripts/release_helper.py --suggest --threshold 80
```

### Before Release: Validate Everything

```bash
cd /root/distask
source .venv/bin/activate
python scripts/release_helper.py --validate
```

### Release Process

```bash
cd /root/distask
source .venv/bin/activate

# 1. Dry-run first
python scripts/release_helper.py --full-cycle --dry-run --threshold 80

# 2. Review output, then execute
python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80

# 3. Restart services (if needed)
sudo systemctl restart distask.service distask-web.service
```

## Troubleshooting

### No Features Suggested

**Problem**: `--suggest` returns no candidates

**Solutions**:
1. Lower threshold: `--threshold 50`
2. Update feature queue: `python scripts/feature_agent.py`
3. Check queue: `cat automation/feature_queue.json`

### Validation Fails

**Problem**: `--validate` reports failures

**Solutions**:
1. Fix formatting: `black .`
2. Fix style: Address flake8 issues
3. Fix tests: Run `pytest` separately
4. Clean git: `git status` and commit/stash changes

### GitHub Release Fails

**Problem**: Release creation fails

**Solutions**:
1. Check credentials: Verify `GITHUB_TOKEN` in `.env`
2. Check permissions: Token needs `repo` scope
3. Manual release: Create release on GitHub UI

### Version File Missing

**Problem**: Version file not found

**Solution**: Already created as `VERSION` (starts at `1.0.0`)

## Files Created/Modified

**New Files:**
- `scripts/release_helper.py` - Main release helper
- `scripts/validate.py` - Validation module
- `VERSION` - Version tracking (starts at `1.0.0`)
- `CHANGELOG.md` - Auto-generated changelog
- `docs/RELEASE_FLOW.md` - Complete guide
- `docs/release_prompt_templates.md` - AI templates
- `tests/` - Test structure

**Modified Files:**
- `requirements.txt` - Added validation tools
- `scripts/feature_agent.py` - Added `--release` flag
- Documentation updated (README, CLAUDE, etc.)

## Quick Reference

```bash
# Suggest release batch
python scripts/release_helper.py --suggest --threshold 80

# Validate
python scripts/release_helper.py --validate

# Dry-run release
python scripts/release_helper.py --full-cycle --dry-run --threshold 80

# Execute release
python scripts/release_helper.py --full-cycle --yes --auto-select --threshold 80

# Check version
cat VERSION

# View changelog
cat CHANGELOG.md
```

## Integration with Existing Workflow

The release helper integrates seamlessly with:
- **PR-first workflow**: Features implemented via PRs before release
- **Feature agent**: Reads from `automation/feature_queue.json`
- **Git hooks**: FR markers auto-injected from branch names
- **Systemd services**: Manual restart after release

See `docs/FEATURE_REQUEST_WORKFLOW.md` for PR-first workflow details.

