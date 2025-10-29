# Feature Request Implementation Workflow

This document outlines the complete workflow for implementing feature requests in DisTask, emphasizing a **PR-first approach** to ensure code quality, proper tracking, and automated completion detection.

## Overview

When implementing a feature request, you must follow this process:
1. **Create a Pull Request** (before writing code)
2. **Get Code Review** (discuss approach, get feedback)
3. **Implement the Feature** (write code, commit with FR markers)
4. **Merge PR** (automation detects completion)

## Step-by-Step Workflow

### 1. Feature Request Created

Feature requests are submitted via `/request-feature` in Discord or manually added to the database. Each request receives a unique ID (e.g., `#123`).

**View the backlog:**
- GitHub: `feature_requests.md`
- Automation queue: `automation/feature_queue.md`

### 2. Create Pull Request First

**Before writing any code**, create a PR to discuss the implementation approach:

1. **Create a feature branch** following the naming convention:
   ```bash
   git checkout -b feature/123-short-description
   ```
   Example: `feature/123-modal-export`, `feature/456-user-permissions`

2. **Create an empty commit or add a PR description**:
   ```bash
   git commit --allow-empty -m "WIP: Feature request #123 - Short description"
   git push origin feature/123-short-description
   ```

3. **Open a Pull Request** on GitHub with:
   - **Title**: Include the feature request ID, e.g., `feat: Add modal export FR-123`
   - **Description**: Explain the approach, link to the feature request, discuss edge cases
   - Example PR description:
     ```markdown
     Implements feature request #123: Modal export functionality
     
     ## Approach
     - Add export button to board view modal
     - Export format: JSON or CSV
     - Include all columns and tasks
     
     ## Changes
     - [ ] Add export button UI
     - [ ] Implement export logic
     - [ ] Add tests
     
     Related: Feature Request #123
     ```

### 3. Code Review & Discussion

- Reviewers comment on the approach, suggest improvements
- Discuss edge cases, UI/UX considerations
- Ensure the implementation aligns with project architecture
- **Do not merge until approval**

### 4. Implement the Feature

Once the PR is approved, implement the feature:

1. **Install git hooks** (if not already installed):
   ```bash
   ./scripts/setup-git-hooks.sh
   ```
   This ensures FR markers are automatically added to commit messages.

2. **Make commits** following conventional commit format:
   ```bash
   git commit -m "feat: add modal export button FR-123"
   git commit -m "feat: implement JSON export logic FR-123"
   git commit -m "test: add export functionality tests FR-123"
   ```

3. **Git hooks will:**
   - **Auto-inject FR markers**: If your branch is `feature/123-*`, the `prepare-commit-msg` hook automatically adds `FR-123` to commit messages
   - **Validate markers**: The `commit-msg` hook warns if FR markers are missing (non-blocking)

4. **Update PR description** with progress:
   ```markdown
   ## Changes
   - [x] Add export button UI
   - [x] Implement export logic
   - [x] Add tests
   ```

### 5. Commit Message Patterns

The automation recognizes these patterns (case-insensitive):
- `FR-123` (preferred)
- `feature-request #123`
- `feature/123`, `feature-123`, `feature_123`

**Best practices:**
- Include FR marker in the subject line: `feat: add feature FR-123`
- Or in the footer: `Fixes FR-123`
- Git hooks auto-inject if branch matches `feature/<id>-*`

### 6. Merge PR

Once code review is complete and tests pass:

1. **Merge the PR** (squash merge or merge commit)
2. **Automation detects completion** via:
   - **PR title/description**: Scans for FR markers in merged PRs
   - **Commit messages**: Scans commit history for FR markers
   - **Merge commit**: Links PR to feature request

3. **Feature request is marked `completed`** automatically:
   - Status updated in database
   - `feature_requests.md` updated on GitHub
   - Commit hash and PR number stored in completion metadata

### 7. Verification

After merging, verify completion:

1. **Check logs**:
   ```bash
   journalctl -u distask-feature-agent.service --since "1 hour ago"
   ```
   Look for: `Marking feature #123 as completed via PR #456`

