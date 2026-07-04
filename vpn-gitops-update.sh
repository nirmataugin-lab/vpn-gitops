#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/vpn-gitops"
BRANCH="main"
NODE_TYPE_FILE="/etc/vpn-node-type"
SECRETS_FILE="/etc/sing-box/secrets.env"
DEST="/etc/sing-box/config.json"
TMP="/tmp/sing-box.config.rendered.json"

log() { echo "[VPN-GITOPS] $*"; }
fail() { echo "[VPN-GITOPS] ERROR: $*" >&2; exit 1; }

command -v git >/dev/null || fail "git is not installed"
command -v jq >/dev/null || fail "jq is not installed"
command -v envsubst >/dev/null || fail "envsubst is not installed. Install gettext-base."

[ -d "$REPO_DIR/.git" ] || fail "$REPO_DIR is not a git repo"
[ -f "$NODE_TYPE_FILE" ] || fail "Missing $NODE_TYPE_FILE. Put vps1 or vps2 inside."
[ -f "$SECRETS_FILE" ] || fail "Missing $SECRETS_FILE"

NODE_TYPE="$(tr -d '[:space:]' < "$NODE_TYPE_FILE")"
case "$NODE_TYPE" in
  vps1) TEMPLATE="$REPO_DIR/vps1/sing-box.template.json" ;;
  vps2) TEMPLATE="$REPO_DIR/vps2/sing-box.template.json" ;;
  *) fail "Unknown node type: $NODE_TYPE" ;;
esac

[ -f "$TEMPLATE" ] || fail "Template not found: $TEMPLATE"

cd "$REPO_DIR"
log "Fetching latest repo"
git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" != "$REMOTE" ]; then
  log "New changes detected, resetting to origin/$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  log "Repo already up to date; rendering anyway to catch local secrets changes"
fi

set -a
# shellcheck disable=SC1090
source "$SECRETS_FILE"
set +a

REQUIRED_COMMON=(CASCADE_UUID VPS2_PORT VPS2_REALITY_SERVER_NAME VPS2_REALITY_SHORT_ID)
REQUIRED_VPS1=(CLIENT_UUID VPS1_REALITY_PRIVATE_KEY VPS1_REALITY_SHORT_ID REALITY_SERVER_NAME VPS2_IP VPS2_REALITY_PUBLIC_KEY)
REQUIRED_VPS2=(VPS2_REALITY_PRIVATE_KEY)

check_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    fail "Secret variable $name is empty or missing in $SECRETS_FILE"
  fi
}

for v in "${REQUIRED_COMMON[@]}"; do check_var "$v"; done
if [ "$NODE_TYPE" = "vps1" ]; then
  for v in "${REQUIRED_VPS1[@]}"; do check_var "$v"; done
else
  for v in "${REQUIRED_VPS2[@]}"; do check_var "$v"; done
fi

log "Rendering template: $TEMPLATE"
envsubst < "$TEMPLATE" > "$TMP"

log "Validating rendered JSON"
jq empty "$TMP"

log "Backing up current config"
if [ -f "$DEST" ]; then
  cp "$DEST" "${DEST}.bak"
fi

log "Applying rendered config"
install -m 600 "$TMP" "$DEST"

log "Restarting sing-box"
systemctl restart sing-box
sleep 2

if ! systemctl is-active --quiet sing-box; then
  log "sing-box failed, rolling back"
  if [ -f "${DEST}.bak" ]; then
    cp "${DEST}.bak" "$DEST"
    systemctl restart sing-box || true
  fi
  fail "Deploy failed and rollback attempted"
fi

log "Deploy OK"
