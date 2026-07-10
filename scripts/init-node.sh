#!/usr/bin/env bash
set -euo pipefail

NODE_TYPE_FILE="/etc/vpn-node-type"
SECRETS_FILE="/etc/sing-box/secrets.env"

log() { echo "[INIT-NODE] $*"; }
err() { echo "[INIT-NODE] ERROR: $*" >&2; exit 1; }

# ------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------
command -v sing-box >/dev/null || err "sing-box is not installed"
command -v openssl   >/dev/null || err "openssl is not installed"

[ -f "$NODE_TYPE_FILE" ] || err "Missing $NODE_TYPE_FILE -- run: echo vps1|vps2|vps3 > $NODE_TYPE_FILE"

NODE_TYPE="$(tr -d '[:space:]' < "$NODE_TYPE_FILE")"
case "$NODE_TYPE" in
  vps1|vps2|vps3) log "Node type detected: $NODE_TYPE" ;;
  *)              err "Unknown node type '$NODE_TYPE' (expected vps1, vps2 or vps3)" ;;
esac

# ------------------------------------------------------------------
# Generate one-shot values
# ------------------------------------------------------------------
gen_uuid()     { sing-box generate uuid; }
gen_keypair()  { sing-box generate reality-keypair; }
gen_short_id() { openssl rand -hex 8; }

# ------------------------------------------------------------------
# Create secrets directory
# ------------------------------------------------------------------
mkdir -p /etc/sing-box
touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

# ------------------------------------------------------------------
# Helper: write key=value to secrets file
# ------------------------------------------------------------------
write_secret() {
  local key="$1" value="$2"
  sed -i "/^${key}=/d" "$SECRETS_FILE"
  echo "${key}=\"${value}\"" >> "$SECRETS_FILE"
}

# ------------------------------------------------------------------
# Prompt helper
# ------------------------------------------------------------------
prompt() {
  local var="$1" label="$2" default="${3:-}"
  local val
  if [ -n "$default" ]; then
    read -r -p "$label [$default]: " val
    val="${val:-$default}"
  else
    read -r -p "$label: " val
  fi
  write_secret "$var" "$val"
  echo "$val"
}

# ==================================================================
# VPS1
# ==================================================================
init_vps1() {
  log "Generating VPS1 secrets"

  CLIENT_UUID=$(gen_uuid)
  write_secret "CLIENT_UUID" "$CLIENT_UUID"
  log "CLIENT_UUID generated"

  eval "$(gen_keypair | sed -n 's/^PrivateKey: \(.*\)/VPS1_PRIVATE_KEY=\1/p; s/^PublicKey: \(.*\)/VPS1_PUBLIC_KEY=\1/p')"
  write_secret "VPS1_REALITY_PRIVATE_KEY" "$VPS1_PRIVATE_KEY"
  write_secret "VPS1_REALITY_PUBLIC_KEY" "$VPS1_PUBLIC_KEY"
  log "VPS1 Reality keypair generated"

  VPS1_SHORT_ID=$(gen_short_id)
  write_secret "VPS1_REALITY_SHORT_ID" "$VPS1_SHORT_ID"
  log "VPS1_REALITY_SHORT_ID generated"

  echo ""
  log "Enter the following values for VPS1:"

  prompt "REALITY_SERVER_NAME" "VPS1 Reality server name (your domain)"
  prompt "CASCADE_UUID" "Cascade UUID (generate on VPS2, paste here)"
  prompt "VPS2_IP" "VPS2 public IP address"
  prompt "VPS2_PORT" "VPS2 inbound port" "443"
  prompt "VPS2_REALITY_SERVER_NAME" "VPS2 Reality server name" "www.cloudflare.com"
  prompt "VPS2_REALITY_PUBLIC_KEY" "VPS2 Reality public key (generated on VPS2)"
  prompt "VPS2_REALITY_SHORT_ID" "VPS2 Reality short ID (generated on VPS2)"

  echo ""
  log "VPS1 secrets written to $SECRETS_FILE"
  echo ""
  echo "============================================================"
  echo "  SHARE THESE WITH VPS1:"
  echo "    VPS1_REALITY_PUBLIC_KEY = $VPS1_PUBLIC_KEY"
  echo "    VPS1_REALITY_SHORT_ID   = $VPS1_SHORT_ID"
  echo "============================================================"
}

