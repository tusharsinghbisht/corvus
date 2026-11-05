#!/usr/bin/env python3
"""Host-only encrypted PostgreSQL/config snapshots and isolated restore checks.

Never mounted in the app, never exposes a Docker socket to it, and never starts an
application worker against restored data. Keys and snapshots remain outside Git.
"""

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from cryptography.fernet import Fernet
from psycopg.conninfo import conninfo_to_dict

MAX_ARCHIVE = 128 * 1024 * 1024
CONFIG_FILES = (
    "server.json",
    "database-password",
    "wazuh-ca.pem",
    "login.json",
    "deploy.env",
    "analyst.json",
)
TABLES = ("alerts", "connections", "triage_attempts", "report_reviews", "investigation_steps")
STATUS_FIELDS = {
    "configured",
    "encrypted",
    "last_success_at",
    "last_failure_at",
    "last_restore_verified_at",
    "last_error",
    "archive_bytes",
    "retained_snapshots",
    "schedule",
    "last_attempt_at",
    "in_progress",
}
SNAPSHOT_PATTERN = re.compile(r"corvus-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}\.cvb$")


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    base: Path = Path("/home/ubuntu/.config/corvus")

    @property
    def app(self):
        return self.base / "app"

    @property
    def key(self):
        return self.base / "backup-key"

    @property
    def archives(self):
        return self.base / "backups/encrypted"

    @property
    def status(self):
        return self.app / "operations/backup-status.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def command(args, *, timeout=300, **kwargs):
    try:
        result = subprocess.run(
            args,
            stdout=kwargs.pop("stdout", subprocess.PIPE),
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackupError("command_failed") from exc
    if result.returncode:
        # Subprocess output may contain credentials or COPY data; never print it.
        raise BackupError("command_failed")
    return result.stdout


def cipher(paths):
    if paths.key.is_symlink() or paths.key.stat().st_mode & 0o077:
        raise BackupError("unsafe_key_permissions")
    return Fernet(paths.key.read_bytes().strip())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def status(paths, **changes):
    try:
        previous = json.loads(paths.status.read_text())
    except (OSError, ValueError):
        previous = {}
    value = {key: value for key, value in previous.items() if key in STATUS_FIELDS}
    value.update(
        {
            "configured": True,
            "encrypted": True,
            "schedule": "Daily, 03:30 UTC (up to 10 minutes randomized delay)",
            **changes,
        }
    )
    paths.status.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = paths.status.with_name(".status-" + uuid4().hex)
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o444)
    os.replace(temporary, paths.status)


@contextmanager
def exclusive(paths):
    paths.archives.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (paths.archives / ".lock").open("a") as file:
        os.chmod(file.name, 0o600)
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupError("already_running") from exc
        # Remove only this tool's abandoned private plaintext work directories.
        for path in paths.archives.iterdir():
            if (
                re.fullmatch(r"\.working-[a-z0-9_]{8}", path.name)
                and path.is_dir()
                and not path.is_symlink()
            ):
                shutil.rmtree(path)
        # A killed check can leave an isolated DB; never touch application containers.
        stale = (
            command(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "label=corvus.restore-check=true",
                    "--filter",
                    "name=^/corvus-restore-check-",
                ]
            )
            .decode()
            .splitlines()
        )
        for identifier in stale:
            if re.fullmatch(r"[a-f0-9]{12,64}", identifier):
                command(["docker", "rm", "-f", "-v", identifier])
        yield


