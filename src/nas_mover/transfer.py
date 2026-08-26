from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Literal

from .models import PlannedMove

Verification = Literal["size", "sha256"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_move(move: PlannedMove, *, verify: Verification = "size") -> None:
    source, destination = move.source_path, move.destination_path
    if not source.is_file():
        raise RuntimeError(f"Source vanished: {source}")
    if destination.exists():
        raise RuntimeError(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    temp = destination.with_name(f".nas-mover.{destination.name}.{os.getpid()}.partial")
    try:
        shutil.copy2(source, temp)
        after, copied = source.stat(), temp.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"Source changed during copy: {source}")
        if copied.st_size != after.st_size:
            raise RuntimeError(f"Destination size verification failed: {source}")
        if verify == "sha256" and _sha256(source) != _sha256(temp):
            raise RuntimeError(f"SHA-256 verification failed: {source}")
        if verify not in {"size", "sha256"}:
            raise ValueError(f"Unknown verification mode: {verify}")
        os.replace(temp, destination)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(destination.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        source.unlink()
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise
