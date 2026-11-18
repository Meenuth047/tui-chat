from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Room:
    """A conversation. For email this is a peer address/thread."""

    id: str
    adapter: str
    name: str
    peer: str | None = None

    def label(self) -> str:
        return self.name or self.peer or self.id


@dataclass(slots=True, frozen=True)
class Message:
    id: str
    room_id: str
    adapter: str
    author: str
    body: str
    ts: float
    outgoing: bool = False
    subject: str | None = None
    raw_id: str | None = None

    @property
    def when(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.ts))
