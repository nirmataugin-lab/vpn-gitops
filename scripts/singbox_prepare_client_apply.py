#!/usr/bin/env python3
"""
Controlled sing-box client apply preparation.

Creates a vpn_clients record in the production SQLite database within a
controlled transaction.  By default everything is rolled back.
Use --commit-db to persist only the vpn_clients row (sing-box config is
never written at this stage).

Flags:
  --telegram-id   Required. Telegram user ID.
  --email         Optional. Override auto-generated email.
  --inbound-tag   Optional. Target inbound tag (default: vless-reality).
  --commit-db     Persist the vpn_clients record to SQLite only.
  --apply-config  BLOCKED. Will always error at this stage.
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import uuid as uuid_module
from pathlib import Path
from typing import Any

from app.database import init_db, transaction
from app.models.vpn_client import VpnClient
from app.services.singbox_client_service import SingBoxClientService
from app.services.singbox_config_service import SingBoxConfigService

logger = logging.getLogger(__name__)

PROD_DB_PATH = "/opt/bots/vpn_bot_v2/data/bot.db"
CONF_DIR = "/etc/sing-box/conf"
INBOUNDS_PATH = f"{CONF_DIR}/inbounds.json"
SERVER_ID = "vps2"
DEFAULT_INBOUND_TAG = "vless-reality"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _prod_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(PROD_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def file_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return "FILE_NOT_FOUND"
    except PermissionError:
        return "PERMISSION_DENIED"


def count_vpn_clients(conn: sqlite3.Connection | None = None) -> int:
    close = False
    if conn is None:
        conn = _prod_conn()
        close = True
    try:
        row = conn.execute("SELECT COUNT(*) FROM vpn_clients").fetchone()
        return row[0] if row else 0
    finally:
        if close:
            conn.close()


def count_live_users() -> int:
    try:
        with open(INBOUNDS_PATH) as f:
            config: dict[str, Any] = json.load(f)
        return sum(len(inb.get("users", [])) for inb in config.get("inbounds", []))
    except (FileNotFoundError, PermissionError):
        return -1


def mask_vless_secrets(uri: str | None) -> str | None:
    if uri is None:
        return None
    uuid_part = uri.split("@")[0]
    remainder = uri.split("@", 1)[1] if "@" in uri else ""
    hidden = []
    for segment in remainder.split("&"):
        if segment.startswith("pbk="):
            val = segment.split("=", 1)[1]
            hidden.append(f"pbk={val[:4]}...{val[-4:]}")
        elif segment.startswith("sni="):
            val = segment.split("=", 1)[1]
            if len(val) > 8:
                hidden.append(f"sni={val[:4]}...{val[-4:]}")
            else:
                hidden.append("sni=***")
        elif segment.startswith("sid="):
            val = segment.split("=", 1)[1]
            if len(val) > 4:
                hidden.append(f"sid={val[:4]}...")
            else:
                hidden.append("sid=***")
        else:
            hidden.append(segment)
    return f"{uuid_part}@{'&'.join(hidden)}"


def uuid_in_live_config(uuid: str) -> bool:
    try:
        with open(INBOUNDS_PATH) as f:
            config: dict[str, Any] = json.load(f)
        for inbound in config.get("inbounds", []):
            for user in inbound.get("users", []):
                if user.get("uuid") == uuid or user.get("password") == uuid:
                    return True
        return False
    except (FileNotFoundError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(telegram_id: str, email: str | None, inbound_tag: str,
        commit_db: bool, apply_config: bool) -> dict[str, Any]:
    report: dict[str, Any] = {}
    errors: list[str] = []

    singbox_svc = SingBoxClientService(conf_dir=CONF_DIR)
    config_svc = SingBoxConfigService(conf_dir=CONF_DIR)

    initial_vpn_count = count_vpn_clients()
    initial_inbounds_hash = file_hash(INBOUNDS_PATH)
    initial_live_users = count_live_users()
    report["initial_state"] = {
        "vpn_clients_count": initial_vpn_count,
        "inbounds_hash": initial_inbounds_hash,
        "live_users": initial_live_users,
    }
    report["flags"] = {
        "telegram_id": telegram_id,
        "email": email,
        "inbound_tag": inbound_tag,
        "commit_db": commit_db,
        "apply_config": apply_config,
    }

    # --apply-config is blocked at this stage
    if apply_config:
        msg = "apply-config disabled in this stage"
        errors.append(msg)
        report["success"] = False
        report["errors"] = errors
        report["message"] = msg
        return report

    # --- connect to production DB ---
    conn = _prod_conn()
    try:
        conn.execute("BEGIN")

        # --- find user ---
        user_row = conn.execute(
            "SELECT id, telegram_id, username FROM users WHERE telegram_id = ?",
            (int(telegram_id),),
        ).fetchone()
        if user_row is None:
            msg = f"User with telegram_id {telegram_id} not found"
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        user_id = user_row["id"]
        user_telegram_id = user_row["telegram_id"]
        report["user"] = {
            "id": user_id,
            "telegram_id": user_telegram_id,
            "username": user_row["username"],
        }

        # --- find active subscription ---
        sub_row = conn.execute(
            "SELECT id, status, plan_name FROM subscriptions "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()
        if sub_row is None:
            msg = f"No active subscription found for user {telegram_id}"
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        subscription_id = sub_row["id"]
        report["subscription"] = {
            "id": subscription_id,
            "status": sub_row["status"],
            "plan_name": sub_row["plan_name"],
        }

        # --- duplicate check: existing vpn_client for telegram_id + subscription_id ---
        existing_vpn = conn.execute(
            "SELECT id, uuid FROM vpn_clients "
            "WHERE telegram_id = ? AND subscription_id = ?",
            (user_telegram_id, subscription_id),
        ).fetchone()
        if existing_vpn is not None:
            msg = (f"vpn_client already exists for telegram_id={telegram_id} "
                   f"subscription_id={subscription_id} (uuid={existing_vpn['uuid']})")
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        # --- inbound_tag validation ---
        inbound_found = False
        for inbound in singbox_svc.config.get("inbounds", []):
            if inbound.get("tag") == inbound_tag:
                inbound_found = True
                break
        if not inbound_found:
            msg = f"Inbound tag '{inbound_tag}' not found in live config"
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        # --- generate UUID ---
        new_uuid = str(uuid_module.uuid4())

        # --- duplicate UUID check ---
        if uuid_in_live_config(new_uuid):
            msg = f"UUID collision — generated UUID {new_uuid} already exists in live config"
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        display_email = email or f"user-{telegram_id}"

        # --- build VpnClient dataclass ---
        client = VpnClient(
            uuid=new_uuid,
            email=display_email,
            inbound_tag=inbound_tag,
        )
        report["vpn_client"] = {
            "uuid": client.uuid,
            "email": client.email,
            "inbound_tag": client.inbound_tag,
        }

        # --- build VLESS URI (using new architecture) ---
        inbound = singbox_svc._find_inbound(inbound_tag)
        vless_uri = singbox_svc._build_vless_uri(new_uuid, inbound)
        report["vless_uri"] = vless_uri
        report["vless_uri_masked"] = mask_vless_secrets(vless_uri)

        # --- add to in-memory config ---
        try:
            modified_config = config_svc.add_client(client)
        except ValueError as e:
            errors.append(str(e))
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = str(e)
            return report

        # --- sing-box check on temp config ---
        check_ok, check_err = singbox_svc.verify_config(modified_config)
        report["singbox_check"] = {
            "passed": check_ok,
            "error": check_err if not check_ok else "",
        }
        if not check_ok:
            msg = f"sing-box check failed: {check_err}"
            errors.append(msg)
            conn.rollback()
            report["success"] = False
            report["errors"] = errors
            report["message"] = msg
            return report

        # --- insert vpn_clients record ---
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO vpn_clients "
            "(user_id, telegram_id, uuid, subscription_id, server_id, inbound_tag, "
            " status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (user_id, user_telegram_id, new_uuid, subscription_id,
             SERVER_ID, inbound_tag, now, now),
        )
        inserted_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        report["vpn_client"]["db_id"] = inserted_id

        # --- commit or rollback ---
        if commit_db:
            conn.commit()
            report["commit_db"] = True
            report["message"] = ("vpn_clients record committed to DB "
                                 f"(id={inserted_id}, uuid={new_uuid}). "
                                 "sing-box config NOT written.")
        else:
            conn.rollback()
            report["commit_db"] = False
            report["message"] = ("Rolled back. vpn_clients record NOT saved. "
                                 "Use --commit-db to persist.")

        report["success"] = True
        return report

    except BaseException as e:
        conn.rollback()
        errors.append(str(e))
        report["success"] = False
        report["errors"] = errors
        report["message"] = str(e)
        return report
    finally:
        conn.close()


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        description="Controlled sing-box client apply preparation (Stage 7)"
    )
    parser.add_argument(
        "--telegram-id",
        type=str,
        required=True,
        help="Telegram user ID",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email for the client (overrides auto-generated)",
    )
    parser.add_argument(
        "--inbound-tag",
        type=str,
        default=DEFAULT_INBOUND_TAG,
        help=f"Target inbound tag (default: {DEFAULT_INBOUND_TAG})",
    )
    parser.add_argument(
        "--commit-db",
        action="store_true",
        help="Commit vpn_clients record to SQLite (sing-box config still NOT written)",
    )
    parser.add_argument(
        "--apply-config",
        action="store_true",
        help="BLOCKED at this stage — always errors",
    )
    args = parser.parse_args()

    report = run(
        telegram_id=args.telegram_id,
        email=args.email,
        inbound_tag=args.inbound_tag,
        commit_db=args.commit_db,
        apply_config=args.apply_config,
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report.get("success") else 1)


if __name__ == "__main__":
    main()
