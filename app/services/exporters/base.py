"""Base Exporter protocol."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.capability_model import CapabilityModel


class Exporter(ABC):
    """Базовый класс экспортёра."""

    @abstractmethod
    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        """Экспортирует данные в строковый формат."""
