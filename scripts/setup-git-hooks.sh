#!/bin/bash
# Setup script for DisTask git hooks
# Installs commit-msg and prepare-commit-msg hooks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
TEMPLATE_DIR="$REPO_ROOT/git-hooks"

echo "🔧 Setting up DisTask git hooks..."

# Ensure .git/hooks directory exists
if [ ! -d "$HOOKS_DIR" ]; then
    echo "❌ Error: .git/hooks directory not found. Are you in a git repository?"
    exit 1
fi

# Ensure template hooks directory exists
if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "❌ Error: git-hooks template directory not found at $TEMPLATE_DIR"
    exit 1
fi

# Install commit-msg hook
if [ -f "$TEMPLATE_DIR/commit-msg" ]; then
    cp "$TEMPLATE_DIR/commit-msg" "$HOOKS_DIR/commit-msg"
    chmod +x "$HOOKS_DIR/commit-msg"
    echo "✅ Installed commit-msg hook"
else
    echo "⚠️  Warning: commit-msg template not found"
fi

# Install prepare-commit-msg hook
if [ -f "$TEMPLATE_DIR/prepare-commit-msg" ]; then
    cp "$TEMPLATE_DIR/prepare-commit-msg" "$HOOKS_DIR/prepare-commit-msg"
    chmod +x "$HOOKS_DIR/prepare-commit-msg"
    echo "✅ Installed prepare-commit-msg hook"
else
    echo "⚠️  Warning: prepare-commit-msg template not found"
fi

echo ""
echo "✨ Git hooks installed successfully!"
echo ""
echo "The hooks will:"
echo "  • Validate FR markers in commit messages (commit-msg)"
echo "  • Auto-inject FR markers from branch names (prepare-commit-msg)"
echo ""
echo "To disable hooks temporarily, use: git commit --no-verify"

