import json
import ssl
import unittest
from unittest.mock import MagicMock, patch

from corvus.config import Config
from corvus.errors import BackendError
from corvus.transport import Transport, _Connection


class TransportTests(unittest.TestCase):
    def config(self, **kwargs):
        return Config("https://127.0.0.1:19200", "reader", "test-password", **kwargs)

    def test_tls_verification_stays_enabled_in_legacy_mode(self):
        for legacy in [False, True]:
            client = Transport(self.config(allow_legacy_ca=legacy))
            self.assertTrue(client.context.check_hostname)
            self.assertEqual(client.context.verify_mode, ssl.CERT_REQUIRED)
            if legacy:
                self.assertFalse(client.context.verify_flags & ssl.VERIFY_X509_STRICT)

    @patch("corvus.transport.http.client.HTTPConnection.connect")
    def test_tunnel_uses_explicit_verified_server_name(self, connect):
        context = MagicMock()
        connection = _Connection(
            "127.0.0.1", 19200, context=context, tls_server_name="wazuh.indexer"
        )
        connection.sock = object()
        original = connection.sock
        connection.connect()
        context.wrap_socket.assert_called_once_with(original, server_hostname="wazuh.indexer")

    @patch("corvus.transport._Connection")
    def test_success_does_not_record_credentials(self, connection):
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({"ok": True}).encode()
        client = Transport(self.config())
        self.assertEqual(
            client.request("POST", "/wazuh-alerts-*/_search", {"size": 0}), {"ok": True}
        )
        self.assertNotIn("test-password", json.dumps(client.audit))
        self.assertNotIn("Authorization", json.dumps(client.audit))
        connection.return_value.close.assert_called_once()

    @patch("corvus.transport._Connection")
    def test_permissions_and_redirects_are_not_empty_results(self, connection):
        response = connection.return_value.getresponse.return_value
        for status, code in [
            (401, "authentication_failed"),
            (403, "permission_denied"),
            (404, "not_found"),
            (302, "redirect_refused"),
            (503, "backend_unavailable"),
        ]:
            response.status = status
            with self.subTest(status=status), self.assertRaises(BackendError) as error:
                Transport(self.config()).request("GET", "/test")
            self.assertEqual(error.exception.code, code)

    @patch("corvus.transport._Connection")
    def test_request_budget_and_invalid_json(self, connection):
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b"not json"
        client = Transport(self.config(), max_requests=1)
        with self.assertRaises(BackendError) as error:
            client.request("GET", "/test")
        self.assertEqual(error.exception.code, "invalid_response")
        with self.assertRaises(BackendError) as error:
            client.request("GET", "/test")
        self.assertEqual(error.exception.code, "budget_exhausted")
