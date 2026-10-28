import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra/wazuh/prune-archives.py"
SPEC = importlib.util.spec_from_file_location("archive_retention", SCRIPT)
RETENTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETENTION)


class ArchiveRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "archives"
        self.month = self.root / "2026" / "Jan"
        self.month.mkdir(parents=True)
        self.now = datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp()

    def make_file(self, name, age_hours=96):
        path = self.month / name
        path.write_text("test data")
        modified = self.now - age_hours * 3600
        os.utime(path, (modified, modified))
        return path

    def test_selects_only_expired_recognized_files(self):
        old = self.make_file("ossec-archive-06.json.gz")
        checksum = self.make_file("ossec-archive-06.json.sum")
        self.make_file("ossec-archive-09.json", age_hours=24)
        self.make_file("unexpected.json.gz")
        self.make_file("ossec-alerts-06.json.gz")
        self.assertEqual(RETENTION.expired_files(self.root, self.now), sorted([old, checksum]))
        self.assertTrue(old.exists(), "Discovery must not delete files")

    def test_skips_active_file_even_when_it_is_an_old_hardlink(self):
        active = self.make_file("ossec-archive-06.json")
        os.link(active, self.root / "archives.json")
        self.assertEqual(RETENTION.expired_files(self.root, self.now), [])

    def test_skips_current_date_and_invalid_calendar_dates(self):
        self.make_file("ossec-archive-10.json.gz")
        self.make_file("ossec-archive-32.json.gz")
        self.assertEqual(RETENTION.expired_files(self.root, self.now), [])

    def test_skips_symlinks_to_files_and_directories(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        external_file = outside / "ossec-archive-06.json.gz"
        external_file.write_text("must be preserved")
        os.utime(external_file, (self.now - 400000, self.now - 400000))
        (self.month / external_file.name).symlink_to(external_file)
        (self.root / "2025").symlink_to(outside, target_is_directory=True)
        self.assertEqual(RETENTION.expired_files(self.root, self.now), [])
        self.assertTrue(external_file.exists())

    def test_refuses_symlink_archive_root(self):
        link = Path(self.temp.name) / "linked-root"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            RETENTION.expired_files(link, self.now)

    def test_does_not_visit_alerts_sibling(self):
        alerts = self.root.parent / "alerts" / "2026" / "Jan"
        alerts.mkdir(parents=True)
        alert = alerts / "ossec-archive-06.json.gz"
        alert.write_text("must be preserved")
        os.utime(alert, (self.now - 400000, self.now - 400000))
        self.assertEqual(RETENTION.expired_files(self.root, self.now), [])
        self.assertTrue(alert.exists())


if __name__ == "__main__":
    unittest.main()
