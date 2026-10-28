#!/usr/bin/env python3
"""Provision the lab's dedicated Corvus index reader; run on the Wazuh host.

Uses the existing administrator credentials only for provisioning. The application
receives a separate account limited to reading alert/archive indices. Never prints
passwords or puts them in command-line arguments.
"""

import base64
import json
import os
import pwd
import secrets
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROLE = "corvus_investigator_readonly"
USERNAME = "corvus-reader"
ROLE_BODY = {
    "cluster_permissions": [
        "cluster_composite_ops_ro",
        "indices:data/read/scroll",
        "indices:data/read/scroll/clear",
    ],
    "index_permissions": [
        {
            "index_patterns": ["wazuh-alerts-*", "wazuh-archives-*"],
            "allowed_actions": ["read"],
        }
    ],
    "tenant_permissions": [],
}


def main():
    root = Path("/home/ubuntu/.config/corvus")
    admin = json.loads((root / "wazuh-credentials.json").read_text())
    ctx = ssl.create_default_context(
        cafile="/opt/wazuh-docker/single-node/config/wazuh_indexer_ssl_certs/root-ca.pem"
    )
    ctx.check_hostname = False
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def request(path, method="GET", data=None, credentials=None):
        user, password = credentials or (admin["dashboard_username"], admin["dashboard_password"])
        auth = base64.b64encode((user + ":" + password).encode()).decode()
        req = Request(
            "https://127.0.0.1:9200" + path,
            headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"},
            method=method,
            data=None if data is None else json.dumps(data).encode(),
        )
        try:
            with urlopen(req, context=ctx, timeout=25) as response:
                return json.load(response)
        except HTTPError as exc:
            if method == "GET" and exc.code == 404:
                return None
            raise

    path = root / "wazuh-reader.json"
    existing_user = request("/_plugins/_security/api/internalusers/" + USERNAME)
    if path.exists():
        account = json.loads(path.read_text())
    elif existing_user:
        raise SystemExit(
            "Reader already exists without a local credential file; refusing to reset it."
        )
    else:
        account = {
            "username": USERNAME,
            "password": "Aa1!" + secrets.token_hex(20),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Save first. A retry reuses this password if the API request failed.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(account, file, indent=2)
            file.write("\n")
        owner = pwd.getpwnam("ubuntu")
        os.chown(path, owner.pw_uid, owner.pw_gid)
    if account.get("username") != USERNAME or not account.get("password"):
        raise SystemExit("Unexpected reader credential file; refusing to continue.")
    if not existing_user:
        request(
            "/_plugins/_security/api/internalusers/" + USERNAME,
            "PUT",
            {"password": account["password"], "backend_roles": [], "attributes": {}},
        )

    existing_role = request("/_plugins/_security/api/roles/" + ROLE)
    if existing_role:
        current = existing_role[ROLE]
        # Refuse to silently broaden or replace an existing role definition.
        if current.get("cluster_permissions") != ROLE_BODY["cluster_permissions"]:
            raise SystemExit(
                "Existing reader role differs; inspect it before changing permissions."
            )
        permissions = current.get("index_permissions", [])
        if (
            len(permissions) != 1
            or any(
                permissions[0].get(key) != value
                for key, value in ROLE_BODY["index_permissions"][0].items()
            )
            or current.get("tenant_permissions")
        ):
            raise SystemExit(
                "Existing reader role differs; inspect it before changing permissions."
            )
    else:
        request("/_plugins/_security/api/roles/" + ROLE, "PUT", ROLE_BODY)

    mapping = request("/_plugins/_security/api/rolesmapping/" + ROLE)
    wanted = {"users": [USERNAME], "backend_roles": [], "hosts": []}
    if mapping and any(mapping[ROLE].get(key, []) != value for key, value in wanted.items()):
        raise SystemExit("Existing role mapping differs; refusing to replace it.")
    if not mapping:
        request("/_plugins/_security/api/rolesmapping/" + ROLE, "PUT", wanted)

    credentials = (account["username"], account["password"])
    for pattern in ["wazuh-alerts-*", "wazuh-archives-*"]:
        request(
            "/" + pattern + "/_search", "POST", {"size": 0, "track_total_hits": False}, credentials
        )
        print("Read verified:", pattern)
    # Missing-document update has no upsert: even unexpected authorization would
    # not create or change a document. It must be forbidden for this role.
    current = "wazuh-archives-4.x-" + datetime.now(timezone.utc).strftime("%Y.%m.%d")
    try:
        request(
            "/" + current + "/_update/__corvus_permission_probe__",
            "POST",
            {"doc": {"probe": True}},
            credentials,
        )
    except HTTPError as exc:
        if exc.code != 403:
            raise
        print("Write denial verified: HTTP 403")
    else:
        raise SystemExit("Reader unexpectedly allowed document updates!")
    try:
        request("/.opendistro_security/_search", "POST", {"size": 0}, credentials)
    except HTTPError as exc:
        if exc.code != 403:
            raise
        print("Protected-index denial verified: HTTP 403")
    else:
        raise SystemExit("Reader unexpectedly allowed protected-index access!")
    print("Private reader credentials:", path)


if __name__ == "__main__":
    main()
