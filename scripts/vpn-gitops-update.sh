#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/vpn-gitops"
BRANCH="main"
REMOTE="origin"
NODE_TYPE_FILE="/etc/vpn-node-type"
SECRETS_FILE="/etc/sing-box/secrets.env"
CONF_DIR="/etc/sing-box/conf"
TMP_DIR="/tmp/sing-box-render.$$"
BAK_DIR="/tmp/sing-box-backup.$(date +%Y%m%d_%H%M%S)"

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
[ -d "$CONF_DIR" ]                   || fail "Missing $CONF_DIR"

# ------------------------------------------------------------------
# Detect node type
# ------------------------------------------------------------------
NODE_TYPE="$(tr -d '[:space:]' < "$NODE_TYPE_FILE")"
case "$NODE_TYPE" in
  vps1|vps2) log "Node type: $NODE_TYPE" ;;
  *)         fail "Unknown node type '$NODE_TYPE' (expected vps1 or vps2)" ;;
esac

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
# Step 3 — detect mode: split (conf/*.template) or combined
# ------------------------------------------------------------------
TEMPLATE_DIR="$REPO_DIR/$NODE_TYPE/conf"
COMBINED_TEMPLATE="$REPO_DIR/$NODE_TYPE/sing-box.template.json"

USE_SPLIT=false
if [ -d "$TEMPLATE_DIR" ] && ls "$TEMPLATE_DIR"/*.template >/dev/null 2>&1; then
  USE_SPLIT=true
  log "Mode: split templates ($TEMPLATE_DIR)"
elif [ -f "$COMBINED_TEMPLATE" ]; then
  log "Mode: combined template ($COMBINED_TEMPLATE)"
else
  fail "No templates found for $NODE_TYPE (checked $TEMPLATE_DIR and $COMBINED_TEMPLATE)"
fi

# ------------------------------------------------------------------
# Step 4 — extract & validate required variables from templates
# ------------------------------------------------------------------
extract_vars() {
  local dir_or_file="$1"
  if [ -d "$dir_or_file" ]; then
    grep -rohP '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "$dir_or_file" 2>/dev/null || true
  elif [ -f "$dir_or_file" ]; then
    grep -oP '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "$dir_or_file" 2>/dev/null || true
  fi
}

REQUIRED_VARS=()
while IFS= read -r var; do
  name="${var#\$\{}"
  name="${name%\}}"
  REQUIRED_VARS+=("$name")
done < <(if "$USE_SPLIT"; then extract_vars "$TEMPLATE_DIR"; else extract_vars "$COMBINED_TEMPLATE"; fi | sort -u)

if [ ${#REQUIRED_VARS[@]} -eq 0 ]; then
  fail "No variables found in templates — nothing to render"
fi

log "Required variables: ${REQUIRED_VARS[*]}"
for name in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!name:-}" ]; then
    fail "Required variable '$name' is empty or missing in $SECRETS_FILE"
  fi
done

# ------------------------------------------------------------------
# Step 5 — render templates
# ------------------------------------------------------------------
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

if [ "$USE_SPLIT" = true ]; then
  for tmpl in "$TEMPLATE_DIR"/*.template; do
    [ -f "$tmpl" ] || continue
    base="$(basename "$tmpl" .template)"
    rendered="$TMP_DIR/$base"
    log "Rendering $tmpl -> $rendered"
    envsubst < "$tmpl" > "$rendered"
    jq empty "$rendered" || fail "Invalid JSON in $rendered (from $tmpl)"
    if grep -qP '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "$rendered"; then
      fail "Unsubstituted variables found in $rendered — check $SECRETS_FILE"
    fi
  done
  log "All split configs rendered and validated"
else
  rendered="$TMP_DIR/config.json"
  log "Rendering $COMBINED_TEMPLATE -> $rendered"
  envsubst < "$COMBINED_TEMPLATE" > "$rendered"
  jq empty "$rendered" || fail "Invalid JSON in rendered config"
  if grep -qP '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "$rendered"; then
    fail "Unsubstituted variables found in $rendered — check $SECRETS_FILE"
  fi
  log "Combined config rendered and validated"
fi

# ------------------------------------------------------------------
# Step 6 — backup current conf directory
# ------------------------------------------------------------------
log "Backing up $CONF_DIR to $BAK_DIR"
cp -a "$CONF_DIR" "$BAK_DIR"

# ------------------------------------------------------------------
# Step 7 — deploy rendered configs
# ------------------------------------------------------------------
deploy_split() {
  log "Deploying split configs to $CONF_DIR"
  for f in "$CONF_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    if [ -f "$TMP_DIR/$base" ]; then
      install -m 600 "$TMP_DIR/$base" "$f"
      log "  Updated $f"
    else
      rm -f "$f"
      log "  Removed stale $f"
    fi
  done
  for f in "$TMP_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    target="$CONF_DIR/$base"
    if [ ! -f "$target" ]; then
      install -m 600 "$f" "$target"
      log "  Created $target"
    fi
  done
}

deploy_combined() {
  local src="$1"
  local dst="/etc/sing-box/config.json"
  log "Deploying combined config to $dst"
  install -m 600 "$src" "$dst"
}

if [ "$USE_SPLIT" = true ]; then
  deploy_split
else
  deploy_combined "$TMP_DIR/config.json"
fi

# ------------------------------------------------------------------
# Step 8 — validate with sing-box check
# ------------------------------------------------------------------
if command -v sing-box >/dev/null; then
  if [ "$USE_SPLIT" = true ]; then
    log "Validating with: sing-box check -C $CONF_DIR"
    sing-box check -C "$CONF_DIR" || fail "sing-box config validation failed"
  else
    log "Validating with: sing-box check -c /etc/sing-box/config.json"
    sing-box check -c /etc/sing-box/config.json || fail "sing-box config validation failed"
  fi
else
  log "sing-box binary not found — skipping config validation"
fi

# ------------------------------------------------------------------
# Step 9 — restart sing-box
# ------------------------------------------------------------------
log "Restarting sing-box"
systemctl restart sing-box || true
sleep 2

# ------------------------------------------------------------------
# Step 10 — verify and rollback on failure
# ------------------------------------------------------------------
if systemctl is-active --quiet sing-box; then
  log "Deploy successful"
  rm -rf "$TMP_DIR" "$BAK_DIR"
  exit 0
fi

log "sing-box failed to start — rolling back"
if [ -d "$BAK_DIR" ]; then
  log "Restoring backup from $BAK_DIR"
  rm -rf "$CONF_DIR"
  cp -a "$BAK_DIR" "$CONF_DIR"
  systemctl restart sing-box || true
  log "Rollback complete — previous config restored"
fi
rm -rf "$TMP_DIR"
fail "Deploy failed — rolled back to previous config"
