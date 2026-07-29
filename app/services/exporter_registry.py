"""ExporterRegistry — реестр экспортёров форматов."""

from typing import Any

from app.services.capability_model import CapabilityModel
from app.services.exporters import JsonExporter, UriExporter, YamlExporter
from app.services.exporters.base import Exporter


class ExporterRegistry:
    """Реестр экспортёров."""

    def __init__(self):
        self._exporters: dict[str, Exporter] = {}

    def register(self, format_name: str, exporter: Exporter) -> None:
        """Регистрирует экспортёр для формата."""
        self._exporters[format_name.lower()] = exporter

    def get(self, format_name: str) -> Exporter | None:
        """Возвращает экспортёр для формата."""
        return self._exporters.get(format_name.lower())

    def has(self, format_name: str) -> bool:
        """Проверяет, зарегистрирован ли формат."""
        return format_name.lower() in self._exporters

    def export(
        self,
        format_name: str,
        data: dict[str, Any],
        capability: CapabilityModel,
    ) -> str:
        """Экспортирует данные через соответствующий экспортёр."""
        exporter = self.get(format_name)
        if exporter is None:
            raise ValueError(f"Unknown format: {format_name}")
        return exporter.export(data, capability)

    def list_formats(self) -> list[str]:
        """Список доступных форматов."""
        return list(self._exporters.keys())


def create_default_registry() -> ExporterRegistry:
    """Создает реестр с базовыми экспортёрами."""
    registry = ExporterRegistry()
    registry.register("uri", UriExporter())
    registry.register("json", JsonExporter())
    registry.register("yaml", YamlExporter())
    return registry
