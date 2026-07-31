import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from app.services.singbox_client_service import SingBoxClientService
from app.services.singbox_config_service import SingBoxConfigService

# The script module — imported via importlib to control DB_PATH monkey-patch
import importlib.util
import sys

SPEC = importlib.util.spec_from_file_location(
    "singbox_prepare_client_apply",
    "scripts/singbox_prepare_client_apply.py",
)
MOD = importlib.util.module_from_spec(SPEC)

SAMPLE_INBOUNDS = {
    "inbounds": [
        {
            "type": "vless",
            "tag": "vless-reality",
            "listen": "::",
            "listen_port": 59505,
            "users": [
                {
                    "uuid": "d0b8fd48-185a-467d-9c10-447ede1228e8",
                    "flow": "xtls-rprx-vision",
                }
            ],
            "tls": {
                "enabled": True,
                "server_name": "www.iij.ad.jp",
                "reality": {
                    "enabled": True,
                    "handshake": {
                        "server": "www.iij.ad.jp",
                        "server_port": 443,
                    },
                    "private_key": "WAxxT-kZ2OaSUDUZStcd64CQgqIdgU2IbbDeaAIHrXQ",
                    "short_id": [""],
                },
            },
        },
        {
            "type": "vless",
            "tag": "cascade-in",
            "listen": "::",
            "listen_port": 443,
            "users": [
                {
                    "uuid": "d12e97b9-68c1-4b24-b333-f36f2ee0a290",
                    "flow": "xtls-rprx-vision",
                }
            ],
            "tls": {
                "enabled": True,
                "server_name": "www.cloudflare.com",
                "reality": {
                    "enabled": True,
                    "handshake": {
                        "server": "www.cloudflare.com",
                        "server_port": 443,
                    },
                    "private_key": "SKiso-t8Ja7b6xDWDc_wb8H3zLa--FC88Al2zk1cN20",
                    "short_id": ["aa9393a74b38bcb0"],
                },
            },
        },
    ]
}


def _make_temp_conf(inbounds_data: dict | None = None) -> str:
    tmpdir = tempfile.mkdtemp()
    data = inbounds_data or SAMPLE_INBOUNDS
    with open(os.path.join(tmpdir, "inbounds.json"), "w") as f:
        json.dump(data, f, indent=2)
    for fname, content in [
        (
            "dns.json",
            json.dumps(
                {"dns": {"servers": [{"tag": "local", "type": "local"}]}}
            ),
        ),
        ("log.json", json.dumps({"log": {"disabled": True}})),
        (
            "outbounds.json",
            json.dumps(
                {
                    "outbounds": [
                        {"type": "direct", "tag": "direct"},
                        {"type": "block", "tag": "block"},
                    ]
                }
            ),
        ),
        (
            "route.json",
            json.dumps({"route": {"rules": [], "final": "direct"}}),
        ),
        ("ntp.json", json.dumps({"ntp": {"enabled": False}})),
    ]:
        with open(os.path.join(tmpdir, fname), "w") as f:
            f.write(content)
    return tmpdir


