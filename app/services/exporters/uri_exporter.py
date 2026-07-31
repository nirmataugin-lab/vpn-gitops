"""UriExporter — экспорт в URI формат (VLESS, VMess, Trojan, etc.)."""

from typing import Any

from app.services.capability_model import Capability, CapabilityModel
from app.services.exporters.base import Exporter
from app.services.uri_value_serializer import UriValueSerializer


class UriExporter(Exporter):
    """Экспортёр URI-формата для VPN-клиентов.

    Генерирует строки вида: vless://uuid@host:port?params#name
    """

    def __init__(self, transport_registry=None):
        from urllib.parse import quote
        self._uri_serializer = UriValueSerializer()
        self._transport_registry = transport_registry
        self._quote = quote

    def export(self, data: dict[str, Any], capability: CapabilityModel) -> str:
        """Экспортирует конфиг в URI.

        Args:
            data: {
                "scheme": "vless",
                "host": "example.com",
                "port": 443,
                "uuid": "...",
                "name": "My Server",
                "transport": "ws",
                "transport_params": {...},
                "tls": true,
                "sni": "...",
                "flow": "...",
                "extra": {...},
                "reality": false,
                "pbk": "",
                "sid": "",
                "spx": "",
                "fp": ""
            }
            capability: профиль возможностей клиента

        Returns:
            URI строка
        """
        scheme = data.get("scheme", "vless")
        host = data.get("host", "")
        port = data.get("port", 443)
        uuid = data.get("uuid", "")
        name = data.get("name", "VPN")
        transport = data.get("transport", "tcp")
        tls = data.get("tls", False)
        sni = data.get("sni", "")
        flow = data.get("flow", "")
        extra = data.get("extra", {})
        reality = data.get("reality", False)
        pbk = data.get("pbk", "")
        sid = data.get("sid", "")
        spx = data.get("spx", "")
        fp = data.get("fp", "")

        # Build userinfo: uuid@
        userinfo = f"{uuid}@" if uuid else ""

        # Build query parameters
        params = {}

        # Basic params
        if flow:
            params["flow"] = flow

        # Security (TLS/REALITY)
        # REALITY is a form of TLS, so check reality first if both are set
        if reality:
            params["security"] = "reality"
            if pbk:
                params["pbk"] = pbk
            if sid:
                params["sid"] = sid
            if spx:
                params["spx"] = spx
            if fp:
                params["fp"] = fp
            if sni:
                params["sni"] = sni
        elif tls:
            params["security"] = "tls"
            if sni:
                params["sni"] = sni
            if fp:
                params["fp"] = fp

        # Transport-specific params - use TransportRegistry if available
        if self._transport_registry and self._transport_registry.has(transport):
            transport_params = data.get("transport_params", {})
            if transport_params:
                uri_params = self._transport_registry.uri_params(transport, transport_params)
                params.update(uri_params)
        else:
            # Fallback to inline logic if no registry
            self._add_transport_params_fallback(params, transport, data.get("transport_params", {}))

        # Extra parameter (JSON) - если клиент поддерживает
        if capability.has(Capability.SUPPORTS_EXTRA) and extra:
            params["extra"] = self._uri_serializer.serialize(extra)

        # Build query string
        query_parts = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            serialized = self._uri_serializer.serialize(value)
            query_parts.append(f"{key}={serialized}")

        query_string = "&".join(query_parts)
        query_string = "?" + query_string if query_string else ""

        # Build fragment
        fragment = f"#{self._uri_serializer.serialize(name)}" if name else ""

        return f"{scheme}://{userinfo}{host}:{port}{query_string}{fragment}"

    def _add_transport_params_fallback(
        self, params: dict[str, Any], transport: str, transport_params: dict[str, Any]
    ) -> None:
        """Fallback logic when TransportRegistry is not available."""
        if transport == "ws":
            params["type"] = "ws"
            if "path" in transport_params:
                params["path"] = transport_params["path"]
            if "headers" in transport_params:
                params["headers"] = self._serialize_headers(transport_params["headers"])
        elif transport == "grpc":
            params["type"] = "grpc"
            if "serviceName" in transport_params:
                params["serviceName"] = transport_params["serviceName"]
        elif transport in ("h2", "http2"):
            params["type"] = "h2"
            if "path" in transport_params:
                params["path"] = transport_params["path"]
        elif transport == "httpupgrade":
            params["type"] = "httpupgrade"
            if "path" in transport_params:
                params["path"] = transport_params["path"]
        elif transport == "xhttp":
            params["type"] = "xhttp"
            if "path" in transport_params:
                params["path"] = transport_params["path"]
            if "host" in transport_params:
                params["host"] = transport_params["host"]

    def _serialize_headers(self, headers: dict[str, str]) -> str:
        """Сериализует headers в формат URI."""
        parts = []
        for k, v in headers.items():
            parts.append(f"{k}:{v}")
        return ";".join(parts)