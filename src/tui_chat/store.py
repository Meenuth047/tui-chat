from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .models import Message, Room

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    adapter TEXT NOT NULL,
    name TEXT NOT NULL,
    peer TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    adapter TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    ts REAL NOT NULL,
    outgoing INTEGER NOT NULL DEFAULT 0,
    subject TEXT,
    raw_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_room_ts ON messages(room_id, ts);
"""


class Store:
    """Local SQLite cache for offline history and search."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert_room(self, room: Room) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO rooms(id, adapter, name, peer) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, peer=excluded.peer",
                (room.id, room.adapter, room.name, room.peer),
            )
            self._conn.commit()

    def rooms(self) -> list[Room]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM rooms ORDER BY name").fetchall()
        return [Room(r["id"], r["adapter"], r["name"], r["peer"]) for r in rows]

    def add_message(self, message: Message) -> bool:
        """Insert a message, returning False if it was already stored."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO messages"
                "(id, room_id, adapter, author, body, ts, outgoing, subject, raw_id)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    message.id,
                    message.room_id,
                    message.adapter,
                    message.author,
                    message.body,
                    message.ts,
                    int(message.outgoing),
                    message.subject,
                    message.raw_id,
                ),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def messages(self, room_id: str, limit: int = 200) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE room_id=? ORDER BY ts DESC LIMIT ?",
                (room_id, limit),
            ).fetchall()
        return [self._row(r) for r in reversed(rows)]

    def search(self, query: str, limit: int = 50) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE body LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r: sqlite3.Row) -> Message:
        return Message(
            id=r["id"],
            room_id=r["room_id"],
            adapter=r["adapter"],
            author=r["author"],
            body=r["body"],
            ts=r["ts"],
            outgoing=bool(r["outgoing"]),
            subject=r["subject"],
            raw_id=r["raw_id"],
        )
