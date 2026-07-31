"""CapabilityRegistry — реестр профилей клиентов."""

from app.services.capability_model import (
    Capability,
    CapabilityModel,
    validate_capability_model,
)


class CapabilityRegistry:
    """Реестр профилей клиентов (CapabilityModel).

    Позволяет получать профиль клиента по его идентификатору.
    """

    def __init__(self):
        self._profiles: dict[str, CapabilityModel] = {}

    def register(self, client_id: str, profile: CapabilityModel) -> None:
        """Регистрирует профиль клиента."""
        errors = validate_capability_model(profile)
        if errors:
            raise ValueError(f"Invalid capability profile for {client_id}: {errors}")
        self._profiles[client_id] = profile

    def get(self, client_id: str) -> CapabilityModel | None:
        """Возвращает профиль клиента."""
        return self._profiles.get(client_id)

    def has(self, client_id: str) -> bool:
        """Проверяет, есть ли профиль для клиента."""
        return client_id in self._profiles

    def list_clients(self) -> list[str]:
        """Возвращает список зарегистрированных клиентов."""
        return list(self._profiles.keys())


def create_default_registry() -> CapabilityRegistry:
    """Создает и заполняет реестр стандартными профилями клиентов."""
    registry = CapabilityRegistry()

    # V2RayNG (Android) — поддерживает URI, flat params, extra, xhttp, ws, grpc, reality, flow
    registry.register("v2rayn", CapabilityModel(
        client_id="v2rayn",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_PUBLIC_KEY,
            Capability.SUPPORTS_SHORT_ID,
        },
    ))

    # V2RayN (Windows) — похож на V2RayNG
    registry.register("v2rayn-windows", CapabilityModel(
        client_id="v2rayn-windows",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_PUBLIC_KEY,
            Capability.SUPPORTS_SHORT_ID,
        },
    ))

    # V2RayTun (iOS)
    registry.register("v2raytun", CapabilityModel(
        client_id="v2raytun",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
        },
    ))

    # Hiddify (Android/Windows/macOS) — поддерживает downloadSettings
    registry.register("hiddify", CapabilityModel(
        client_id="hiddify",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_DOWNLOAD_SETTINGS,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_HYSTERIA2,
            Capability.SUPPORTS_TUIC,
        },
    ))

    # Streisand
    registry.register("streisand", CapabilityModel(
        client_id="streisand",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
        },
    ))

    # NekoBox (Android/iOS)
    registry.register("nekobox", CapabilityModel(
        client_id="nekobox",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_HYSTERIA2,
            Capability.SUPPORTS_TUIC,
        },
    ))

    # FoXray (iOS/macOS)
    registry.register("foxray", CapabilityModel(
        client_id="foxray",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
        },
    ))

    # Clash (Meta, Premium, Verge) — поддерживает YAML/JSON конфиги
    registry.register("clash", CapabilityModel(
        client_id="clash",
        capabilities={
            Capability.SUPPORTS_YAML,
            Capability.SUPPORTS_JSON,
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_HYSTERIA2,
            Capability.SUPPORTS_TUIC,
        },
    ))

    # sing-box (официальный клиент) — полная поддержка
    registry.register("sing-box", CapabilityModel(
        client_id="sing-box",
        capabilities={
            Capability.SUPPORTS_URI,
            Capability.SUPPORTS_JSON,
            Capability.SUPPORTS_YAML,
            Capability.SUPPORTS_FLAT_PARAMS,
            Capability.SUPPORTS_EXTRA,
            Capability.SUPPORTS_DOWNLOAD_SETTINGS,
            Capability.SUPPORTS_XMUX,
            Capability.SUPPORTS_XHTTP,
            Capability.SUPPORTS_WS,
            Capability.SUPPORTS_GRPC,
            Capability.SUPPORTS_HTTPUPGRADE,
            Capability.SUPPORTS_REALITY,
            Capability.SUPPORTS_FLOW,
            Capability.SUPPORTS_PUBLIC_KEY,
            Capability.SUPPORTS_SHORT_ID,
            Capability.SUPPORTS_HYSTERIA2,
            Capability.SUPPORTS_TUIC,
            Capability.SUPPORTS_TROJAN,
            Capability.SUPPORTS_WIREGUARD,
            Capability.SUPPORTS_SHADOWSOCKS,
        },
    ))

    return registry
