import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from corvus.cli import main
from corvus.config import Config
from corvus.models import SearchResult


class CLITests(unittest.TestCase):
    @patch("corvus.cli.Transport")
    @patch("corvus.cli.load_config")
    @patch("corvus.cli.WazuhAdapter")
    def test_collect_writes_a_private_bundle_without_credentials(self, adapter, config, transport):
        config.return_value = Config("https://localhost:19200", "reader", "test-password")
        transport.return_value.audit = []
        adapter.return_value.get_alert.return_value = {
            "reference": {"backend": "test", "index": "test-index", "id": "alert"},
            "context": {"timestamp": "2020-01-01T12:00:00Z", "agent_id": "001"},
            "source": {"message": "test evidence"},
        }
        adapter.return_value.search_events.return_value = SearchResult([], {}, 0, "eq")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.json"
            console = io.StringIO()
            with redirect_stdout(console):
                status = main(
                    ["collect", "--index", "test-index", "--id", "alert", "--out", str(output)]
                )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.read_text())["status"], "collected")
            self.assertNotIn("test-password", output.read_text())
            self.assertNotIn("test-password", console.getvalue())

    @patch("corvus.cli.Transport")
    @patch("corvus.cli.load_config")
    @patch("corvus.cli.WazuhAdapter")
    def test_truncated_search_has_distinct_exit_status(self, adapter, config, transport):
        config.return_value = Config("https://localhost:19200", "reader", "test-password")
        adapter.return_value.list_alerts.return_value = SearchResult(
            [], {}, 10, "eq", truncated=True
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["alerts", "--agent-id", "001"]), 2)

    def test_invalid_lookback_is_rejected_before_connecting(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["alerts", "--agent-id", "001", "--since-minutes", "0"]), 1)