def capture_database(paths, destination):
    configuration = json.loads((paths.app / "server.json").read_text())
    networks = json.loads(
        command(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", "corvus-db-1"]
        )
    )
    host = networks["corvus_private"]["IPAddress"]
    info = conninfo_to_dict(configuration["database_url"]) | {
        "host": host,
        "connect_timeout": "10",
        "application_name": "corvus_backup",
    }
    with psycopg.connect(**info, autocommit=True) as db:
        # Block schema migrations, not ingestion. Export one snapshot for dump and counts.
        db.execute("SELECT pg_advisory_lock(hashtext('corvus.schema'))")
        with db.transaction():
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = db.execute("SELECT pg_export_snapshot()").fetchone()[0]
            schema = db.execute("SELECT max(version) FROM schema_versions").fetchone()[0]
            if schema < 4:
                raise BackupError("unsupported_schema")
            counts = {
                table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in TABLES
                if table != "investigation_steps" or schema >= 6
            }
            with destination.open("wb") as output:
                command(
                    [
                        "docker",
                        "exec",
                        "corvus-db-1",
                        "pg_dump",
                        "-U",
                        "corvus",
                        "-d",
                        "corvus",
                        "-Fc",
                        f"--snapshot={snapshot}",
                    ],
                    stdout=output,
                )
    image = (
        command(["docker", "inspect", "--format", "{{.Config.Image}}", "corvus-api-1"])
        .decode()
        .strip()
    )
    return {"schema_version": schema, "counts": counts, "observed_api_image": image}


def pack(paths, dump, metadata):
    files = {"database.dump": dump.read_bytes()}
    for name in CONFIG_FILES:
        path = paths.app / name
        if not path.exists():
            if name == "analyst.json":
                continue
            raise BackupError("missing_configuration")
        if path.is_symlink() or not path.is_file():
            raise BackupError("unsafe_configuration")
        files["config/" + name] = path.read_bytes()
    if sum(map(len, files.values())) > MAX_ARCHIVE - 65536:
        raise BackupError("archive_too_large")
    manifest = {
        "format_version": 1,
        "created_at": now(),
        **metadata,
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        },
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o600
            archive.addfile(member, io.BytesIO(data))
    if output.tell() > MAX_ARCHIVE:
        raise BackupError("archive_too_large")
    return output.getvalue()


def unpack(paths, archive_path):
    if archive_path.is_symlink() or archive_path.stat().st_size > MAX_ARCHIVE * 2 + 4096:
        raise BackupError("unsafe_archive")
    data = cipher(paths).decrypt(archive_path.read_bytes())
    if len(data) > MAX_ARCHIVE:
        raise BackupError("archive_too_large")
    allowed = {"database.dump", "manifest.json", *["config/" + name for name in CONFIG_FILES]}
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive:
            if (
                member.name not in allowed
                or not member.isfile()
                or member.name in files
                or member.size > MAX_ARCHIVE
            ):
                raise BackupError("unsafe_archive_member")
            files[member.name] = archive.extractfile(member).read()
    manifest = json.loads(files.pop("manifest.json"))
    if manifest["format_version"] != 1 or set(files) != set(manifest["files"]):
        raise BackupError("manifest_invalid")
    for name, content in files.items():
        if manifest["files"][name] != {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }:
            raise BackupError("checksum_mismatch")
    return manifest, files


