#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${STATE_DIR:-/var/lib/vpn-alert}"
STATE_FILE="${STATE_FILE:-${STATE_DIR}/state.json}"
LOG_PREFIX="[VPN-ALERT]"
ANTISPAM_SECONDS="${ANTISPAM_SECONDS:-1800}"
MEMORY_CURRENT_WARN_BYTES="${MEMORY_CURRENT_WARN_BYTES:-734003200}"
MEMORY_PEAK_WARN_BYTES="${MEMORY_PEAK_WARN_BYTES:-838860800}"
JOURNAL_SINCE="${JOURNAL_SINCE:-6 minutes ago}"

mkdir -p "$STATE_DIR"

log() {
  printf '%s %s\n' "$LOG_PREFIX" "$*"
}

warn() {
  log "WARN: $*"
}

state_get() {
  local key="$1"
  python3 - "$STATE_FILE" "$key" <<'PY'
import json
import sys

path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

value = data
for part in key.split("."):
    if not isinstance(value, dict) or part not in value:
        sys.exit(0)
    value = value[part]

if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is not None:
    print(value)
PY
}

state_set_status() {
  local key="$1" value="$2"
  python3 - "$STATE_FILE" "$key" "$value" <<'PY'
import json
import os
import sys
import time

path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

statuses = data.setdefault("statuses", {})
statuses[key] = value
data["updated_at"] = int(time.time())

tmp = f"{path}.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, path)
PY
}

mark_send_allowed() {
  local hash="$1" now
  now=$(date +%s)
  python3 - "$STATE_FILE" "$hash" "$now" "$ANTISPAM_SECONDS" <<'PY'
import json
import os
import sys

path, key, now, ttl = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

last_sent = data.setdefault("last_sent", {})
last = int(last_sent.get(key, 0) or 0)
if now - last < ttl:
    print("suppress")
    sys.exit(0)

last_sent[key] = now
for old_key, old_ts in list(last_sent.items()):
    try:
        old_ts = int(old_ts)
    except Exception:
        old_ts = 0
    if now - old_ts > ttl * 48:
        last_sent.pop(old_key, None)
data["updated_at"] = now

tmp = f"{path}.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, path)
print("send")
PY
}

load_env() {
  local candidates=(
    "${ENV_FILE:-}"
    "/opt/vpn-gitops/secrets/.env"
    "/home/ubuntu/secrets/.env"
    "/home/ubuntu/.env"
    "/etc/sing-box/secrets.env"
  )
  local file
  for file in "${candidates[@]}"; do
    if [ -n "$file" ] && [ -f "$file" ]; then
      set -a
      # shellcheck disable=SC1090
      source "$file"
      set +a
      log "Loaded Telegram settings from $file"
      return 0
    fi
  done
  warn "No .env file found for Telegram settings"
}

telegram_send() {
  local severity="$1" text="$2" message hash allowed
  message="${severity} VPN infrastructure alert
host=$(hostname -f 2>/dev/null || hostname)
${text}"
  hash=$(printf '%s' "$message" | sha256sum | awk '{print $1}')
  allowed=$(mark_send_allowed "$hash")
  if [ "$allowed" != "send" ]; then
    log "Suppressed duplicate alert: ${text%%$'\n'*}"
    return 0
  fi

  if [ -z "${BOT_TOKEN:-}" ]; then
    warn "BOT_TOKEN is not configured; alert was not sent: ${text%%$'\n'*}"
    return 0
  fi
  if [ -z "${ADMIN_CHAT_ID:-}" ]; then
    warn "ADMIN_CHAT_ID is not configured; alert was not sent: ${text%%$'\n'*}"
    return 0
  fi

  if curl -fsS --max-time 10 \
    -d "chat_id=${ADMIN_CHAT_ID}" \
    --data-urlencode "text=${message}" \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" >/dev/null; then
    log "Sent alert: ${text%%$'\n'*}"
  else
    warn "Telegram API request failed"
  fi
}

service_result() {
  local unit="$1"
  systemctl show "$unit" -p Result --value 2>/dev/null || true
}

check_sing_box() {
  local active previous
  active=$(systemctl is-active sing-box.service 2>/dev/null || true)
  previous=$(state_get statuses.sing_box || true)
  if [ "$active" != "active" ]; then
    telegram_send "🚨 Critical" "sing-box.service status=${active:-unknown}"
  elif [ -n "$previous" ] && [ "$previous" != "active" ]; then
    telegram_send "✅ Recovery" "sing-box.service is healthy again"
  fi
  state_set_status sing_box "${active:-unknown}"
}

