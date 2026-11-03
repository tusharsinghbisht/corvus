#!/usr/bin/env python3
"""Install host-only backup configuration. No secrets are printed or replaced."""

import os
import shutil
import subprocess
from pathlib import Path

from backup import Paths, status
from cryptography.fernet import Fernet


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the authorized VM')
    paths = Paths()
    root = Path(__file__).resolve().parent.parent
    if root != Path('/opt/corvus/app') or not (paths.app / 'server.json').is_file():
        raise SystemExit('Use the canonical VM checkout and existing app configuration')
    os.umask(0o077)
    paths.archives.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths.archives.chmod(0o700)
    if not paths.key.exists():
        fd = os.open(paths.key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(Fernet.generate_key() + b'\n')
            file.flush()
            os.fsync(file.fileno())
    if paths.key.is_symlink() or paths.key.stat().st_mode & 0o077:
        raise SystemExit('Inspect unsafe backup key permissions; existing key left unchanged')
    paths.status.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    paths.status.parent.chmod(0o755)
    status(paths)
    env = paths.app / 'deploy.env'
    lines = env.read_text().splitlines()
    indices = [index for index, line in enumerate(lines) if line.startswith('COMPOSE_FILE=')]
    if len(indices) > 1: raise SystemExit('Inspect duplicate COMPOSE_FILE configuration')
    value = lines[indices[0]].split('=',1)[1] if indices else 'compose.yaml'
    entries = value.split(':')
    if any(entry not in ('compose.yaml','compose.analyst.yaml','compose.backups.yaml') for entry in entries):
        raise SystemExit('Inspect nonstandard Compose overrides before enabling backup status')
    if 'compose.backups.yaml' not in entries: entries.append('compose.backups.yaml')
    line = 'COMPOSE_FILE=' + ':'.join(entries)
    if indices: lines[indices[0]] = line
    else: lines.append(line)
    # Preserve ownership; no model credential or server configuration is changed.
    env.write_text('\n'.join(lines) + '\n')
    env.chmod(0o600)
    for name in ('corvus-backup.service','corvus-backup.timer'):
        shutil.copyfile(root / 'infra/systemd' / name, Path('/etc/systemd/system') / name)
        (Path('/etc/systemd/system') / name).chmod(0o644)
    subprocess.run(['systemctl','daemon-reload'], check=True)
    print('Private backup key retained outside Git; host units installed. No app Docker socket mount.')
    print('Run systemctl start corvus-backup.service, inspect success, then enable --now corvus-backup.timer.')


if __name__ == '__main__':
    main()
