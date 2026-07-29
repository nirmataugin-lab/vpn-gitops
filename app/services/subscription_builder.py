"""SubscriptionBuilder — сборщик подписок."""

from typing import Any

from app.services.capability_model import Capability, CapabilityModel
from app.services.capability_registry import CapabilityRegistry
from app.services.exporter_registry import ExporterRegistry


class SubscriptionBuilder:
    """Собирает ответ подписки для клиента."""

    def __init__(
        self,
        exporter_registry: ExporterRegistry,
        capability_registry: CapabilityRegistry,
    ):
        self._exporter_registry = exporter_registry
        self._capability_registry = capability_registry

    def build(
        self,
        configs: list[dict[str, Any]],
        client_id: str | None = None,
        format_name: str = "uri",
    ) -> str:
        """Строит подписку для списка конфигураций.

        Args:
            configs: Список конфигураций серверов
            client_id: Идентификатор клиента (для выбора capability профиля)
            format_name: Формат вывода (uri, json, yaml)

        Returns:
            Строка подписки
        """
        capability = self._get_capability(client_id)
        exporter = self._exporter_registry.get(format_name)

        if exporter is None:
            raise ValueError(f"Exporter for format '{format_name}' not found")

        exported_lines = []
        for config in configs:
            export_data = self._prepare_export_data(config, capability)
            line = exporter.export(export_data, capability)
            exported_lines.append(line)

        return "\n".join(exported_lines) + "\n"

    def _get_capability(self, client_id: str | None) -> CapabilityModel:
        """Возвращает профиль capability для клиента."""
        if client_id and self._capability_registry.has(client_id):
            return self._capability_registry.get(client_id)

        # Fallback: максимально совместимый профиль
        from app.services.capability_model import CapabilityModel, Capability
        return CapabilityModel(
            client_id="default",
            capabilities={
                Capability.SUPPORTS_URI,
                Capability.SUPPORTS_FLAT_PARAMS,
                Capability.SUPPORTS_EXTRA,
            },
        )

    def _prepare_export_data(
        self,
        config: dict[str, Any],
        capability: CapabilityModel,
    ) -> dict[str, Any]:
        """Подготавливает данные для экспортёра.

        Args:
            config: Конфигурация сервера из БД/конфига
            capability: Профиль возможностей клиента

        Returns:
            Данные, готовые для экспортёра
        """
        # Базовые поля
        export_data = {
            "scheme": config.get("scheme", "vless"),
            "host": config.get("host", ""),
            "port": config.get("port", 443),
            "uuid": config.get("uuid", config.get("user", "")),
            "name": config.get("name", config.get("fragment", "")),
            "transport": config.get("transport", "tcp"),
            "transport_params": config.get("transport_params", {}),
            "tls": config.get("tls", False),
            "sni": config.get("sni", ""),
            "flow": config.get("flow", ""),
            "extra": config.get("extra", {}),
            "reality": config.get("reality", False),
            "pbk": config.get("pbk", ""),
            "sid": config.get("sid", ""),
            "spx": config.get("spx", ""),
            "fp": config.get("fp", ""),
        }

        # Добавляем extra параметры, если клиент поддерживает
        if capability.has(Capability.SUPPORTS_EXTRA):
            extra = {}
            if "downloadSettings" in config:
                extra["downloadSettings"] = config["downloadSettings"]
            if "xmux" in config:
                extra["xmux"] = config["xmux"]
            if extra:
                export_data["extra"] = extra

        return export_data