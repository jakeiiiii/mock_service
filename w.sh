#!/usr/bin/env bash
# Wipe ALL git history (local + remote) and replace it with a single commit.
# Usage:
#   bash wipe-history.sh        # prompts for confirmation
#   bash wipe-history.sh -y     # skip the confirmation prompt
#
# This is destructive and irreversible. The old commits are discarded and the
# remote is force-pushed. Old commits may still linger on GitHub by SHA until
# it garbage-collects, and any forks/clones keep the old history.

set -euo pipefail

REMOTE_URL="https://github.com/jakeiiiii/mock_service.git"
BRANCH="main"
COMMIT_MSG="Initial commit"

# Run from the script's own directory (the repo root).
cd "$(dirname "$0")"

if [ "${1:-}" != "-y" ] && [ "${1:-}" != "--yes" ]; then
  echo "This will ERASE all git history (local and remote) for:"
  echo "  $(pwd)"
  echo "  remote: $REMOTE_URL"
  read -r -p "Type 'y' to continue: " reply
  [ "$reply" = "y" ] || { echo "Aborted."; exit 1; }
fi

rm -rf .git
git init -q
git add -A
git commit -q -m "$COMMIT_MSG"
git branch -M "$BRANCH"
git remote add origin "$REMOTE_URL"
git push -f origin "$BRANCH"

echo "Done. History wiped and force-pushed to $BRANCH."
