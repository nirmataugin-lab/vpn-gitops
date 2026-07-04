#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/vpn-gitops"
BRANCH="main"
REMOTE="origin"
NODE_TYPE_FILE="/etc/vpn-node-type"
SECRETS_FILE="/etc/sing-box/secrets.env"
DEST="/etc/sing-box/config.json"
TMP="/tmp/sing-box.config.rendered.json"
BAK="${DEST}.bak"

log() { echo "[VPN-GITOPS] $*"; }
fail() { echo "[VPN-GITOPS] ERROR: $*" >&2; exit 1; }

# ------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------
command -v git      >/dev/null || fail "git is not installed"
command -v jq       >/dev/null || fail "jq is not installed"
command -v envsubst >/dev/null || fail "envsubst is not installed (apt-get install gettext-base)"

[ -d "$REPO_DIR/.git" ]              || fail "$REPO_DIR is not a git repository"
[ -f "$NODE_TYPE_FILE" ]             || fail "Missing $NODE_TYPE_FILE — must contain vps1 or vps2"
[ -f "$SECRETS_FILE" ]               || fail "Missing $SECRETS_FILE"

# ------------------------------------------------------------------
# Detect node type
# ------------------------------------------------------------------
NODE_TYPE="$(tr -d '[:space:]' < "$NODE_TYPE_FILE")"
case "$NODE_TYPE" in
  vps1) TEMPLATE="$REPO_DIR/vps1/sing-box.template.json" ;;
  vps2) TEMPLATE="$REPO_DIR/vps2/sing-box.template.json" ;;
  *)    fail "Unknown node type '$NODE_TYPE' (expected vps1 or vps2)" ;;
esac
[ -f "$TEMPLATE" ] || fail "Template not found: $TEMPLATE"

# ------------------------------------------------------------------
# Step 1 — git pull
# ------------------------------------------------------------------
cd "$REPO_DIR"
log "Pulling latest changes from $REMOTE/$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH" 2>&1 || fail "git pull failed"

# ------------------------------------------------------------------
# Step 2 — load secrets
# ------------------------------------------------------------------
set -a
# shellcheck disable=SC1090
source "$SECRETS_FILE"
set +a

# ------------------------------------------------------------------
# Step 3 — validate required environment variables
# ------------------------------------------------------------------
REQUIRED_COMMON=(
  CASCADE_UUID
  VPS2_PORT
  VPS2_REALITY_SERVER_NAME
  VPS2_REALITY_SHORT_ID
)
REQUIRED_VPS1=(
  CLIENT_UUID
  VPS1_REALITY_PRIVATE_KEY
  VPS1_REALITY_SHORT_ID
  REALITY_SERVER_NAME
  VPS2_IP
  VPS2_REALITY_PUBLIC_KEY
)
REQUIRED_VPS2=(
  VPS2_REALITY_PRIVATE_KEY
)

check_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    fail "Required variable '$name' is empty or missing in $SECRETS_FILE"
  fi
}

for v in "${REQUIRED_COMMON[@]}"; do check_var "$v"; done
if [ "$NODE_TYPE" = "vps1" ]; then
  for v in "${REQUIRED_VPS1[@]}"; do check_var "$v"; done
else
  for v in "${REQUIRED_VPS2[@]}"; do check_var "$v"; done
fi

# ------------------------------------------------------------------
# Step 4 — render template
# ------------------------------------------------------------------
log "Rendering template: $TEMPLATE"
envsubst < "$TEMPLATE" > "$TMP"

# ------------------------------------------------------------------
# Step 5 — validate rendered config
# ------------------------------------------------------------------
log "Validating JSON syntax"
jq empty "$TMP"

if command -v sing-box >/dev/null; then
  log "Validating with sing-box check"
  sing-box check -c "$TMP" || fail "sing-box config validation failed"
fi

# ------------------------------------------------------------------
# Step 6 — backup current config
# ------------------------------------------------------------------
if [ -f "$DEST" ]; then
  log "Backing up current config to $BAK"
  cp "$DEST" "$BAK"
fi

# ------------------------------------------------------------------
# Step 7 — deploy new config
# ------------------------------------------------------------------
log "Applying rendered config"
install -m 600 "$TMP" "$DEST"

# ------------------------------------------------------------------
# Step 8 — restart sing-box
# ------------------------------------------------------------------
log "Restarting sing-box"
systemctl restart sing-box || true
sleep 2

# ------------------------------------------------------------------
# Step 9 — verify and rollback on failure
# ------------------------------------------------------------------
if systemctl is-active --quiet sing-box; then
  log "Deploy successful"
  rm -f "$TMP" "$BAK"
  exit 0
fi

log "sing-box failed to start — rolling back"
if [ -f "$BAK" ]; then
  install -m 600 "$BAK" "$DEST"
  systemctl restart sing-box || true
  log "Rollback complete — previous config restored"
fi
rm -f "$TMP"
fail "Deploy failed — rolled back to previous config"
