"""Private connection configuration; no credentials in URLs or reports."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ConfigError


@dataclass(frozen=True)
class Config:
    indexer_url: str
    username: str
    password: str = field(repr=False)
    ca_file: Path | None = None
    tls_server_name: str | None = None
    allow_legacy_ca: bool = False
    timeout_seconds: float = 15

    def __post_init__(self):
        if not isinstance(self.indexer_url, str):
            raise ConfigError("Indexer URL must be a string")
        try:
            url = urlsplit(self.indexer_url)
            port = url.port
        except ValueError as exc:
            raise ConfigError("Invalid indexer URL") from exc
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ConfigError(
                "Indexer URL must be HTTPS without credentials, a path, query, or fragment"
            )
        if not isinstance(self.username, str) or not self.username or ":" in self.username:
            raise ConfigError("A valid username is required")
        if not isinstance(self.password, str) or not self.password:
            raise ConfigError("A password is required")
        if type(self.allow_legacy_ca) is not bool:
            raise ConfigError("allow_legacy_ca must be a JSON boolean")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not 1 <= self.timeout_seconds <= 60
        ):
            raise ConfigError("timeout_seconds must be between 1 and 60")
        if self.tls_server_name is not None and (
            not isinstance(self.tls_server_name, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", self.tls_server_name)
        ):
            raise ConfigError("Invalid TLS server name")
        if self.ca_file is not None and not self.ca_file.is_file():
            raise ConfigError("Configured CA file does not exist")


def load_config(path: str | Path | None = None) -> Config:
    location = Path(
        path or os.environ.get("CORVUS_CONFIG", "~/.config/corvus/config.json")
    ).expanduser()
    try:
        if os.name == "posix" and location.stat().st_mode & 0o077:
            raise ConfigError(
                "Configuration contains credentials; restrict its permissions with chmod 600"
            )
        data = json.loads(location.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("Cannot read a valid private Corvus configuration file") from exc
    allowed = {
        "indexer_url",
        "username",
        "password",
        "ca_file",
        "tls_server_name",
        "allow_legacy_ca",
        "timeout_seconds",
    }
    if not isinstance(data, dict) or set(data) - allowed:
        raise ConfigError(
            "Configuration must be an object containing only supported connection settings"
        )
    if data.get("ca_file") is not None:
        if not isinstance(data["ca_file"], str):
            raise ConfigError("ca_file must be a path string")
        ca = Path(data["ca_file"]).expanduser()
        data["ca_file"] = ca if ca.is_absolute() else location.parent / ca
    try:
        return Config(**data)
    except TypeError as exc:
        raise ConfigError("Missing or invalid connection settings") from exc
