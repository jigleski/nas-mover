from pathlib import Path

import pytest

from nas_mover import Branch, PlannedMove, execute_move


def make_move(tmp_path: Path, content: bytes = b"nas data") -> tuple[PlannedMove, Path, Path]:
    source_root, destination_root = tmp_path / "source", tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    source = source_root / "nested" / "file.bin"
    source.parent.mkdir()
    source.write_bytes(content)
    source_branch = Branch(source_root, 0, False, 1000, 900, 100)
    destination_branch = Branch(destination_root, 1, True, 1000, 1000, 0)
    move = PlannedMove(source_branch, destination_branch, Path("nested/file.bin"), len(content), source.stat().st_atime, source.stat().st_mtime, "test")
    return move, source, destination_root / "nested/file.bin"


def test_execute_move_copies_verifies_and_deletes_source(tmp_path: Path) -> None:
    move, source, destination = make_move(tmp_path)
    execute_move(move, verify="sha256")
    assert not source.exists()
    assert destination.read_bytes() == b"nas data"
    assert not list(destination.parent.glob(".nas-mover.*.partial"))


def test_execute_move_refuses_existing_destination_and_preserves_source(tmp_path: Path) -> None:
    move, source, destination = make_move(tmp_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"existing")
    with pytest.raises(RuntimeError, match="already exists"):
        execute_move(move)
    assert source.exists()
    assert destination.read_bytes() == b"existing"


def test_execute_move_rejects_vanished_source(tmp_path: Path) -> None:
    move, source, _ = make_move(tmp_path)
    source.unlink()
    with pytest.raises(RuntimeError, match="vanished"):
        execute_move(move)


def test_execute_move_removes_bad_temporary_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    move, source, _ = make_move(tmp_path)

    def bad_copy(source_path: Path, destination_path: Path) -> None:
        destination_path.write_bytes(b"wrong!!!")

    monkeypatch.setattr("nas_mover.transfer.shutil.copy2", bad_copy)
    with pytest.raises(RuntimeError, match="SHA-256"):
        execute_move(move, verify="sha256")
    assert source.exists()
    assert not list((tmp_path / "destination" / "nested").glob(".nas-mover.*.partial"))


def test_execute_move_rejects_unknown_verification_mode(tmp_path: Path) -> None:
    move, source, _ = make_move(tmp_path)
    with pytest.raises(ValueError, match="Unknown verification"):
        execute_move(move, verify="crc" )  # type: ignore[arg-type]
    assert source.exists()
