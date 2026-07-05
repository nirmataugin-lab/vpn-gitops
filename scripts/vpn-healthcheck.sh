#!/usr/bin/env bash
set -euo pipefail

VPS2_HOST="${VPS2_HOST:-165.154.212.11}"
EXPECTED_EXIT_IP="${EXPECTED_EXIT_IP:-165.154.212.11}"
LOG_FILE="${LOG_FILE:-/var/log/vpn-healthcheck.log}"
STATE_FILE="${STATE_FILE:-/var/lib/vpn-healthcheck/state.json}"
ALERT_THRESHOLD="${ALERT_THRESHOLD:-3}"

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$STATE_FILE")"

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

log() {
    printf '%s %s\n' "$(timestamp)" "$*" >> "$LOG_FILE"
}

json_escape() {
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
}

tcp_check() {
    local port="$1"
    timeout 5 nc -z "$VPS2_HOST" "$port" >/dev/null 2>&1
}

udp_check() {
    local port="$1"
    timeout 5 nc -uz "$VPS2_HOST" "$port" >/dev/null 2>&1
}

tcp_latency_ms() {
    python3 - "$VPS2_HOST" 443 <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
start = time.monotonic()
try:
    with socket.create_connection((host, port), timeout=5):
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(elapsed_ms)
except Exception:
    sys.exit(1)
PY
}

external_ip() {
    timeout 10 curl -fsS4 https://api.ipify.org 2>/dev/null
}

previous_failures=0
if [ -f "$STATE_FILE" ]; then
    previous_failures=$(jq -r '.consecutive_failures // 0' "$STATE_FILE" 2>/dev/null || printf '0')
fi

critical_failures=0
details=()

for port in 443 8080; do
    if tcp_check "$port"; then
        details+=("tcp_${port}=PASS")
    else
        details+=("tcp_${port}=FAIL")
        critical_failures=$((critical_failures + 1))
    fi
done

if tcp_check 8082; then
    details+=("tcp_8082=PASS")
else
    details+=("tcp_8082=WARN")
fi

for port in 59507 59508; do
    if udp_check "$port"; then
        details+=("udp_${port}=PASS")
    else
        details+=("udp_${port}=FAIL")
        critical_failures=$((critical_failures + 1))
    fi
done

latency=""
if latency=$(tcp_latency_ms); then
    details+=("latency_tcp_443_ms=${latency}")
else
    details+=("latency_tcp_443_ms=FAIL")
    critical_failures=$((critical_failures + 1))
fi

exit_ip=""
if exit_ip=$(external_ip) && [ -n "$exit_ip" ]; then
    if [ "$exit_ip" = "$EXPECTED_EXIT_IP" ]; then
        details+=("external_ip=${exit_ip}")
    else
        details+=("external_ip=${exit_ip},expected=${EXPECTED_EXIT_IP}")
        critical_failures=$((critical_failures + 1))
    fi
else
    details+=("external_ip=FAIL")
    critical_failures=$((critical_failures + 1))
fi

if [ "$critical_failures" -eq 0 ]; then
    status="OK"
    consecutive_failures=0
else
    status="FAIL"
    consecutive_failures=$((previous_failures + 1))
fi

details_text=$(IFS=' '; printf '%s' "${details[*]}")
log "status=${status} failures=${critical_failures} consecutive_failures=${consecutive_failures} ${details_text}"

if [ "$consecutive_failures" -ge "$ALERT_THRESHOLD" ]; then
    log "ALERT consecutive_failures=${consecutive_failures} threshold=${ALERT_THRESHOLD} host=${VPS2_HOST}"
fi

details_json=$(printf '%s\n' "$details_text" | json_escape)
tmp_state="${STATE_FILE}.tmp"
cat > "$tmp_state" <<JSON
{
  "checked_at": "$(timestamp)",
  "status": "${status}",
  "vps2_host": "${VPS2_HOST}",
  "expected_exit_ip": "${EXPECTED_EXIT_IP}",
  "external_ip": "${exit_ip}",
  "tcp_443_latency_ms": ${latency:-null},
  "failures": ${critical_failures},
  "consecutive_failures": ${consecutive_failures},
  "details": ${details_json}
}
JSON
mv "$tmp_state" "$STATE_FILE"

# Monitoring failures are reported via log/state. Keep the oneshot unit healthy so
# the timer continues running and consecutive failure tracking can trigger ALERT.
exit 0
