import pytest
from textual.widgets import Input, ListView, RichLog

from tui_chat.adapters.demo import DemoAdapter
from tui_chat.app import ChatApp
from tui_chat.bus import Bus
from tui_chat.store import Store


def make_app(tmp_path) -> ChatApp:
    bus = Bus()
    store = Store(tmp_path / "m.db")
    return ChatApp(bus=bus, store=store, adapters=[DemoAdapter(bus)])


async def test_app_lists_demo_rooms(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        rooms = app.query_one("#rooms", ListView)
        assert len(rooms.children) == 2


async def test_sending_writes_to_log(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        compose = app.query_one("#compose", Input)
        compose.value = "hello there"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#log", RichLog)
        assert log.lines


async def test_incoming_message_reaches_store(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.store.rooms()


@pytest.mark.parametrize("bindings_key", ["ctrl+r"])
async def test_refresh_binding_runs(tmp_path, bindings_key):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press(bindings_key)
        await pilot.pause()
        assert app.query_one("#rooms", ListView).children


async def test_pushed_message_reaches_store_and_log(tmp_path):
    bus = Bus()
    store = Store(tmp_path / "m.db")
    adapter = DemoAdapter(bus, interval=0.05)
    app = ChatApp(bus=bus, store=store, adapters=[adapter])
    async with app.run_test() as pilot:
        await pilot.pause(0.4)
        stored = store.messages("demo:ada") + store.messages("demo:grace")
        assert stored, "no pushed message landed in the store"
        assert app.query_one("#log", RichLog).lines
