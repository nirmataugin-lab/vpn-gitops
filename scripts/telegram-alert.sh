#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${STATE_DIR:-/var/lib/vpn-alert}"
STATE_FILE="${STATE_FILE:-${STATE_DIR}/state.json}"
LOG_PREFIX="[VPN-ALERT]"
ANTISPAM_SECONDS="${ANTISPAM_SECONDS:-21600}"
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

state_update() {
  local action="$1" key="${2:-}" value="${3:-}"
  python3 - "$STATE_FILE" "$action" "$key" "$value" <<'PY'
import json
import os
import sys
import time

path, action, key, value = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

now = int(time.time())
if action == "status":
    data.setdefault("statuses", {})[key] = value
elif action == "incident":
    data.setdefault("incidents", {})[key] = value
elif action == "clear_incident":
    data.setdefault("incidents", {}).pop(key, None)
    data.setdefault("last_sent", {}).pop(key, None)
elif action == "sent":
    data.setdefault("last_sent", {})[key] = now
else:
    raise SystemExit(f"unknown action: {action}")

data["updated_at"] = now
tmp = f"{path}.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, path)
PY
}

send_allowed() {
  local key="$1" now
  now=$(date +%s)
  python3 - "$STATE_FILE" "$key" "$now" "$ANTISPAM_SECONDS" <<'PY'
import json
import sys

path, key, now, ttl = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

last = int(data.get("last_sent", {}).get(key, 0) or 0)
print("send" if now - last >= ttl else "suppress")
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

message_title() {
  case "$1" in
    critical) printf '🚨 VPN Critical' ;;
    warning) printf '⚠️ VPN Warning' ;;
    recovery) printf '✅ VPN Recovery' ;;
  esac
}

telegram_send() {
  local severity="$1" key="$2" event="$3" details="${4:-}" host now title message allowed
  allowed=$(send_allowed "$key")
  if [ "$allowed" != "send" ]; then
    log "Suppressed duplicate ${severity}: ${event}"
    return 0
  fi

  host=$(hostname -f 2>/dev/null || hostname)
  now=$(date -u '+%Y-%m-%d %H:%M UTC')
  title=$(message_title "$severity")
  message=$(printf '%s\n\nHost: %s\nEvent: %s' "$title" "$host" "$event")
  if [ -n "$details" ]; then
    message=$(printf '%s\n\n%s' "$message" "$details")
  fi
  message=$(printf '%s\n\nTime:\n%s' "$message" "$now")

  if [ "${DRY_RUN:-0}" = "1" ]; then
    printf '%s\n' "$message"
    state_update sent "$key"
    log "Dry-run alert: ${event}"
    return 0
  fi

  if [ -z "${BOT_TOKEN:-}" ]; then
    warn "BOT_TOKEN is not configured; alert was not sent: ${event}"
    return 0
  fi
  if [ -z "${ADMIN_CHAT_ID:-}" ]; then
    warn "ADMIN_CHAT_ID is not configured; alert was not sent: ${event}"
    return 0
  fi

  if curl -fsS --max-time 10 \
    -d "chat_id=${ADMIN_CHAT_ID}" \
    --data-urlencode "text=${message}" \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" >/dev/null; then
    state_update sent "$key"
    log "Sent ${severity}: ${event}"
  else
    warn "Telegram API request failed"
  fi
}

raise_incident() {
  local severity="$1" key="$2" event="$3" details="${4:-}"
  telegram_send "$severity" "$key" "$event" "$details"
  state_update incident "$key" "$severity"
}

recover_incident() {
  local key="$1" event="$2" details="${3:-}" previous
  previous=$(state_get "incidents.${key}" || true)
  [ -n "$previous" ] || return 0
  state_update clear_incident "$key"
  telegram_send recovery "$key" "$event" "$details"
}

service_result() {
  local unit="$1"
  systemctl show "$unit" -p Result --value 2>/dev/null || true
}

