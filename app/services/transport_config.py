"""TransportConfig — типизированные конфигурации для каждого транспорта.

Architecture v1.0.1: каждый транспорт имеет свой датакласс с конкретными полями.
Никаких dict[str, Any] — все поля типизированы.
"""

from dataclasses import KW_ONLY, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransportConfig:
    """Базовый класс конфигурации транспорта."""

    _: KW_ONLY
    schema_version: int = 1
    transport_version: int = 1


@dataclass(frozen=True)
class DownloadSettings:
    """Настройки загрузки для транспортов."""

    address: str = ""
    port: int = 0
    path: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class XMuxSettings:
    """Настройки XMUX мультиплексирования."""

    enabled: bool = False
    concurrency: int = 8
    idle_timeout: str = "60s"
    stream_buffer_size: int = 65536


@dataclass(frozen=True)
class Headers:
    """HTTP headers."""

    entries: dict[str, str] = field(default_factory=dict)

    def to_uri_format(self) -> str:
        return ";".join(f"{k}:{v}" for k, v in self.entries.items())


@dataclass(frozen=True)
class XHttpConfig(TransportConfig):
    """xHTTP транспорт (RFC 9110 + xHTTP extensions)."""

    host: str
    port: int
    uuid: str
    path: str = "/"
    flow: str = ""
    encryption: str = "none"
    download_settings: DownloadSettings = field(default_factory=DownloadSettings)
    xmux: XMuxSettings = field(default_factory=XMuxSettings)


@dataclass(frozen=True)
class WebSocketConfig(TransportConfig):
    """WebSocket транспорт."""

    host: str
    port: int
    uuid: str
    path: str = "/"
    headers: Headers = field(default_factory=Headers)
    early_data_header_name: str = ""
    max_early_data: int = 0


@dataclass(frozen=True)
class GrpcConfig(TransportConfig):
    """gRPC транспорт."""

    host: str
    port: int
    uuid: str
    service_name: str = ""
    multi_mode: bool = False


@dataclass(frozen=True)
class HttpUpgradeConfig(TransportConfig):
    """HTTPUpgrade транспорт."""

    host: str
    port: int
    uuid: str
    path: str = "/"
    headers: Headers = field(default_factory=Headers)


@dataclass(frozen=True)
class RealityConfig(TransportConfig):
    """REALITY транспорт."""

    host: str
    port: int
    uuid: str
    flow: str = ""
    public_key: str = ""
    short_id: str = ""
    spider_x: str = ""
    fingerprint: str = "chrome"


@dataclass(frozen=True)
class Hysteria2Config(TransportConfig):
    """Hysteria2 транспорт."""

    host: str
    port: int
    password: str
    obfs: str = ""
    obfs_password: str = ""
    sni: str = ""
    download_settings: DownloadSettings = field(default_factory=DownloadSettings)


@dataclass(frozen=True)
class TuicConfig(TransportConfig):
    """TUIC транспорт."""

    host: str
    port: int
    uuid: str
    password: str
    congestion_control: str = "bbr"
    heartbeat: str = "10s"
    download_settings: DownloadSettings = field(default_factory=DownloadSettings)


@dataclass(frozen=True)
class TrojanConfig(TransportConfig):
    """Trojan транспорт."""

    host: str
    port: int
    password: str
    sni: str = ""
    fingerprint: str = "chrome"


@dataclass(frozen=True)
class WireGuardConfig(TransportConfig):
    """WireGuard транспорт."""

    host: str
    port: int
    private_key: str
    public_key: str
    reserved: str = ""
    mtu: int = 1280


@dataclass(frozen=True)
class ShadowsocksConfig(TransportConfig):
    """Shadowsocks транспорт."""

    host: str
    port: int
    method: str
    password: str
    plugin: str = ""
    plugin_opts: str = ""


@dataclass(frozen=True)
class VLessConfig(TransportConfig):
    """VLESS транспорт (базовый, без транспорта)."""

    host: str
    port: int
    uuid: str
    flow: str = ""
    encryption: str = "none"


@dataclass(frozen=True)
class VMessConfig(TransportConfig):
    """VMess транспорт."""

    host: str
    port: int
    uuid: str
    alter_id: int = 0
    security: str = "auto"


TRANSPORT_CONFIG_MAP: dict[str, type[TransportConfig]] = {
    "xhttp": XHttpConfig,
    "ws": WebSocketConfig,
    "grpc": GrpcConfig,
    "httpupgrade": HttpUpgradeConfig,
    "reality": RealityConfig,
    "hysteria2": Hysteria2Config,
    "tuic": TuicConfig,
    "trojan": TrojanConfig,
    "wireguard": WireGuardConfig,
    "shadowsocks": ShadowsocksConfig,
    "vless": VLessConfig,
    "vmess": VMessConfig,
}


def get_transport_config_class(transport: str) -> type[TransportConfig]:
    """Возвращает класс конфигурации для транспорта."""
    return TRANSPORT_CONFIG_MAP.get(transport.lower(), TransportConfig)