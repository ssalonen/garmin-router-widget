import json
import os
import sqlite3
from datetime import datetime, timezone


def _db_path() -> str:
    return os.environ.get("LOG_DB_PATH", "logs.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            ts          REAL,
            level       TEXT,
            payload     TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_log(payload: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO device_logs (received_at, ts, level, payload) VALUES (?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                payload.get("ts"),
                payload.get("level", "INFO"),
                json.dumps(payload),
            ),
        )


def get_recent_logs(n: int = 50, level_filter: str | None = None) -> list[dict]:
    with _get_conn() as conn:
        if level_filter:
            rows = conn.execute(
                "SELECT * FROM device_logs WHERE level = ? ORDER BY id DESC LIMIT ?",
                (level_filter, n),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM device_logs ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
    return [
        {
            "id": row["id"],
            "received_at": row["received_at"],
            "level": row["level"],
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]
