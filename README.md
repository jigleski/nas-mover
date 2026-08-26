# nas-mover

Safety-conscious planner and mover for tiered mergerFS storage. The implementation
is organized as a testable package in `src/nas_mover`.

The package separates domain models, mergerfs policy selection, move planning,
Linux host discovery, locking, and filesystem transfer. `nas-mover` is
dry-run by default; `--live` is required to apply a plan.

## Development

Install the package and test dependencies in an isolated environment:

```text
python -m pip install -e ".[test]"
python -m pytest
```

Run a Linux host discovery and dry run with the installed command:

```text
nas-mover --fstab /etc/fstab --mount /mnt/nas/data
nas-mover --live --fstab /etc/fstab --mount /mnt/nas/data
```

The live form should only be used after reviewing the preceding dry-run output.

Prepare a dedicated NAS sandbox with six fixture files, then clean up only
those files after testing:

```text
nas-mover-test-fixtures /mnt/nas/ssd1-data/data/mover-test
nas-mover --fstab /etc/fstab --mount /mnt/nas/data
nas-mover --live --fstab /etc/fstab --mount /mnt/nas/data
nas-mover-test-fixtures /mnt/nas/ssd1-data/data/mover-test --cleanup
```

For a production pool containing a test directory, add `--scope mover-test`
to both mover commands. This restricts planning to that relative directory on
each branch:

```text
sudo nas-mover --fstab /etc/fstab --mount /mnt/nas/data --scope mover-test
sudo nas-mover --live --fstab /etc/fstab --mount /mnt/nas/data --scope mover-test
```

Use a dedicated mergerfs test pool for this sequence. The fixture command
refuses filesystem roots and traversal outside its supplied sandbox, and
cleanup removes only its named `test-*.bin` files.

Pytest enables branch coverage and enforces a 90% total threshold. Tests use
`tmp_path` for real file operations. The live integration test is skipped unless
`NAS_MOVER_TEST_SANDBOX` points to a dedicated non-root sandbox directory:

```text
$env:NAS_MOVER_TEST_SANDBOX = "C:\\nas-mover-test-sandbox"
python -m pytest -m integration
```

The integration test creates and deletes only its own fixture beneath that
sandbox. Never point it at a production mount, the repository, or a drive root.
