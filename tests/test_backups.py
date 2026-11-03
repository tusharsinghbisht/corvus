import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet, InvalidToken

from infra import backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = backup.Paths(Path(temporary.name))
        self.paths.app.mkdir(mode=0o700)
        self.paths.archives.mkdir(mode=0o700, parents=True)
        self.paths.key.write_bytes(Fernet.generate_key())
        self.paths.key.chmod(0o600)
        self.server_key = Fernet.generate_key()
        for name in backup.CONFIG_FILES:
            (self.paths.app / name).write_text("private-unit-test-secret")
        (self.paths.app / "server.json").write_text(
            json.dumps({"encryption_key": self.server_key.decode()})
        )
        self.dump = self.paths.base / "database.dump"
        self.dump.write_bytes(b"unit-test-custom-dump")
        self.metadata = {"schema_version": 5, "counts": {name: 1 for name in backup.TABLES}}

    def archive(self):
        target = self.paths.archives / "corvus-20261103T010101Z-abcdef12.cvb"
        target.write_bytes(
            backup.cipher(self.paths).encrypt(backup.pack(self.paths, self.dump, self.metadata))
        )
        target.chmod(0o600)
        return target

    def test_authenticated_encrypted_roundtrip_and_no_plaintext_secrets_in_snapshot(self):
        archive = self.archive()
        self.assertNotIn(b"private-unit-test-secret", archive.read_bytes())
        manifest, files = backup.unpack(self.paths, archive)
        self.assertEqual(files["database.dump"], self.dump.read_bytes())
        self.assertEqual(manifest["counts"], self.metadata["counts"])
        self.assertEqual(files["config/server.json"], (self.paths.app / "server.json").read_bytes())
        data = bytearray(archive.read_bytes())
        data[len(data) // 2] ^= 1
        archive.write_bytes(data)
        with self.assertRaises(InvalidToken):
            backup.unpack(self.paths, archive)

    def test_permissions_and_symlinked_configuration_are_refused(self):
        self.paths.key.chmod(0o644)
        with self.assertRaises(backup.BackupError):
            backup.cipher(self.paths)
        self.paths.key.chmod(0o600)
        config = self.paths.app / "analyst.json"
        config.unlink()
        config.symlink_to(self.dump)
        with self.assertRaises(backup.BackupError):
            backup.pack(self.paths, self.dump, self.metadata)

    def test_unsafe_tar_members_and_duplicate_names_are_never_extracted(self):
        for name, symlink, duplicate in (
            ("../../outside", False, False),
            ("database.dump", True, False),
            ("database.dump", False, True),
        ):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as archive:
                member = tarfile.TarInfo(name)
                if symlink:
                    member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                else:
                    member.size = 1
                archive.addfile(member, None if symlink else io.BytesIO(b"x"))
                if duplicate:
                    archive.addfile(member, io.BytesIO(b"x"))
            path = self.paths.archives / "unsafe.cvb"
            path.write_bytes(backup.cipher(self.paths).encrypt(output.getvalue()))
            with self.assertRaises(backup.BackupError):
                backup.unpack(self.paths, path)
        self.assertFalse((self.paths.base.parent / "outside").exists())

    def test_bounds_are_explicit_and_retention_never_deletes_manual_backups(self):
        manual = self.paths.archives / "operator-backup.dump"
        manual.write_bytes(b"leave-alone")

        def capture(paths, destination):
            destination.write_bytes(self.dump.read_bytes())
            return self.metadata

        with (
            patch.object(backup, "capture_database", side_effect=capture),
            patch.object(backup, "restore_check"),
        ):
            for _ in range(3):
                backup.create(self.paths, verify_restore=True, keep=2)
            self.assertEqual(len(backup.snapshots(self.paths)), 2)
            self.assertEqual(manual.read_bytes(), b"leave-alone")
            before = {p.name for p in backup.snapshots(self.paths)}
            with patch.object(
                backup, "restore_check", side_effect=backup.BackupError("restore_count_mismatch")
            ):
                with self.assertRaises(backup.BackupError):
                    backup.create(self.paths, verify_restore=True, keep=2)
            self.assertEqual({p.name for p in backup.snapshots(self.paths)}, before)
        with patch.object(backup, "MAX_ARCHIVE", 10):
            with self.assertRaises(backup.BackupError):
                backup.pack(self.paths, self.dump, self.metadata)

    def test_lock_and_abandoned_work_cleanup_are_scoped_to_this_tool(self):
        work = self.paths.archives / ".working-abcdefgh"
        work.mkdir()
        (work / "database.dump").write_bytes(b"private-stale-work")
        other = self.paths.archives / "operator-work"
        other.mkdir()
        with patch.object(backup, "command", return_value=b""):
            with backup.exclusive(self.paths):
                self.assertFalse(work.exists())
                self.assertTrue(other.exists())
                with self.assertRaises(backup.BackupError):
                    with backup.exclusive(self.paths):
                        pass
        self.assertEqual(os.stat(self.paths.archives / ".lock").st_mode & 0o777, 0o600)

    def test_restore_check_uses_networkless_database_and_disarms_only_that_copy(self):
        token = Fernet(self.server_key).encrypt(b"private-reader-secret")
        calls = []

        def command(args, **kwargs):
            calls.append((args, kwargs))
            if args[-1] == "SELECT encrypted_password FROM connections":
                return token + b"\n"
            if args[-1] == "SELECT max(version) FROM schema_versions":
                return b"5\n"
            for table in backup.TABLES:
                if args[-1] == f"SELECT count(*) FROM {table}":
                    return b"1\n"
            if args[-1].startswith("SELECT count(*)"):
                return b"0\n"
            return b""

        with patch.object(backup, "command", side_effect=command):
            backup.restore_check(self.paths, self.archive())
        run = next(args for args, _ in calls if args[:2] == ["docker", "run"])
        self.assertIn("none", run)
        self.assertIn("--network", run)
        self.assertNotIn("-p", run)
        self.assertNotIn("-v", run)
        self.assertTrue(all("corvus-db-1" not in args for args, _ in calls))
        disarm = next(
            kwargs["input"] for args, kwargs in calls if "psql" in args and "input" in kwargs
        )
        self.assertIn(b"restored_backup_requires_reapproval", disarm)
        self.assertTrue(json.loads(self.paths.status.read_text())["last_restore_verified_at"])
