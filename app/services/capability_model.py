"""CapabilityModel — модель возможностей клиента."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityModel:
    """Модель возможностей клиента.

    Каждый клиент (V2RayNG, sing-box, Hiddify и т.д.) описывается набором capability.
    Это данные, а не код — позволяет добавлять клиентов без изменения production-кода.
    """

    client_id: str
    capabilities: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    capability_version: int = 1
    schema_version: int = 1

    def has(self, capability: str) -> bool:
        """Проверяет наличие capability."""
        return capability in self.capabilities

    def has_all(self, capabilities: set[str]) -> bool:
        """Проверяет наличие всех capability."""
        return capabilities.issubset(self.capabilities)

    def has_any(self, capabilities: set[str]) -> bool:
        """Проверяет наличие хотя бы одной capability."""
        return bool(capabilities & self.capabilities)


# Стандартные capability
class Capability:
    # Форматы вывода
    SUPPORTS_URI = "supports_uri"
    SUPPORTS_JSON = "supports_json"
    SUPPORTS_YAML = "supports_yaml"
    SUPPORTS_QR = "supports_qr"

    # Параметры URI
    SUPPORTS_FLAT_PARAMS = "supports_flat_params"
    SUPPORTS_EXTRA = "supports_extra"
    SUPPORTS_DOWNLOAD_SETTINGS = "supports_download_settings"
    SUPPORTS_XMUX = "supports_xmux"

    # Транспорты
    SUPPORTS_XHTTP = "supports_xhttp"
    SUPPORTS_WS = "supports_ws"
    SUPPORTS_GRPC = "supports_grpc"
    SUPPORTS_HTTPUPGRADE = "supports_httpupgrade"
    SUPPORTS_REALITY = "supports_reality"
    SUPPORTS_HYSTERIA2 = "supports_hysteria2"
    SUPPORTS_TUIC = "supports_tuic"
    SUPPORTS_TROJAN = "supports_trojan"
    SUPPORTS_WIREGUARD = "supports_wireguard"
    SUPPORTS_SHADOWSOCKS = "supports_shadowsocks"

    # Особенности
    REQUIRES_ENCRYPTION = "requires_encryption"
    REQUIRES_TLS = "requires_tls"
    SUPPORTS_FLOW = "supports_flow"
    SUPPORTS_PUBLIC_KEY = "supports_public_key"
    SUPPORTS_SHORT_ID = "supports_short_id"


# Зависимости между capability
CAPABILITY_DEPENDENCIES: dict[str, set[str]] = {
    Capability.SUPPORTS_XHTTP: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_GRPC: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_REALITY: {Capability.SUPPORTS_EXTRA, Capability.SUPPORTS_FLOW},
    Capability.SUPPORTS_HYSTERIA2: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_TUIC: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_FLOW: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_PUBLIC_KEY: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_SHORT_ID: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_DOWNLOAD_SETTINGS: {Capability.SUPPORTS_EXTRA},
    Capability.SUPPORTS_XMUX: {Capability.SUPPORTS_EXTRA},
}


def validate_capability_model(model: CapabilityModel) -> list[str]:
    """Валидирует модель capability.

    Returns:
        Список ошибок (пустой = валидно).

    """
    errors = []

    # Проверка: есть хотя бы один формат вывода
    has_format = any(
        c in model.capabilities
        for c in (Capability.SUPPORTS_URI, Capability.SUPPORTS_JSON, Capability.SUPPORTS_YAML)
    )
    if not has_format:
        errors.append("Client must support at least one output format (uri, json, or yaml)")

    # Проверка зависимостей
    for cap in model.capabilities:
        deps = CAPABILITY_DEPENDENCIES.get(cap, set())
        for dep in deps:
            if dep not in model.capabilities:
                errors.append(f"{cap} requires {dep}, but {dep} is missing")

    return errors
