# Setup

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

## 3. Install update script on both VPS

```bash
install -m 755 /opt/vpn-gitops/scripts/vpn-gitops-update.sh /usr/local/bin/vpn-gitops-update.sh
```

## 4. Set node type

VPS-1:

```bash
echo vps1 > /etc/vpn-node-type
```

VPS-2:

```bash
echo vps2 > /etc/vpn-node-type
```

## 5. Generate Reality keypair

On VPS-1:

```bash
sing-box generate reality-keypair
openssl rand -hex 8
```

On VPS-2:

```bash
sing-box generate reality-keypair
openssl rand -hex 8
```

## 6. Create secrets file on VPS-1

```bash
mkdir -p /etc/sing-box
nano /etc/sing-box/secrets.env
chmod 600 /etc/sing-box/secrets.env
```

Example VPS-1 secrets:

```bash
CLIENT_UUID="f569f98c-6f0e-405f-bc25-80e029d88dd2"
CASCADE_UUID="PUT_CASCADE_UUID_HERE"

REALITY_SERVER_NAME="vibezero.duckdns.org"
VPS1_REALITY_PRIVATE_KEY="PUT_VPS1_REALITY_PRIVATE_KEY_HERE"
VPS1_REALITY_SHORT_ID="PUT_VPS1_SHORT_ID_HERE"

VPS2_IP="165.154.212.11"
VPS2_PORT="443"
VPS2_REALITY_SERVER_NAME="www.cloudflare.com"
VPS2_REALITY_PUBLIC_KEY="PUT_VPS2_REALITY_PUBLIC_KEY_HERE"
VPS2_REALITY_SHORT_ID="PUT_VPS2_SHORT_ID_HERE"
```

## 7. Create secrets file on VPS-2

```bash
mkdir -p /etc/sing-box
nano /etc/sing-box/secrets.env
chmod 600 /etc/sing-box/secrets.env
```

Example VPS-2 secrets:

```bash
CASCADE_UUID="PUT_CASCADE_UUID_HERE"
VPS2_PORT="443"
VPS2_REALITY_SERVER_NAME="www.cloudflare.com"
VPS2_REALITY_PRIVATE_KEY="PUT_VPS2_REALITY_PRIVATE_KEY_HERE"
VPS2_REALITY_SHORT_ID="PUT_VPS2_SHORT_ID_HERE"
```

## 8. First deploy

```bash
/usr/local/bin/vpn-gitops-update.sh
```

## 9. Auto update every minute

```bash
(crontab -l 2>/dev/null; echo '* * * * * /usr/local/bin/vpn-gitops-update.sh >/var/log/vpn-gitops.log 2>&1') | crontab -
```
