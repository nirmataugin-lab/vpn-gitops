#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_DIR="${ARCHIVE_DIR:-/opt/backup/archive}"
WORK_DIR=""

declare -a RESULTS=()

cleanup() {
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

result() {
    RESULTS+=("$2|$1|$3")
}

latest_backup() {
    local latest
    latest=$(ls -1t "$ARCHIVE_DIR"/backup-*.tar.zst "$ARCHIVE_DIR"/backup_*.tar.gz 2>/dev/null | head -1 || true)
    [ -n "$latest" ] && printf '%s\n' "$latest"
}

extract_archive() {
    local archive="$1"
    local target="$2"

    case "$archive" in
        *.tar.zst) tar --use-compress-program=unzstd -xf "$archive" -C "$target" ;;
        *.tar.gz|*.tgz) tar -xzf "$archive" -C "$target" ;;
        *) return 1 ;;
    esac
}

exists() {
    [ -e "$RESTORE_ROOT/$1" ]
}

mode_is() {
    local path="$1"
    local regex="$2"
    local mode

    mode=$(stat -c '%a' "$path")
    [[ "$mode" =~ $regex ]]
}

archive=$(latest_backup || true)
if [ -z "$archive" ]; then
    echo "No backup archive found in $ARCHIVE_DIR"
    exit 1
fi

WORK_DIR=$(mktemp -d)
RESTORE_ROOT="$WORK_DIR/restore"
mkdir -p "$RESTORE_ROOT"

if extract_archive "$archive" "$RESTORE_ROOT"; then
    result "unpack latest backup" "PASS" "$(basename "$archive") -> $RESTORE_ROOT"
else
    result "unpack latest backup" "FAIL" "archive extraction failed"
fi

sha_file="${archive}.sha256"
if [ -f "$sha_file" ]; then
    if (cd "$(dirname "$archive")" && sha256sum -c "$sha_file" >/dev/null 2>&1); then
        result "SHA256" "PASS" "$sha_file"
    else
        result "SHA256" "FAIL" "checksum verification failed: $sha_file"
    fi
else
    result "SHA256" "FAIL" "missing checksum file: $sha_file"
fi

singbox_json_count=$(find "$RESTORE_ROOT/etc-sing-box" -type f -name '*.json' -print 2>/dev/null | wc -l)
if [ "$singbox_json_count" -gt 0 ]; then
    invalid_json=0
    while IFS= read -r json_file; do
        if ! python3 -m json.tool "$json_file" >/dev/null 2>&1; then
            invalid_json=1
            break
        fi
    done < <(find "$RESTORE_ROOT/etc-sing-box" -type f -name '*.json' -print 2>/dev/null)

    if [ "$invalid_json" -eq 0 ]; then
        result "sing-box JSON files" "PASS" "found and parsed $singbox_json_count JSON file(s)"
    else
        result "sing-box JSON files" "FAIL" "at least one restored sing-box JSON is invalid"
    fi
else
    result "sing-box JSON files" "FAIL" "no JSON files under etc-sing-box"
fi

if exists "secrets.env"; then
    secrets_path="$RESTORE_ROOT/secrets.env"
elif exists "etc-sing-box/secrets.env"; then
    secrets_path="$RESTORE_ROOT/etc-sing-box/secrets.env"
else
    secrets_path=""
fi

if [ -n "$secrets_path" ]; then
    result "secrets.env" "PASS" "$secrets_path"
else
    result "secrets.env" "FAIL" "not found"
fi

unit_count=$(find "$RESTORE_ROOT/systemd" -maxdepth 1 -type f \( -name '*.service' -o -name '*.timer' \) -print 2>/dev/null | wc -l)
if [ "$unit_count" -gt 0 ]; then
    result "systemd unit files" "PASS" "found $unit_count unit file(s)"
else
    result "systemd unit files" "FAIL" "no .service/.timer files under systemd"
fi

if exists "databases/mariadb-all.sql"; then
    result "MariaDB dump" "PASS" "$RESTORE_ROOT/databases/mariadb-all.sql"