check_sing_box() {
  local active
  active=$(systemctl is-active sing-box.service 2>/dev/null || true)
  if [ "$active" != "active" ]; then
    raise_incident critical sing_box "sing-box.service is not active" "Status: ${active:-unknown}"
  else
    recover_incident sing_box "sing-box.service recovered" "Status: active"
  fi
  state_update status sing_box "${active:-unknown}"
}

check_memory() {
  local current peak current_mb peak_mb details
  current=$(systemctl show sing-box.service -p MemoryCurrent --value 2>/dev/null || printf '0')
  peak=$(systemctl show sing-box.service -p MemoryPeak --value 2>/dev/null || printf '0')
  [[ "$current" =~ ^[0-9]+$ ]] || current=0
  [[ "$peak" =~ ^[0-9]+$ ]] || peak=0
  current_mb=$((current / 1024 / 1024))
  peak_mb=$((peak / 1024 / 1024))

  if [ "$current" -gt "$MEMORY_CURRENT_WARN_BYTES" ] || [ "$peak" -gt "$MEMORY_PEAK_WARN_BYTES" ]; then
    details=$(printf 'MemoryCurrent: %s MB\nMemoryPeak: %s MB' "$current_mb" "$peak_mb")
    raise_incident warning memory_high "Memory usage high" "$details"
  else
    details=$(printf 'MemoryCurrent: %s MB\nMemoryPeak: %s MB' "$current_mb" "$peak_mb")
    recover_incident memory_high "Memory usage recovered" "$details"
  fi
}

check_healthcheck() {
  local file="/var/lib/vpn-healthcheck/state.json" status details
  [ -f "$file" ] || return 0
  status=$(python3 - "$file" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("status", ""))
except Exception:
    pass
PY
)
  details=$(python3 - "$file" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit
for name in ("checked_at", "details", "consecutive_failures"):
    value = data.get(name)
    if value not in (None, ""):
        print(f"{name}: {value}")
PY
)
  if [ "$status" = "FAIL" ]; then
    raise_incident critical healthcheck_fail "vpn-healthcheck FAIL" "$details"
  elif [ "$status" = "OK" ]; then
    recover_incident healthcheck_fail "vpn-healthcheck recovered" "$details"
  fi
  [ -n "$status" ] && state_update status healthcheck "$status"
}

check_backup() {
  local result details
  result=$(service_result vpn-backup.service)
  [ -n "$result" ] || return 0
  details=$(printf 'Unit: vpn-backup.service\nResult: %s' "$result")
  if [ "$result" != "success" ]; then
    raise_incident critical backup_failed "backup FAILED" "$details"
  else
    recover_incident backup_failed "backup recovered" "$details"
  fi
  state_update status backup "$result"
}

check_restore_test() {
  local unit result details
  for unit in vpn-restore-test.service restore-test.service; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      result=$(service_result "$unit")
      [ -n "$result" ] || return 0
      details=$(printf 'Unit: %s\nResult: %s' "$unit" "$result")
      if [ "$result" != "success" ]; then
        raise_incident critical restore_test_failed "restore-test FAILED" "$details"
      else
        recover_incident restore_test_failed "restore-test recovered" "$details"
      fi
      state_update status restore_test "$result"
      return 0
    fi
  done
}

check_oom() {
  local line
  line=$(journalctl -k --since "$JOURNAL_SINCE" --no-pager 2>/dev/null | grep -Eim1 'oom-killer|Out of memory|Killed process' || true)
  if [ -n "$line" ]; then
    raise_incident critical kernel_oom "kernel OOM" "$line"
  fi
}

check_failover() {
  local line
  line=$(journalctl -u vpn-failover.service --since "$JOURNAL_SINCE" -o cat --no-pager 2>/dev/null | grep -Eim1 'switch(ed)? route|route (changed|updated|switched)' || true)
  if [ -n "$line" ]; then
    raise_incident warning failover_route_changed "failover switched route" "$line"
  fi
}

main() {
  load_env || true
  if [ "${1:-}" = "--test" ]; then
    log "Test notification disabled; no Telegram message sent"
    return 0
  fi

  check_oom
  check_sing_box
  check_memory
  check_healthcheck
  check_backup
  check_restore_test
  check_failover
}

main "$@"