def _setup_test_db(db_path: str) -> int:
    """Create users, subscriptions, vpn_clients tables and return test user id."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id BIGINT NOT NULL UNIQUE,
            username VARCHAR(128),
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_banned INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            balance REAL NOT NULL DEFAULT 0.0,
            trial_used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            plan_name VARCHAR(64) NOT NULL,
            start_date TEXT,
            end_date TEXT,
            traffic_limit_bytes INTEGER,
            traffic_used_bytes INTEGER NOT NULL DEFAULT 0,
            device_limit INTEGER NOT NULL DEFAULT 1,
            auto_renew INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS vpn_clients (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL,
            uuid VARCHAR(36) NOT NULL UNIQUE,
            subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
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
        "INSERT INTO users (id, telegram_id, username) VALUES (?, ?, ?)",
        (1, 6430387100, "TestUser"),
    )
    conn.execute(
        "INSERT INTO subscriptions (id, user_id, status, plan_name) "
        "VALUES (?, ?, ?, ?)",
        (1, 1, "active", "trial"),
    )
    conn.commit()
    conn.close()
    return 1  # user_id


class TestSingBoxPrepareClientApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SPEC.loader.exec_module(MOD)
        # Patch module-level constants after exec_module
        cls._patch_constants()

    @classmethod
    def _patch_constants(cls):
        MOD.PROD_DB_PATH = "/tmp/opencode/test_prepare_client_apply.db"
        MOD.CONF_DIR = "/tmp/opencode/test_prepare_client_apply_conf"
        MOD.INBOUNDS_PATH = f"{MOD.CONF_DIR}/inbounds.json"
        MOD.SERVER_ID = "vps2"
        MOD.DEFAULT_INBOUND_TAG = "vless-reality"

    def setUp(self):
        self._patch_constants()
        # Remove leftover db/conf
        if os.path.exists(MOD.PROD_DB_PATH):
            os.unlink(MOD.PROD_DB_PATH)
        if os.path.exists(MOD.CONF_DIR):
            for fname in os.listdir(MOD.CONF_DIR):
                os.remove(os.path.join(MOD.CONF_DIR, fname))
            os.rmdir(MOD.CONF_DIR)
        self._setup_db()
        self._setup_conf()

    def tearDown(self):
        if os.path.exists(MOD.PROD_DB_PATH):
            os.unlink(MOD.PROD_DB_PATH)
        if os.path.exists(MOD.CONF_DIR):
            for fname in os.listdir(MOD.CONF_DIR):
                os.remove(os.path.join(MOD.CONF_DIR, fname))
            os.rmdir(MOD.CONF_DIR)

    def _setup_db(self):
        _setup_test_db(MOD.PROD_DB_PATH)

    def _setup_conf(self):
        os.makedirs(MOD.CONF_DIR, exist_ok=True)
        with open(MOD.INBOUNDS_PATH, "w") as f:
            json.dump(SAMPLE_INBOUNDS, f, indent=2)
        for fname, content in [
            (
                "dns.json",
                json.dumps(
                    {"dns": {"servers": [{"tag": "local", "type": "local"}]}}
                ),
            ),
            ("log.json", json.dumps({"log": {"disabled": True}})),
            (
                "outbounds.json",
                json.dumps(
                    {
                        "outbounds": [
                            {"type": "direct", "tag": "direct"},
                            {"type": "block", "tag": "block"},
                        ]
                    }
                ),
            ),
            (
                "route.json",
                json.dumps({"route": {"rules": [], "final": "direct"}}),
            ),
            ("ntp.json", json.dumps({"ntp": {"enabled": False}})),
        ]:
            with open(os.path.join(MOD.CONF_DIR, fname), "w") as f:
                f.write(content)

    # ------------------------------------------------------------------
    # 1. default rollback
    # ------------------------------------------------------------------
    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_default_rollback(self, mock_check):
        """Default (no flags) rolls back — vpn_clients count unchanged."""
        count_before = MOD.count_vpn_clients()
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)

        report = MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=False,
        )

        self.assertTrue(report["success"])
        self.assertFalse(report["commit_db"])
        self.assertEqual(MOD.count_vpn_clients(), count_before)
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)
        self.assertIn("Rolled back", report["message"])
        self.assertIn("vpn_client", report)
        self.assertIn("uuid", report["vpn_client"])
        self.assertIn("vless_uri", report)

    # ------------------------------------------------------------------
    # 2. --commit-db saves vpn_clients only
    # ------------------------------------------------------------------
    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_commit_db_persists_vpn_clients(self, mock_check):
        """--commit-db persists the vpn_clients row; inbounds.json untouched."""
        count_before = MOD.count_vpn_clients()
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)

        report = MOD.run(
            telegram_id="6430387100",
            email="commit-test@example.com",
            inbound_tag="vless-reality",
            commit_db=True,
            apply_config=False,
        )

        self.assertTrue(report["success"])
        self.assertTrue(report["commit_db"])
        # vpn_clients count increased by 1
        self.assertEqual(MOD.count_vpn_clients(), count_before + 1)
        # inbounds.json untouched
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)
        # Verify the record is actually queryable
        conn = sqlite3.connect(MOD.PROD_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT uuid, status, server_id, inbound_tag FROM vpn_clients "
            "WHERE telegram_id = ?", (6430387100,)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["uuid"], report["vpn_client"]["uuid"])
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["server_id"], "vps2")

    # ------------------------------------------------------------------
    # 3. duplicate protection
    # ------------------------------------------------------------------
    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_duplicate_vpn_client_rejected(self, mock_check):
        """Creating a second vpn_client for same telegram_id+subscription_id is rejected."""
        # Insert first record via the pipeline
        report1 = MOD.run(
            telegram_id="6430387100",
            email="first@example.com",
            inbound_tag="vless-reality",
            commit_db=True,
            apply_config=False,
        )
        self.assertTrue(report1["success"])

        # Second attempt should fail
        report2 = MOD.run(
            telegram_id="6430387100",
            email="second@example.com",
            inbound_tag="vless-reality",
            commit_db=True,
            apply_config=False,
        )
        self.assertFalse(report2["success"])
        self.assertIn("already exists", report2["message"])

    # ------------------------------------------------------------------
    # 4. --apply-config forbidden
    # ------------------------------------------------------------------
    def test_apply_config_blocked(self):
        """--apply-config always errors at this stage."""
        report = MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=True,
        )
        self.assertFalse(report["success"])
        self.assertIn("apply-config disabled", report["message"])

    # ------------------------------------------------------------------
    # 5. live config hash unchanged (after rollback and after commit-db)
    # ------------------------------------------------------------------
    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_live_config_hash_unchanged_after_rollback(self, mock_check):
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)
        MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=False,
        )
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_live_config_hash_unchanged_after_commit_db(self, mock_check):
        hash_before = MOD.file_hash(MOD.INBOUNDS_PATH)
        MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=True,
            apply_config=False,
        )
        self.assertEqual(MOD.file_hash(MOD.INBOUNDS_PATH), hash_before)

    # ------------------------------------------------------------------
    # 6. sing-box check passes on temp config
    # ------------------------------------------------------------------
    def test_singbox_check_passes_on_temp_config(self):
        """Real sing-box check runs and passes on the generated temp config."""
        report = MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=False,
        )
        self.assertTrue(report["success"])
        self.assertTrue(report["singbox_check"]["passed"])

    # ------------------------------------------------------------------
    # 7. user not found
    # ------------------------------------------------------------------
    def test_user_not_found(self):
        report = MOD.run(
            telegram_id="9999999999",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=False,
        )
        self.assertFalse(report["success"])
        self.assertIn("not found", report["message"])

    # ------------------------------------------------------------------
    # 8. no active subscription
    # ------------------------------------------------------------------
    def test_no_active_subscription(self):
        """User exists but has no active subscription."""
        conn = sqlite3.connect(MOD.PROD_DB_PATH)
        conn.execute("UPDATE subscriptions SET status = 'expired' WHERE user_id = 1")
        conn.commit()
        conn.close()

        report = MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="vless-reality",
            commit_db=False,
            apply_config=False,
        )
        self.assertFalse(report["success"])
        self.assertIn("No active subscription", report["message"])

    # ------------------------------------------------------------------
    # 9. inbound tag not found
    # ------------------------------------------------------------------
    def test_inbound_tag_not_found(self):
        report = MOD.run(
            telegram_id="6430387100",
            email=None,
            inbound_tag="nonexistent-tag",
            commit_db=False,
            apply_config=False,
        )
        self.assertFalse(report["success"])
        self.assertIn("not found in live config", report["message"])


if __name__ == "__main__":
    unittest.main()
