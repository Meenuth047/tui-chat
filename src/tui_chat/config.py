from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "tui-chat"


@dataclass(slots=True)
class AccountConfig:
    name: str
    address: str
    adapter: str = "email"
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465
    use_ssl: bool = True
    password: str = ""
    password_env: str = ""

    def resolve_password(self) -> str:
        if self.password:
            return self.password
        if self.password_env:
            return os.environ.get(self.password_env, "")
        return ""


@dataclass(slots=True)
class FriendConfig:
    name: str
    address: str


@dataclass(slots=True)
class AppConfig:
    cache_path: Path
    accounts: list[AccountConfig] = field(default_factory=list)
    friends: list[FriendConfig] = field(default_factory=list)


def default_config_path() -> Path:
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def default_cache_path() -> Path:
    return Path(user_data_dir(APP_NAME)) / "messages.db"


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else default_config_path()
    data: dict = {}
    if config_path.exists():
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)

    accounts = [AccountConfig(**a) for a in data.get("account", [])]
    friends = [FriendConfig(**f) for f in data.get("friend", [])]

    cache = data.get("general", {}).get("cache")
    cache_path = Path(cache).expanduser() if cache else default_cache_path()

    return AppConfig(cache_path=cache_path, accounts=accounts, friends=friends)
