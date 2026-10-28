import json
import os
import tempfile
import unittest
from pathlib import Path

from corvus.config import Config, load_config
from corvus.errors import ConfigError


class ConfigTests(unittest.TestCase):
    def test_rejects_insecure_or_credential_bearing_urls(self):
        for url in [
            "http://localhost:9200",
            "https://user:secret@host",
            "https://host/path",
            "https://host?q=secret",
            "https://host#x",
        ]:
            with self.subTest(url=url), self.assertRaises(ConfigError):
                Config(url, "reader", "test-password")

    def test_password_is_not_in_repr(self):
        config = Config("https://localhost:9200", "reader", "test-password")
        self.assertNotIn("test-password", repr(config))

    def test_rejects_invalid_options(self):
        for options in [
            {"allow_legacy_ca": "false"},
            {"timeout_seconds": 0},
            {"tls_server_name": "host/path"},
            {"indexer_url": None},
        ]:
            with self.subTest(options=options), self.assertRaises(ConfigError):
                Config(
                    **{
                        "indexer_url": "https://localhost",
                        "username": "reader",
                        "password": "test-password",
                        **options,
                    }
                )

    def test_loads_private_config_and_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            data = {
                "indexer_url": "https://localhost:9200",
                "username": "reader",
                "password": "test-password",
            }
            path.write_text(json.dumps(data))
            path.chmod(0o600)
            self.assertEqual(load_config(path).username, "reader")
            data["unexpected"] = True
            path.write_text(json.dumps(data))
            with self.assertRaises(ConfigError):
                load_config(path)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions")
    def test_rejects_shared_credential_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}")
            path.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "chmod 600"):
                load_config(path)
