"""Subscription Server — HTTP сервер для раздачи подписок."""

from typing import Any

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.services.exporter_registry import create_default_registry as create_exporter_registry
from app.services.capability_registry import create_default_registry as create_capability_registry
from app.services.subscription_builder import SubscriptionBuilder


app = FastAPI(title="Kontakt VPN Subscription Server")

# Инициализация компонентов
_exporter_registry = create_exporter_registry()
_capability_registry = create_capability_registry()
_subscription_builder = SubscriptionBuilder(
    exporter_registry=_exporter_registry,
    capability_registry=_capability_registry,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/sub", response_class=PlainTextResponse)
async def get_subscription(
    request: Request,
    format: str = Query("uri", description="Output format: uri, json, yaml"),
    client: str | None = Query(None, description="Client ID for capability profile"),
    token: str | None = Query(None, description="Authentication token"),
):
    """Возвращает подписку в запрошенном формате.

    Query параметры:
    - format: uri, json, yaml (default: uri)
    - client: Client ID для выбора capability профиля (v2rayn, sing-box, hiddify, etc.)
    - token: Токен авторизации (если требуется)
    """
    # TODO: Добавить проверку токена
    # if not verify_token(token):
    #     raise HTTPException(status_code=401, detail="Invalid token")

    # Получаем список конфигураций из БД/конфига
    configs = _load_configs()

    try:
        subscription = _subscription_builder.build(
            configs=configs,
            client_id=client,
            format_name=format,
        )
        return subscription
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _load_configs() -> list[dict[str, Any]]:
    """Загружает конфигурации серверов.

    В будущем — из БД или файла конфигурации.
    Сейчас — моковые данные для тестирования.
    """
    return [
        {
            "scheme": "vless",
            "host": "example.com",
            "port": 443,
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "US-East-1",
            "transport": "ws",
            "transport_params": {
                "path": "/vpn",
                "headers": {"Host": "example.com"},
            },
            "tls": True,
            "sni": "example.com",
            "flow": "",
            "extra": {},
        },
        {
            "scheme": "vless",
            "host": "example2.com",
            "port": 8443,
            "uuid": "11111111-2222-3333-4444-555555555555",
            "name": "EU-West-1",
            "transport": "grpc",
            "transport_params": {
                "serviceName": "grpc",
            },
            "tls": True,
            "sni": "example2.com",
            "flow": "xtls-rprx-vision",
            "extra": {},
        },
        {
            "scheme": "vless",
            "host": "reality.example.com",
            "port": 443,
            "uuid": "22222222-3333-4444-5555-666666666666",
            "name": "REALITY-Server",
            "transport": "reality",
            "transport_params": {
                "pbk": "public_key_123",
                "sid": "short123",
                "spx": "spider_x_value",
                "fp": "chrome",
            },
            "reality": True,
            "sni": "reality.example.com",
            "flow": "xtls-rprx-vision",
            "extra": {},
        },
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)