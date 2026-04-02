#!/bin/zsh
# Removes the macOS launchd services for Virtual Org.

set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_VALUE="$(id -u)"

BOT_LABEL="com.maxshepcross.virtual-org.bot"
WORKER_LABEL="com.maxshepcross.virtual-org.worker"
BOT_PLIST="$LAUNCH_AGENTS_DIR/$BOT_LABEL.plist"
WORKER_PLIST="$LAUNCH_AGENTS_DIR/$WORKER_LABEL.plist"

launchctl bootout "gui/$UID_VALUE/$BOT_LABEL" 2>/dev/null || true
launchctl bootout "gui/$UID_VALUE/$WORKER_LABEL" 2>/dev/null || true

rm -f "$BOT_PLIST" "$WORKER_PLIST"

echo "Removed:"
echo "  $BOT_LABEL"
echo "  $WORKER_LABEL"
