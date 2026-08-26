from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import parse_size
from .models import Branch


@dataclass(frozen=True)
class Pool:
    mountpoint: Path
    branches: list[Path]
    options: dict[str, str | bool]
    min_free_bytes: int


def parse_fstab(path: Path, mount_override: Path | None = None) -> Pool:
    entries: list[tuple[str, str, str]] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fields = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(fields) >= 4 and fields[2] == "fuse.mergerfs":
            entries.append((fields[0], fields[1], fields[3]))
    if mount_override is not None:
        entries = [entry for entry in entries if Path(entry[1]) == mount_override]
    if not entries:
        raise RuntimeError("No matching fuse.mergerfs entry found in fstab")
    if len(entries) != 1:
        raise RuntimeError("More than one matching mergerfs entry exists")
    source, mountpoint, raw_options = entries[0]
    options: dict[str, str | bool] = {}
    for option in raw_options.split(","):
        key, separator, value = option.partition("=")
        options[key] = value if separator else True
    return Pool(
        Path(mountpoint),
        [Path(branch) for branch in source.split(":")],
        options,
        parse_size(str(options["minfreespace"])) if "minfreespace" in options else 0,
    )


def require_mount(path: Path, runner=subprocess.run) -> None:
    result = runner(["mountpoint", "-q", str(path)], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Required filesystem is not mounted: {path}")


def backing_source(path: Path, runner=subprocess.run) -> str:
    result = runner(
        ["findmnt", "-n", "-o", "SOURCE", "--target", str(path)],
        check=True, capture_output=True, text=True,
    )
    source = re.sub(r"\[.*\]$", "", result.stdout.strip())
    if not source:
        raise RuntimeError(f"Could not determine backing device for {path}")
    return source


def rotational_for_path(path: Path, runner=subprocess.run) -> bool:
    source = backing_source(path, runner)
    result = runner(
        ["lsblk", "-dn", "-o", "ROTA", source],
        check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if value not in {"0", "1"}:
        raise RuntimeError(f"Could not determine rotational status for {path}: {value!r}")
    return value == "1"


def stat_branch(path: Path, order: int, runner=subprocess.run) -> Branch:
    info = os.statvfs(path)
    block_size = info.f_frsize or info.f_bsize
    return Branch(
        path, order, rotational_for_path(path, runner),
        info.f_blocks * block_size,
        info.f_bavail * block_size,
        (info.f_blocks - info.f_bfree) * block_size,
    )


def discover_branches(pool: Pool, runner=subprocess.run) -> list[Branch]:
    require_mount(pool.mountpoint, runner)
    branches: list[Branch] = []
    for order, path in enumerate(pool.branches):
        require_mount(path, runner)
        branches.append(stat_branch(path, order, runner))
    return branches
