#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/vpn-gitops"
BRANCH="main"
REMOTE="origin"
NODE_TYPE_FILE="/etc/vpn-node-type"
SECRETS_FILE="/etc/sing-box/secrets.env"
CONF_DIR="/etc/sing-box/conf"
COMBINED_DEST="/etc/sing-box/config.json"
TMP_DIR="/tmp/sing-box-render.$$"
BAK_DIR="/tmp/sing-box-backup.$(date +%Y%m%d_%H%M%S)"
BAK="/tmp/sing-box-config-backup.$(date +%Y%m%d_%H%M%S).json"

log() { echo "[VPN-GITOPS] $*"; }
fail() { echo "[VPN-GITOPS] ERROR: $*" >&2; exit 1; }

# ------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------
command -v git      >/dev/null || fail "git is not installed"
command -v jq       >/dev/null || fail "jq is not installed"
command -v envsubst >/dev/null || fail "envsubst is not installed (apt-get install gettext-base)"

[ -d "$REPO_DIR/.git" ]              || fail "$REPO_DIR is not a git repository"
[ -f "$NODE_TYPE_FILE" ]             || fail "Missing $NODE_TYPE_FILE — must contain vps1, vps2 or vps3"
[ -f "$SECRETS_FILE" ]               || fail "Missing $SECRETS_FILE"

# ------------------------------------------------------------------
# Detect node type
# ------------------------------------------------------------------
NODE_TYPE="$(tr -d '[:space:]' < "$NODE_TYPE_FILE")"
case "$NODE_TYPE" in
  vps1|vps2|vps3) log "Node type: $NODE_TYPE" ;;
  *)              fail "Unknown node type '$NODE_TYPE' (expected vps1, vps2 or vps3)" ;;
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
# Step 6 — validate with sing-box check
# ------------------------------------------------------------------
if command -v sing-box >/dev/null; then
  if [ "$USE_SPLIT" = true ]; then
    log "Validating with: sing-box check -C $TMP_DIR"
    sing-box check -C "$TMP_DIR" || fail "sing-box config validation failed"
  else
    log "Validating with: sing-box check -c $TMP_DIR/config.json"
    sing-box check -c "$TMP_DIR/config.json" || fail "sing-box config validation failed"
  fi
else
  log "sing-box binary not found — skipping config validation"
fi

# ------------------------------------------------------------------
# Step 7 — compare rendered config with current config
# ------------------------------------------------------------------
has_split_changes() {
  local f base target

  if [ ! -d "$CONF_DIR" ]; then
    return 0
  fi

  for f in "$TMP_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    target="$CONF_DIR/$base"
    if [ ! -f "$target" ] || ! cmp -s "$target" "$f"; then
      return 0
    fi
  done

  for f in "$CONF_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    if [ ! -f "$TMP_DIR/$base" ]; then
      return 0
    fi
  done

  return 1
}

show_split_diff() {
  local f base target

  if [ ! -d "$CONF_DIR" ]; then
    log "Current config directory $CONF_DIR does not exist"
  fi

  for f in "$TMP_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    target="$CONF_DIR/$base"
    if [ ! -f "$target" ]; then
      diff -u /dev/null "$f" || true
    elif ! cmp -s "$target" "$f"; then
      diff -u "$target" "$f" || true
    fi
  done

  for f in "$CONF_DIR"/*.json; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    if [ ! -f "$TMP_DIR/$base" ]; then
      diff -u "$f" /dev/null || true
    fi
  done
}

if [ "$USE_SPLIT" = true ]; then
  if has_split_changes; then
    log "Config changes detected:"
    show_split_diff
  else
    log "No config changes, skipping deploy and restart"
    rm -rf "$TMP_DIR"
    exit 0
  fi
else
  if [ -f "$COMBINED_DEST" ] && cmp -s "$COMBINED_DEST" "$TMP_DIR/config.json"; then
    log "No config changes, skipping deploy and restart"
    rm -rf "$TMP_DIR"
    exit 0
  fi
  log "Config changes detected:"
  if [ -f "$COMBINED_DEST" ]; then
    diff -u "$COMBINED_DEST" "$TMP_DIR/config.json" || true
  else
    diff -u /dev/null "$TMP_DIR/config.json" || true
  fi
fi

# ------------------------------------------------------------------
# Step 8 — backup current config
# ------------------------------------------------------------------
if [ "$USE_SPLIT" = true ]; then
  if [ -d "$CONF_DIR" ]; then
    log "Backing up $CONF_DIR to $BAK_DIR"
    cp -a "$CONF_DIR" "$BAK_DIR"
  fi
else
  if [ -f "$COMBINED_DEST" ]; then
    log "Backing up current config to $BAK"
    cp "$COMBINED_DEST" "$BAK"
  fi
fi

# ------------------------------------------------------------------
# Step 9 — deploy rendered configs
# ------------------------------------------------------------------
deploy_split() {
  log "Deploying split configs to $CONF_DIR"
  mkdir -p "$CONF_DIR"
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
# Step 10 — restart sing-box
# ------------------------------------------------------------------
log "Restarting sing-box"
systemctl restart sing-box || true
sleep 2

# ------------------------------------------------------------------
# Step 11 — verify and rollback on failure
# ------------------------------------------------------------------
if systemctl is-active --quiet sing-box; then
  log "Deploy successful"
  rm -rf "$TMP_DIR" "$BAK_DIR"
  exit 0
fi

log "sing-box failed to start — rolling back"
if [ "$USE_SPLIT" = true ] && [ -d "$BAK_DIR" ]; then
  log "Restoring backup from $BAK_DIR"
  rm -rf "$CONF_DIR"
  cp -a "$BAK_DIR" "$CONF_DIR"
  systemctl restart sing-box || true
  log "Rollback complete — previous config restored"
elif [ -f "$BAK" ]; then
  install -m 600 "$BAK" "$COMBINED_DEST"
  systemctl restart sing-box || true
  log "Rollback complete — previous config restored"
fi
rm -rf "$TMP_DIR"
fail "Deploy failed — rolled back to previous config"
