import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from ..storage import load_json


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    origin: str
    encryption_key: str = field(repr=False)
    admin_username: str
    admin_password: str = field(repr=False)
    ca_file: str
    indexer_hosts: list[str]
    allow_legacy_ca: bool = False
    tls_server_name: str | None = None

    def __post_init__(self):
        url = urlsplit(self.origin)
        local_http = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
        if (
            (url.scheme != "https" and not local_http)
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("Origin must be a bare HTTPS origin (HTTP is local-development only)")
        if not self.admin_username or len(self.admin_password) < 16:
            raise ValueError(
                "An admin username and password of at least 16 characters are required"
            )
        if not self.indexer_hosts or any(
            not isinstance(host, str) or not host for host in self.indexer_hosts
        ):
            raise ValueError("An operator-controlled indexer hostname allowlist is required")
        if type(self.allow_legacy_ca) is not bool:
            raise ValueError("allow_legacy_ca must be boolean")
        Fernet(self.encryption_key.encode())

    @property
    def secure(self):
        return self.origin.startswith("https://")

    @property
    def cipher(self):
        return Fernet(self.encryption_key.encode())

    @classmethod
    def load(cls):
        path = Path(os.environ.get("CORVUS_SERVER_CONFIG", "/run/corvus/server.json"))
        if path.stat().st_mode & 0o077:
            raise ValueError("Server configuration must have mode 0600")
        return cls(**load_json(path))
