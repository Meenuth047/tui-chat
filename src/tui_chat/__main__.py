from __future__ import annotations

import argparse
import logging
import sys

from .adapters.base import Adapter
from .adapters.demo import DemoAdapter
from .adapters.email import EmailAdapter
from .app import ChatApp
from .bus import Bus
from .config import AppConfig, load_config
from .store import Store


def build_adapters(config: AppConfig, bus: Bus) -> list[Adapter]:
    friends = [(f.name, f.address) for f in config.friends]
    adapters: list[Adapter] = []
    for account in config.accounts:
        if account.adapter == "email":
            adapters.append(EmailAdapter(bus, account, friends=friends))
        else:
            logging.warning("unknown adapter %r; skipping account %s", account.adapter, account.name)
    return adapters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tui-chat", description="Chat from the terminal.")
    parser.add_argument("-c", "--config", help="Path to config.toml")
    parser.add_argument("--demo", action="store_true", help="Run with the in-memory demo adapter")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    config = load_config(args.config)
    bus = Bus()
    store = Store(config.cache_path)

    demo = args.demo or not config.accounts
    if demo and not args.demo:
        print("No accounts configured; starting in demo mode. See config.example.toml.")
    adapters = [DemoAdapter(bus)] if demo else build_adapters(config, bus)

    app = ChatApp(bus=bus, store=store, adapters=adapters)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
