#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_DIR="/opt/backup/archive"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

latest=$(ls -1t "$ARCHIVE_DIR"/backup-*.tar.zst 2>/dev/null | head -1)
if [ -z "$latest" ]; then
    err "No backup archives found in ${ARCHIVE_DIR}"
    exit 1
fi

sha_file="${latest}.sha256"
if [ ! -f "$sha_file" ]; then
    err "SHA256 file not found: ${sha_file}"
    exit 1
fi

echo "============================================"
echo "  DRY-RUN: Restore verification"
echo "  Archive: $(basename "$latest")"
echo "  Size:    $(du -h "$latest" | cut -f1)"
echo "============================================"
echo ""

echo ">>> [1/5] Checking SHA256 integrity..."
if sha256sum -c "$sha_file" >/dev/null 2>&1; then
    echo "  SHA256: OK ($(awk '{print $1}' "$sha_file"))"
else
    err "SHA256 mismatch! Archive is corrupted."
    exit 1
fi
echo ""

echo ">>> [2/5] Archive contents (top-level):"
tar -tf "$latest" | grep -E '^\./[^/]+/?$' | sort | while read -r entry; do
    if [[ "$entry" == */ ]]; then
        echo "  DIR  $entry"
    else
        size=$(tar -xf "$latest" --to-stdout "$entry" 2>/dev/null | wc -c)
        echo "  FILE $entry  ($(numfmt --to=iec "$size" 2>/dev/null || echo "${size}B"))"
    fi
done
echo ""

echo ">>> [3/5] Verifying required components..."
all_ok=true
for entry in etc-sing-box vpn-gitops bots databases systemd; do
    if tar -tf "$latest" "./${entry}/" &>/dev/null; then
        count=$(tar -tf "$latest" "./${entry}/" | wc -l)
        echo "  [OK] ./${entry}/ ($count entries)"
    else
        err "  [MISSING] ./${entry}/"
        all_ok=false
    fi
done
if tar -tf "$latest" "./secrets.env" &>/dev/null; then
    echo "  [OK] ./secrets.env"
else
    err "  [MISSING] ./secrets.env"
    all_ok=false
fi
echo ""
if [ "$all_ok" = true ]; then
    echo ">>> [3/5] All required components present."
else
    err "Some required components are missing from the archive!"
    exit 1
fi
echo ""

echo ">>> [4/5] Database dumps:"
for dump in mariadb-all.sql postgresql-all.sql; do
    if tar -tf "$latest" "./databases/${dump}" &>/dev/null; then
        dsize=$(tar -xf "$latest" --to-stdout "./databases/${dump}" 2>/dev/null | wc -c)
        echo "  [OK] ${dump} ($(numfmt --to=iec "$dsize" 2>/dev/null || echo "${dsize}B"))"
    else
        echo "  [--] ${dump} (not present)"
    fi
done
echo ""

echo ">>> [5/5] Systemd units in archive:"
tar -tf "$latest" | grep '^\./systemd/' | grep -v '/$' | while read -r f; do
    echo "  $(basename "$f")"
done
echo ""

echo "     Verifying expected systemd units..."
expected_units=(
    sing-box.service
    vpn_bot.service
    alsero_crm.service
    vpn-backup.service
    vpn-backup.timer
    vpn-gitops-update.service
    vpn-gitops-update.timer
    vpn-failover.service
    vpn-failover.timer
)
all_units_ok=true
for unit in "${expected_units[@]}"; do
    if tar -tf "$latest" "./systemd/${unit}" &>/dev/null; then
        echo "  [OK] ${unit}"
    else
        err "  [MISSING] ${unit}"
        all_units_ok=false
    fi
done
if [ "$all_units_ok" = false ]; then
    err "Some expected systemd units are missing from archive!"
    exit 1
fi
echo "  All expected systemd units present."
echo ""

echo "============================================"
echo "  Dry-run completed successfully."
echo "  No files were restored."
echo "============================================"
