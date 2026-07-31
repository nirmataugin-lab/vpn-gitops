import sqlite3

from app.database import DB_PATH, get_connection
from app.models.vpn_client import VpnClient


class VpnClientRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        return get_connection()

    def create(
        self, client: VpnClient, conn: sqlite3.Connection | None = None
    ) -> VpnClient:
        c = conn or self._get_conn()
        c.execute(
            "INSERT INTO vpn_clients (uuid, email, inbound_tag, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                client.uuid,
                client.email,
                client.inbound_tag,
                int(client.enabled),
                client.created_at,
            ),
        )
        return client

    def get_by_uuid(self, uuid: str, conn: sqlite3.Connection | None = None) -> VpnClient | None:
        c = conn or self._get_conn()
        row = c.execute(
            "SELECT * FROM vpn_clients WHERE uuid = ?", (uuid,)
        ).fetchone()
        if row is None:
            return None
        return VpnClient(
            uuid=row["uuid"],
            email=row["email"],
            inbound_tag=row["inbound_tag"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )

    def count(self, conn: sqlite3.Connection | None = None) -> int:
        c = conn or self._get_conn()
        return c.execute("SELECT COUNT(*) FROM vpn_clients").fetchone()[0]

    def delete(self, uuid: str, conn: sqlite3.Connection | None = None) -> bool:
        c = conn or self._get_conn()
        cursor = c.execute("DELETE FROM vpn_clients WHERE uuid = ?", (uuid,))
        return cursor.rowcount > 0
