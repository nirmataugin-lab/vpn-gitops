"""YAML Exporter."""

from typing import Any

from app.services.capability_model import CapabilityModel
from app.services.exporters.base import Exporter


class YamlExporter(Exporter):
    """Экспорт в YAML."""

    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        try:
            import yaml
        except ImportError:
            raise RuntimeError("PyYAML is required for YAML export. Install with: pip install pyyaml")
        return yaml.dump(data, allow_unicode=True, sort_keys=False).rstrip()
