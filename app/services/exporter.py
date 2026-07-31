"""Exporter — протокол и реализации экспортёров."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.capability_model import CapabilityModel


class Exporter(ABC):
    """Базовый класс экспортёра."""

    @abstractmethod
    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        """Экспортирует данные в целевой формат."""


class JsonExporter(Exporter):
    """Экспорт в JSON."""

    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        import json
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class YamlExporter(Exporter):
    """Экспорт в YAML."""

    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        try:
            import yaml
        except ImportError:
            raise RuntimeError("PyYAML is required for YAML export. Install with: pip install pyyaml")
        return yaml.dump(data, allow_unicode=True, sort_keys=False).rstrip()