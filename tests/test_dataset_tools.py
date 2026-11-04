import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra.simulations import prepare
from infra.simulations.build import export
from infra.simulations.seal import sha


class DatasetToolsTests(unittest.TestCase):
    def definition(self, root, *, dependencies=False):
        directory = root / "definitions"
        directory.mkdir()
        (root / "ground-truth").mkdir()
        content = 'atomic_tests:\n  - name: Safe test\n    auto_generated_guid: reviewed-test\n    executor:\n      name: command_prompt\n      command: "whoami #{args}"\n    input_arguments:\n      args:\n        default: /all\n'
        if dependencies:
            content += "    dependencies: [unreviewed]\n"
        path = directory / "T1033.yaml"
        path.write_text(content)
        return {"T1033": ("reviewed-test", hashlib.sha256(path.read_bytes()).hexdigest())}

    def test_preparation_verifies_pin_resolves_only_reviewed_inputs_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(prepare, "TESTS", self.definition(root)):
                campaign = prepare.prepare(root, "test-host", 3)
                self.assertEqual(campaign["tests"][0]["command"], "whoami /all")
                self.assertRegex(campaign["run_id"], r"^CORVUS-ART-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$")
                self.assertEqual(
                    (root / "ground-truth/campaign.json").stat().st_mode & 0o777, 0o600
                )
                with self.assertRaises(FileExistsError):
                    prepare.prepare(root, "test-host")

    def test_changed_definition_or_unapproved_dependencies_are_refused(self):
        for dependencies in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                mapping = self.definition(root, dependencies=dependencies)
                if not dependencies:
                    (root / "definitions/T1033.yaml").write_text("modified")
                with patch.object(prepare, "TESTS", mapping), self.assertRaises(ValueError):
                    prepare.prepare(root, "test-host")
                self.assertFalse((root / "ground-truth/campaign.json").exists())

    def test_campaign_bounds_refuse_scope_expansion(self):
        for rounds in (0, 4):
            with self.assertRaises(ValueError):
                prepare.prepare(Path("/unused"), "test-host", rounds)

    def test_incomplete_or_missing_index_manifest_cannot_become_a_replay_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.gz"
            for rows in (
                [],
                [{"type": "event", "document": {}}],
                [{"type": "manifest", "events": 1, "complete_within_queries": True}],
                [{"type": "manifest", "events": 0, "complete_within_queries": False}],
            ):
                with gzip.open(path, "wt") as file:
                    for row in rows:
                        file.write(json.dumps(row) + "\n")
                with self.assertRaises(ValueError):
                    export(path)

    def test_complete_export_preserves_source_values_and_stable_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.gz"
            document = {"source": {"untrusted": "<script>do not execute</script>"}}
            with gzip.open(path, "wt") as file:
                for row in (
                    {"type": "event", "document": document},
                    {"type": "manifest", "events": 1, "complete_within_queries": True},
                ):
                    file.write(json.dumps(row) + "\n")
            events, manifest = export(path)
            self.assertEqual(events, [document])
            self.assertEqual(manifest["events"], 1)
            self.assertEqual(sha(path), hashlib.sha256(path.read_bytes()).hexdigest())
