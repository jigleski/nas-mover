from pathlib import Path
from types import SimpleNamespace

import pytest

from nas_mover import Branch, PlannedMove
from nas_mover.cli import run
from nas_mover.config import MoverConfig, parse_size
from nas_mover.discovery import (
    Pool,
    backing_source,
    discover_branches,
    parse_fstab,
    require_mount,
    rotational_for_path,
    stat_branch,
)
from nas_mover.sandbox import Sandbox


def test_config_uses_production_defaults_and_validates() -> None:
    config = MoverConfig()
    config.validate()
    assert (config.watermark_percent, config.tolerance_percent) == (80.0, 2.0)
    assert parse_size("20G") == 20 * 1024**3


def test_config_rejects_unsafe_values() -> None:
    with pytest.raises(ValueError, match="watermark"):
        MoverConfig(watermark_percent=101).validate()
    with pytest.raises(ValueError, match="verification"):
        MoverConfig(verification="md5").validate()
    with pytest.raises(ValueError, match="tolerance"):
        MoverConfig(tolerance_percent=-1).validate()
    with pytest.raises(ValueError, match="policy"):
        MoverConfig(policy="bogus").validate()  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="file_age"):
        MoverConfig(min_file_age_hours=-1).validate()
    with pytest.raises(ValueError, match="extra_free"):
        MoverConfig(extra_free_percent=-1).validate()


def test_sandbox_rejects_root_and_escape_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="filesystem root"):
        Sandbox(Path(tmp_path.anchor))
    sandbox = Sandbox(tmp_path / "sandbox")
    with pytest.raises(ValueError, match="escapes"):
        sandbox.path(Path("..") / "outside")


def test_sandbox_creates_and_removes_only_named_fixtures(tmp_path: Path) -> None:
    sandbox = Sandbox(tmp_path / "sandbox")
    fixtures = sandbox.create_fixtures(2)
    keep = sandbox.create_fixture(Path("keep.txt"), b"keep")
    assert all(sandbox.path(relative).is_file() for relative in fixtures)
    sandbox.remove_fixtures(fixtures)
    assert not sandbox.path(fixtures[0]).exists()
    assert keep.exists()


def test_parse_fstab_selects_mergerfs_and_reads_reserve(tmp_path: Path) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text(
        "# ignored\n"
        "/ssd1:/ssd2:/hdd /pool fuse.mergerfs defaults,minfreespace=20G 0 0\n"
    )
    pool = parse_fstab(fstab, Path("/pool"))
    assert pool == Pool(
        Path("/pool"), [Path("/ssd1"), Path("/ssd2"), Path("/hdd")],
        {"defaults": True, "minfreespace": "20G"}, 20 * 1024**3,
    )


def test_parse_fstab_rejects_missing_or_ambiguous_pool(tmp_path: Path) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text("/dev/sda /data ext4 defaults 0 0\n")
    with pytest.raises(RuntimeError, match="No matching"):
        parse_fstab(fstab)
    fstab.write_text(
        "/a:/b /one fuse.mergerfs defaults 0 0\n"
        "/c:/d /two fuse.mergerfs defaults 0 0\n"
    )
    with pytest.raises(RuntimeError, match="More than one"):
        parse_fstab(fstab, None)


def test_discovery_checks_mounts_devices_and_capacity(tmp_path: Path) -> None:
    def runner(*args, **kwargs):
        command = args[0]
        if command[0] == "mountpoint":
            return SimpleNamespace(returncode=0, stdout="")
        if command[0] == "findmnt":
            device = "/dev/ssd" if command[-1].endswith("ssd") else "/dev/hdd"
            return SimpleNamespace(returncode=0, stdout=f"{device}\n")
        device_type = "0" if command[-1] == "/dev/ssd" else "1"
        return SimpleNamespace(returncode=0, stdout=f"{device_type}\n")

    pool = Pool(tmp_path, [tmp_path / "ssd", tmp_path / "hdd"], {}, 0)
    info = SimpleNamespace(f_frsize=10, f_bsize=10, f_blocks=100, f_bavail=40, f_bfree=20)
    import nas_mover.discovery as discovery
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(discovery.os, "statvfs", lambda path: info, raising=False)
    try:
        branches = discover_branches(pool, runner)
    finally:
        monkeypatch.undo()
    assert [branch.rotational for branch in branches] == [False, True]
    assert branches[0].total_bytes == 1000


def test_discovery_rejects_mount_and_device_errors(tmp_path: Path) -> None:
    failed = lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="")
    with pytest.raises(RuntimeError, match="not mounted"):
        require_mount(tmp_path, failed)
    blank = lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="")
    with pytest.raises(RuntimeError, match="backing device"):
        backing_source(tmp_path, blank)
    invalid = lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="2")
    with pytest.raises(RuntimeError, match="rotational"):
        rotational_for_path(tmp_path, invalid)


def test_cli_is_dry_run_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text("/ssd1:/ssd2:/hdd /pool fuse.mergerfs defaults 0 0\n")
    branches = [
        Branch(tmp_path / "ssd1", 0, False, 100, 10, 90),
        Branch(tmp_path / "ssd2", 1, False, 100, 20, 80),
        Branch(tmp_path / "hdd", 2, True, 100, 100, 0),
    ]
    move = PlannedMove(branches[0], branches[2], Path("file"), 1, 0, 0, "test")
    monkeypatch.setattr("nas_mover.cli.discover_branches", lambda pool: branches)
    monkeypatch.setattr("nas_mover.cli.plan_moves", lambda *args, **kwargs: [move])
    execute = SimpleNamespace(called=False)
    monkeypatch.setattr("nas_mover.cli.execute_move", lambda *args, **kwargs: setattr(execute, "called", True))

    assert run(["--fstab", str(fstab), "--mount", "/pool"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert not execute.called

    assert run(["--live", "--fstab", str(fstab), "--mount", "/pool"]) == 0
    assert execute.called
