from __future__ import annotations

import asyncio
import itertools
import time
import uuid

from ..bus import Bus, Incoming
from ..models import Message, Room
from .base import Adapter


class DemoAdapter(Adapter):
    """In-memory adapter so the UI runs without any credentials.

    Emits a fake incoming message every few seconds to exercise the real-time
    push path through the Bus.
    """

    name = "demo"

    def __init__(self, bus: Bus, interval: float = 8.0) -> None:
        super().__init__(bus)
        self._interval = interval
        self._rooms = {
            "demo:ada": Room("demo:ada", self.name, "Ada"),
            "demo:grace": Room("demo:grace", self.name, "Grace"),
        }
        self._messages: dict[str, list[Message]] = {rid: [] for rid in self._rooms}
        self._task: asyncio.Task | None = None
        self._counter = itertools.count(1)

    async def start(self) -> None:
        await super().start()
        self._task = asyncio.create_task(self._ticker(), name="demo-ticker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
        await super().stop()

    async def rooms(self) -> list[Room]:
        return list(self._rooms.values())

    async def history(self, room: Room, limit: int = 100) -> list[Message]:
        return self._messages.get(room.id, [])[-limit:]

    async def send(self, room: Room, text: str) -> Message:
        message = self._make(room, "you", text, outgoing=True)
        self._messages[room.id].append(message)
        return message

    async def _ticker(self) -> None:
        peers = itertools.cycle(self._rooms.values())
        while True:
            await asyncio.sleep(self._interval)
            room = next(peers)
            message = self._make(room, room.name, f"ping #{next(self._counter)}", outgoing=False)
            self._messages[room.id].append(message)
            await self.bus.publish(Incoming(message))

    def _make(self, room: Room, author: str, body: str, *, outgoing: bool) -> Message:
        return Message(
            id=str(uuid.uuid4()),
            room_id=room.id,
            adapter=self.name,
            author=author,
            body=body,
            ts=time.time(),
            outgoing=outgoing,
        )
