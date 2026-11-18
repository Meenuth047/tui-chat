from tui_chat.models import Message, Room


def test_room_label_prefers_name_then_peer_then_id():
    assert Room("id", "email", "Alice", "a@b.com").label() == "Alice"
    assert Room("id", "email", "", "a@b.com").label() == "a@b.com"
    assert Room("id", "email", "").label() == "id"


def test_message_when_is_hh_mm():
    message = Message("1", "r", "demo", "Ada", "hi", 0.0)
    assert len(message.when) == 5
    assert message.when[2] == ":"
