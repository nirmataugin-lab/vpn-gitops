#!/usr/bin/env python3
"""Controlled live apply for a pending vpn_clients row.

Defaults to dry-run. Live inbounds.json is written only with --apply.
"""

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.vpn_client import VpnClient
from app.services.singbox_client_service import SingBoxClientService
from app.services.singbox_config_service import SingBoxConfigService

PROD_DB_PATH = "/opt/bots/vpn_bot_v2/data/bot.db"
CONF_DIR = "/etc/sing-box/conf"
INBOUNDS_PATH = f"{CONF_DIR}/inbounds.json"
SERVICE_NAME = "sing-box"


def _prod_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(PROD_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_live_config() -> dict[str, Any]:
    with open(INBOUNDS_PATH) as f:
        return json.load(f)


def dump_config(config: dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def count_live_users(config: dict[str, Any] | None = None) -> int:
    if config is None:
        config = load_live_config()
    return sum(len(inbound.get("users", [])) for inbound in config.get("inbounds", []))


def uuid_exists(config: dict[str, Any], uuid: str) -> bool:
    for inbound in config.get("inbounds", []):
        for user in inbound.get("users", []):
            if user.get("uuid") == uuid or user.get("password") == uuid:
                return True
    return False


def inbound_exists(config: dict[str, Any], inbound_tag: str) -> bool:
    return any(inbound.get("tag") == inbound_tag for inbound in config.get("inbounds", []))


def get_vpn_client(vpn_client_id: int) -> sqlite3.Row | None:
    conn = _prod_conn()
    try:
        return conn.execute(
            "SELECT * FROM vpn_clients WHERE id = ?",
            (vpn_client_id,),
        ).fetchone()
    finally:
        conn.close()


def get_vpn_client_status(vpn_client_id: int) -> str | None:
    row = get_vpn_client(vpn_client_id)
    return None if row is None else row["status"]


def backup_path(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return f"{INBOUNDS_PATH}.backup.{stamp}"


def make_diff(before_config: dict[str, Any], after_config: dict[str, Any]) -> str:
    before = dump_config(before_config).splitlines(keepends=True)
    after = dump_config(after_config).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=INBOUNDS_PATH,
            tofile=f"{INBOUNDS_PATH} (pending)",
        )
    )


def build_modified_config(row: sqlite3.Row, live_config: dict[str, Any]) -> dict[str, Any]:
    client = VpnClient(
        uuid=row["uuid"],
        email=f"vpn-client-{row['id']}",
        inbound_tag=row["inbound_tag"],
    )
    config_svc = SingBoxConfigService(conf_dir=CONF_DIR)
    config_svc._config = deepcopy(live_config)
    return config_svc.add_client(client)


def write_temp_config_and_check(config: dict[str, Any]) -> tuple[bool, str]:
    service = SingBoxClientService(conf_dir=CONF_DIR)
    return service.verify_config(config)


def atomic_write_live_config(config: dict[str, Any]) -> None:
    live_path = Path(INBOUNDS_PATH)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{live_path.name}.", suffix=".tmp", dir=str(live_path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(dump_config(config))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, INBOUNDS_PATH)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def reload_singbox() -> tuple[bool, str]:
    result = subprocess.run(
        ["systemctl", "reload", SERVICE_NAME],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip() or result.stdout.strip()


def restore_backup(path: str) -> None:
    shutil.copy2(path, INBOUNDS_PATH)


def run(vpn_client_id: int, apply: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {
        "vpn_client_id": vpn_client_id,
        "mode": "apply" if apply else "dry-run",
        "apply_requested": apply,
    }

    hash_before = file_hash(INBOUNDS_PATH)
    live_config = load_live_config()
    users_before = count_live_users(live_config)
    report["initial_state"] = {
        "inbounds_hash": hash_before,
        "live_users": users_before,
    }

    row = get_vpn_client(vpn_client_id)
    if row is None:
        report.update(success=False, message=f"vpn_client id={vpn_client_id} not found")
        return report

    row_status = row["status"]
    report["vpn_client"] = {
        "id": row["id"],
        "telegram_id": row["telegram_id"],
        "uuid": row["uuid"],
        "status_before": row_status,
        "inbound_tag": row["inbound_tag"],
        "server_id": row["server_id"],
    }

    if row_status != "pending":
        report.update(success=False, message=f"vpn_client status is '{row_status}', expected 'pending'")
        return report
    if uuid_exists(live_config, row["uuid"]):
        report.update(success=False, message=f"UUID {row['uuid']} already exists in live config")
        return report
    if not inbound_exists(live_config, row["inbound_tag"]):
        report.update(success=False, message=f"Inbound tag '{row['inbound_tag']}' not found in live config")
        return report

    try:
        modified_config = build_modified_config(row, live_config)
    except ValueError as exc:
        report.update(success=False, message=str(exc))
        return report

    diff = make_diff(live_config, modified_config)
    future_backup = backup_path()
    report["future"] = {
        "backup_path": future_backup,
        "live_users_after_apply": count_live_users(modified_config),
    }
    report["diff"] = diff
    report["diff_summary"] = {
        "lines": len(diff.splitlines()),
        "generated": bool(diff),
    }

    check_ok, check_err = write_temp_config_and_check(modified_config)
    report["singbox_check"] = {
        "passed": check_ok,
        "error": "" if check_ok else check_err,
    }
    if not check_ok:
        report.update(success=False, message=f"sing-box check failed: {check_err}")
        return report

    if not apply:
        hash_after = file_hash(INBOUNDS_PATH)
        status_after = get_vpn_client_status(vpn_client_id)
        report["final_state"] = {
            "inbounds_hash": hash_after,
            "live_users": count_live_users(),
            "vpn_client_status": status_after,
        }
        report.update(
            success=True,
            message="Dry-run only. Live config was not written; reload was not executed.",
        )
        return report

    current_hash = file_hash(INBOUNDS_PATH)
    if current_hash != hash_before:
        report.update(
            success=False,
            message="live inbounds.json hash changed between read and apply; refusing to write",
            current_hash=current_hash,
        )
        return report

    shutil.copy2(INBOUNDS_PATH, future_backup)
    report["backup_created"] = future_backup
    try:
        atomic_write_live_config(modified_config)
        post_write_ok, post_write_err = write_temp_config_and_check(load_live_config())
        report["post_write_check"] = {
            "passed": post_write_ok,
            "error": "" if post_write_ok else post_write_err,
        }
        if not post_write_ok:
            restore_backup(future_backup)
            restore_ok, restore_err = write_temp_config_and_check(load_live_config())
            report["restore_check"] = {
                "passed": restore_ok,
                "error": "" if restore_ok else restore_err,
            }
            report.update(success=False, message=f"post-write sing-box check failed: {post_write_err}")
            return report

        reload_ok, reload_err = reload_singbox()
        report["reload"] = {
            "passed": reload_ok,
            "error": "" if reload_ok else reload_err,
        }
        if not reload_ok:
            restore_backup(future_backup)
            restore_ok, restore_err = write_temp_config_and_check(load_live_config())
            report["restore_check"] = {
                "passed": restore_ok,
                "error": "" if restore_ok else restore_err,
            }
            report.update(success=False, message=f"systemctl reload {SERVICE_NAME} failed: {reload_err}")
            return report
    finally:
        report["final_state"] = {
            "inbounds_hash": file_hash(INBOUNDS_PATH),
            "live_users": count_live_users(),
            "vpn_client_status": get_vpn_client_status(vpn_client_id),
        }

    report.update(success=True, message="Applied pending vpn_client to live sing-box config.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Controlled apply for an existing pending vpn_clients row"
    )
    parser.add_argument("--vpn-client-id", type=int, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write live inbounds.json and reload sing-box. Omitted means dry-run.",
    )
    args = parser.parse_args()

    report = run(vpn_client_id=args.vpn_client_id, apply=args.apply)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report.get("success") else 1)


if __name__ == "__main__":
    main()