else
    result "MariaDB dump" "FAIL" "databases/mariadb-all.sql not found"
fi

if exists "databases/postgresql-all.sql"; then
    result "PostgreSQL dump" "PASS" "$RESTORE_ROOT/databases/postgresql-all.sql"
else
    result "PostgreSQL dump" "FAIL" "databases/postgresql-all.sql not found"
fi

if [ -d "$RESTORE_ROOT/bots" ] && find "$RESTORE_ROOT/bots" -mindepth 1 -maxdepth 2 -print -quit 2>/dev/null | grep -q .; then
    result "bots" "PASS" "$RESTORE_ROOT/bots"
else
    result "bots" "FAIL" "bots directory missing or empty"
fi

if [ -d "$RESTORE_ROOT/vpn-gitops" ] && [ -d "$RESTORE_ROOT/vpn-gitops/.git" ]; then
    result "vpn-gitops" "PASS" "$RESTORE_ROOT/vpn-gitops"
else
    result "vpn-gitops" "FAIL" "vpn-gitops directory or .git missing"
fi

permission_failures=()
if [ -n "$secrets_path" ] && ! mode_is "$secrets_path" '^(600|640)$'; then
    permission_failures+=("$(basename "$secrets_path") mode $(stat -c '%a' "$secrets_path")")
fi

while IFS= read -r unit; do
    if ! mode_is "$unit" '^644$'; then
        permission_failures+=("$(basename "$unit") mode $(stat -c '%a' "$unit")")
    fi
done < <(find "$RESTORE_ROOT/systemd" -maxdepth 1 -type f \( -name '*.service' -o -name '*.timer' \) -print 2>/dev/null)

while IFS= read -r script; do
    case "$script" in
        */venv/*) continue ;;
    esac
    if ! mode_is "$script" '^(775|755|750|700)$'; then
        permission_failures+=("${script#$RESTORE_ROOT/} mode $(stat -c '%a' "$script")")
    fi
done < <(find "$RESTORE_ROOT" -type f -name '*.sh' -print 2>/dev/null)

if [ "${#permission_failures[@]}" -eq 0 ]; then
    result "file permissions" "PASS" "secrets.env, systemd units and shell scripts have expected modes"
else
    result "file permissions" "FAIL" "${permission_failures[*]}"
fi

missing_dirs=()
for dir in etc-sing-box systemd databases bots vpn-gitops; do
    [ -d "$RESTORE_ROOT/$dir" ] || missing_dirs+=("$dir")
done

if [ "${#missing_dirs[@]}" -eq 0 ]; then
    result "directory structure" "PASS" "etc-sing-box systemd databases bots vpn-gitops"
else
    result "directory structure" "FAIL" "missing: ${missing_dirs[*]}"
fi

singbox_config="$RESTORE_ROOT/etc-sing-box/config.json"
if [ ! -f "$singbox_config" ]; then
    result "sing-box check" "FAIL" "etc-sing-box/config.json not found"
elif ! command -v sing-box >/dev/null 2>&1; then
    result "sing-box check" "FAIL" "sing-box binary not found"
elif sing-box check -D "$RESTORE_ROOT/etc-sing-box" -c "$singbox_config" >/dev/null 2>&1; then
    result "sing-box check" "PASS" "$singbox_config"
else
    result "sing-box check" "FAIL" "sing-box check failed for restored config"
fi

printf 'Restore test for: %s\n' "$archive"
printf 'Temporary restore dir: %s\n\n' "$WORK_DIR"
printf '%-28s %-6s %s\n' "CHECK" "STATUS" "DETAIL"
printf '%-28s %-6s %s\n' "-----" "------" "------"

failed=0
for row in "${RESULTS[@]}"; do
    IFS='|' read -r status name detail <<< "$row"
    printf '%-28s %-6s %s\n' "$name" "$status" "$detail"
    [ "$status" = "FAIL" ] && failed=1
done

exit "$failed"
