#!/usr/bin/env python3
"""Prune closed Wazuh archive files after 72h; dry-run unless --apply is given.

Only the archive subtree of the fixed lab Docker volume is eligible. Alert logs,
active archive files, symlinks, and unexpected filenames are never selected.
Indexed archive retention is configured separately through OpenSearch ISM.
"""

import argparse
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

VOLUME_NAME = "single-node_wazuh_logs"
RETENTION_SECONDS = 3 * 24 * 60 * 60
MONTHS = dict(
    zip(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        range(1, 13),
    )
)
ARCHIVE_NAME = re.compile(r"ossec-archive-(\d{2})\.(?:json|log)(?:\.gz)?(?:\.sum)?")


def expired_files(root: Path, now: float):
    """Return eligible closed files without changing the filesystem."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Archive root must be an existing, non-symlink directory")
    active_inodes = set()
    for name in ("archives.json", "archives.log"):
        try:
            info = (root / name).stat()
            active_inodes.add((info.st_dev, info.st_ino))
        except FileNotFoundError:
            pass

    today = datetime.fromtimestamp(now, timezone.utc).date()
    selected = []
    for year in root.iterdir():
        if year.is_symlink() or not year.is_dir() or not re.fullmatch(r"\d{4}", year.name):
            continue
        for month in year.iterdir():
            if month.is_symlink() or not month.is_dir() or month.name not in MONTHS:
                continue
            for path in month.iterdir():
                match = ARCHIVE_NAME.fullmatch(path.name)
                if not match or path.is_symlink() or not path.is_file():
                    continue
                try:
                    file_date = datetime(int(year.name), MONTHS[month.name], int(match[1])).date()
                    info = path.stat()
                except (ValueError, FileNotFoundError):
                    continue
                if file_date >= today or (info.st_dev, info.st_ino) in active_inodes:
                    continue
                if info.st_mtime < now - RETENTION_SECONDS:
                    selected.append(path)
    return sorted(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete eligible files")
    args = parser.parse_args()
    result = subprocess.run(
        ["/usr/bin/docker", "volume", "inspect", VOLUME_NAME],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    volumes = json.loads(result.stdout)
    if len(volumes) != 1 or volumes[0].get("Name") != VOLUME_NAME:
        raise RuntimeError("Unexpected Docker volume response")
    root = Path(volumes[0]["Mountpoint"]) / "archives"
    now = time.time()
    candidates = expired_files(root, now)
    total_bytes = 0
    processed = 0
    for path in candidates:
        # Recheck age and active-file identity immediately before deletion.
        if path.is_symlink():
            continue
        try:
            info = path.stat()
            active = []
            for name in ("archives.json", "archives.log"):
                try:
                    active_info = (root / name).stat()
                    active.append((active_info.st_dev, active_info.st_ino))
                except FileNotFoundError:
                    pass
            if info.st_mtime >= now - RETENTION_SECONDS or (info.st_dev, info.st_ino) in active:
                continue
            if args.apply:
                path.unlink()
            total_bytes += info.st_size
            processed += 1
        except FileNotFoundError:
            continue
    mode = "deleted" if args.apply else "would_delete"
    print(
        json.dumps({"mode": mode, "files": processed, "bytes": total_bytes, "retention_hours": 72})
    )
    usage = shutil.disk_usage(root)
    if usage.used / usage.total >= 0.8:
        print("WARNING: archive filesystem usage is >=80%; investigate storage growth.")


if __name__ == "__main__":
    main()
