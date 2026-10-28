"""Private evidence-file output; no silent overwrites."""

import json
import os
from pathlib import Path

MAX_JSON_BYTES = 16 * 1024 * 1024


def parse_json(payload):
    """Reject ambiguous duplicate keys and non-standard NaN/Infinity values."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("JSON contains duplicate object keys")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("JSON contains a non-finite number")

    try:
        return json.loads(payload, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError("Cannot parse a valid JSON document") from exc


def load_json(path):
    """Read a bounded local JSON object without echoing its potentially sensitive contents."""
    with Path(path).expanduser().open("rb") as file:
        payload = file.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("JSON input exceeds the 16 MiB limit")
    data = parse_json(payload)
    if not isinstance(data, dict):
        raise ValueError("JSON document must be an object")
    return data


def save_private(path, data):
    output = Path(path).expanduser()
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(payload)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output
