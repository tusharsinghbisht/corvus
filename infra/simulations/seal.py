"""Privately seal a verified dataset using the existing host backup key. Run as root."""

import argparse
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seal(root):
    if os.geteuid() != 0:
        raise ValueError("Use sudo on the authorized VM")
    key = Path("/home/ubuntu/.config/corvus/backup-key")
    if key.is_symlink() or key.stat().st_mode & 0o077:
        raise ValueError("Unsafe backup key permissions")
    cipher = Fernet(key.read_bytes().strip())
    paths = []
    for directory in ("definitions", "ground-truth", "inputs", "evidence", "native/verified"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_symlink():
                raise ValueError("Dataset symlink refused")
            if path.is_file() and not path.name.endswith((".partial", ".private.log")):
                paths.append(path)
    if not paths or sum(path.stat().st_size for path in paths) > 256 * 1024 * 1024:
        raise ValueError("Unencrypted dataset bound exceeded")
    manifest = {
        "format_version": 1,
        "files": {
            str(path.relative_to(root)): {"bytes": path.stat().st_size, "sha256": sha(path)}
            for path in paths
        },
        "privacy": "Private real telemetry; ground-truth annotations are separate from replay inputs. Do not upload or send to models without selected-input approval.",
    }
    raw = json.dumps(manifest, sort_keys=True, indent=2).encode()
    temporary = root / (".sealing-" + uuid4().hex + ".tar.gz")
    target = root.parent / (root.name + ".tar.gz.fernet")
    if target.exists():
        raise ValueError("Refusing to overwrite an existing sealed dataset")
    os.umask(0o077)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for path in paths:
                archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
            info = tarfile.TarInfo("SHA256MANIFEST.json")
            info.size = len(raw)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(raw))
        if temporary.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Compressed dataset bound exceeded")
        encrypted = cipher.encrypt(temporary.read_bytes())
        # Authenticate the envelope and recheck every decrypted member before publishing.
        with tarfile.open(fileobj=io.BytesIO(cipher.decrypt(encrypted)), mode="r:gz") as archive:
            decoded = json.load(archive.extractfile("SHA256MANIFEST.json"))
            for name, binding in decoded["files"].items():
                member = archive.getmember(name)
                if not member.isfile() or member.size != binding["bytes"]:
                    raise ValueError("Archive member mismatch")
                data = archive.extractfile(member).read()
                if hashlib.sha256(data).hexdigest() != binding["sha256"]:
                    raise ValueError("Sealed dataset checksum mismatch")
        with target.open("xb") as file:
            file.write(encrypted)
            file.flush()
            os.fsync(file.fileno())
        (root / "SHA256MANIFEST.json").write_bytes(raw)
        (root / "SHA256MANIFEST.json").chmod(0o600)
        print(
            json.dumps(
                {
                    "sealed_files": len(paths),
                    "encrypted_bytes": len(encrypted),
                    "sha256": hashlib.sha256(encrypted).hexdigest(),
                    "authenticated_decrypt_and_all_member_checksums": "passed",
                }
            )
        )
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    seal(parser.parse_args().directory)
