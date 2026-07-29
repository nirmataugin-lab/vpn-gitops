import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from app.database import DB_PATH, get_connection, init_db, transaction
from app.models.vpn_client import VpnClient
from app.services.singbox_client_db_service import SingBoxClientDbService
from app.services.singbox_client_service import SingBoxClientService
from app.services.singbox_config_service import SingBoxConfigService
from app.services.vpn_client_repository import VpnClientRepository

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
                    "handshake": {"server": "www.iij.ad.jp", "server_port": 443},
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
        {
            "type": "vmess",
            "tag": "vmess-ws",
            "listen": "127.0.0.1",
            "listen_port": 8001,
            "users": [{"uuid": "d0b8fd48-185a-467d-9c10-447ede1228e8"}],
            "transport": {"type": "ws", "path": "/vmess-argo"},
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


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = _make_temp_conf()
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)

        self._orig_db_path = DB_PATH
        import app.database as dbmod

        dbmod.DB_PATH = self.db_path
        init_db()
        self.repo = VpnClientRepository(db_path=self.db_path)

    def tearDown(self):
        import app.database as dbmod

        dbmod.DB_PATH = self._orig_db_path
        for fname in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, fname))
        os.rmdir(self.tmpdir)
        os.unlink(self.db_path)

    # --- 1. VpnClientRepository: create + count + rollback -----------------------
    def test_repository_create_and_count(self):
        count_before = self.repo.count()
        client = VpnClient(
            uuid="test-uuid-1111",
            email="repo-test@example.com",
            inbound_tag="vless-reality",
        )
        self.repo.create(client)
        self.assertEqual(self.repo.count(), count_before + 1)
        got = self.repo.get_by_uuid("test-uuid-1111")
        self.assertIsNotNone(got)
        self.assertEqual(got.email, "repo-test@example.com")

    def test_repository_rollback(self):
        count_before = self.repo.count()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            client = VpnClient(
                uuid="rollback-uuid",
                email="rollback@test.com",
                inbound_tag="vless-reality",
            )
            self.repo.create(client, conn=conn)
            self.assertEqual(self.repo.count(conn=conn), count_before + 1)
            conn.rollback()
        finally:
            conn.close()
        self.assertEqual(self.repo.count(), count_before)

    def test_repository_delete(self):
        client = VpnClient(
            uuid="delete-uuid",
            email="delete@test.com",
            inbound_tag="vless-reality",
        )
        self.repo.create(client)
        self.assertIsNotNone(self.repo.get_by_uuid("delete-uuid"))
        self.repo.delete("delete-uuid")
        self.assertIsNone(self.repo.get_by_uuid("delete-uuid"))

    # --- 2. SingBoxClientDbService: create client + generate URI -----------------
    def test_db_service_create_client_vless(self):
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        client, uri = db_svc.create_client(
            email="db-svc-test", inbound_tag="vless-reality"
        )
        self.assertIsNotNone(client.uuid)
        self.assertEqual(client.email, "db-svc-test")
        self.assertEqual(client.inbound_tag, "vless-reality")
        self.assertIsNotNone(uri)
        self.assertTrue(uri.startswith("vless://"))
        self.assertIn(client.uuid, uri)
        self.assertIn("165.154.212.11", uri)

    def test_db_service_create_client_vmess(self):
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        client, uri = db_svc.create_client(
            email="vmess-test", inbound_tag="vmess-ws"
        )
        self.assertIsNotNone(client.uuid)
        self.assertIsNone(uri)

    def test_db_service_create_client_inbound_not_found(self):
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        with self.assertRaises(ValueError):
            db_svc.create_client(email="bad", inbound_tag="nonexistent")

    def test_db_service_get_client(self):
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        client, _ = db_svc.create_client(
            email="get-test", inbound_tag="vless-reality"
        )
        got = db_svc.get_client(client.uuid)
        self.assertIsNotNone(got)
        self.assertEqual(got.uuid, client.uuid)

    # --- 3. SingBoxConfigService: in-memory config manipulation ------------------
    def test_config_service_add_client(self):
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        original_count = config_svc.user_count

        client = VpnClient(
            uuid="new-uuid-for-config",
            email="config-test",
            inbound_tag="vless-reality",
        )
        modified = config_svc.add_client(client)

        new_count = sum(
            len(inb.get("users", [])) for inb in modified.get("inbounds", [])
        )
        self.assertEqual(new_count, original_count + 1)

        target = None
        for inbound in modified.get("inbounds", []):
            if inbound.get("tag") == "vless-reality":
                target = inbound
                break
        self.assertIsNotNone(target)
        uuids = [u["uuid"] for u in target["users"]]
        self.assertIn("new-uuid-for-config", uuids)

    def test_config_service_original_unchanged(self):
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        original_hash = config_svc.config_hash

        client = VpnClient(
            uuid="another-uuid",
            email="no-change",
            inbound_tag="vless-reality",
        )
        config_svc.add_client(client)

        self.assertEqual(config_svc.config_hash, original_hash)

    def test_config_service_remove_client(self):
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        config_copy = config_svc.add_client(
            VpnClient(
                uuid="remove-me",
                email="remove-test",
                inbound_tag="vless-reality",
            )
        )
        count_with = sum(
            len(inb.get("users", [])) for inb in config_copy.get("inbounds", [])
        )
        config_removed = config_svc.remove_client(config_copy, "remove-me")
        count_without = sum(
            len(inb.get("users", []))
            for inb in config_removed.get("inbounds", [])
        )
        self.assertEqual(count_without, count_with - 1)

    def test_config_service_add_to_unsupported_raises(self):
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        with self.assertRaises(ValueError):
            config_svc.add_client(
                VpnClient(
                    uuid="x", email="x", inbound_tag="nonexistent"
                )
            )

    # --- 4. SingBoxClientService.verify_config ----------------------------------
    @mock.patch.object(
        SingBoxClientService,
        "_run_singbox_check",
        return_value=(True, ""),
    )
    def test_verify_config_passes(self, mock_check):
        svc = SingBoxClientService(conf_dir=self.tmpdir)
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        client = VpnClient(
            uuid="verify-uuid",
            email="verify-test",
            inbound_tag="vless-reality",
        )
        modified = config_svc.add_client(client)
        ok, err = svc.verify_config(modified)
        self.assertTrue(ok)
        self.assertEqual(err, "")

    # --- 5. Full pipeline end-to-end (with mock check) --------------------------
    @mock.patch.object(
        SingBoxClientService,
        "_run_singbox_check",
        return_value=(True, ""),
    )
    def test_full_pipeline_with_rollback(self, mock_check):
        count_before = self.repo.count()
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        singbox_svc = SingBoxClientService(conf_dir=self.tmpdir)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            client, uri = db_svc.create_client(
                email="full-pipeline-test",
                inbound_tag="vless-reality",
                conn=conn,
            )
            self.assertEqual(self.repo.count(conn=conn), count_before + 1)
            self.assertIsNotNone(uri)
            self.assertTrue(uri.startswith("vless://"))

            modified = config_svc.add_client(client)

            ok, err = singbox_svc.verify_config(modified)
            self.assertTrue(ok)

            conn.rollback()
        finally:
            conn.close()

        self.assertEqual(self.repo.count(), count_before)

    # --- 6. Verify live config unchanged after dry-run --------------------------
    @mock.patch.object(
        SingBoxClientService,
        "_run_singbox_check",
        return_value=(True, ""),
    )
    def test_no_live_config_change(self, mock_check):
        config_svc = SingBoxConfigService(conf_dir=self.tmpdir)
        db_svc = SingBoxClientDbService(
            repository=self.repo, conf_dir=self.tmpdir
        )
        singbox_svc = SingBoxClientService(conf_dir=self.tmpdir)

        original_hash = config_svc.config_hash
        original_users = config_svc.user_count

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            client, uri = db_svc.create_client(
                email="no-change-test", inbound_tag="vless-reality", conn=conn
            )
            modified = config_svc.add_client(client)
            ok, err = singbox_svc.verify_config(modified)
            self.assertTrue(ok)
            conn.rollback()
        finally:
            conn.close()

        config_svc2 = SingBoxConfigService(conf_dir=self.tmpdir)
        self.assertEqual(config_svc2.config_hash, original_hash)
        self.assertEqual(config_svc2.user_count, original_users)
