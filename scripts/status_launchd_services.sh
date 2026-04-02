#!/bin/zsh
# Shows whether the macOS launchd services for Virtual Org are loaded.

set -euo pipefail

UID_VALUE="$(id -u)"

BOT_LABEL="com.maxshepcross.virtual-org.bot"
WORKER_LABEL="com.maxshepcross.virtual-org.worker"

show_status() {
  local label="$1"
  echo
  echo "$label"
  launchctl print "gui/$UID_VALUE/$label" 2>/dev/null | sed -n '1,20p' || echo "  not loaded"
}

show_status "$BOT_LABEL"
show_status "$WORKER_LABEL"
