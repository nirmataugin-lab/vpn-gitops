"""TransportSerializer — протокол и базовые сериализаторы."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.capability_model import Capability
from app.services.transport_config import (
    XHttpConfig,
    WebSocketConfig,
    GrpcConfig,
    HttpUpgradeConfig,
    RealityConfig,
    Hysteria2Config,
    TuicConfig,
    TrojanConfig,
    WireGuardConfig,
    ShadowsocksConfig,
)


class TransportSerializer(ABC):
    """Базовый класс сериализатора транспорта."""

    @abstractmethod
    def serialize(self, config: "TransportConfig") -> dict[str, Any]:
        """Сериализует конфиг транспорта в dict."""

    @abstractmethod
    def required_capabilities(self, config: "TransportConfig") -> set[Capability]:
        """Возвращает capability, необходимые для этого транспорта."""

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Возвращает параметры для URI query string.

        Args:
            params: Словарь параметров транспорта (transport_params)

        Returns:
            Словарь параметров для URI query string
        """
        return {}


class TCPSerializer(TransportSerializer):
    """Сериализатор для базового TCP транспорта."""

    def serialize(self, config: "TransportConfig") -> dict[str, Any]:
        return {
            "type": "tcp",
        }

    def required_capabilities(self, config: "TransportConfig") -> set[Capability]:
        return set()

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "tcp"}
        if "security" in params:
            result["security"] = params["security"]
        return result


class XHttpSerializer(TransportSerializer):
    """Сериализатор для xHTTP."""

    def serialize(self, config: "XHttpConfig") -> dict[str, Any]:
        return {
            "type": "xhttp",
            "host": config.host,
            "path": config.path,
        }

    def required_capabilities(self, config: "XHttpConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "xhttp"}
        if "path" in params:
            result["path"] = params["path"]
        if "host" in params:
            result["host"] = params["host"]
        return result


class WebSocketSerializer(TransportSerializer):
    """Сериализатор для WebSocket."""

    def serialize(self, config: "WebSocketConfig") -> dict[str, Any]:
        return {
            "type": "ws",
            "path": config.path,
            "headers": config.headers,
        }

    def required_capabilities(self, config: "WebSocketConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "ws"}
        if "path" in params:
            result["path"] = params["path"]
        if "headers" in params and params["headers"]:
            result["headers"] = ";".join(f"{k}:{v}" for k, v in params["headers"].items())
        return result


class GrpcSerializer(TransportSerializer):
    """Сериализатор для gRPC."""

    def serialize(self, config: "GrpcConfig") -> dict[str, Any]:
        return {
            "type": "grpc",
            "serviceName": config.service_name,
            "multiMode": config.multi_mode,
        }

    def required_capabilities(self, config: "GrpcConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "grpc"}
        if "serviceName" in params:
            result["serviceName"] = params["serviceName"]
        return result


class HttpUpgradeSerializer(TransportSerializer):
    """Сериализатор для HTTPUpgrade."""

    def serialize(self, config: "HttpUpgradeConfig") -> dict[str, Any]:
        return {
            "type": "httpupgrade",
            "path": config.path,
            "headers": config.headers,
        }

    def required_capabilities(self, config: "HttpUpgradeConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "httpupgrade"}
        if "path" in params:
            result["path"] = params["path"]
        if "headers" in params and params["headers"]:
            result["headers"] = ";".join(f"{k}:{v}" for k, v in params["headers"].items())
        return result


class RealitySerializer(TransportSerializer):
    """Сериализатор для REALITY (TCP + REALITY security)."""

    def serialize(self, config: "RealityConfig") -> dict[str, Any]:
        return {
            "type": "tcp",
            "security": "reality",
            "pbk": config.public_key,
            "sid": config.short_id,
            "spx": config.spider_x,
            "fp": config.fingerprint,
        }

    def required_capabilities(self, config: "RealityConfig") -> set[Capability]:
        return {
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_PUBLIC_KEY,
            Capability.SUPPORTS_SHORT_ID,
        }

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {
            "type": "tcp",
            "security": "reality",
        }
        for key in ("pbk", "sid", "spx", "fp", "sni", "flow"):
            if key in params:
                result[key] = params[key]
        return result


class Hysteria2Serializer(TransportSerializer):
    """Сериализатор для Hysteria2."""

    def serialize(self, config: "Hysteria2Config") -> dict[str, Any]:
        return {
            "type": "hysteria2",
            "password": config.password,
            "obfs": config.obfs,
            "obfsPassword": config.obfs_password,
            "sni": config.sni,
        }

    def required_capabilities(self, config: "Hysteria2Config") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "hysteria2"}
        for key in ("password", "obfs", "obfsPassword", "sni"):
            if key in params:
                result[key] = params[key]
        return result


class TuicSerializer(TransportSerializer):
    """Сериализатор для TUIC."""

    def serialize(self, config: "TuicConfig") -> dict[str, Any]:
        return {
            "type": "tuic",
            "password": config.password,
            "congestionControl": config.congestion_control,
            "heartbeat": config.heartbeat,
        }

    def required_capabilities(self, config: "TuicConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "tuic"}
        for key in ("password", "congestionControl", "heartbeat"):
            if key in params:
                result[key] = params[key]
        return result


class TrojanSerializer(TransportSerializer):
    """Сериализатор для Trojan."""

    def serialize(self, config: "TrojanConfig") -> dict[str, Any]:
        return {
            "type": "trojan",
            "password": config.password,
        }

    def required_capabilities(self, config: "TrojanConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "trojan"}
        if "password" in params:
            result["password"] = params["password"]
        return result


class WireGuardSerializer(TransportSerializer):
    """Сериализатор для WireGuard."""

    def serialize(self, config: "WireGuardConfig") -> dict[str, Any]:
        return {
            "type": "wireguard",
        }

    def required_capabilities(self, config: "WireGuardConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"type": "wireguard"}


class ShadowsocksSerializer(TransportSerializer):
    """Сериализатор для Shadowsocks."""

    def serialize(self, config: "ShadowsocksConfig") -> dict[str, Any]:
        return {
            "type": "shadowsocks",
            "method": config.method,
            "password": config.password,
        }

    def required_capabilities(self, config: "ShadowsocksConfig") -> set[Capability]:
        return {Capability.SUPPORTS_EXTRA}

    def uri_params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {"type": "shadowsocks"}
        for key in ("method", "password"):
            if key in params:
                result[key] = params[key]
        return result


# Registry
TRANSPORT_SERIALIZERS: dict[str, TransportSerializer] = {
    "tcp": TCPSerializer(),
    "xhttp": XHttpSerializer(),
    "ws": WebSocketSerializer(),
    "grpc": GrpcSerializer(),
    "httpupgrade": HttpUpgradeSerializer(),
    "reality": RealitySerializer(),
    "hysteria2": Hysteria2Serializer(),
    "tuic": TuicSerializer(),
    "trojan": TrojanSerializer(),
    "wireguard": WireGuardSerializer(),
    "shadowsocks": ShadowsocksSerializer(),
}


def get_transport_serializer(transport: str) -> TransportSerializer:
    """Возвращает сериализатор для транспорта."""
    serializer = TRANSPORT_SERIALIZERS.get(transport.lower())
    if serializer is None:
        raise ValueError(f"Unknown transport: {transport}")
    return serializer