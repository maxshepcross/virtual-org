#!/bin/zsh
# Installs macOS launchd services so Virtual Org starts at login and restarts on failure.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$REPO_DIR/.venv/bin/python3"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$REPO_DIR/.context/launchd-logs"
UID_VALUE="$(id -u)"

BOT_LABEL="com.maxshepcross.virtual-org.bot"
WORKER_LABEL="com.maxshepcross.virtual-org.worker"
BOT_PLIST="$LAUNCH_AGENTS_DIR/$BOT_LABEL.plist"
WORKER_PLIST="$LAUNCH_AGENTS_DIR/$WORKER_LABEL.plist"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing Python environment at $PYTHON_BIN"
  echo "Run the project setup first so .venv exists."
  exit 1
fi

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

write_plist() {
  local label="$1"
  local program="$2"
  local plist_path="$3"
  local stdout_log="$4"
  local stderr_log="$5"

  cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$REPO_DIR/$program</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$stdout_log</string>
  <key>StandardErrorPath</key>
  <string>$stderr_log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF
}

write_plist \
  "$BOT_LABEL" \
  "bot.py" \
  "$BOT_PLIST" \
  "$LOG_DIR/bot.out.log" \
  "$LOG_DIR/bot.err.log"

write_plist \
  "$WORKER_LABEL" \
  "worker.py" \
  "$WORKER_PLIST" \
  "$LOG_DIR/worker.out.log" \
  "$LOG_DIR/worker.err.log"

launchctl bootout "gui/$UID_VALUE/$BOT_LABEL" 2>/dev/null || true
launchctl bootout "gui/$UID_VALUE/$WORKER_LABEL" 2>/dev/null || true

launchctl bootstrap "gui/$UID_VALUE" "$BOT_PLIST"
launchctl bootstrap "gui/$UID_VALUE" "$WORKER_PLIST"

launchctl kickstart -k "gui/$UID_VALUE/$BOT_LABEL"
launchctl kickstart -k "gui/$UID_VALUE/$WORKER_LABEL"

echo "Installed and started:"
echo "  $BOT_LABEL"
echo "  $WORKER_LABEL"
echo
echo "Logs live in:"
echo "  $LOG_DIR"
