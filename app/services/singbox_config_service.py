import hashlib
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.models.vpn_client import VpnClient

logger = logging.getLogger(__name__)


class SingBoxConfigService:
    def __init__(self, conf_dir: str = "/etc/sing-box/conf"):
        self.conf_dir = Path(conf_dir)
        self._config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        inbounds_path = self.conf_dir / "inbounds.json"
        with open(inbounds_path) as f:
            return json.load(f)

    def add_client(self, client: VpnClient) -> dict[str, Any]:
        config_copy: dict[str, Any] = deepcopy(self._config)
        target_inbound = None
        for inbound in config_copy.get("inbounds", []):
            if inbound.get("tag") == client.inbound_tag:
                target_inbound = inbound
                break

        if target_inbound is None:
            raise ValueError(f"Inbound '{client.inbound_tag}' not found")

        inbound_type = target_inbound["type"]
        if inbound_type in ("vless", "vmess", "tuic"):
            new_user: dict[str, Any] = {"uuid": client.uuid}
            existing_users = target_inbound.get("users", [])
            if existing_users and "flow" in existing_users[0]:
                new_user["flow"] = existing_users[0]["flow"]
            target_inbound.setdefault("users", []).append(new_user)
        elif inbound_type == "hysteria2":
            target_inbound.setdefault("users", []).append(
                {"password": client.uuid}
            )
        elif inbound_type == "http":
            pass
        else:
            raise ValueError(f"Unsupported inbound type '{inbound_type}'")

        return config_copy

    def remove_client(self, config: dict[str, Any], uuid: str) -> dict[str, Any]:
        config_copy: dict[str, Any] = deepcopy(config)
        for inbound in config_copy.get("inbounds", []):
            inbound["users"] = [
                u
                for u in inbound.get("users", [])
                if u.get("uuid") != uuid and u.get("password") != uuid
            ]
        return config_copy

    @property
    def user_count(self) -> int:
        count = 0
        for inbound in self._config.get("inbounds", []):
            count += len(inbound.get("users", []))
        return count

    @property
    def config_hash(self) -> str:
        return hashlib.md5(
            json.dumps(self._config, sort_keys=True).encode()
        ).hexdigest()
