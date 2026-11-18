from __future__ import annotations

from abc import ABC, abstractmethod

from ..bus import Bus, Status
from ..models import Message, Room


class Adapter(ABC):
    """A transport. Adapters push received messages onto the Bus.

    A real-time backend (XMPP/Matrix) implements this same interface, so the
    UI never has to know which transport a room belongs to.
    """

    name: str = "base"

    def __init__(self, bus: Bus) -> None:
        self.bus = bus

    async def start(self) -> None:
        await self.bus.publish(Status(self.name, "online"))

    async def stop(self) -> None:
        await self.bus.publish(Status(self.name, "offline"))

    @abstractmethod
    async def rooms(self) -> list[Room]:
        """Conversations this adapter knows about."""

    @abstractmethod
    async def history(self, room: Room, limit: int = 100) -> list[Message]:
        """Recent messages for a room (may be empty if the Store is the source)."""

    @abstractmethod
    async def send(self, room: Room, text: str) -> Message:
        """Send text to a room and return the resulting local Message."""
