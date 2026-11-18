from tui_chat.models import Message, Room
from tui_chat.store import Store


def test_add_and_read_messages_in_order(tmp_path):
    store = Store(tmp_path / "m.db")
    room = Room("email:a@b.com", "email", "Alice", "a@b.com")
    store.upsert_room(room)
    for i in range(3):
        store.add_message(Message(str(i), room.id, "email", "Alice", f"hi {i}", 100 + i))
    assert [m.body for m in store.messages(room.id)] == ["hi 0", "hi 1", "hi 2"]


def test_duplicate_message_is_ignored(tmp_path):
    store = Store(tmp_path / "m.db")
    room = Room("r", "demo", "R")
    msg = Message("same", room.id, "demo", "Ada", "hello", 1.0)
    assert store.add_message(msg) is True
    assert store.add_message(msg) is False
    assert len(store.messages(room.id)) == 1


def test_search_filters_by_body(tmp_path):
    store = Store(tmp_path / "m.db")
    room = Room("r", "demo", "R")
    store.add_message(Message("1", room.id, "demo", "Ada", "deployment failed", 1.0))
    store.add_message(Message("2", room.id, "demo", "Ada", "all good", 2.0))
    assert [m.id for m in store.search("deploy")] == ["1"]


def test_rooms_sorted_by_name(tmp_path):
    store = Store(tmp_path / "m.db")
    store.upsert_room(Room("b", "demo", "Zoe"))
    store.upsert_room(Room("a", "demo", "Ada"))
    assert [r.name for r in store.rooms()] == ["Ada", "Zoe"]