2. **Check database**:
   ```sql
   SELECT id, title, status, completed_at, analysis_data->>'commit_hash' 
   FROM feature_requests 
   WHERE id = 123;
   ```

3. **View updated backlog**: Check `feature_requests.md` on GitHub

## Branch Naming Convention

**Required format:** `feature/<id>-<short-slug>`

- `<id>`: Feature request ID (number)
- `<short-slug>`: Brief description (kebab-case)

**Examples:**
- ✅ `feature/123-modal-export`
- ✅ `feature/456-user-permissions`
- ❌ `feature/modal-export` (missing ID)
- ❌ `feat/123-export` (wrong prefix)

## PR Requirements

### PR Title

**Must include FR marker:**
- ✅ `feat: Add modal export FR-123`
- ✅ `feat(ui): Implement export functionality (FR-123)`
- ❌ `feat: Add modal export` (missing FR marker)

### PR Description

**Recommended format:**
```markdown
Implements feature request #123: [Brief Description]

## Approach
[Explain your implementation strategy]

## Changes
- [ ] Task 1
- [ ] Task 2

## Testing
[How you tested]

Related: Feature Request #123
```

Include FR marker in description for redundancy (automation scans both title and body).

## Troubleshooting

### Feature not marked as completed

**Check:**
1. Did you include FR marker in commit messages?
   ```bash
   git log --oneline | grep -i "FR-123"
   ```

2. Did you include FR marker in PR title/description?

3. Has the automation run since merge?
   - Runs nightly at 03:30 CST
   - Or manually: `sudo systemctl start distask-feature-agent.service`

4. Check automation logs:
   ```bash
   journalctl -u distask-feature-agent.service --since "1 day ago"
   ```

**Solution:** Use `/mark-feature-completed` admin command or manually add FR marker and re-run automation.

### Git hooks not working

**Installation:**
```bash
./scripts/setup-git-hooks.sh
```

**Verify:**
```bash
ls -la .git/hooks/commit-msg .git/hooks/prepare-commit-msg
```

**Manual override:** Use `git commit --no-verify` to skip hooks (not recommended).

### Missing FR marker warning

If you see a warning but commit proceeds:
- The hook is non-blocking (allows override)
- Simply amend the commit: `git commit --amend -m "new message FR-123"`
- Or include FR marker in the next commit

## Manual Completion (Admin Only)

If automation misses a completion, use the admin command:

```
/mark-feature-completed <feature_id> [commit_hash]
```

**Requirements:**
- Must have `Manage Guild` permission
- Useful for edge cases (external contributions, manual merges)

## Automation Details

The feature agent (`scripts/feature_agent.py`) runs nightly and:

1. **Scans commits** since last run (incremental)
2. **Scans merged PRs** via GitHub API (checks title + description)
3. **Extracts FR markers** using regex patterns
4. **Marks features complete** in database
5. **Exports updated backlog** to GitHub

**State tracking:**
- Last processed commit: `data/feature_agent_state.json`
- Last processed PR number: stored in state
- Cursor-based scanning prevents reprocessing

## Benefits of PR-First Approach

1. **Early feedback**: Discuss approach before implementation
2. **Code quality**: Review ensures standards are met
3. **Documentation**: PR descriptions serve as implementation docs
4. **Automation**: PR scanning provides redundancy if commit markers are missed
5. **Traceability**: Link between PR, commits, and feature requests

## Quick Reference

```bash
# 1. Create branch
git checkout -b feature/123-short-slug

# 2. Install hooks (first time)
./scripts/setup-git-hooks.sh

# 3. Make commits (hooks auto-add FR-123)
git commit -m "feat: implement feature"

# 4. Push and create PR
git push origin feature/123-short-slug
# Then open PR on GitHub with title: "feat: Description FR-123"

# 5. After merge, verify completion
journalctl -u distask-feature-agent.service --since "1 hour ago"
```

## Related Documentation

- [README.md](../README.md) - General project overview
- [CLAUDE.md](../CLAUDE.md) - Development guidelines
- [AGENTS.md](../AGENTS.md) - Automation details

