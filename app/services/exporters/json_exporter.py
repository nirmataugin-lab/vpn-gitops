"""JSON Exporter."""

from typing import Any

from app.services.capability_model import CapabilityModel
from app.services.exporters.base import Exporter


class JsonExporter(Exporter):
    """Экспорт в JSON."""

    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        import json
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
