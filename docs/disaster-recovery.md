# Disaster Recovery Runbook

## Архитектура

```
Клиент → VPS1 (165.154.212.11, routing brain) → VPS2 (exit node) → Интернет
```

- **VPS1** — маршрутизатор, принимает клиентские подключения, направляет трафик на VPS2
- **VPS2** — выходная нода, каскадом получает трафик от VPS1 и отправляет в интернет

---

## 1. Что бэкапится

| Компонент | Источник | Назначение |
|-----------|----------|------------|
| sing-box конфиг | `/etc/sing-box/` | Полная директория (бинарник, конфиги, TLS-сертификаты, secrets) |
| VPN GitOps репозиторий | `/opt/vpn-gitops/` | Шаблоны, скрипты, маршруты |
| Системные unit-файлы | `/etc/systemd/system/sing-box.service`, `vpn-*` | systemd сервисы и таймеры |
| Secrets | `/etc/sing-box/secrets.env` | Ключи шифрования, UUID, параметры подключения |
| Боты | `/opt/bots/` | Исходники, venv, БД, secrets |
| MariaDB | `mariadb-dump --all-databases` | Дамп всех БД (hiddifypanel) |
| PostgreSQL | `pg_dumpall` | Дамп всех БД PostgreSQL |
| Системные конфиги | crontab, sshd_config, nftables, systemd-overrides | |

### Что НЕ бэкапится (требует ручного восстановления)

| Компонент | Причина |
|-----------|---------|
| `vpn-backup.service`, `vpn-backup.timer` | Не включены в список бэкапа systemd |
| `vpn_bot.service` | Не включён в список бэкапа systemd |
| `alsero_crm.service` | Не включён в список бэкапа systemd |
| Пакеты ОС | Устанавливаются через `apt` |

---

## 2. Где лежат архивы

```
/opt/backup/archive/
  backup-YYYYMMDD-HHMM.tar.zst
  backup-YYYYMMDD-HHMM.tar.zst.sha256
```

Схема хранения: максимум **14 последних** архивов, старые удаляются автоматически.

**Восстановление через git (альтернативный канал):**
- Репозиторий: `git@github.com:nirmataugin-lab/vpn-gitops.git`
- Ветка: `main`

---

## 3. Как проверить целостность backup

```bash
# Выбрать последний архив
latest=$(ls -1t /opt/backup/archive/backup-*.tar.zst | head -1)

# Проверить SHA256
sha256sum -c "${latest}.sha256"

# Проверить содержимое (без распаковки)
tar -tf "$latest" | grep -E '^\./[^/]+/?$' | sort

# Проверить что все компоненты на месте
for d in etc-sing-box vpn-gitops bots databases systemd; do
    tar -tf "$latest" "./${d}/" >/dev/null && echo "OK: $d" || echo "MISSING: $d"
done
tar -tf "$latest" "./secrets.env" >/dev/null && echo "OK: secrets.env" || echo "MISSING: secrets.env"
```

**Dry-run скрипт:**
```bash
/opt/backup/scripts/restore-dry-run.sh
```

---

## 4. Как восстановить VPS1 с нуля

> **Важно:** VPS1 не имеет собственного бекапа на этой ноде. Восстановление VPS1 выполняется по той же процедуре, что и VPS2 (разделы 6–9), но с IP VPS1 и его собственным secrets.env.

1. Развернуть Ubuntu 24.04 на VPS1
2. Выполнить разделы **6–9**, заменив IP и secrets на VPS1
3. Скопировать `secrets.env` VPS1 из защищённого хранилища (Bitwarden/Keepass)
4. Настроить маршрутизацию: `vpn-route vps2`
5. Проверить каскад с VPS2

---

## 5. Как восстановить VPS2 с нуля

**Целевое время: 15 минут**

### Предварительные требования
- Доступ к панели управления VPS (развернуть Ubuntu 24.04)
- SSH-доступ root
- Backup-архив на внешнем хранилище (или из `/opt/backup/archive/` если диск жив)

---

## 6. Какие пакеты поставить

```bash
apt update
apt install -y git jq gettext-base zstd mariadb-client postgresql-client
```

**sing-box** — бинарник восстанавливается из backup (путь: `./etc-sing-box/sing-box`), либо скачивается вручную:

