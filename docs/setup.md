# Setup guide

## 1. Install packages on both VPS

```bash
apt update && apt install -y git jq gettext-base
```

## 2. Clone repo on both VPS

```bash
rm -rf /opt/vpn-gitops
mkdir -p /opt/vpn-gitops
cd /opt/vpn-gitops
git clone https://github.com/YOUR_USERNAME/vpn-gitops.git .
```

## 3. Install update script

```bash
install -m 755 /opt/vpn-gitops/scripts/vpn-gitops-update.sh /usr/local/bin/vpn-gitops-update.sh
```

## 4. Set node type

VPS1:

```bash
echo vps1 > /etc/vpn-node-type
```

VPS2:

```bash
echo vps2 > /etc/vpn-node-type
```

## 5. Generate Reality keypairs

VPS1 and VPS2 each need their own keypair and short ID.

```bash
sing-box generate reality-keypair
openssl rand -hex 8
```

Copy the private key, public key, and short ID for each node.

## 6. Create secrets file on VPS1

```bash
mkdir -p /etc/sing-box
# Edit and paste your secrets (see example below)
nano /etc/sing-box/secrets.env
chmod 600 /etc/sing-box/secrets.env
```

**VPS1 secrets file** (`/etc/sing-box/secrets.env`):

```bash
# Client
CLIENT_UUID="PASTE_CLIENT_UUID_HERE"

# Cascade (shared with VPS2)
CASCADE_UUID="PASTE_CASCADE_UUID_HERE"

# VPS1 Reality (own inbound)
REALITY_SERVER_NAME="YOUR_VPS1_DOMAIN_HERE"
VPS1_REALITY_PRIVATE_KEY="PASTE_VPS1_PRIVATE_KEY_HERE"
VPS1_REALITY_SHORT_ID="PASTE_VPS1_SHORT_ID_HERE"

# VPS2 connection (cascade outbound)
VPS2_IP="YOUR_VPS2_IP_HERE"
VPS2_PORT="443"
VPS2_REALITY_SERVER_NAME="www.cloudflare.com"
VPS2_REALITY_PUBLIC_KEY="PASTE_VPS2_PUBLIC_KEY_HERE"
VPS2_REALITY_SHORT_ID="PASTE_VPS2_SHORT_ID_HERE"
```

## 7. Create secrets file on VPS2

```bash
mkdir -p /etc/sing-box
nano /etc/sing-box/secrets.env
chmod 600 /etc/sing-box/secrets.env
```

**VPS2 secrets file** (`/etc/sing-box/secrets.env`):

```bash
# Cascade (shared with VPS1)
CASCADE_UUID="PASTE_CASCADE_UUID_HERE"

# VPS2 inbound
VPS2_PORT="443"
VPS2_REALITY_SERVER_NAME="www.cloudflare.com"
VPS2_REALITY_PRIVATE_KEY="PASTE_VPS2_PRIVATE_KEY_HERE"
VPS2_REALITY_SHORT_ID="PASTE_VPS2_SHORT_ID_HERE"
```

## 8. First deploy

```bash
/usr/local/bin/vpn-gitops-update.sh
```

## 9. Auto-update every minute (cron)

```bash
(crontab -l 2>/dev/null; echo '* * * * * /usr/local/bin/vpn-gitops-update.sh >/var/log/vpn-gitops.log 2>&1') | crontab -
```

## Required variables

### VPS1

| Variable | Source |
|----------|--------|
| `CLIENT_UUID` | Your client UUID |
| `CASCADE_UUID` | Shared cascade UUID (same on VPS2) |
| `REALITY_SERVER_NAME` | Your domain for VPS1 Reality handshake |
| `VPS1_REALITY_PRIVATE_KEY` | `sing-box generate reality-keypair` on VPS1 |
| `VPS1_REALITY_SHORT_ID` | `openssl rand -hex 8` on VPS1 |
| `VPS2_IP` | VPS2 public IP |
| `VPS2_PORT` | VPS2 inbound port |
| `VPS2_REALITY_SERVER_NAME` | Target for VPS2 Reality handshake |
| `VPS2_REALITY_PUBLIC_KEY` | From VPS2 keypair |
| `VPS2_REALITY_SHORT_ID` | From VPS2 `openssl rand -hex 8` |

### VPS2

| Variable | Source |
|----------|--------|
| `CASCADE_UUID` | Shared cascade UUID (same on VPS1) |
| `VPS2_PORT` | VPS2 inbound port |
| `VPS2_REALITY_SERVER_NAME` | Target for VPS2 Reality handshake |
| `VPS2_REALITY_PRIVATE_KEY` | `sing-box generate reality-keypair` on VPS2 |
| `VPS2_REALITY_SHORT_ID` | `openssl rand -hex 8` on VPS2 |
