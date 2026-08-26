import os
import uuid
from pathlib import Path

import pytest

from nas_mover import Branch, PlannedMove, execute_move


@pytest.mark.integration
def test_live_sandbox_move() -> None:
    sandbox_value = os.environ.get("NAS_MOVER_TEST_SANDBOX")
    if not sandbox_value:
        pytest.skip("Set NAS_MOVER_TEST_SANDBOX to run live sandbox tests")

    sandbox = Path(sandbox_value).resolve()
    if sandbox == Path(sandbox.anchor) or sandbox == Path.cwd().resolve():
        pytest.fail("Refusing an unsafe or repository-root integration sandbox")
    source_root = (sandbox / "source").resolve()
    destination_root = (sandbox / "destination").resolve()
    if not source_root.is_relative_to(sandbox) or not destination_root.is_relative_to(sandbox):
        pytest.fail("Integration branch paths must remain inside the sandbox")
    sandbox.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(exist_ok=True)
    destination_root.mkdir(exist_ok=True)
    source = source_root / f"fixture-{uuid.uuid4().hex}.bin"
    source.write_bytes(b"sandbox only")

    move = PlannedMove(
        Branch(source_root, 0, False, 100, 90, 10),
        Branch(destination_root, 1, True, 100, 100, 0),
        source.relative_to(source_root), source.stat().st_size,
        source.stat().st_atime, source.stat().st_mtime, "integration",
    )
    execute_move(move, verify="sha256")
    assert (destination_root / "fixture.bin").read_bytes() == b"sandbox only"
    assert not source.exists()
