import json
import logging
import os
import subprocess
import tempfile
import uuid as uuid_module
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.models.vpn_client import DryRunResult, VpnClient
from app.services.exporters.uri_exporter import UriExporter
from app.services.transport_registry import create_default_registry as create_transport_registry
from app.services.capability_registry import create_default_registry as create_capability_registry
from app.services.capability_model import CapabilityModel, Capability

logger = logging.getLogger(__name__)


class SingBoxClientService:
    SERVER_HOST = "165.154.212.11"
    SING_BOX_BIN = "/usr/bin/sing-box"

    def __init__(self, conf_dir: str = "/etc/sing-box/conf"):
        self.conf_dir = Path(conf_dir)
        self.config: dict[str, Any] = {}
        self._load_config()
        # Initialize new architecture components
        self._transport_registry = create_transport_registry()
        self._uri_exporter = UriExporter(transport_registry=self._transport_registry)

    def _load_config(self) -> None:
        inbounds_path = self.conf_dir / "inbounds.json"
        if not inbounds_path.exists():
            raise FileNotFoundError(f"inbounds.json not found at {inbounds_path}")
        with open(inbounds_path) as f:
            self.config = json.load(f)

    def _find_inbound(self, inbound_tag: str) -> dict | None:
        for inbound in self.config.get("inbounds", []):
            if inbound.get("tag") == inbound_tag:
                return inbound
        return None

    def _uuid_exists(self, uuid: str) -> bool:
        for inbound in self.config.get("inbounds", []):
            for user in inbound.get("users", []):
                if user.get("uuid") == uuid:
                    return True
                if user.get("password") == uuid:
                    return True
        return False

    def _get_server_name(self, inbound: dict) -> str | None:
        tls = inbound.get("tls") or {}
        server_name = tls.get("server_name")
        if not server_name:
            reality = tls.get("reality") or {}
            handshake = reality.get("handshake") or {}
            server_name = handshake.get("server")
        return server_name

    def _get_short_id(self, inbound: dict) -> str:
        tls = inbound.get("tls") or {}
        reality = tls.get("reality") or {}
        short_ids = reality.get("short_id") or []
        if short_ids:
            return short_ids[0]
        return ""

    def _get_flow(self, inbound: dict) -> str:
        users = inbound.get("users") or []
        if users:
            flow = users[0].get("flow")
            if flow:
                return flow
        return ""

    def _run_singbox_check(self, temp_dir: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.SING_BOX_BIN, "check", "-C", temp_dir],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip() or result.stdout.strip()
        except FileNotFoundError:
            return False, "sing-box binary not found"
        except subprocess.TimeoutExpired:
            return False, "sing-box check timed out"
        except Exception as e:
            return False, str(e)

    def _write_temp_config(self, temp_dir: str) -> None:
        for fname in os.listdir(self.conf_dir):
            src = self.conf_dir / fname
            if src.is_file():
                dst = os.path.join(temp_dir, fname)
                with open(src) as fin:
                    data = fin.read()
                with open(dst, "w") as fout:
                    fout.write(data)

    def _build_vless_uri(
        self, uuid: str, inbound: dict, public_key: str | None = None
    ) -> str | None:
        """Generate VLESS URI using new architecture (UriExporter + TransportRegistry)."""
        if inbound.get("type") != "vless":
            return None
        port = inbound.get("listen_port")
        server_name = self._get_server_name(inbound)
        short_id = self._get_short_id(inbound)
        flow = self._get_flow(inbound)
        tag = inbound.get("tag", "")

        # Build data dict for UriExporter
        data = {
            "scheme": "vless",
            "host": self.SERVER_HOST,
            "port": port,
            "uuid": uuid,
            "name": tag,
            "transport": "tcp",
            "transport_params": {
                "security": "reality",
                "pbk": public_key or "",
                "sid": short_id,
                "spx": "",
                "fp": "chrome",
                "sni": server_name or "",
                "flow": flow,
            },
            "tls": True,
            "reality": True,
            "sni": server_name or "",
            "flow": flow,
            "extra": {},
        }

        # Use capability profile for V2RayNG (most common client)
        from app.services.capability_model import CapabilityModel, Capability
        capability = CapabilityModel(
            client_id="v2rayn",
            capabilities={
                Capability.SUPPORTS_URI,
                Capability.SUPPORTS_EXTRA,
                Capability.SUPPORTS_XHTTP,
                Capability.SUPPORTS_WS,
                Capability.SUPPORTS_GRPC,
                Capability.SUPPORTS_REALITY,
                Capability.SUPPORTS_FLOW,
                Capability.SUPPORTS_PUBLIC_KEY,
                Capability.SUPPORTS_SHORT_ID,
            },
        )

        try:
            return self._uri_exporter.export(data, capability)
        except Exception as e:
            logger.warning(f"Failed to build URI with new architecture: {e}")
            return None

    def create_client_dry_run(
        self,
        inbound_tag: str,
        email: str,
        public_key: str | None = None,
    ) -> DryRunResult:
        inbound = self._find_inbound(inbound_tag)
        if inbound is None:
            return DryRunResult(
                success=False,
                message=f"Inbound '{inbound_tag}' not found",
                errors=[f"inbound with tag '{inbound_tag}' does not exist"],
            )

        new_uuid = str(uuid_module.uuid4())
        if self._uuid_exists(new_uuid):
            return DryRunResult(
                success=False,
                message="UUID collision — generated UUID already exists",
                errors=["UUID collision detected"],
            )

        vpn_client = VpnClient(
            uuid=new_uuid,
            email=email,
            inbound_tag=inbound_tag,
        )

        config_copy = deepcopy(self.config)
        target_inbound = None
        for inbound in config_copy.get("inbounds", []):
            if inbound.get("tag") == inbound_tag:
                target_inbound = inbound
                break

        inbound_type = target_inbound["type"]
        if inbound_type in ("vless", "vmess", "tuic"):
            new_user = {"uuid": new_uuid}
            existing_users = target_inbound.get("users", [])
            if existing_users and "flow" in existing_users[0]:
                new_user["flow"] = existing_users[0]["flow"]
            target_inbound.setdefault("users", []).append(new_user)
        elif inbound_type == "hysteria2":
            target_inbound.setdefault("users", []).append(
                {"password": new_uuid}
            )
        elif inbound_type == "http":
            pass
        else:
            return DryRunResult(
                success=False,
                message=f"Unsupported inbound type '{inbound_type}'",
                errors=[f"inbound type '{inbound_type}' not supported"],
            )

        temp_dir_obj = tempfile.mkdtemp(prefix="singbox_dryrun_")
        try:
            self._write_temp_config(temp_dir_obj)
            temp_inbounds = os.path.join(temp_dir_obj, "inbounds.json")
            with open(temp_inbounds, "w") as f:
                json.dump(config_copy, f, indent=2, ensure_ascii=False)

            check_ok, check_err = self._run_singbox_check(temp_dir_obj)
            if not check_ok:
                return DryRunResult(
                    success=False,
                    message=f"sing-box check failed: {check_err}",
                    errors=[f"sing-box check failed: {check_err}"],
                )

            vless_uri = self._build_vless_uri(new_uuid, target_inbound, public_key)
            return DryRunResult(
                success=True,
                message=f"Client {email} created (dry-run)",
                vpn_client=vpn_client,
                vless_uri=vless_uri,
            )
        finally:
            for fname in os.listdir(temp_dir_obj):
                try:
                    os.remove(os.path.join(temp_dir_obj, fname))
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir_obj)
            except OSError:
                pass

    def disable_client_dry_run(self, uuid: str) -> DryRunResult:
        if not self._uuid_exists(uuid):
            return DryRunResult(
                success=False,
                message=f"UUID '{uuid}' not found",
                errors=[f"UUID '{uuid}' does not exist in any inbound"],
            )

        config_copy = deepcopy(self.config)
        found = False
        for inbound in config_copy.get("inbounds", []):
            users = inbound.get("users", [])
            inbound["users"] = [
                u for u in users
                if u.get("uuid") != uuid and u.get("password") != uuid
            ]
            original_count = len(users)
            new_count = len(inbound["users"])
            if new_count < original_count:
                found = True

        if not found:
            return DryRunResult(
                success=False,
                message=f"UUID '{uuid}' not found during disable",
                errors=[f"UUID '{uuid}' could not be located for removal"],
            )

        temp_dir_obj = tempfile.mkdtemp(prefix="singbox_dryrun_")
        try:
            self._write_temp_config(temp_dir_obj)
            temp_inbounds = os.path.join(temp_dir_obj, "inbounds.json")
            with open(temp_inbounds, "w") as f:
                json.dump(config_copy, f, indent=2, ensure_ascii=False)

            check_ok, check_err = self._run_singbox_check(temp_dir_obj)
            if not check_ok:
                return DryRunResult(
                    success=False,
                    message=f"sing-box check failed: {check_err}",
                    errors=[f"sing-box check failed: {check_err}"],
                )

            return DryRunResult(
                success=True,
                message=f"Client with UUID '{uuid}' disabled (removed in memory)",
            )
        finally:
            for fname in os.listdir(temp_dir_obj):
                try:
                    os.remove(os.path.join(temp_dir_obj, fname))
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir_obj)
            except OSError:
                pass

    def remove_client_dry_run(self, uuid: str) -> DryRunResult:
        return self.disable_client_dry_run(uuid)

    def verify_config(self, config: dict) -> tuple[bool, str]:
        temp_dir_obj = tempfile.mkdtemp(prefix="singbox_verify_")
        try:
            self._write_temp_config(temp_dir_obj)
            temp_inbounds = os.path.join(temp_dir_obj, "inbounds.json")
            with open(temp_inbounds, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            check_ok, check_err = self._run_singbox_check(temp_dir_obj)
            if not check_ok:
                return False, check_err
            return True, ""
        finally:
            for fname in os.listdir(temp_dir_obj):
                try:
                    os.remove(os.path.join(temp_dir_obj, fname))
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir_obj)
            except OSError:
                pass