"""Bounded local indicator inspection. No network lookups or threat-reputation claims."""

import ipaddress
import re

VERSION = "0.1"
IP_FIELDS = {"sourceip", "destinationip", "ipaddress", "srcip", "dstip"}
DOMAIN_FIELDS = {"queryname", "dnsquery"}
HASH_LENGTHS = {"MD5": 32, "SHA1": 40, "SHA256": 64, "SHA512": 128, "IMPHASH": 32}


def inspect(bundle):
    observations = {}
    visited = 0
    truncated = False

    def add(kind, value, facts, document, path):
        nonlocal truncated
        key = (kind, value)
        if key not in observations:
            if len(observations) >= 32:
                truncated = True
                return
            observations[key] = {"kind": kind, "value": value, "facts": facts, "sources": []}
        source = {"reference": document["reference"], "path": path}
        if source not in observations[key]["sources"]:
            if len(observations[key]["sources"]) < 8:
                observations[key]["sources"].append(source)
            else:
                truncated = True

    def walk(value, document, path="", depth=0):
        nonlocal visited, truncated
        if depth > 8 or visited >= 25000:
            truncated = True
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            visited += 1
            if visited > 25000:
                truncated = True
                return
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if isinstance(item, dict):
                walk(item, document, pointer, depth + 1)
            elif isinstance(item, str) and len(item) <= 1024:
                field = key.lower()
                if field in IP_FIELDS:
                    try:
                        address = ipaddress.ip_address(item)
                    except ValueError:
                        continue
                    category = next(
                        (
                            label
                            for flag, label in (
                                (address.is_loopback, "loopback"),
                                (address.is_link_local, "link-local"),
                                (address.is_multicast, "multicast"),
                                (address.is_unspecified, "unspecified"),
                                (address.is_reserved, "reserved"),
                                (address.is_private, "private or special-use"),
                                (address.is_global, "globally routable"),
                            )
                            if flag
                        ),
                        "special-use",
                    )
                    add(
                        "ip",
                        str(address),
                        [
                            f"IPv{address.version}",
                            category,
                            "Address class is not a safety or reputation verdict.",
                        ],
                        document,
                        pointer,
                    )
                elif field in DOMAIN_FIELDS and len(item) <= 253:
                    domain = item.rstrip(".").lower()
                    if re.fullmatch(
                        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                        domain,
                    ):
                        add(
                            "domain",
                            domain,
                            [
                                "Observed DNS query name; no DNS resolution or reputation lookup performed."
                            ],
                            document,
                            pointer,
                        )
                elif field == "hashes":
                    for part in item.split(","):
                        algorithm, separator, digest = part.strip().partition("=")
                        algorithm = algorithm.upper().replace("-", "")
                        if (
                            separator
                            and algorithm in HASH_LENGTHS
                            and len(digest) == HASH_LENGTHS[algorithm]
                            and re.fullmatch("[a-fA-F0-9]+", digest)
                        ):
                            add(
                                "hash",
                                digest.lower(),
                                [
                                    algorithm,
                                    "Syntactically valid digest; file identity and reputation are not established.",
                                ],
                                document,
                                pointer,
                            )

    documents = [bundle["alert"], *bundle["events"]]
    for document in documents[:25]:
        walk(document["source"], document)
    return {
        "version": VERSION,
        "mode": "local_deterministic",
        "observations": list(observations.values()),
        "truncated": truncated or len(documents) > 25,
        "limitations": [
            "Selected evidence only; indicator strings are untrusted observations, not validated endpoints or file identities.",
            "No external services, model requests, DNS queries, threat-feed, geolocation, or sandbox lookups. No malicious/benign verdict or response authorization.",
        ],
    }
