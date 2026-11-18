from __future__ import annotations

import asyncio
import email
import email.utils
import inspect
import logging
import time
import uuid
from email.message import EmailMessage
from email.policy import default as default_policy

import aioimaplib
import aiosmtplib

from ..bus import Bus, Incoming, Status
from ..config import AccountConfig
from ..models import Message, Room
from .base import Adapter

log = logging.getLogger(__name__)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


class EmailAdapter(Adapter):
    """Email as chat: IMAP IDLE for push, SMTP for sending.

    A room is a peer address. Subjects are collapsed so a thread reads like a
    DM. This authenticates as *you*, so the person you talk to needs no special
    client -- they just use their normal mail app.
    """

    name = "email"

    def __init__(
        self,
        bus: Bus,
        account: AccountConfig,
        friends: list[tuple[str, str]],
        idle_timeout: float = 25 * 60,
    ) -> None:
        super().__init__(bus)
        self.account = account
        self.address = account.address
        self._idle_timeout = idle_timeout
        self._rooms: dict[str, Room] = {}
        for name, address in friends:
            room = Room(self._room_id(address), self.name, name or address, address)
            self._rooms[address.lower()] = room
        self._client: aioimaplib.IMAP4_SSL | None = None
        self._task: asyncio.Task | None = None

    @property
    def label(self) -> str:
        return self.account.name or self.address

    def _room_id(self, peer: str) -> str:
        return f"email:{peer.lower()}"

    def _room_for(self, peer: str, name: str | None = None) -> Room:
        key = peer.lower()
        room = self._rooms.get(key)
        if room is None:
            room = Room(self._room_id(peer), self.name, name or peer, peer)
            self._rooms[key] = room
        return room

    async def start(self) -> None:
        await self.bus.publish(Status(self.name, "connecting", self.account.imap_host))
        self._task = asyncio.create_task(self._run(), name=f"email:{self.label}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._logout()
        await super().stop()

    async def rooms(self) -> list[Room]:
        return list(self._rooms.values())

    async def history(self, room: Room, limit: int = 100) -> list[Message]:
        return []  # history is served from the local Store

    async def send(self, room: Room, text: str) -> Message:
        message = EmailMessage()
        message["From"] = self.address
        message["To"] = room.peer or room.name
        message["Subject"] = f"chat: {room.name}"
        message_id = email.utils.make_msgid()
        message["Message-ID"] = message_id
        message.set_content(text)

        await aiosmtplib.send(
            message,
            hostname=self.account.smtp_host or f"smtp.{self.address.split('@')[-1]}",
            port=self.account.smtp_port,
            username=self.address,
            password=self.account.resolve_password(),
            use_tls=self.account.use_ssl,
        )
        return Message(
            id=message_id,
            room_id=room.id,
            adapter=self.name,
            author=self.address,
            body=text,
            ts=time.time(),
            outgoing=True,
            subject=message["Subject"],
            raw_id=message_id,
        )

    async def _run(self) -> None:
        backoff = 1
        while True:
            try:
                await self._connect()
                await self.bus.publish(Status(self.name, "online", self.address))
                backoff = 1
                await self._poll()
                while True:
                    await self._idle_once()
                    await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                log.warning("email %s: connection lost: %s", self.label, exc)
                await self.bus.publish(Status(self.name, "reconnecting", str(exc)))
                await self._logout()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _connect(self) -> None:
        client = aioimaplib.IMAP4_SSL(
            host=self.account.imap_host or f"imap.{self.address.split('@')[-1]}",
            port=self.account.imap_port,
        )
        await client.wait_hello_from_server()
        await client.login(self.address, self.account.resolve_password())
        await client.select("INBOX")
        self._client = client

    async def _logout(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.logout()
            except Exception:  # noqa: BLE001
                pass

    async def _poll(self) -> None:
        client = self._client
        if client is None:
            return
        result, data = await client.search("UNSEEN")
        if result != "OK" or not data or data[0] is None:
            return
        uids = data[0].split()
        for uid in reversed(uids[-25:]):
            await self._fetch(uid)

    async def _fetch(self, uid: bytes) -> None:
        client = self._client
        if client is None:
            return
        result, data = await client.fetch(uid, "(RFC822)")
        if result != "OK":
            return
        raw = next((p for p in data if isinstance(p, (bytes, bytearray))), None)
        if raw is None:
            return

        msg = email.message_from_bytes(raw, policy=default_policy)
        from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
        if (from_addr or "").lower() == self.address.lower():
            return

        room = self._room_for(from_addr, from_name)
        message = Message(
            id=msg.get("Message-ID") or str(uuid.uuid4()),
            room_id=room.id,
            adapter=self.name,
            author=from_name or from_addr,
            body=self._body(msg),
            ts=self._timestamp(msg),
            outgoing=False,
            subject=msg.get("Subject"),
            raw_id=msg.get("Message-ID"),
        )
        await self.bus.publish(Incoming(message))
        await self._mark_seen(uid)

    async def _mark_seen(self, uid: bytes) -> None:
        client = self._client
        if client is None:
            return
        try:
            await client.store(uid, "+FLAGS", "(\\Seen)")
        except Exception:  # noqa: BLE001 - dedupe is also enforced in the Store
            log.debug("could not mark uid %s seen", uid)

    async def _idle_once(self) -> None:
        client = self._client
        if client is None:
            return
        idle_future = await _maybe_await(client.idle_start(timeout=self._idle_timeout))
        try:
            await client.wait_server_push()
        finally:
            await _maybe_await(client.idle_done())
            if isinstance(idle_future, asyncio.Future):
                idle_future.cancel()

    @staticmethod
    def _body(msg: email.message.Message) -> str:
        try:
            if msg.is_multipart():
                part = msg.get_body(preferencelist=("plain",))
                if part is not None:
                    return part.get_content().strip()
            payload = msg.get_payload(decode=True)
            if payload is not None:
                return payload.decode(msg.get_content_charset() or "utf-8", "replace").strip()
        except Exception:  # noqa: BLE001
            pass
        return str(msg.get_payload()).strip()

    @staticmethod
    def _timestamp(msg: email.message.Message) -> float:
        try:
            dt = email.utils.parsedate_to_datetime(msg.get("Date"))
            if dt is not None:
                return dt.timestamp()
        except Exception:  # noqa: BLE001
            pass
        return time.time()
