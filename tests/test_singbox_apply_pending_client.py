import importlib.util
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from app.services.singbox_client_service import SingBoxClientService
from tests.test_singbox_prepare_client_apply import SAMPLE_INBOUNDS

SPEC = importlib.util.spec_from_file_location(
    "singbox_apply_pending_client",
    "scripts/singbox_apply_pending_client.py",
)
MOD = importlib.util.module_from_spec(SPEC)


def _remove_sqlite_files(db_path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except FileNotFoundError:
            pass


def _setup_test_db(db_path: str, *, status: str = "pending", inbound_tag: str = "vless-reality", uuid: str = "393fe174-0000-4000-8000-000000009735") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE vpn_clients (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            uuid VARCHAR(36) NOT NULL UNIQUE,
            subscription_id INTEGER,
            server_id VARCHAR(64) NOT NULL,
            inbound_tag VARCHAR(128) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            expires_at TEXT,
            traffic_limit_bytes INTEGER,
            traffic_used_bytes INTEGER NOT NULL DEFAULT 0,
            device_limit INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            disabled_at TEXT
        );
    """)
    conn.execute(
        "INSERT INTO vpn_clients "
        "(id, user_id, telegram_id, uuid, subscription_id, server_id, inbound_tag, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 1, 6430387100, uuid, 1, "vps2", inbound_tag, status),
    )
    conn.commit()
    conn.close()


def _setup_conf(conf_dir: str, data: dict | None = None) -> None:
    os.makedirs(conf_dir, exist_ok=True)
    with open(os.path.join(conf_dir, "inbounds.json"), "w") as f:
        json.dump(data or SAMPLE_INBOUNDS, f, indent=2)
    for fname, content in [
        ("dns.json", json.dumps({"dns": {"servers": [{"tag": "local", "type": "local"}]}})),
        ("log.json", json.dumps({"log": {"disabled": True}})),
        ("outbounds.json", json.dumps({"outbounds": [{"type": "direct", "tag": "direct"}]})),
        ("route.json", json.dumps({"route": {"rules": [], "final": "direct"}})),
        ("ntp.json", json.dumps({"ntp": {"enabled": False}})),
    ]:
        with open(os.path.join(conf_dir, fname), "w") as f:
            f.write(content)


class TestSingBoxApplyPendingClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SPEC.loader.exec_module(MOD)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="apply_pending_test_")
        self.db_path = os.path.join(self.tmpdir, "bot.db")
        self.conf_dir = os.path.join(self.tmpdir, "conf")
        MOD.PROD_DB_PATH = self.db_path
        MOD.CONF_DIR = self.conf_dir
        MOD.INBOUNDS_PATH = os.path.join(self.conf_dir, "inbounds.json")
        _setup_test_db(self.db_path)
        _setup_conf(self.conf_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_dry_run_success(self, mock_check):
        report = MOD.run(vpn_client_id=1)

        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "dry-run")
        self.assertTrue(report["singbox_check"]["passed"])
        self.assertIn("Dry-run only", report["message"])

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_status_not_pending(self, mock_check):
        _remove_sqlite_files(self.db_path)
        _setup_test_db(self.db_path, status="active")

        report = MOD.run(vpn_client_id=1)

        self.assertFalse(report["success"])
        self.assertIn("expected 'pending'", report["message"])

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_uuid_already_exists(self, mock_check):
        _remove_sqlite_files(self.db_path)
        _setup_test_db(
            self.db_path,
            uuid="d0b8fd48-185a-467d-9c10-447ede1228e8",
        )

        report = MOD.run(vpn_client_id=1)

        self.assertFalse(report["success"])
        self.assertIn("already exists", report["message"])

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_inbound_missing(self, mock_check):
        _remove_sqlite_files(self.db_path)
        _setup_test_db(self.db_path, inbound_tag="missing-inbound")

        report = MOD.run(vpn_client_id=1)

        self.assertFalse(report["success"])
        self.assertIn("not found", report["message"])

    @mock.patch.object(MOD, "reload_singbox")
    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_apply_requires_explicit_flag(self, mock_check, mock_reload):
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)

        report = MOD.run(vpn_client_id=1)

        self.assertTrue(report["success"])
        self.assertFalse(report["apply_requested"])
        self.assertNotIn("backup_created", report)
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)
        mock_reload.assert_not_called()

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_diff_generated(self, mock_check):
        report = MOD.run(vpn_client_id=1)

        self.assertTrue(report["diff_summary"]["generated"])
        self.assertIn("+          \"uuid\": \"393fe174-0000-4000-8000-000000009735\"", report["diff"])

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_backup_path_generated(self, mock_check):
        report = MOD.run(vpn_client_id=1)

        self.assertTrue(report["future"]["backup_path"].startswith(MOD.INBOUNDS_PATH + ".backup."))

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_live_config_unchanged_in_dry_run(self, mock_check):
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)
        users_before = MOD.count_live_users()

        report = MOD.run(vpn_client_id=1)

        self.assertTrue(report["success"])
        self.assertEqual(report["final_state"]["inbounds_hash"], hash_before)
        self.assertEqual(report["final_state"]["live_users"], users_before)
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)
        self.assertEqual(MOD.count_live_users(), users_before)


if __name__ == "__main__":
    unittest.main()
