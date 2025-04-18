#!/bin/bash
# push_code.sh - Push local changes to GitHub

set -e

# Change to repo root
cd "$(dirname "$0")/.."

echo "Committing and pushing changes..."

BRANCH="main"

# Stage all changes
git add .

# Commit with a timestamped message
git commit -m "Update: $(date '+%Y-%m-%d %H:%M:%S')" || echo "Nothing to commit."

# Push to GitHub
git push origin "$BRANCH"

echo "✅ Pushed to GitHub branch: $BRANCH"