check_memory() {
  local current peak current_mb peak_mb
  current=$(systemctl show sing-box.service -p MemoryCurrent --value 2>/dev/null || printf '0')
  peak=$(systemctl show sing-box.service -p MemoryPeak --value 2>/dev/null || printf '0')
  [[ "$current" =~ ^[0-9]+$ ]] || current=0
  [[ "$peak" =~ ^[0-9]+$ ]] || peak=0
  current_mb=$((current / 1024 / 1024))
  peak_mb=$((peak / 1024 / 1024))
  if [ "$current" -gt "$MEMORY_CURRENT_WARN_BYTES" ]; then
    telegram_send "⚠ Warning" "MemoryCurrent=${current_mb}MB exceeds 700MB"
  fi
  if [ "$peak" -gt "$MEMORY_PEAK_WARN_BYTES" ]; then
    telegram_send "⚠ Warning" "MemoryPeak=${peak_mb}MB exceeds 800MB"
  fi
}

check_healthcheck() {
  local file="/var/lib/vpn-healthcheck/state.json" status previous
  [ -f "$file" ] || return 0
  status=$(python3 - "$file" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("status", ""))
except Exception:
    pass
PY
)
  previous=$(state_get statuses.healthcheck || true)
  if [ "$status" = "FAIL" ]; then
    telegram_send "🚨 Critical" "vpn-healthcheck status=FAIL"
  elif [ "$status" = "OK" ] && [ "$previous" = "FAIL" ]; then
    telegram_send "✅ Recovery" "vpn-healthcheck status=OK"
  fi
  [ -n "$status" ] && state_set_status healthcheck "$status"
}

check_backup() {
  local result previous
  result=$(service_result vpn-backup.service)
  [ -n "$result" ] || return 0
  previous=$(state_get statuses.backup || true)
  if [ "$result" != "success" ]; then
    telegram_send "🚨 Critical" "backup FAILED: vpn-backup.service Result=${result}"
  elif [ "$previous" != "" ] && [ "$previous" != "success" ]; then
    telegram_send "✅ Recovery" "backup again PASS"
  fi
  state_set_status backup "$result"
}

check_restore_test() {
  local unit result previous
  for unit in vpn-restore-test.service restore-test.service vpn-restore-test.timer restore-test.timer; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      result=$(service_result "$unit")
      previous=$(state_get statuses.restore_test || true)
      if [ -n "$result" ] && [ "$result" != "success" ]; then
        telegram_send "🚨 Critical" "restore-test FAILED: ${unit} Result=${result}"
      elif [ "$result" = "success" ] && [ "$previous" != "" ] && [ "$previous" != "success" ]; then
        telegram_send "✅ Recovery" "restore-test again PASS"
      fi
      [ -n "$result" ] && state_set_status restore_test "$result"
      return 0
    fi
  done
}

check_oom() {
  local line
  line=$(journalctl -k --since "$JOURNAL_SINCE" --no-pager 2>/dev/null | grep -Eim1 'oom-killer|Out of memory|Killed process' || true)
  if [ -n "$line" ]; then
    telegram_send "🚨 Critical" "OOM killer detected\n${line}"
  fi
}

check_failover() {
  local line
  line=$(journalctl -u vpn-failover.service --since "$JOURNAL_SINCE" -o cat --no-pager 2>/dev/null | grep -Eim1 'switch(ed)? route|route (changed|updated|switched)' || true)
  if [ -n "$line" ]; then
    telegram_send "⚠ Warning" "failover switched route\n${line}"
  fi
}

check_gitops_deploy() {
  local line
  line=$(journalctl -u vpn-gitops-update.service --since "$JOURNAL_SINCE" --no-pager 2>/dev/null | grep -Eim1 'Deploy successful|Deploying .*config' || true)
  if [ -n "$line" ]; then
    telegram_send "⚠ Warning" "GitOps deployed configuration\n${line}"
  fi
}

main() {
  load_env || true
  if [ "${1:-}" = "--test" ]; then
    telegram_send "✅ Recovery" "Test notification from vpn-alert; no incident was created"
    return 0
  fi

  check_oom
  check_sing_box
  check_memory
  check_healthcheck
  check_backup
  check_restore_test
  check_failover
  check_gitops_deploy
}

main "$@"
