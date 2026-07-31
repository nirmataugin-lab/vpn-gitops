import sqlite3
from contextlib import contextmanager

DB_PATH = "/home/ubuntu/database.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection | None = None):
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        if close:
            conn.close()


def init_db(conn: sqlite3.Connection | None = None) -> None:
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vpn_clients (
            uuid TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            inbound_tag TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    if close:
        conn.close()
