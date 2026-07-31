"""UriValueSerializer — сериализация отдельных значений URI-параметров.

Фиксирует BUG-001: str(v) для вложенных структур даёт невалидный JSON.
Правильное решение: json.dumps(v, separators=(",", ":")) для всех не-примитивных типов.
"""

import json
from typing import Any


class UriValueSerializer:
    """Сериализует отдельные значения в строковое представление для URI.

    Правила:
    - str -> значение как есть (без кавычек)
    - int -> str(value)
    - bool -> "true" / "false" (lowercase)
    - None -> пустая строка
    - list/dict -> compact JSON (json.dumps с separators=(",", ":"))
    - float -> str(value) (edge case, не ожидается в URI)
    """

    def serialize(self, value: Any) -> str:
        """Сериализует значение в строку для URI query-параметра."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        return str(value)
