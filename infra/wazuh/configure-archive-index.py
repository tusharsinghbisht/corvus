#!/usr/bin/env python3
"""Configure/check the current lab's archive policy and dashboard data view.

Run on the Wazuh host with access to its protected credentials and CA. Does not
create credentials, expose APIs, or alter alert index retention.
"""

import argparse
import base64
import json
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

POLICY_ID = "corvus-archives-retention"
VIEW_ID = "corvus-wazuh-archives"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["policy", "dashboard", "verify"])
    parser.add_argument("--policy-file", default="/opt/corvus/config/archive-retention-policy.json")
    args = parser.parse_args()
    credentials = json.loads(Path("/home/ubuntu/.config/corvus/wazuh-credentials.json").read_text())
    basic = base64.b64encode(
        (credentials["dashboard_username"] + ":" + credentials["dashboard_password"]).encode()
    ).decode()
    context = ssl.create_default_context(
        cafile="/opt/wazuh-docker/single-node/config/wazuh_indexer_ssl_certs/root-ca.pem"
    )
    # The endpoint is host loopback; validate its CA without hostname matching.
    context.check_hostname = False
    # Official Wazuh CA omits Key Usage; Python 3.14 otherwise rejects it.
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def request(path, method="GET", data=None, dashboard=False):
        base = "https://wazuh.tusharr.xyz" if dashboard else "https://127.0.0.1:9200"
        headers = {"Authorization": "Basic " + basic, "Content-Type": "application/json"}
        if dashboard:
            # Wazuh disables dashboard multitenancy in this deployment. An
            # explicit tenant header can put the object outside the UI context.
            headers["osd-xsrf"] = "true"
        payload = json.dumps(data).encode() if data is not None else None
        req = Request(base + path, headers=headers, method=method, data=payload)
        try:
            with urlopen(req, context=None if dashboard else context, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404 and method == "GET":
                return None
            raise

    if args.operation == "policy":
        desired = json.loads(Path(args.policy_file).read_text())
        existing = request("/_plugins/_ism/policies/" + POLICY_ID)
        if existing:
            print("Policy already exists; not overwriting it. Use verify to inspect it.")
            return
        created = request("/_plugins/_ism/policies/" + POLICY_ID, "PUT", desired)
        print("Created policy:", created.get("_id", POLICY_ID))
    elif args.operation == "dashboard":
        path = "/api/saved_objects/index-pattern/" + VIEW_ID
        existing = request(path, dashboard=True)
        if existing:
            if existing.get("attributes", {}).get("title") != "wazuh-archives-*":
                raise RuntimeError("Saved-object ID is occupied by a different index pattern")
            print("Archive index pattern already exists; not overwriting it.")
        else:
            created = request(
                path,
                "POST",
                {
                    "attributes": {"title": "wazuh-archives-*", "timeFieldName": "timestamp"},
                },
                dashboard=True,
            )
            print("Created default-context index pattern:", created["id"])
        # Direct GET alone is insufficient: also check the listing used by the UI.
        for attempt in range(6):
            listing = request(
                "/api/saved_objects/_find?type=index-pattern&per_page=100&fields=title",
                dashboard=True,
            )
            if listing and any(
                item.get("id") == VIEW_ID for item in listing.get("saved_objects", [])
            ):
                print("Verified: archive index pattern appears in the dashboard listing.")
                break
            if attempt < 5:
                time.sleep(1)
        else:
            raise RuntimeError("Index pattern exists but is not visible in the dashboard listing")
    else:
        for path in [
            "/_plugins/_ism/policies/" + POLICY_ID,
            "/_plugins/_ism/explain/wazuh-archives-*?show_policy=true",
            "/_cat/indices/wazuh-archives-*?format=json&h=index,health,docs.count,store.size",
            "/_cluster/health",
        ]:
            print(path, json.dumps(request(path)))
        query = {
            "size": 0,
            "aggs": {
                "agents": {"terms": {"field": "agent.name", "size": 10}},
                "channels": {"terms": {"field": "data.win.system.channel", "size": 10}},
                "without_rule_id": {
                    "filter": {"bool": {"must_not": [{"exists": {"field": "rule.id"}}]}}
                },
            },
        }
        result = request("/wazuh-archives-*/_search", "POST", query)
        print("Archive evidence summary:", json.dumps(result))


if __name__ == "__main__":
    main()
