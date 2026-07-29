import json
import logging
import uuid as uuid_module
from pathlib import Path
from typing import Any

from app.models.vpn_client import VpnClient
from app.services.vpn_client_repository import VpnClientRepository
from app.services.exporters.uri_exporter import UriExporter
from app.services.transport_registry import create_default_registry as create_transport_registry
from app.services.capability_registry import create_default_registry as create_capability_registry
from app.services.capability_model import CapabilityModel, Capability

logger = logging.getLogger(__name__)


class SingBoxClientDbService:
    SERVER_HOST = "165.154.212.11"

    def __init__(
        self,
        repository: VpnClientRepository | None = None,
        conf_dir: str = "/etc/sing-box/conf",
    ):
        self.repo = repository or VpnClientRepository()
        self.conf_dir = Path(conf_dir)
        # Initialize new architecture components
        self._transport_registry = create_transport_registry()
        self._capability_registry = create_capability_registry()
        self._uri_exporter = UriExporter(transport_registry=create_transport_registry())

    def _load_inbounds(self) -> list[dict]:
        inbounds_path = self.conf_dir / "inbounds.json"
        with open(inbounds_path) as f:
            config: dict[str, Any] = json.load(f)
        return config.get("inbounds", [])

    def _find_inbound(self, inbound_tag: str) -> dict | None:
        for inbound in self._load_inbounds():
            if inbound.get("tag") == inbound_tag:
                return inbound
        return None

    def _build_vless_uri(
        self, client: VpnClient, public_key: str | None = None
    ) -> str | None:
        """Generate VLESS URI using new architecture (UriExporter + TransportRegistry)."""
        inbound = self._find_inbound(client.inbound_tag)
        if inbound is None or inbound.get("type") != "vless":
            return None

        port = inbound.get("listen_port")
        tls = inbound.get("tls") or {}
        server_name = tls.get("server_name")
        if not server_name:
            reality = tls.get("reality") or {}
            handshake = reality.get("handshake") or {}
            server_name = handshake.get("server")

        reality = tls.get("reality") or {}
        short_ids = reality.get("short_id") or []
        short_id = short_ids[0] if short_ids else ""

        users = inbound.get("users") or []
        flow = users[0].get("flow", "") if users else ""

        # Build data dict for UriExporter
        data = {
            "scheme": "vless",
            "host": self.SERVER_HOST,
            "port": port,
            "uuid": client.uuid,
            "name": inbound.get("tag", "").replace(" ", "_"),
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

        # Use capability profile for V2RayNG-like clients (supports extra)
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

        return self._uri_exporter.export(data, capability)

    def create_client(
        self,
        email: str,
        inbound_tag: str,
        public_key: str | None = None,
        conn=None,
    ) -> tuple[VpnClient, str | None]:
        inbound = self._find_inbound(inbound_tag)
        if inbound is None:
            raise ValueError(f"Inbound '{inbound_tag}' not found")

        new_uuid = str(uuid_module.uuid4())
        client = VpnClient(uuid=new_uuid, email=email, inbound_tag=inbound_tag)
        self.repo.create(client, conn=conn)
        uri = self._build_vless_uri(client, public_key)
        return client, uri

    def get_client(self, uuid: str, conn=None) -> VpnClient | None:
        return self.repo.get_by_uuid(uuid, conn=conn)