# tui-chat

A terminal chat client with **pluggable transport adapters**. The first working
adapter is **email**: it authenticates as *you* over IMAP/SMTP, so the person you
talk to needs no special client — they just use their normal mail app.

Real-time is handled with **IMAP IDLE** (server push), so messages appear as they
arrive rather than on a poll timer.

```
┌─ rooms ───────┬─ Alice ──────────────────────────────────┐
│ ▸ Alice       │ Alice  14:03                             │
│   Bob         │ shipping the patch now                   │
│               │ you    14:03                             │
│               │ perfect, thanks                          │
│               ├──────────────────────────────────────────┤
│               │ Type a message and press Enter           │
└───────────────┴──────────────────────────────────────────┘
```

## Why email first

Of the platforms discussed, email is the only one where a terminal client can act
as **yourself**, peer-to-peer, without violating terms of service:

| Platform | Terminal user chats as themselves? | Notes |
|---|---|---|
| Email | Yes | IMAP + SMTP as you; friend uses any mail app |
| Discord | No | Official API is bot-only; user "selfbots" break ToS |
| Google Chat | No | No user-facing read/send API exists |

If your friend's provider floods the inbox with one email per line, consider
batching — or move to a live protocol (see Roadmap).

## Architecture

```
adapters (email / demo / future XMPP-Matrix)
        │  publish Incoming / Status
        ▼
      Bus (asyncio.Queue)  ──►  ChatApp (Textual)
        │                         │
        ▼                         ▼
     Store (SQLite)  ◄──── history + search + dedupe
```

- `models.py` — `Room`, `Message`
- `bus.py` — one asyncio queue adapters publish to and the UI consumes
- `store.py` — SQLite cache (offline history, search, duplicate suppression)
- `adapters/base.py` — the `Adapter` interface every transport implements
- `adapters/email.py` — IMAP IDLE + SMTP
- `adapters/xmpp.py` — real-time chat via XMPP (slixmpp)
- `adapters/demo.py` — in-memory adapter, no credentials needed
- `app.py` — Textual three-pane UI

Because the UI only ever talks to the `Adapter` interface and the `Bus`, adding a
real-time backend means writing one new adapter — no UI changes.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run the demo (no credentials)

```bash
.venv/bin/tui-chat --demo
```

## Configure

```bash
cp config.example.toml ~/.config/tui-chat/config.toml
export TUI_CHAT_XMPP_PASSWORD='your-password'   # must match `password_env`
.venv/bin/tui-chat
```

Both adapters are driven entirely by the config file — keep whichever
`[[account]]` blocks you want.

**XMPP** (real-time) — you need a JID (`you@server`); register on a public server
(`jabber.at`, `xmpp.jp`, `disroot.org`) or self-host Snikket/Prosody. Your friend
joins the same server with any XMPP client (Conversations, Gajim, Swift). Rooms
are keyed by bare JID.

**Email** (async, near-real-time via IMAP IDLE) — Gmail requires an App Password
(2FA); "less secure apps" was removed in 2022. Use `imap.gmail.com` /
`smtp.gmail.com`. A room is a friend's address; subjects are collapsed so threads
read like DMs.

Credentials stay local — never commit them; prefer `password_env`.

## Tests

```bash
.venv/bin/python -m pytest -q
```

On machines with ROS installed, a stray `launch_testing` pytest plugin can break
collection. Work around it with:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p asyncio
```

## Roadmap

- [x] Adapter interface + Bus + Store
- [x] Email adapter (IMAP IDLE push, SMTP send)
- [x] XMPP adapter — real-time terminal chat with any XMPP client
- [ ] Matrix adapter (via an existing homeserver)
- [ ] Mute/batch outgoing email to avoid inbox spam
- [ ] Message search UI (`Store.search` is already there)
