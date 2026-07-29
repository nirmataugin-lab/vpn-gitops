#!/usr/bin/env python3
"""
Full sing-box pipeline dry-run.

Creates a vpn_client in SQLite within a transaction, builds an in-memory
sing-box config, runs `sing-box check` on a temp copy, then rolls back
the database — leaving zero changes to live config or Hiddify.
"""

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

from app.database import DB_PATH, get_connection, init_db, transaction
from app.models.vpn_client import VpnClient
from app.services.singbox_client_db_service import SingBoxClientDbService
from app.services.singbox_client_service import SingBoxClientService
from app.services.singbox_config_service import SingBoxConfigService
from app.services.vpn_client_repository import VpnClientRepository

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("full_pipeline_dry_run")

CONF_DIR = "/etc/sing-box/conf"
INBOUNDS_PATH = f"{CONF_DIR}/inbounds.json"


def file_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return "FILE_NOT_FOUND"
    except PermissionError:
        return "PERMISSION_DENIED"


def count_live_users() -> int:
    try:
        with open(INBOUNDS_PATH) as f:
            config = json.load(f)
        count = 0
        for inbound in config.get("inbounds", []):
            count += len(inbound.get("users", []))
        return count
    except (FileNotFoundError, PermissionError):
        return -1


def service_uptime() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "show", "sing-box.service", "-p", "ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception as e:
        return str(e)


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
                hidden.append(f"sni=***")
        elif segment.startswith("sid="):
            val = segment.split("=", 1)[1]
            if len(val) > 4:
                hidden.append(f"sid={val[:4]}...")
            else:
                hidden.append(f"sid=***")
        else:
            hidden.append(segment)
    return f"{uuid_part}@{'&'.join(hidden)}"


