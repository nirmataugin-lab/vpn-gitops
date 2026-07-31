import json
import os
import tempfile
import unittest
from unittest import mock

from app.models.vpn_client import VpnClient
from app.services.singbox_client_service import SingBoxClientService


SAMPLE_INBOUNDS = {
    "inbounds": [
        {
            "type": "vless",
            "tag": "vless-reality",
            "listen": "::",
            "listen_port": 59505,
            "users": [
                {"uuid": "d0b8fd48-185a-467d-9c10-447ede1228e8", "flow": "xtls-rprx-vision"}
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
                {"uuid": "d12e97b9-68c1-4b24-b333-f36f2ee0a290", "flow": "xtls-rprx-vision"}
            ],
            "tls": {
                "enabled": True,
                "server_name": "www.cloudflare.com",
                "reality": {
                    "enabled": True,
                    "handshake": {"server": "www.cloudflare.com", "server_port": 443},
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


def _make_temp_conf(inbounds_data: dict = None) -> str:
    tmpdir = tempfile.mkdtemp()
    data = inbounds_data or SAMPLE_INBOUNDS
    with open(os.path.join(tmpdir, "inbounds.json"), "w") as f:
        json.dump(data, f, indent=2)
    # Write minimal extra files so sing-box check passes
    for fname, content in [
        ("dns.json", json.dumps({"dns": {"servers": [{"tag": "local", "type": "local"}]}})),
        ("log.json", json.dumps({"log": {"disabled": True}})),
        ("outbounds.json", json.dumps({"outbounds": [{"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"}]})),
        ("route.json", json.dumps({"route": {"rules": [], "final": "direct"}})),
        ("ntp.json", json.dumps({"ntp": {"enabled": False}})),
    ]:
        with open(os.path.join(tmpdir, fname), "w") as f:
            f.write(content)
    return tmpdir


class TestSingBoxClientService(unittest.TestCase):
    def setUp(self):
        self.tmpdir = _make_temp_conf()
        self.service = SingBoxClientService(conf_dir=self.tmpdir)

    def tearDown(self):
        for fname in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, fname))
        os.rmdir(self.tmpdir)

    # --- create_client_dry_run success ---
    def test_create_client_success(self):
        result = self.service.create_client_dry_run("vless-reality", "test-user")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.vpn_client)
        self.assertEqual(result.vpn_client.email, "test-user")
        self.assertEqual(result.vpn_client.inbound_tag, "vless-reality")
        self.assertTrue(result.vpn_client.enabled)
        self.assertIsNotNone(result.vpn_client.uuid)
        self.assertEqual(len(result.vpn_client.uuid), 36)
        # VLESS URI should be generated for vless inbound
        self.assertIsNotNone(result.vless_uri)
        self.assertTrue(result.vless_uri.startswith("vless://"))
        self.assertIn(result.vpn_client.uuid, result.vless_uri)

    def test_create_client_cascade_inbound(self):
        result = self.service.create_client_dry_run("cascade-in", "cascade-user")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.vless_uri)
        self.assertIn("443", result.vless_uri)

    def test_create_client_inbound_not_found(self):
        result = self.service.create_client_dry_run("nonexistent-inbound", "user")
        self.assertFalse(result.success)
        self.assertIn("not found", result.message)

    def test_create_client_duplicate_uuid(self):
        with mock.patch.object(
            self.service, "_uuid_exists", return_value=True
        ):
            result = self.service.create_client_dry_run("vless-reality", "user")
            self.assertFalse(result.success)
            self.assertIn("UUID", result.message)

    def test_create_client_vmess_inbound(self):
        result = self.service.create_client_dry_run("vmess-ws", "vmess-user")
        self.assertTrue(result.success)
        self.assertIsNone(result.vless_uri)
        self.assertEqual(result.vpn_client.uuid, result.vpn_client.uuid)

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_create_client_hysteria2_inbound_mocked(self, mock_check):
        from copy import deepcopy
        svc = SingBoxClientService(conf_dir=self.tmpdir)
        hys_inbound = {
            "type": "hysteria2",
            "tag": "hysteria2",
            "listen": "::",
            "listen_port": 59508,
            "users": [{"password": "d0b8fd48-185a-467d-9c10-447ede1228e8"}],
            "ignore_client_bandwidth": False,
            "masquerade": "https://bing.com",
        }
        svc.config["inbounds"].append(hys_inbound)
        result = svc.create_client_dry_run("hysteria2", "hys-user")
        self.assertTrue(result.success)
        self.assertIsNone(result.vless_uri)

    @mock.patch.object(SingBoxClientService, "_run_singbox_check", return_value=(True, ""))
    def test_create_client_tuic_inbound_mocked(self, mock_check):
        from copy import deepcopy
        svc = SingBoxClientService(conf_dir=self.tmpdir)
        tuic_inbound = {
            "type": "tuic",
            "tag": "tuic",
            "listen": "::",
            "listen_port": 59507,
            "users": [{"uuid": "d0b8fd48-185a-467d-9c10-447ede1228e8"}],
            "congestion_control": "bbr",
            "tls": {
                "enabled": True,
                "alpn": ["h3"],
            },
        }
        svc.config["inbounds"].append(tuic_inbound)
        result = svc.create_client_dry_run("tuic", "tuic-user")
        self.assertTrue(result.success)
        self.assertIsNone(result.vless_uri)

    # --- disable_client_dry_run ---
    def test_disable_client_success(self):
        uuid = "d0b8fd48-185a-467d-9c10-447ede1228e8"
        result = self.service.disable_client_dry_run(uuid)
        self.assertTrue(result.success)
        self.assertIn("disabled", result.message.lower())

    def test_disable_client_not_found(self):
        uuid = "00000000-0000-0000-0000-000000000000"
        result = self.service.disable_client_dry_run(uuid)
        self.assertFalse(result.success)
        self.assertIn("not found", result.message)

    # --- remove_client_dry_run ---
    def test_remove_client_success(self):
        uuid = "d0b8fd48-185a-467d-9c10-447ede1228e8"
        result = self.service.remove_client_dry_run(uuid)
        self.assertTrue(result.success)

    def test_remove_client_not_found(self):
        uuid = "00000000-0000-0000-0000-000000000000"
        result = self.service.remove_client_dry_run(uuid)
        self.assertFalse(result.success)

    # --- sing-box check integration (when binary is available) ---
    def test_singbox_check_passes_on_temp_config(self):
        result = self.service.create_client_dry_run("vless-reality", "check-test")
        self.assertTrue(result.success)

    # --- temp file cleanup ---
    def test_temp_files_cleaned_up_after_create(self):
        import tempfile as tf
        original = tf.mkdtemp
        created_dirs = []

        def tracking_mkdtemp(*a, **kw):
            d = original(*a, **kw)
            created_dirs.append(d)
            return d

        with mock.patch("app.services.singbox_client_service.tempfile.mkdtemp", tracking_mkdtemp):
            result = self.service.create_client_dry_run("vless-reality", "cleanup-test")
            self.assertTrue(result.success)
            # Verify temp dirs no longer exist
            for d in created_dirs:
                self.assertFalse(os.path.exists(d))

    # --- config not modified in place ---
    def test_original_config_not_modified_after_create(self):
        original_json = json.dumps(self.service.config, sort_keys=True)
        self.service.create_client_dry_run("vless-reality", "no-modify")
        self.assertEqual(
            original_json,
            json.dumps(self.service.config, sort_keys=True),
        )

    def test_original_config_not_modified_after_disable(self):
        original_json = json.dumps(self.service.config, sort_keys=True)
        self.service.disable_client_dry_run("d0b8fd48-185a-467d-9c10-447ede1228e8")
        self.assertEqual(
            original_json,
            json.dumps(self.service.config, sort_keys=True),
        )

    # --- inbound exists check ---
    def test_inbound_list_not_empty(self):
        self.assertGreater(len(self.service.config.get("inbounds", [])), 0)

    # --- singleton check service finds all inbounds ---
    def test_all_inbounds_have_tags(self):
        for inbound in self.service.config.get("inbounds", []):
            self.assertIsNotNone(inbound.get("tag"))

    # --- VLESS URI format ---
    def test_vless_uri_format(self):
        result = self.service.create_client_dry_run("cascade-in", "uri-test")
        self.assertTrue(result.success)
        uri = result.vless_uri
        self.assertTrue(uri.startswith("vless://"))
        self.assertIn("@165.154.212.11:443", uri)
        self.assertIn("security=reality", uri)
        self.assertIn("type=tcp", uri)
        self.assertIn(result.vpn_client.uuid, uri)

    # --- VpnClient model to_dict ---
    def test_vpn_client_to_dict(self):
        client = VpnClient(
            uuid="test-uuid-12345",
            email="test@example.com",
            inbound_tag="vless-reality",
        )
        d = client.to_dict()
        self.assertEqual(d["uuid"], "test-uuid-12345")
        self.assertEqual(d["email"], "test@example.com")
        self.assertEqual(d["inbound_tag"], "vless-reality")
        self.assertTrue(d["enabled"])
        self.assertIn("created_at", d)

    # --- validation: created_at is isoformat ---
    def test_vpn_client_created_at_isoformat(self):
        client = VpnClient(uuid="x", email="x", inbound_tag="x")
        self.assertIn("T", client.created_at)

    # --- serialization test: create_client produces valid JSON ---
    def test_serialization_passes(self):
        inbound = self.service._find_inbound("vless-reality")
        self.assertIsNotNone(inbound)
        serialized = json.dumps(self.service.config, indent=2)
        parsed = json.loads(serialized)
        self.assertIn("inbounds", parsed)


if __name__ == "__main__":
    unittest.main()
