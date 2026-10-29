import json
import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from corvus.errors import ConfigError
from corvus.providers import ModelError
from corvus.providers.azure_foundry import AzureFoundryClient, FoundryConfig, load_foundry_config
from corvus.storage import save_private

ENDPOINT = "https://test-resource.openai.azure.com/openai/v1"
FAKE_KEY = "unit-test-key-not-a-real-credential"


def completion(**changes):
    data = {
        "model": "DeepSeek-V4-Flash",
        "choices": [{"finish_reason": "stop", "message": {"content": '{"example":true}'}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "ignored": "do-not-copy",
        },
    }
    data.update(changes)
    return json.dumps(data).encode()


class FoundryConfigTests(unittest.TestCase):
    def test_private_configuration_and_secret_repr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foundry.json"
            save_private(path, {"endpoint": ENDPOINT, "api_key": FAKE_KEY})
            config = load_foundry_config(path)
            self.assertEqual(config.model, "DeepSeek-V4-Flash")
            self.assertNotIn(FAKE_KEY, repr(config))
            if os.name == "posix":
                path.chmod(0o644)
                with self.assertRaises(ConfigError):
                    load_foundry_config(path)

    def test_invalid_urls_and_options_are_rejected(self):
        endpoints = [
            "http://test.openai.azure.com/openai/v1",
            "https://test.openai.azure.com.attacker.invalid/openai/v1",
            "https://user:secret@test.openai.azure.com/openai/v1",
            ENDPOINT + "?api-key=secret",
            ENDPOINT + "#fragment",
            "https://test.openai.azure.com:80/openai/v1",
            "https://test.openai.azure.com/other",
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigError):
                FoundryConfig(endpoint, FAKE_KEY)
        for changes in (
            {"api_key": "bad\r\nheader"},
            {"model": "../other"},
            {"max_tokens": True},
            {"max_tokens": 8193},
            {"timeout_seconds": float("nan")},
            {"timeout_seconds": False},
        ):
            with self.assertRaises(ConfigError):
                FoundryConfig(**{"endpoint": ENDPOINT, "api_key": FAKE_KEY, **changes})

    def test_unknown_settings_do_not_silently_change_provider_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foundry.json"
            save_private(path, {"endpoint": ENDPOINT, "api_key": FAKE_KEY, "verify_tls": False})
            with self.assertRaises(ConfigError):
                load_foundry_config(path)


class FoundryClientTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.read.return_value = completion()
        self.patcher = patch(
            "corvus.providers.azure_foundry.http.client.HTTPSConnection",
            return_value=self.connection,
        )
        self.factory = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = AzureFoundryClient(FoundryConfig(ENDPOINT, FAKE_KEY))
        self.messages = [{"role": "user", "content": "Synthetic JSON test"}]

    def test_verified_tls_exact_model_json_mode_and_no_secret_in_payload(self):
        reply = self.client.complete(self.messages)
        context = self.factory.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        args, kwargs = self.connection.request.call_args
        self.assertEqual(args, ("POST", "/openai/v1/chat/completions"))
        self.assertEqual(kwargs["headers"]["api-key"], FAKE_KEY)
        self.assertNotIn(FAKE_KEY.encode(), kwargs["body"])
        request = json.loads(kwargs["body"])
        self.assertEqual(request["model"], "DeepSeek-V4-Flash")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertEqual(
            reply.usage, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        )
        self.assertEqual(reply.finish_reason, "stop")
        self.connection.close.assert_called_once()

    def test_explicit_larger_output_budget_does_not_change_model_or_retry(self):
        client = AzureFoundryClient(FoundryConfig(ENDPOINT, FAKE_KEY, max_tokens=8192))
        client.complete(self.messages)
        payload = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(payload["model"], "DeepSeek-V4-Flash")
        self.connection.request.assert_called_once()

    def test_http_errors_are_sanitized_never_retried_or_redirected(self):
        for status in (302, 401, 403, 404, 429, 500):
            self.connection.reset_mock()
            self.response.status = status
            self.response.read.return_value = FAKE_KEY.encode()
            with self.subTest(status=status), self.assertRaises(ModelError) as caught:
                self.client.complete(self.messages)
            self.assertNotIn(FAKE_KEY, str(caught.exception))
            self.connection.request.assert_called_once()
            self.connection.close.assert_called_once()
            self.response.read.assert_not_called()

    def test_request_size_is_checked_before_connecting(self):
        with (
            patch("corvus.providers.azure_foundry.MAX_REQUEST_BYTES", 16),
            self.assertRaises(ModelError),
        ):
            self.client.complete(self.messages)
        self.factory.assert_not_called()

    def test_response_size_is_bounded(self):
        with (
            patch("corvus.providers.azure_foundry.MAX_RESPONSE_BYTES", 16),
            self.assertRaises(ModelError) as caught,
        ):
            self.client.complete(self.messages)
        self.assertEqual(caught.exception.code, "model_response_too_large")
        self.connection.close.assert_called_once()

    def test_incomplete_and_tool_call_responses_are_not_reports(self):
        for choice, code in [
            (
                {"finish_reason": "length", "message": {"content": "{}"}},
                "incomplete_model_response",
            ),
            (
                {
                    "finish_reason": "stop",
                    "message": {"content": "{}", "tool_calls": [{"name": "execute"}]},
                },
                "unexpected_model_tool_call",
            ),
        ]:
            self.response.read.return_value = completion(choices=[choice])
            with self.assertRaises(ModelError) as caught:
                self.client.complete(self.messages)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.reply.content, "{}")
            self.assertEqual(caught.exception.reply.model, "DeepSeek-V4-Flash")
            self.assertEqual(caught.exception.diagnostics["finish_reason"], choice["finish_reason"])
            self.assertEqual(caught.exception.diagnostics["usage"]["completion_tokens"], 20)

    def test_empty_incomplete_reply_retains_safe_diagnostics_not_reasoning(self):
        self.response.read.return_value = completion(
            choices=[
                {
                    "finish_reason": "length",
                    "message": {"content": None, "reasoning_content": "PRIVATE-REASONING"},
                }
            ]
        )
        with self.assertRaises(ModelError) as caught:
            self.client.complete(self.messages)
        error = caught.exception
        self.assertEqual(error.code, "incomplete_model_response")
        self.assertIsNone(error.reply)
        self.assertEqual(error.diagnostics["finish_reason"], "length")
        self.assertEqual(error.diagnostics["usage"]["completion_tokens"], 20)
        self.assertNotIn("PRIVATE-REASONING", json.dumps(error.diagnostics))
        self.assertNotIn("PRIVATE-REASONING", str(error))
        self.connection.request.assert_called_once()

    def test_unknown_finish_reason_is_not_echoed_in_diagnostics(self):
        self.response.read.return_value = completion(
            choices=[
                {
                    "finish_reason": "PRIVATE-UNEXPECTED-DATA",
                    "message": {"content": "{}"},
                }
            ]
        )
        with self.assertRaises(ModelError) as caught:
            self.client.complete(self.messages)
        self.assertEqual(caught.exception.diagnostics["finish_reason"], "other")
        self.assertEqual(caught.exception.reply.finish_reason, "other")
        self.assertNotIn("PRIVATE-UNEXPECTED-DATA", json.dumps(caught.exception.diagnostics))

    def test_invalid_envelopes_and_connection_errors_are_explicit(self):
        for payload in (b"not JSON", b"[]", b'{"choices":[]}', completion(usage=None)):
            self.response.read.return_value = payload
            with self.assertRaises(ModelError):
                self.client.complete(self.messages)
        self.connection.request.side_effect = TimeoutError(FAKE_KEY)
        with self.assertRaises(ModelError) as caught:
            self.client.complete(self.messages)
        self.assertEqual(caught.exception.code, "model_connection_failed")
        self.assertNotIn(FAKE_KEY, str(caught.exception))