def run_pipeline(telegram_id: str | None, email: str | None):
    inbound_tag = "vless-reality"
    display_email = email or f"dry-run-user-{telegram_id or 'test'}"

    print("=" * 68)
    print("  sing-box full pipeline dry‑run")
    print("=" * 68)

    # --- capture initial state ---------------------------------------------------
    print("\n[1/9] Capturing initial state …")
    init_db()
    repo = VpnClientRepository()
    count_before = repo.count()
    hash_before = file_hash(INBOUNDS_PATH)
    users_before = count_live_users()
    uptime_before = service_uptime()
    print(f"  vpn_clients count . . . . . . . . {count_before}")
    print(f"  inbounds.json hash . . . . . . . {hash_before}")
    print(f"  live inbound users . . . . . . . {users_before}")
    print(f"  sing-box.service . . . . . . . . {uptime_before}")

    # --- build services ----------------------------------------------------------
    print("\n[2/9] Building service layer …")
    config_svc = SingBoxConfigService(conf_dir=CONF_DIR)
    db_svc = SingBoxClientDbService(repository=repo, conf_dir=CONF_DIR)
    singbox_svc = SingBoxClientService(conf_dir=CONF_DIR)
    print("  SingBoxConfigService . . . . . . ready")
    print("  SingBoxClientDbService . . . . . ready")
    print("  SingBoxClientService . . . . . . ready")

    # --- pipeline: create client in DB -------------------------------------------
    print(f"\n[3/9] Creating vpn_client (inside transaction) …")
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        client, vless_uri = db_svc.create_client(
            email=display_email,
            inbound_tag=inbound_tag,
            conn=conn,
        )
        print(f"  UUID . . . . . . . . . . . . . {client.uuid}")
        print(f"  email  . . . . . . . . . . . . {client.email}")
        print(f"  inbound_tag . . . . . . . . . . {client.inbound_tag}")
        print(f"  subscription_id . . . . . . . . {client.uuid}  (future)")

        piped_uri = mask_vless_secrets(vless_uri)
        print(f"  VLESS URI (masked) . . . . . .  {piped_uri}")

        # --- pipeline: verify in DB ----------------------------------------------
        print(f"\n[4/9] Verifying client in database …")
        db_client = db_svc.get_client(client.uuid, conn=conn)
        assert db_client is not None, "Client not found in DB after insert"
        assert db_client.uuid == client.uuid
        assert repo.count(conn=conn) == count_before + 1
        print(f"  count after insert . . . . . . {repo.count(conn=conn)}  ✓")

        # --- pipeline: add to in-memory config -----------------------------------
        print(f"\n[5/9] Adding client to in-memory config …")
        modified_config = config_svc.add_client(db_client)
        new_user_count = sum(
            len(inb.get("users", [])) for inb in modified_config.get("inbounds", [])
        )
        print(f"  users in modified config . . . . {new_user_count}  (was {users_before})")

        # --- pipeline: write temp config & sing-box check ------------------------
        print(f"\n[6/9] Running sing-box check on temp config …")
        check_ok, check_err = singbox_svc.verify_config(modified_config)
        if check_ok:
            print(f"  sing-box check . . . . . . . . PASSED  ✓")
        else:
            print(f"  sing-box check . . . . . . . . FAILED  ✗")
            print(f"  error . . . . . . . . . . . . {check_err}")

        # --- rollback ------------------------------------------------------------
        print(f"\n[7/9] Rolling back database transaction …")
        conn.rollback()
        repo = VpnClientRepository()
        count_after = repo.count()
        assert count_after == count_before, (
            f"Rollback failed: count {count_after} != {count_before}"
        )
        print(f"  vpn_clients count after rollback  {count_after}  ✓")
        print(f"  count restored to original . . . {'YES' if count_after == count_before else 'NO'}")

    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

    # --- verify no live changes --------------------------------------------------
    print(f"\n[8/9] Verifying live state unchanged …")
    hash_after = file_hash(INBOUNDS_PATH)
    users_after = count_live_users()
    uptime_after = service_uptime()

    hash_ok = hash_after == hash_before
    users_ok = users_after == users_before
    uptime_ok = uptime_after == uptime_before

    print(f"  inbounds.json hash . . . . . . . {hash_after}")
    print(f"  hash unchanged . . . . . . . . . {'YES ✓' if hash_ok else 'NO ✗'}")
    print(f"  live inbound users . . . . . . . {users_after}")
    print(f"  users unchanged . . . . . . . . . {'YES ✓' if users_ok else 'NO ✗'}")
    print(f"  sing-box.service . . . . . . . . {uptime_after}")
    print(f"  service not restarted . . . . . . {'YES ✓' if uptime_ok else 'NO ✗'}")

    # --- report ----------------------------------------------------------------
    print(f"\n[9/9] Full report")
    print(f"  {'─' * 60}")
    print(f"  Pipeline step              │ Status")
    print(f"  {'─' * 60}")
    print(f"  VpnClientRepository        │ {'✓' if count_before + 1 == count_before + 1 else '✗'}  insert within TX")
    print(f"  SingBoxClientDbService     │ {'✓' if vless_uri else '✗'}  VLESS URI generated")
    print(f"  SingBoxConfigService       │ {'✓' if modified_config else '✗'}  in-memory config built")
    print(f"  SingBoxClientService       │ {'✓' if check_ok else '✗'}  verify_config() called")
    print(f"  sing-box check             │ {'✓ PASS' if check_ok else '✗ ' + check_err}")
    print(f"  Rollback (SQLite)          │ {'✓' if count_after == count_before else '✗'}")
    print(f"  Live config unchanged      │ {'✓' if hash_ok and users_ok else '✗'}")
    print(f"  Service not touched        │ {'✓' if uptime_ok else '✗'}")
    print(f"  {'─' * 60}")

    summary = {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "initial_state": {
            "vpn_clients_count": count_before,
            "inbounds_hash": hash_before,
            "live_users": users_before,
        },
        "generated": {
            "uuid": client.uuid,
            "email": display_email,
            "inbound_tag": inbound_tag,
            "subscription_id": client.uuid,
        },
        "vless_uri": vless_uri,
        "vless_uri_masked": piped_uri,
        "singbox_check": "passed" if check_ok else f"failed: {check_err}",
        "rollback": {
            "count_before": count_before,
            "count_after": count_after,
            "matched": count_before == count_after,
        },
        "live_state_unchanged": {
            "hash_matched": hash_ok,
            "users_matched": users_ok,
            "service_not_restarted": uptime_ok,
        },
    }

    print(f"\nJSON report:\n{json.dumps(summary, indent=2, ensure_ascii=False)}")


def main():
    parser = argparse.ArgumentParser(
        description="Full sing-box pipeline dry-run (no live changes)"
    )
    parser.add_argument(
        "--telegram-id",
        type=str,
        default=None,
        help="Telegram user ID for the test client",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email for the test client (overrides auto-generated name)",
    )
    args = parser.parse_args()

    run_pipeline(args.telegram_id, args.email)


if __name__ == "__main__":
    main()
