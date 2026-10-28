#!/usr/bin/env python3
"""One-time lab secret provisioning. Run with sudo; never prints credentials."""

import base64
import hashlib
import json
import os
import pwd
import secrets
import shutil
import ssl
import tempfile
from pathlib import Path

DESTINATION = Path("/home/ubuntu/.config/corvus/app")
CA = Path("/opt/wazuh-docker/single-node/config/wazuh_indexer_ssl_certs/root-ca.pem")
CA_FINGERPRINT = "2cc7b946d4819644c0875e49cbfb98b446f782b99f0d601f2341b20a9095885e"


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo to set container-specific file ownership")
    required = {"server.json", "database-password", "wazuh-ca.pem", "login.json", "deploy.env"}
    if DESTINATION.exists():
        if required <= {path.name for path in DESTINATION.iterdir()}:
            print("Existing application secrets left unchanged:", DESTINATION)
            return
        raise SystemExit(
            "Partial secret directory exists; inspect it rather than overwriting credentials"
        )
    der = ssl.PEM_cert_to_DER_cert(CA.read_text())
    if hashlib.sha256(der).hexdigest() != CA_FINGERPRINT:
        raise SystemExit("Wazuh CA fingerprint changed; verify before provisioning")
    owner = pwd.getpwnam("ubuntu")
    temporary = Path(tempfile.mkdtemp(prefix="app-setup-", dir=DESTINATION.parent))
    try:
        database_password = secrets.token_urlsafe(32)
        admin_password = secrets.token_urlsafe(32)
        config = {
            "database_url": f"postgresql://corvus:{database_password}@db:5432/corvus",
            "origin": "https://corvus.0xbenzo.dev",
            "encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "admin_username": "admin",
            "admin_password": admin_password,
            "ca_file": "/run/corvus/wazuh-ca.pem",
            "indexer_hosts": ["wazuh.indexer"],
            "allow_legacy_ca": True,
        }
        contents = {
            "server.json": (json.dumps(config, indent=2), 10001, 0o400),
            "database-password": (database_password, 999, 0o400),
            "wazuh-ca.pem": (CA.read_text(), 10001, 0o400),
            "login.json": (
                json.dumps(
                    {"url": config["origin"], "username": "admin", "password": admin_password},
                    indent=2,
                ),
                owner.pw_uid,
                0o600,
            ),
            "deploy.env": (f"CORVUS_CONFIG_DIR={DESTINATION}\n", owner.pw_uid, 0o600),
        }
        for name, (content, uid, mode) in contents.items():
            path = temporary / name
            path.write_text(content + "\n")
            os.chown(path, uid, uid)
            path.chmod(mode)
        os.chown(temporary, owner.pw_uid, owner.pw_gid)
        temporary.chmod(0o700)
        temporary.rename(DESTINATION)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    print("Private application configuration created:", DESTINATION)
    print("Browser credentials are in login.json; do not paste them into chat or logs")


if __name__ == "__main__":
    main()
