"""TransportRegistry — реестр сериализаторов транспортов."""

from typing import Any

from app.services.transport_config import TransportConfig
from app.services.transport_serializer import (
    GrpcSerializer,
    HttpUpgradeSerializer,
    Hysteria2Serializer,
    RealitySerializer,
    ShadowsocksSerializer,
    TCPSerializer,
    TransportSerializer,
    TrojanSerializer,
    TuicSerializer,
    WebSocketSerializer,
    WireGuardSerializer,
    XHttpSerializer,
)


class TransportRegistry:
    """Реестр сериализаторов транспортов."""

    def __init__(self):
        self._serializers: dict[str, TransportSerializer] = {}

    def register(self, transport: str, serializer: TransportSerializer) -> None:
        """Регистрирует сериализатор для транспорта."""
        self._serializers[transport.lower()] = serializer

    def get(self, transport: str) -> TransportSerializer | None:
        """Возвращает сериализатор для транспорта."""
        return self._serializers.get(transport.lower())

    def has(self, transport: str) -> bool:
        """Проверяет, зарегистрирован ли транспорт."""
        return transport.lower() in self._serializers

    def serialize(self, transport: str, config: TransportConfig) -> dict[str, Any]:
        """Сериализует конфиг через соответствующий сериализатор."""
        serializer = self.get(transport)
        if serializer is None:
            raise ValueError(f"Unknown transport: {transport}")
        return serializer.serialize(config)

    def required_capabilities(self, transport: str, config: TransportConfig) -> set:
        """Возвращает capability, необходимые для транспорта."""
        serializer = self.get(transport)
        if serializer is None:
            raise ValueError(f"Unknown transport: {transport}")
        return serializer.required_capabilities(config)

    def uri_params(self, transport: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Возвращает транспорт-специфичные параметры для URI."""
        serializer = self.get(transport)
        if serializer is None or not params:
            return {}
        if hasattr(serializer, 'uri_params'):
            return serializer.uri_params(params)
        return {}

    def list_transports(self) -> list[str]:
        """Список зарегистрированных транспортов."""
        return list(self._serializers.keys())


def create_default_registry() -> TransportRegistry:
    """Создает реестр с зарегистрированными стандартными сериализаторами."""
    registry = TransportRegistry()
    registry.register("tcp", RealitySerializer())
    registry.register("reality", RealitySerializer())
    registry.register("xhttp", XHttpSerializer())
    registry.register("ws", WebSocketSerializer())
    registry.register("grpc", GrpcSerializer())
    registry.register("httpupgrade", HttpUpgradeSerializer())
    registry.register("hysteria2", Hysteria2Serializer())
    registry.register("tuic", TuicSerializer())
    registry.register("trojan", TrojanSerializer())
    registry.register("wireguard", WireGuardSerializer())
    registry.register("shadowsocks", ShadowsocksSerializer())
    return registry