#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/backup"
ARCHIVE_DIR="${BACKUP_DIR}/archive"
TIMESTAMP=$(date +%Y%m%d-%H%M)
ARCHIVE_NAME="backup-${TIMESTAMP}.tar.zst"
ARCHIVE_PATH="${ARCHIVE_DIR}/${ARCHIVE_NAME}"
WORK_DIR=$(mktemp -d)
MAX_ARCHIVES=14

cleanup() {
    rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting backup..."

# === VPN ===
log "Backing up VPN..."
if [ -d /etc/sing-box ]; then
    cp -a /etc/sing-box "${WORK_DIR}/etc-sing-box"
fi
if [ -d /opt/vpn-gitops ]; then
    cp -a /opt/vpn-gitops "${WORK_DIR}/vpn-gitops"
fi
mkdir -p "${WORK_DIR}/systemd"

# Explicit unit files (produce WARN if missing)
for unit in \
    /etc/systemd/system/sing-box.service \
    /etc/systemd/system/vpn_bot.service \
    /etc/systemd/system/alsero_crm.service \
    /etc/systemd/system/vpn-backup.service \
    /etc/systemd/system/vpn-backup.timer; do
    if [ -e "${unit}" ]; then
        cp -a "${unit}" "${WORK_DIR}/systemd/"
    else
        log "WARN: ${unit} not found, skipping"
    fi
done

# Wildcard patterns (silent if no match)
for unit in /etc/systemd/system/vpn-gitops-update.* /etc/systemd/system/vpn-failover.*; do
    [ -e "${unit}" ] && cp -a "${unit}" "${WORK_DIR}/systemd/"
done

# === Secrets ===
log "Backing up Secrets..."
if [ -f /etc/sing-box/secrets.env ]; then
    cp -a /etc/sing-box/secrets.env "${WORK_DIR}/secrets.env"
fi

# === Bots ===
log "Backing up Bots..."
if [ -d /opt/bots ]; then
    cp -a /opt/bots "${WORK_DIR}/bots"
fi

# === Databases ===
log "Backing up Databases..."
mkdir -p "${WORK_DIR}/databases"
if command -v mariadb &>/dev/null || command -v mysql &>/dev/null; then
    MYSQL_CMD=$(command -v mariadb || command -v mysql)
    MYSQLDUMP_CMD=$(command -v mariadb-dump || command -v mysqldump)
    if [ -n "${MYSQLDUMP_CMD}" ] && ${MYSQL_CMD} -e "SELECT 1" &>/dev/null; then
        ${MYSQLDUMP_CMD} --all-databases > "${WORK_DIR}/databases/mariadb-all.sql" 2>/dev/null || \
            log "WARNING: mysqldump failed"
    else
        log "WARNING: MariaDB/MySQL not available or not accessible"
    fi
fi
if command -v pg_dumpall &>/dev/null; then
    pg_dumpall > "${WORK_DIR}/databases/postgresql-all.sql" 2>/dev/null || \
        log "WARNING: pg_dumpall failed"
else
    log "WARNING: PostgreSQL not available"
fi

# === System ===
log "Backing up System configs..."
mkdir -p "${WORK_DIR}/system"
crontab -l > "${WORK_DIR}/system/crontab.txt" 2>/dev/null || log "WARNING: no crontab"
mkdir -p "${WORK_DIR}/system/systemd-overrides"
for unit_dir in /etc/systemd/system/*.d/; do
    if [ -d "${unit_dir}" ]; then
        unit_name=$(basename "$(dirname "${unit_dir}")")
        cp -a "${unit_dir}" "${WORK_DIR}/system/systemd-overrides/${unit_name}.d/" 2>/dev/null || true
    fi
done
if command -v ufw &>/dev/null; then
    ufw status verbose > "${WORK_DIR}/system/ufw-status.txt" 2>/dev/null || true
fi
if command -v nft &>/dev/null; then
    nft list ruleset > "${WORK_DIR}/system/nftables-rules.txt" 2>/dev/null || true
fi
if [ -f /etc/ssh/sshd_config ]; then
    cp -a /etc/ssh/sshd_config "${WORK_DIR}/system/sshd_config"
fi

# === Create archive ===
log "Creating archive: ${ARCHIVE_NAME}"
tar -C "${WORK_DIR}" -c . | zstd -T0 -f -o "${ARCHIVE_PATH}"

# === SHA256 ===
log "Generating SHA256..."
sha256sum "${ARCHIVE_PATH}" > "${ARCHIVE_PATH}.sha256"

# === Verification ===
log "Verifying backup..."
sha256sum -c "${ARCHIVE_PATH}.sha256"
tar -tf "${ARCHIVE_PATH}" > /dev/null
log "Backup verified successfully"

# === Rotate old archives ===
log "Rotating old archives..."
count=$(ls -1 "${ARCHIVE_DIR}"/backup-*.tar.zst 2>/dev/null | wc -l)
if [ "${count}" -gt "${MAX_ARCHIVES}" ]; then
    ls -1t "${ARCHIVE_DIR}"/backup-*.tar.zst | tail -n $((count - MAX_ARCHIVES)) | while read oldfile; do
        rm -f "${oldfile}" "${oldfile}.sha256"
        log "Removed old backup: $(basename "${oldfile}")"
    done
fi

log "Backup completed: ${ARCHIVE_NAME}"
log "Size: $(du -h "${ARCHIVE_PATH}" | cut -f1)"