# ==================================================================
# VPS2
# ==================================================================
init_vps2() {
  log "Generating VPS2 secrets"

  CASCADE_UUID=$(gen_uuid)
  write_secret "CASCADE_UUID" "$CASCADE_UUID"
  log "CASCADE_UUID generated"

  eval "$(gen_keypair | sed -n 's/^PrivateKey: \(.*\)/VPS2_PRIVATE_KEY=\1/p; s/^PublicKey: \(.*\)/VPS2_PUBLIC_KEY=\1/p')"
  write_secret "VPS2_REALITY_PRIVATE_KEY" "$VPS2_PRIVATE_KEY"
  write_secret "VPS2_REALITY_PUBLIC_KEY" "$VPS2_PUBLIC_KEY"
  log "VPS2 Reality keypair generated"

  VPS2_SHORT_ID=$(gen_short_id)
  write_secret "VPS2_REALITY_SHORT_ID" "$VPS2_SHORT_ID"
  log "VPS2_REALITY_SHORT_ID generated"

  echo ""
  log "Enter the following values for VPS2:"

  prompt "VPS2_PORT" "VPS2 inbound port" "443"
  prompt "VPS2_REALITY_SERVER_NAME" "VPS2 Reality server name" "www.cloudflare.com"

  echo ""
  log "VPS2 secrets written to $SECRETS_FILE"
  echo ""
  echo "============================================================"
  echo "  SHARE THESE WITH VPS1:"
  echo "    CASCADE_UUID              = $CASCADE_UUID"
  echo "    VPS2_REALITY_PUBLIC_KEY   = $VPS2_PUBLIC_KEY"
  echo "    VPS2_REALITY_SHORT_ID     = $VPS2_SHORT_ID"
  echo "============================================================"
}

# ==================================================================
# VPS3
# ==================================================================
init_vps3() {
  log "Generating VPS3 secrets"

  CLIENT_UUID=$(gen_uuid)
  write_secret "CLIENT_UUID" "$CLIENT_UUID"
  log "CLIENT_UUID generated"

  VPS3_CASCADE_UUID=$(gen_uuid)
  write_secret "VPS3_CASCADE_UUID" "$VPS3_CASCADE_UUID"
  log "VPS3_CASCADE_UUID generated"

  VPS3_CASCADE_CLIENT_UUID=$(gen_uuid)
  write_secret "VPS3_CASCADE_CLIENT_UUID" "$VPS3_CASCADE_CLIENT_UUID"
  log "VPS3_CASCADE_CLIENT_UUID generated"

  eval "$(gen_keypair | sed -n 's/^PrivateKey: \(.*\)/VPS3_PRIVATE_KEY=\1/p; s/^PublicKey: \(.*\)/VPS3_PUBLIC_KEY=\1/p')"
  write_secret "VPS3_REALITY_PRIVATE_KEY" "$VPS3_PRIVATE_KEY"
  write_secret "VPS3_REALITY_PUBLIC_KEY" "$VPS3_PUBLIC_KEY"
  log "VPS3 Reality keypair generated"

  eval "$(gen_keypair | sed -n 's/^PrivateKey: \(.*\)/VPS3_CASCADE_CLIENT_PRIVATE_KEY=\1/p; s/^PublicKey: \(.*\)/VPS3_CASCADE_CLIENT_PUBLIC_KEY=\1/p')"
  write_secret "VPS3_CASCADE_CLIENT_PRIVATE_KEY" "$VPS3_CASCADE_CLIENT_PRIVATE_KEY"
  write_secret "VPS3_CASCADE_CLIENT_PUBLIC_KEY" "$VPS3_CASCADE_CLIENT_PUBLIC_KEY"
  log "VPS3 cascade client keypair generated"

  VPS3_REALITY_SHORT_ID=$(gen_short_id)
  write_secret "VPS3_REALITY_SHORT_ID" "$VPS3_REALITY_SHORT_ID"
  log "VPS3_REALITY_SHORT_ID generated"

  VPS3_CASCADE_CLIENT_SHORT_ID=$(gen_short_id)
  write_secret "VPS3_CASCADE_CLIENT_SHORT_ID" "$VPS3_CASCADE_CLIENT_SHORT_ID"
  log "VPS3_CASCADE_CLIENT_SHORT_ID generated"

  echo ""
  log "Enter the following values for VPS3:"

  prompt "VPS3_PORT" "VPS3 inbound port" "443"
  prompt "VPS3_REALITY_SERVER_NAME" "VPS3 Reality server name" "www.cloudflare.com"
  prompt "VPS3_IP" "VPS3 public IP address"
  prompt "VPS3_WARP_PRIVATE_KEY" "VPS3 WARP WireGuard private key"

  echo ""
  log "VPS3 secrets written to $SECRETS_FILE"
  echo ""
  echo "============================================================"
  echo "  SHARE THESE WITH VPS1/VPS2:"
  echo "    VPS3_REALITY_PUBLIC_KEY           = $VPS3_PUBLIC_KEY"
  echo "    VPS3_REALITY_SHORT_ID             = $VPS3_REALITY_SHORT_ID"
  echo "    VPS3_CASCADE_UUID                 = $VPS3_CASCADE_UUID"
  echo "============================================================"
}

# ==================================================================
# Main
# ==================================================================
case "$NODE_TYPE" in
  vps1) init_vps1 ;;
  vps2) init_vps2 ;;
  vps3) init_vps3 ;;
esac

echo ""
log "Init complete. Run vpn-gitops-update.sh to deploy."
