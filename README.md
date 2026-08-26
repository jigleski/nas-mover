# nas-mover

Safety-conscious planner and mover for tiered mergerFS storage. The original
host-facing one-shot script remains at `original-oneshot.py`; the testable core
is in `src/nas_mover`.

## Development

Install the package and test dependencies in an isolated environment:

```text
python -m pip install -e ".[test]"
python -m pytest
```

Pytest enables branch coverage and enforces a 90% total threshold. Tests use
`tmp_path` for real file operations. The live integration test is skipped unless
`NAS_MOVER_TEST_SANDBOX` points to a dedicated non-root sandbox directory:

```text
$env:NAS_MOVER_TEST_SANDBOX = "C:\\nas-mover-test-sandbox"
python -m pytest -m integration
```

The integration test creates and deletes only its own fixture beneath that
sandbox. Never point it at a production mount, the repository, or a drive root.
