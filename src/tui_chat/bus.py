from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Union

from .models import Message


@dataclass(slots=True)
class Incoming:
    """A message received from a transport."""

    message: Message


@dataclass(slots=True)
class Status:
    """A connection state change for an adapter."""

    adapter: str
    state: str
    detail: str = ""


Event = Union[Incoming, Status]


class Bus:
    """A single asyncio queue that adapters publish to and the UI consumes."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    async def publish(self, event: Event) -> None:
        await self._queue.put(event)

    async def next(self) -> Event:
        return await self._queue.get()
