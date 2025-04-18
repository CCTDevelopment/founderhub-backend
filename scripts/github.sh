#!/bin/bash
# update_code.sh - Update the local repository with the latest code from GitHub

# Exit immediately if a command fails
set -e

# Change to the repository root (assumes this script is in a "scripts" subfolder)
cd "$(dirname "$0")/.."

echo "Fetching latest changes from GitHub..."

# Define your branch name; adjust if you're using a different branch.
BRANCH="main"

# Fetch the latest changes from the remote repository
git fetch origin

# Switch to the branch and pull the latest changes
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "Repository updated successfully."

# OPTIONAL: Restart your service if necessary.
# For example, if you're using Docker Compose, you might use:
# docker-compose down && docker-compose up -d

# Or if you're using systemd, you might use:
# sudo systemctl restart your_service_name

echo "Service restarted (if applicable)."
