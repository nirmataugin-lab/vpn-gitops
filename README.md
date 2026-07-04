# vpn-gitops Level 2

GitOps repository for a two-node sing-box cascade:

Client -> VPS-1 routing brain -> VPS-2 exit -> Internet

## Security model

This repo must NOT contain secrets.

Do not commit:
- Reality private keys
- Reality public keys if you want maximum privacy
- UUIDs for production users
- SSH keys
- API tokens
- server passwords

Secrets are stored locally on each VPS in:

```bash
/etc/sing-box/secrets.env
```

Templates from this repo are rendered locally into:

```bash
/etc/sing-box/config.json
```

## Files

```text
vps1/sing-box.template.json   # VPS-1 routing brain template
vps2/sing-box.template.json   # VPS-2 exit node template
scripts/vpn-gitops-update.sh  # safe renderer + deploy script
docs/setup.md                 # installation steps
shared/bypass.json            # editable bypass list
shared/routing.json           # routing notes
```

## Node type

On VPS-1:

```bash
echo vps1 > /etc/vpn-node-type
```

On VPS-2:

```bash
echo vps2 > /etc/vpn-node-type
```
