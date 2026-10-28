"""Azure Foundry OpenAI v1 client: one bounded request, no redirects or retries."""

import http.client
import json
import os
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ..errors import ConfigError
from ..storage import load_json, parse_json
from . import ModelError, ModelReply

MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FoundryConfig:
    endpoint: str
    api_key: str = field(repr=False)
    model: str = "DeepSeek-V4-Flash"
    max_tokens: int = 4096
    timeout_seconds: float = 120

    def __post_init__(self):
        if not isinstance(self.endpoint, str):
            raise ConfigError("Foundry endpoint must be a string")
        try:
            url = urlsplit(self.endpoint)
            valid_port = url.port in (None, 443)
        except ValueError as exc:
            raise ConfigError("Invalid Foundry endpoint") from exc
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith((".openai.azure.com", ".services.ai.azure.com"))
            or url.path.rstrip("/") != "/openai/v1"
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or not valid_port
        ):
            raise ConfigError(
                "Foundry endpoint must be an Azure HTTPS /openai/v1 URL without credentials or query"
            )
        if (
            not isinstance(self.api_key, str)
            or not self.api_key
            or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key)
        ):
            raise ConfigError("A valid Foundry API key is required")
        if not isinstance(self.model, str) or not re.fullmatch(
            r"[A-Za-z0-9._-]{1,128}", self.model
        ):
            raise ConfigError("A valid exact deployment/model identifier is required")
        if type(self.max_tokens) is not int or not 256 <= self.max_tokens <= 8192:
            raise ConfigError("max_tokens must be between 256 and 8192")
        if type(self.timeout_seconds) not in (int, float) or not 1 <= self.timeout_seconds <= 180:
            raise ConfigError("Foundry timeout_seconds must be between 1 and 180")


def load_foundry_config(path=None):
    location = Path(
        path or os.environ.get("CORVUS_FOUNDRY_CONFIG", "~/.config/corvus/azure_foundry.json")
    ).expanduser()
    try:
        if os.name == "posix" and location.stat().st_mode & 0o077:
            raise ConfigError("Foundry credentials require private permissions: chmod 600")
        data = load_json(location)
    except ConfigError:
        raise
    except (OSError, ValueError) as exc:
        raise ConfigError("Cannot read a valid private Foundry configuration") from exc
    allowed = {"endpoint", "api_key", "model", "max_tokens", "timeout_seconds"}
    if set(data) - allowed:
        raise ConfigError("Foundry configuration contains unsupported settings")
    try:
        return FoundryConfig(**data)
    except TypeError as exc:
        raise ConfigError("Missing Foundry endpoint or API key") from exc


class AzureFoundryClient:
    def __init__(self, config: FoundryConfig):
        self.config = config

    def complete(self, messages):
        config = self.config
        payload = json.dumps(
            {
                "model": config.model,
                "messages": messages,
                "max_tokens": config.max_tokens,
                "temperature": 0,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise ModelError(
                "model_input_too_large",
                "Model request exceeds the 1 MiB limit; evidence was not truncated or sent",
            )
        url = urlsplit(config.endpoint)
        connection = http.client.HTTPSConnection(
            url.hostname, 443, timeout=config.timeout_seconds, context=ssl.create_default_context()
        )
        try:
            connection.request(
                "POST",
                url.path.rstrip("/") + "/chat/completions",
                body=payload,
                headers={"api-key": config.api_key, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                code = "deployment_not_found" if response.status == 404 else "model_http_error"
                # Never echo provider response bodies, headers, or request credentials.
                raise ModelError(
                    code,
                    f"Azure returned HTTP {response.status}; no retry or model fallback was attempted",
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ModelError(
                    "model_response_too_large", "Model response exceeded the 2 MiB limit"
                )
            try:
                data = parse_json(raw)
                choice = data["choices"][0]
                message = choice["message"]
                if choice.get("finish_reason") != "stop":
                    raise ModelError(
                        "incomplete_model_response",
                        "Model did not finish normally; increase the explicit token budget or investigate the provider",
                    )
                if message.get("tool_calls") or message.get("function_call"):
                    raise ModelError(
                        "unexpected_model_tool_call",
                        "This analyst has no tool-execution capability",
                    )
                content = message["content"]
                model = data["model"]
                if (
                    not isinstance(content, str)
                    or not content.strip()
                    or not isinstance(model, str)
                ):
                    raise ValueError("Missing model content")
                usage = {
                    key: value
                    for key, value in data.get("usage", {}).items()
                    if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    and type(value) is int
                    and value >= 0
                }
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                raise ModelError(
                    "invalid_model_response", "Azure returned an invalid completion envelope"
                ) from exc
            return ModelReply(content, model, usage)
        except (OSError, http.client.HTTPException) as exc:
            raise ModelError(
                "model_connection_failed",
                "Azure connection failed; no automatic retry was attempted",
            ) from exc
        finally:
            connection.close()
