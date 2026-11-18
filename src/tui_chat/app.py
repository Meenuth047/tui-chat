from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog

from .adapters.base import Adapter
from .bus import Bus, Incoming, Status
from .models import Message, Room
from .store import Store


class RoomItem(ListItem):
    def __init__(self, room: Room) -> None:
        super().__init__(Label(room.label()))
        self.room = room


class ChatApp(App):
    """Three-pane chat client: rooms on the left, log in the middle, compose below."""

    CSS = """
    #body { height: 1fr; }
    #rooms { width: 28; border: round $primary; }
    #main { width: 1fr; }
    #log { height: 1fr; border: round $accent; }
    #compose { dock: bottom; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    def __init__(self, bus: Bus, store: Store, adapters: list[Adapter]) -> None:
        super().__init__()
        self.bus = bus
        self.store = store
        self.adapters = adapters
        self._rooms_by_id: dict[str, Room] = {}
        self._current: Room | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield ListView(id="rooms")
            with Vertical(id="main"):
                yield RichLog(id="log", wrap=True, markup=False)
                yield Input(placeholder="Type a message and press Enter", id="compose")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "tui-chat"
        for adapter in self.adapters:
            await adapter.start()
        await self.action_refresh()
        self.run_worker(self._drain_bus(), name="bus", exclusive=False)

    async def on_unmount(self) -> None:
        for adapter in self.adapters:
            await adapter.stop()
        self.store.close()

    async def action_refresh(self) -> None:
        seen: dict[str, Room] = {}
        for adapter in self.adapters:
            for room in await adapter.rooms():
                seen[room.id] = room
        for room in self.store.rooms():
            seen.setdefault(room.id, room)
        self._populate_rooms(sorted(seen.values(), key=lambda r: r.label().lower()))

    def _populate_rooms(self, rooms: list[Room]) -> None:
        list_view = self.query_one("#rooms", ListView)
        list_view.clear()
        self._rooms_by_id = {}
        for room in rooms:
            self._rooms_by_id[room.id] = room
            self.store.upsert_room(room)
            list_view.append(RoomItem(room))
        if rooms and self._current is None:
            self._select_room(rooms[0])

    def _adapter_for(self, room: Room) -> Adapter | None:
        return next((a for a in self.adapters if a.name == room.adapter), None)

    def _select_room(self, room: Room) -> None:
        self._current = room
        self.sub_title = room.label()
        log = self.query_one("#log", RichLog)
        log.clear()
        for message in self.store.messages(room.id):
            self._write(message)
        self.query_one("#compose", Input).focus()

    def _write(self, message: Message) -> None:
        line = Text()
        style = "bold green" if message.outgoing else "bold cyan"
        line.append(message.author, style=style)
        line.append("  ")
        line.append(message.when, style="dim")
        line.append("\n")
        line.append(message.body)
        self.query_one("#log", RichLog).write(line)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text or self._current is None:
            return
        room = self._current
        adapter = self._adapter_for(room)
        if adapter is None:
            self.notify(f"No adapter for {room.label()}", severity="error")
            return
        try:
            message = await adapter.send(room, text)
        except Exception as exc:  # noqa: BLE001 - surface to the user
            self.notify(f"Send failed: {exc}", severity="error")
            return
        self.store.add_message(message)
        self._write(message)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, RoomItem):
            self._select_room(event.item.room)

    async def _drain_bus(self) -> None:
        while True:
            event = await self.bus.next()
            if isinstance(event, Incoming):
                self._on_incoming(event.message)
            elif isinstance(event, Status):
                self._on_status(event)

    def _on_incoming(self, message: Message) -> None:
        if not self.store.add_message(message):
            return
        if self._current is not None and message.room_id == self._current.id:
            self._write(message)
        else:
            self.notify(f"{message.author}: {message.body[:60]}")

    def _on_status(self, event: Status) -> None:
        if event.state == "online":
            self.sub_title = f"{event.adapter} online"
        elif event.state in {"reconnecting", "offline"}:
            self.notify(f"{event.adapter}: {event.state} ({event.detail})", severity="warning")