def restore_check(paths, archive_path, *, publish_status=True):
    manifest, files = unpack(paths, archive_path)
    name = "corvus-restore-check-" + uuid4().hex[:8]
    try:
        command(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--memory=512m",
                "--cpus=0.5",
                "--log-driver=none",
                "--label",
                "corvus.restore-check=true",
                "-e",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e",
                "POSTGRES_USER=corvus",
                "-e",
                "POSTGRES_DB=corvus",
                "postgres:17-bookworm",
            ]
        )
        for _ in range(60):
            try:
                command(["docker", "exec", name, "pg_isready", "-U", "corvus"], timeout=5)
                break
            except BackupError:
                time.sleep(1)
        else:
            raise BackupError("restore_database_unavailable")
        command(
            [
                "docker",
                "exec",
                "-i",
                name,
                "pg_restore",
                "-U",
                "corvus",
                "-d",
                "corvus",
                "--exit-on-error",
                "--no-owner",
            ],
            input=files["database.dump"],
        )

        def scalar(sql):
            return (
                command(
                    ["docker", "exec", name, "psql", "-U", "corvus", "-d", "corvus", "-Atc", sql]
                )
                .decode()
                .strip()
            )

        if int(scalar("SELECT max(version) FROM schema_versions")) != manifest["schema_version"]:
            raise BackupError("restore_schema_mismatch")
        for table, count in manifest["counts"].items():
            if table not in TABLES or int(scalar(f"SELECT count(*) FROM {table}")) != count:
                raise BackupError("restore_count_mismatch")
        # Verify the saved server key can decrypt the restored reader credentials.
        server = json.loads(files["config/server.json"])
        reader_cipher = Fernet(server["encryption_key"].encode())
        for token in scalar("SELECT encrypted_password FROM connections").splitlines():
            reader_cipher.decrypt(token.encode())
        # A restored old queue must never replay requests completed after that backup.
        recovery_sql = Path(__file__).with_name("recovery-disarm.sql").read_bytes()
        command(
            [
                "docker",
                "exec",
                "-i",
                name,
                "psql",
                "-U",
                "corvus",
                "-d",
                "corvus",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=recovery_sql,
        )
        if (
            int(
                scalar(
                    "SELECT count(*) FROM triage_attempts WHERE status IN ('pending_collection','collecting','awaiting_approval','queued','requesting')"
                )
            )
            or int(scalar("SELECT count(*) FROM analyst_policies WHERE enabled"))
            or int(scalar("SELECT count(*) FROM sessions"))
        ):
            raise BackupError("restore_disarm_failed")
        if publish_status:
            status(paths, last_restore_verified_at=now(), last_error=None, in_progress=False)
        return manifest
    finally:
        try:
            command(["docker", "rm", "-f", "-v", name], timeout=30)
        except BackupError:
            pass


def snapshots(paths):
    return sorted(
        (
            path
            for path in paths.archives.iterdir()
            if SNAPSHOT_PATTERN.fullmatch(path.name) and path.is_file() and not path.is_symlink()
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def create(paths, *, verify_restore=False, keep=7):
    if not 2 <= keep <= 90:
        raise BackupError("invalid_retention")
    with tempfile.TemporaryDirectory(prefix=".working-", dir=paths.archives) as directory:
        dump = Path(directory) / "database.dump"
        metadata = capture_database(paths, dump)
        if dump.stat().st_size > MAX_ARCHIVE - 65536:
            raise BackupError("archive_too_large")
        plaintext = pack(paths, dump, metadata)
        encrypted = cipher(paths).encrypt(plaintext)
        filename = (
            "corvus-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
            + ".cvb"
        )
        target = paths.archives / filename
        temporary = Path(directory) / "encrypted.cvb"
        with temporary.open("wb") as file:
            file.write(encrypted)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        unpack(paths, temporary)  # Authenticate every member before publishing or pruning.
        if verify_restore:
            restore_check(paths, temporary, publish_status=False)
        os.replace(temporary, target)
        sync_directory(paths.archives)
        for old in snapshots(paths)[:-keep]:
            old.unlink()  # Only this tool's completed encrypted snapshots.
        extra = {"last_restore_verified_at": now()} if verify_restore else {}
        status(
            paths,
            last_success_at=now(),
            last_error=None,
            in_progress=False,
            archive_bytes=len(encrypted),
            retained_snapshots=len(snapshots(paths)),
            **extra,
        )
        return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify-restore"])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--verify-restore", action="store_true")
    parser.add_argument("--keep", type=int, default=7)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run with sudo on the authorized VM")
    paths = Paths()
    os.umask(0o077)
    try:
        with exclusive(paths):
            status(paths, last_attempt_at=now(), in_progress=True)
            if args.action == "create":
                create(paths, verify_restore=args.verify_restore, keep=args.keep)
            else:
                archive = args.archive or (snapshots(paths)[-1] if snapshots(paths) else None)
                if archive is None:
                    raise BackupError("no_snapshot")
                restore_check(paths, archive)
        print(
            "Encrypted backup operation completed; no model calls or live database restore performed"
        )
    except Exception as exc:
        code = str(exc) if isinstance(exc, BackupError) else "backup_failed"
        if code != "already_running":
            try:
                status(paths, last_failure_at=now(), last_error=code, in_progress=False)
            except OSError:
                pass
        print("Backup operation failed: " + code)
        return 75 if code == "already_running" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
