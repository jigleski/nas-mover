from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sandbox:
    root: Path

    def __post_init__(self) -> None:
        resolved = self.root.expanduser().resolve()
        if resolved == Path(resolved.anchor):
            raise ValueError("Sandbox cannot be a filesystem root")
        if resolved == Path.cwd().resolve():
            raise ValueError("Sandbox cannot be the current working directory")
        object.__setattr__(self, "root", resolved)

    def path(self, relative: Path) -> Path:
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"Path escapes sandbox: {relative}")
        return candidate

    def create_fixture(self, relative: Path, content: bytes) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def remove_fixture(self, relative: Path) -> None:
        target = self.path(relative)
        if target.is_file() or target.is_symlink():
            target.unlink()

    def fixture_paths(self, count: int = 6) -> list[Path]:
        if count < 1:
            raise ValueError("Fixture count must be positive")
        return [Path("source") / f"test-{index}.bin" for index in range(1, count + 1)]

    def create_fixtures(self, count: int = 6) -> list[Path]:
        fixtures = self.fixture_paths(count)
        for index, relative in enumerate(fixtures, start=1):
            self.create_fixture(relative, f"nas-mover test fixture {index}\n".encode())
        return fixtures

    def remove_fixtures(self, fixtures: list[Path]) -> None:
        for relative in fixtures:
            self.remove_fixture(relative)
