from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class VpnClient:
    uuid: str
    email: str
    inbound_tag: str
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DryRunResult:
    success: bool
    message: str
    vpn_client: VpnClient | None = None
    vless_uri: str | None = None
    errors: list[str] = field(default_factory=list)
