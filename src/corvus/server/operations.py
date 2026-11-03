"""Authenticated operational readiness. No Docker socket or provider credentials in API."""

from datetime import datetime, timezone
from pathlib import Path

from ..storage import load_json
from ..timeutil import utc

BACKUP_STATUS = Path("/run/corvus/operations/backup-status.json")


def backup_status(path=BACKUP_STATUS):
    try:
        if path.stat().st_size > 8192:
            raise ValueError("Oversized status")
        data = load_json(path)
        # A host-written, sanitized status document, never backup paths or key material.
        safe = {key: data.get(key) is True for key in ("configured", "encrypted", "in_progress")}
        for key in (
            "last_success_at",
            "last_failure_at",
            "last_restore_verified_at",
            "last_attempt_at",
        ):
            if isinstance(data.get(key), str) and len(data[key]) <= 64:
                try:
                    utc(data[key])
                    safe[key] = data[key]
                except ValueError:
                    pass
        for key in ("archive_bytes", "retained_snapshots"):
            if type(data.get(key)) is int and 0 <= data[key] <= 1024**4:
                safe[key] = data[key]
        safe["schedule"] = "Daily, 03:30 UTC (up to 10 minutes randomized delay)"
        allowed_errors = {
            "command_failed",
            "archive_too_large",
            "backup_failed",
            "unsafe_key_permissions",
            "missing_configuration",
            "unsafe_configuration",
            "unsafe_archive",
            "unsafe_archive_member",
            "manifest_invalid",
            "checksum_mismatch",
            "unsupported_schema",
            "restore_database_unavailable",
            "restore_schema_mismatch",
            "restore_count_mismatch",
            "restore_disarm_failed",
            "no_snapshot",
            "invalid_retention",
        }
        safe["last_error"] = (
            data.get("last_error")
            if data.get("last_error") in allowed_errors
            else ("backup_failed" if data.get("last_error") else None)
        )
        return safe
    except (OSError, ValueError, TypeError):
        return {"configured": False, "encrypted": False, "last_error": "status_unavailable"}


def readiness(db, *, status_path=BACKUP_STATUS):
    row = db.execute(
        "SELECT heartbeat_at,analysis_configured FROM worker_runtime WHERE singleton"
    ).fetchone()
    age = (
        None
        if not row["heartbeat_at"]
        else max(0, int((datetime.now(timezone.utc) - row["heartbeat_at"]).total_seconds()))
    )
    backup = backup_status(status_path)

    def recent(field):
        try:
            elapsed = (datetime.now(timezone.utc) - utc(backup[field])).total_seconds()
            return 0 <= elapsed <= 36 * 3600
        except (KeyError, ValueError):
            return False

    backup["recent"] = recent("last_success_at")
    backup["restore_recent"] = recent("last_restore_verified_at")
    if backup.get("in_progress"):
        try:
            if (datetime.now(timezone.utc) - utc(backup["last_attempt_at"])).total_seconds() > 900:
                backup["last_error"] = "backup_interrupted"
        except (KeyError, ValueError):
            backup["last_error"] = "backup_interrupted"
    return {
        "database": "ready",
        "worker": {**row, "heartbeat_age_seconds": age, "ready": age is not None and age < 300},
        "backup": backup,
    }
