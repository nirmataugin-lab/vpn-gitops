# vpn-gitops — Production Level 2

GitOps repository for a two-node sing-box VLESS Reality cascade:

```
Client → VPS1 (routing brain) → VPS2 (exit node) → Internet
```

## Architecture

| Node | Role | Details |
|------|------|---------|
| VPS1 | Routing brain | VLESS+REALITY inbound, RU/private DIRECT, all else → VPS2 |
| VPS2 | Exit node | VLESS+REALITY inbound (VPS1 only), outbound DIRECT |

## Security

**No secrets are stored in this repository.** Secrets live in `/etc/sing-box/secrets.env` on each VPS (mode 600). Templates use `envsubst` placeholders (`${VAR}`) that are rendered locally by the update script.

The git history has been purged of any prior committed secrets. See `.gitignore` for patterns that block accidental leaks.

## Files

```
vps1/sing-box.template.json   # VPS1 routing brain template
vps2/sing-box.template.json   # VPS2 exit node template
scripts/vpn-gitops-update.sh  # Renderer + deploy script (runs via cron)
docs/setup.md                 # Installation & setup guide
shared/bypass.json            # Editable domain bypass list (RU-focused)
shared/routing.json           # Routing documentation
.gitignore                    # Blocks secrets from accidental commits
```

## Deploy pipeline

The update script (`scripts/vpn-gitops-update.sh`) runs the following steps:

1. `git pull` — fetch latest templates
2. Detect node type (`/etc/vpn-node-type`)
3. Load secrets (`/etc/sing-box/secrets.env`)
4. Validate required variables
5. Render template with `envsubst`
6. Validate rendered config (`jq` + `sing-box check`)
7. Backup existing config
8. Deploy new config
9. Restart sing-box
10. Roll back on failure

A cron job runs the script every minute for automatic deployment.

## Node type

On VPS1:

```bash
echo vps1 > /etc/vpn-node-type
```

On VPS2:

```bash
echo vps2 > /etc/vpn-node-type
```
