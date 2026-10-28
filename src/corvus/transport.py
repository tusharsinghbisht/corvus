"""Bounded HTTPS transport; never follows redirects or disables TLS validation."""

import base64
import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

from .config import Config
from .errors import BackendError, ConfigError

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class _Connection(http.client.HTTPSConnection):
    def __init__(self, *args, tls_server_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tls_server_name = tls_server_name

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self.tls_server_name or self.host,
        )


class Transport:
    def __init__(self, config: Config, max_requests: int = 32):
        self.config = config
        self.url = urlsplit(config.indexer_url)
        self.max_requests = max_requests
        self.request_count = 0
        self.audit = []
        try:
            self.context = ssl.create_default_context(cafile=config.ca_file)
        except (OSError, ssl.SSLError) as exc:
            raise ConfigError("Cannot load the configured TLS CA") from exc
        if config.allow_legacy_ca:
            # Explicit lab compatibility for Wazuh's generated CA without Key Usage.
            # Certificate-chain and hostname verification remain enabled.
            self.context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        token = base64.b64encode((config.username + ":" + config.password).encode()).decode()
        self._authorization = "Basic " + token

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if self.request_count >= self.max_requests:
            raise BackendError("budget_exhausted", "Backend request budget exhausted")
        if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path:
            raise ValueError("Invalid backend path")
        self.request_count += 1
        started = time.monotonic()
        entry = {"method": method, "path": path, "status": None}
        connection = _Connection(
            self.url.hostname,
            self.url.port or 443,
            timeout=self.config.timeout_seconds,
            context=self.context,
            tls_server_name=self.config.tls_server_name,
        )
        try:
            payload = None if body is None else json.dumps(body).encode()
            connection.request(
                method,
                path,
                body=payload,
                headers={
                    "Authorization": self._authorization,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            entry["status"] = response.status
            if not 200 <= response.status < 300:
                codes = {
                    401: "authentication_failed",
                    403: "permission_denied",
                    404: "not_found",
                    408: "timeout",
                    429: "rate_limited",
                }
                code = codes.get(response.status, "backend_error")
                if 300 <= response.status < 400:
                    code = "redirect_refused"
                elif response.status >= 500:
                    code = "backend_unavailable"
                # Do not echo arbitrary response bodies, credentials, or headers.
                raise BackendError(
                    code, f"Indexer returned HTTP {response.status}", response.status
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise BackendError("response_too_large", "Backend response exceeded the size limit")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise BackendError("invalid_response", "Backend returned invalid JSON") from exc
            if not isinstance(result, dict):
                raise BackendError("invalid_response", "Backend response must be a JSON object")
            return result
        except ssl.SSLError as exc:
            raise BackendError("tls_error", "TLS verification or handshake failed") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise BackendError("timeout", "Backend request timed out") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise BackendError(
                "connection_failed", "Cannot complete the backend connection"
            ) from exc
        finally:
            entry["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
            self.audit.append(entry)
            connection.close()
