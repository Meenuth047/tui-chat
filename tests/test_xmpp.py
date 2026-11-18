import asyncio

import pytest
import slixmpp

from tui_chat.adapters.xmpp import XmppAdapter
from tui_chat.bus import Bus
from tui_chat.config import AccountConfig


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)


def make_adapter() -> XmppAdapter:
    account = AccountConfig(name="me", address="me@example.org", adapter="xmpp")
    return XmppAdapter(Bus(), account, friends=[("Alice", "alice@example.org")])


def stanza(**fields) -> slixmpp.Message:
    message = slixmpp.Message()
    for key, value in fields.items():
        message[key] = value
    return message


def test_incoming_chat_maps_to_message():
    adapter = make_adapter()
    msg = stanza(**{"from": "alice@example.org/phone", "type": "chat", "body": "hello"})
    result = adapter._to_message(msg)
    assert result is not None
    assert result.room_id == "xmpp:alice@example.org"
    assert result.body == "hello"
    assert result.author == "phone"
    assert result.outgoing is False


def test_groupchat_is_ignored():
    adapter = make_adapter()
    msg = stanza(**{"from": "room@chat.example.org/alice", "type": "groupchat", "body": "hi"})
    assert adapter._to_message(msg) is None


def test_message_without_body_is_ignored():
    adapter = make_adapter()
    msg = stanza(**{"from": "alice@example.org", "type": "chat"})
    assert adapter._to_message(msg) is None


def test_self_message_is_ignored():
    adapter = make_adapter()
    msg = stanza(**{"from": "me@example.org/desktop", "type": "chat", "body": "echo"})
    assert adapter._to_message(msg) is None


def test_unknown_sender_gets_a_room():
    adapter = make_adapter()
    msg = stanza(**{"from": "stranger@example.net/x", "type": "chat", "body": "yo"})
    result = adapter._to_message(msg)
    assert result is not None
    assert result.room_id == "xmpp:stranger@example.net"


async def test_send_requires_connection():
    adapter = make_adapter()
    room = next(iter(adapter._rooms.values()))
    with pytest.raises(ConnectionError):
        await adapter.send(room, "hello")


async def test_send_passes_message_to_client():
    adapter = make_adapter()
    adapter._client = FakeClient()
    adapter._ready = asyncio.Event()
    adapter._ready.set()
    room = next(iter(adapter._rooms.values()))

    message = await adapter.send(room, "hello there")

    assert message.outgoing is True
    assert message.body == "hello there"
    assert adapter._client.sent == [{"mto": "alice@example.org", "mbody": "hello there", "mtype": "chat"}]