```bash
# если нужно скачать заново
bash <(curl -fsSL https://sing-box.app/deb.sh)
```

---

## 7. Как восстановить

### 7.1. Подготовка

```bash
# Определить последний архив
ARCHIVE=$(ls -1t /opt/backup/archive/backup-*.tar.zst | head -1)

# Проверить целостность
sha256sum -c "${ARCHIVE}.sha256"

# Создать временную директорию
WORK_DIR=$(mktemp -d)
trap "rm -rf $WORK_DIR" EXIT

# Распаковать
tar -I zstd -xf "$ARCHIVE" -C "$WORK_DIR"
```

### 7.2. Восстановление /etc/sing-box/

```bash
# Остановить sing-box если запущен
systemctl stop sing-box 2>/dev/null || true

# Восстановить конфиг
cp -a "$WORK_DIR"/etc-sing-box /etc/sing-box
chown -R root:root /etc/sing-box
chmod 600 /etc/sing-box/secrets.env
```

### 7.3. Восстановление /opt/vpn-gitops/

```bash
cp -a "$WORK_DIR"/vpn-gitops /opt/vpn-gitops
```

### 7.4. Восстановление /opt/bots/

```bash
cp -a "$WORK_DIR"/bots /opt/bots
```

### 7.5. Восстановление systemd units

**Из архива (sing-box, vpn-gitops-update, vpn-failover):**
```bash
cp -a "$WORK_DIR"/systemd/* /etc/systemd/system/
systemctl daemon-reload
```

**Вручную (не входят в бэкап):**

Создать `/etc/systemd/system/vpn-backup.service`:
```ini
[Unit]
Description=VPN Backup — archive configs, databases and system state
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/backup/scripts/backup.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Создать `/etc/systemd/system/vpn-backup.timer`:
```ini
[Unit]
Description=Daily VPN backup at 03:30
Requires=vpn-backup.service

[Timer]
OnCalendar=03:30
Persistent=true

