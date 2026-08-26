from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .policy import Policy, SUPPORTED_POLICIES


@dataclass(frozen=True)
class MoverConfig:
    watermark_percent: float = 80.0
    tolerance_percent: float = 2.0
    policy: Policy = "eplfs"
    min_file_age_hours: float = 0.0
    extra_free_percent: float = 0.0
    verification: str = "size"
    fstab_path: Path = Path("/etc/fstab")
    mount_override: Path | None = Path("/mnt/nas/data")
    lock_path: Path = Path("/run/lock/nas-mover.lock")

    def validate(self) -> None:
        if not 0 <= self.watermark_percent <= 100:
            raise ValueError("watermark_percent must be between 0 and 100")
        if not 0 <= self.tolerance_percent <= 100:
            raise ValueError("tolerance_percent must be between 0 and 100")
        if self.policy not in SUPPORTED_POLICIES:
            raise ValueError(f"Unsupported mover policy: {self.policy}")
        if self.min_file_age_hours < 0:
            raise ValueError("min_file_age_hours cannot be negative")
        if self.extra_free_percent < 0:
            raise ValueError("extra_free_percent cannot be negative")
        if self.verification not in {"size", "sha256"}:
            raise ValueError("verification must be 'size' or 'sha256'")


def parse_size(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGTPE]?)(?:i?B?)?\s*", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid size: {value}")
    powers = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
    return int(float(match.group(1)) * 1024 ** powers[match.group(2).upper()])
