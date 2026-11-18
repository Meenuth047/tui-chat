from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime

import slixmpp
from slixmpp.jid import JID

from ..bus import Bus, Incoming, Status
from ..config import AccountConfig
from ..models import Message, Room
from .base import Adapter

log = logging.getLogger(__name__)


class _AuthError(Exception):
    pass


def _connection_error(future: asyncio.Future) -> str:
    if future.cancelled():
        return "connection cancelled"
    exc = future.exception() if future.done() else None
    return str(exc) if exc else "connection closed before session start"


class XmppAdapter(Adapter):
    """Real-time chat over XMPP.

    A room is a peer's bare JID. Messages arrive on the library's `message`
    event and are pushed straight onto the Bus, so the terminal sees them the
    instant the server delivers them. Your friend can use any XMPP client
    (Conversations, Gajim, Swift) -- only your side lives in the terminal.
    """

    name = "xmpp"

    def __init__(
        self,
        bus: Bus,
        account: AccountConfig,
        friends: list[tuple[str, str]],
    ) -> None:
        super().__init__(bus)
        self.account = account
        self.jid = JID(account.address)
        self.jid_bare = self.jid.bare
        self.password = account.resolve_password()
        self.host = account.host
        self.port = account.port

        self._rooms: dict[str, Room] = {}
        for name, jid in friends:
            try:
                bare = JID(jid).bare
            except Exception:  # noqa: BLE001 - ignore malformed entries
                log.warning("ignoring malformed friend jid %r", jid)
                continue
            self._rooms[bare] = Room(self._room_id(bare), self.name, name or bare, bare)

        self._client: slixmpp.ClientXMPP | None = None
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._failed: str | None = None

    @property
    def label(self) -> str:
        return self.account.name or self.jid_bare

    def _room_id(self, peer: str) -> str:
        return f"xmpp:{peer.lower()}"

    def _room_for(self, peer: str, nick: str | None = None) -> Room:
        room = self._rooms.get(peer)
        if room is None:
            room = Room(self._room_id(peer), self.name, nick or peer, peer)
            self._rooms[peer] = room
        return room

    async def start(self) -> None:
        await self.bus.publish(Status(self.name, "connecting", self.jid_bare))
        self._task = asyncio.create_task(self._run(), name=f"xmpp:{self.label}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._cleanup()
        await super().stop()

    async def rooms(self) -> list[Room]:
        return list(self._rooms.values())

    async def history(self, room: Room, limit: int = 100) -> list[Message]:
        return []  # history is served from the local Store

    async def send(self, room: Room, text: str) -> Message:
        client = self._client
        if client is None or not self._ready.is_set():
            raise ConnectionError("xmpp client is not connected")
        client.send_message(mto=room.peer, mbody=text, mtype="chat")
        return Message(
            id=str(uuid.uuid4()),
            room_id=room.id,
            adapter=self.name,
            author=self.jid_bare,
            body=text,
            ts=time.time(),
            outgoing=True,
        )

    async def _run(self) -> None:
        backoff = 1
        while True:
            try:
                await self._session()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except _AuthError as exc:
                await self.bus.publish(Status(self.name, "offline", str(exc)))
                return  # bad credentials will not fix themselves
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                log.warning("xmpp %s: %s", self.jid_bare, exc)
                await self.bus.publish(Status(self.name, "reconnecting", str(exc)))
                await self._cleanup()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _session(self) -> None:
        await self.bus.publish(Status(self.name, "connecting", self.jid_bare))
        self._failed = None
        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()

        client = self._build_client()
        self._client = client

        connect_future = asyncio.ensure_future(client.connect(self.host or None, self.port or None))
        ready_waiter = asyncio.ensure_future(self._ready.wait())
        done, _ = await asyncio.wait(
            {connect_future, ready_waiter}, return_when=asyncio.FIRST_COMPLETED
        )

        if ready_waiter not in done:
            ready_waiter.cancel()
            if self._failed:
                raise _AuthError(self._failed)
            raise ConnectionError(_connection_error(connect_future))

        await self.bus.publish(Status(self.name, "online", self.jid_bare))

        disconnect_waiter = asyncio.ensure_future(self._disconnected.wait())
        await asyncio.wait(
            {connect_future, disconnect_waiter}, return_when=asyncio.FIRST_COMPLETED
        )
        disconnect_waiter.cancel()

        if connect_future.done() and not self._disconnected.is_set():
            error = _connection_error(connect_future)
            if error:
                raise ConnectionError(error)

    def _build_client(self) -> slixmpp.ClientXMPP:
        client = slixmpp.ClientXMPP(self.jid, self.password)
        client.register_plugin("xep_0030")  # service discovery
        client.register_plugin("xep_0199", {"keepalive": True, "frequency": 60})
        client.add_event_handler("session_start", self._on_session_start)
        client.add_event_handler("message", self._handle_stanza)
        client.add_event_handler("failed_auth", self._on_failed_auth)
        client.add_event_handler("disconnected", self._on_disconnected)
        return client

    async def _on_session_start(self, event) -> None:
        client = self._client
        if client is None:
            return
        client.send_presence()
        await client.get_roster()
        self._ready.set()

    def _on_failed_auth(self, event) -> None:
        self._failed = "authentication failed"

    def _on_disconnected(self, event) -> None:
        self._disconnected.set()

    async def _handle_stanza(self, stanza) -> None:
        message = self._to_message(stanza)
        if message is not None:
            await self.bus.publish(Incoming(message))

    def _to_message(self, stanza) -> Message | None:
        mtype = stanza.get("type")
        if mtype in {"groupchat", "error", "headline"}:
            return None
        body = stanza.get("body")
        raw_from = stanza.get("from")
        if not body or raw_from is None:
            return None

        sender = JID(str(raw_from))
        peer = sender.bare
        if peer == self.jid_bare:
            return None

        room = self._room_for(peer, sender.resource or None)
        return Message(
            id=stanza.get("id") or str(uuid.uuid4()),
            room_id=room.id,
            adapter=self.name,
            author=sender.resource or peer,
            body=body,
            ts=self._timestamp(stanza),
            outgoing=False,
        )

    @staticmethod
    def _timestamp(stanza) -> float:
        try:
            stamp = stanza["delay"]["stamp"]
            if isinstance(stamp, datetime):
                return stamp.timestamp()
            if stamp:
                return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
        except Exception:  # noqa: BLE001 - fall back to now
            pass
        return time.time()

    async def _cleanup(self) -> None:
        client, self._client = self._client, None
        self._ready.clear()
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