[Install]
WantedBy=timers.target
```

Создать `/etc/systemd/system/vpn_bot.service`:
```ini
[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/bots/vpn_bot
ExecStart=/opt/bots/vpn_bot/venv/bin/python /opt/bots/vpn_bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Создать `/etc/systemd/system/alsero_crm.service`:
```ini
[Unit]
Description=Alsero CRM Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/bots/alsero_crm
ExecStart=/opt/bots/alsero_crm/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
```

### 7.6. Восстановление secrets.env

```bash
cp "$WORK_DIR"/secrets.env /etc/sing-box/secrets.env
chmod 600 /etc/sing-box/secrets.env
```

### 7.7. Восстановление MariaDB dump

```bash
# Убедиться что MariaDB запущен
systemctl start mariadb 2>/dev/null || true

# Импортировать дамп
mariadb < "$WORK_DIR"/databases/mariadb-all.sql
```

### 7.8. Восстановление PostgreSQL dump

```bash
# Если PostgreSQL установлен
pg_dumpall < "$WORK_DIR"/databases/postgresql-all.sql
```

### 7.9. Скопировать скрипты в /usr/local/bin/

Из `/opt/vpn-gitops/scripts/`:
```bash
cp /opt/vpn-gitops/scripts/vpn-route /usr/local/bin/vpn-route
chmod +x /usr/local/bin/vpn-route
```

Из `/etc/sing-box/health/check.sh` — symlink для `vpn-failover-monitor`:
```bash
# failover-монитор — символическая ссылка на check.sh
ln -sf /etc/sing-box/health/check.sh /usr/local/bin/vpn-failover-monitor
```

Создать `/usr/local/bin/vpn-gitops-update.sh`:
```bash
ln -sf /opt/vpn-gitops/scripts/vpn-gitops-update.sh /usr/local/bin/vpn-gitops-update.sh
```

---

## 8. Как включить сервисы

```bash
# Включить и запустить sing-box
systemctl enable --now sing-box

# Включить таймеры
systemctl enable --now vpn-gitops-update.timer
systemctl enable --now vpn-failover.timer
systemctl enable --now vpn-backup.timer

# Включить и запустить ботов
systemctl enable --now vpn_bot
systemctl enable --now alsero_crm
```

Проверить статус:
```bash
systemctl list-timers --all | grep vpn
systemctl is-enabled sing-box vpn_bot alsero_crm vpn-backup.timer vpn-gitops-update.timer vpn-failover.timer
```

---

## 9. Проверки после восстановления

```bash
# 9.1. Валидация конфигурации sing-box
sing-box check -C /etc/sing-box/conf

# 9.2. Статус сервиса
systemctl status sing-box --no-pager -l

# 9.3. Прослушиваемые порты (ожидаемые: 443, 59505, 59507, 59508, 8080, 8082)
ss -lntup | grep -E ':(443|5950[578]|808[02])'

# 9.4. Статус маршрутизации
vpn-route status

# 9.5. Ошибки в journalctl
journalctl -u sing-box --since "5 minutes ago" -p err --no-pager
journalctl -u vpn_bot --since "5 minutes ago" -p err --no-pager
journalctl -u alsero_crm --since "5 minutes ago" -p err --no-pager
journalctl -u vpn-failover --since "5 minutes ago" -p err --no-pager
journalctl -u vpn-gitops-update --since "5 minutes ago" -p err --no-pager
```

### Ожидаемые порты

| Порт | Назначение |
|------|-----------|
| 443 | VLESS+REALITY (cascade-in from VPS1) |
| 59505 | VLESS+REALITY (client) |
| 59507 | TUIC (client) |
| 59508 | Hysteria2 (client) |
| 8080 | VLESS+REALITY cascade (client) |
| 8082 | HTTP proxy |

---

## 10. Rollback / аварийное восстановление

### Если новый конфиг сломал sing-box

```bash
# Откатить конфиг из backup
cp /etc/sing-box/config.json.bak /etc/sing-box/config.json
systemctl restart sing-box

# Или из conf/ директории
cp /etc/sing-box/conf/route.json.backup.* /etc/sing-box/conf/route.json 2>/dev/null || true
systemctl restart sing-box
```

### Если сломался restore (частичное восстановление)

```bash
# Полный откат изменений — перераспаковать архив заново
ARCHIVE=$(ls -1t /opt/backup/archive/backup-*.tar.zst | head -1)
WORK_DIR=$(mktemp -d)
tar -I zstd -xf "$ARCHIVE" -C "$WORK_DIR"

# Восстановить всё заново (секция 7)
# ...
rm -rf "$WORK_DIR"
```

### Если нет backup-архива

1. Склонировать git-репозиторий: `git clone git@github.com:nirmataugin-lab/vpn-gitops.git /opt/vpn-gitops`
2. Сгенерировать secrets: `/opt/vpn-gitops/scripts/init-node.sh`
3. Создать конфиги вручную через шаблоны
4. Настроить failover и ботов заново

### Если надо откатить бота

```bash
# В архиве есть pre-update backup бота
ls /opt/bots/vpn_bot.backup.*
# При необходимости переименовать обратно
mv /opt/bots/vpn_bot /opt/bots/vpn_bot.broken
mv /opt/bots/vpn_bot.backup.* /opt/bots/vpn_bot
systemctl restart vpn_bot
```

---

## 11. Чеклист «Сервер восстановлен»

- [ ] `sha256sum -c` — архив цел
- [ ] `sing-box check -C /etc/sing-box/conf` — конфиг валиден
- [ ] `systemctl status sing-box` — active (running)
- [ ] `ss -lntup` — все порты слушаются (443, 59505, 59507, 59508, 8080, 8082)
- [ ] `vpn-route status` — корректный маршрут
- [ ] `systemctl status vpn_bot` — active (running)
- [ ] `systemctl status alsero_crm` — active (running)
- [ ] `systemctl list-timers` — все таймеры активны:
  - `vpn-gitops-update.timer` (каждые 5 мин)
  - `vpn-failover.timer` (каждую 1 мин)
  - `vpn-backup.timer` (ежедневно 03:30)
- [ ] `journalctl -p err --since "10 min ago"` — нет ошибок
- [ ] `/etc/sing-box/secrets.env` — права 600, ключи на месте
- [ ] `/opt/backup/scripts/backup.sh` — существует, запускается
- [ ] Telegram bot отвечает на `/start`
- [ ] VPN-клиенты подключаются (проверить хотя бы один протокол)

---

*Документ создан: 2026-07-05*
*Актуален для: VPS1 (165.154.212.11) и VPS2*
