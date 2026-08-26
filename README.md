# nas-mover

`nas-mover` is a Linux command-line tool for moving files between tiers in a
mergerfs pool. It is intended for a NAS with fast SSD landing/cache branches
and larger HDD data branches.

The mover does not replace mergerfs and does not run SnapRAID. mergerfs still
provides the unified mount and its normal file-placement behavior. This tool
looks at the individual branches, plans selected moves, and performs them only
after a copy and verification succeed.

## How It Works

### Mergerfs terms

- A **branch** is one directory or mounted filesystem supplied to mergerfs.
- The **pool mountpoint** is the unified directory users access, such as
  `/mnt/nas/data`.
- A **policy** decides which eligible branch receives a destination file.
- `minfreespace` reserves space on a branch; this mover honors that value from
  fstab.
- The mover uses `findmnt` and `lsblk` to identify whether each branch is SSD
  (`ROTA=0`) or HDD (`ROTA=1`).

### Planning behavior

The planner works in two phases:

1. If one SSD is above the watermark and another is materially below it, move
   cold files from the fuller SSD to the less-full SSD.
2. Once every SSD is within the configured tolerance of the watermark, move
   excess SSD files to eligible HDD branches.

The production defaults are:

| Setting | Default |
| --- | --- |
| SSD watermark | `80%` |
| Watermark tolerance | `2%` |
| HDD destination policy | `eplfs` |
| Verification | Size and source stability |
| Lock file | `/run/lock/nas-mover.lock` |

`eplfs` means “existing path, least free space.” The destination must have the
same parent directory and enough free space after honoring `minfreespace`.

### Live move safety

For each planned file, live mode:

1. Refuses a missing source or existing destination.
2. Copies to a hidden temporary file in the destination directory.
3. Confirms the source size and modification time did not change.
4. Verifies destination size, or SHA-256 when the integration harness requests
   it.
5. Atomically renames the temporary file into place.
6. Flushes destination directory metadata on POSIX systems.
7. Deletes the source only after all previous steps succeed.

Normal `nas-mover` execution is dry-run by default. `--live` is required to
change files.

## This NAS

The validated NAS configuration uses `/mnt/nas/data` as the mergerfs pool:

```text
/mnt/nas/ssd1-data/data
/mnt/nas/ssd2-data/data
/mnt/nas/hdd1-data/data
/mnt/nas/hdd3-data/data
/mnt/nas/hdd4-data/data
/mnt/nas/hdd6-data/data
```

The parity filesystems are not mergerfs data branches and are intentionally
excluded. The configuration also specifies `minfreespace=20G`.

Verify the live configuration before using this tool:

```bash
sudo grep -nE 'fuse\.mergerfs|/mnt/nas' /etc/fstab
findmnt -t fuse.mergerfs
```

The program reads `/etc/fstab` by default and checks that the selected pool and
every branch are mounted. If fstab contains exactly one mergerfs entry, its
mountpoint is selected automatically. If there are multiple entries, use
`mount_override` in the config or `--mount` to select one explicitly. The
program does not mount, unlock, or repair filesystems.

## Install On The NAS

The current development branch is `initial-setup`. Install it in an isolated
virtual environment:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

sudo mkdir -p /opt/nas-mover
sudo chown "$USER:$USER" /opt/nas-mover
git clone --branch initial-setup https://github.com/jigleski/nas-mover.git /opt/nas-mover

cd /opt/nas-mover
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

### Host configuration

Copy [config.example.toml](config.example.toml) to `/etc/nas-mover/config.toml`
and edit the host-specific values. The file is TOML, so lines beginning with
`#` are comments. Paths, percentages, policy, age filtering, reserve space,
and verification mode are all documented there. The loader rejects unknown
keys and invalid enum values.

```bash
sudo install -d -m 0755 /etc/nas-mover
sudo cp config.example.toml /etc/nas-mover/config.toml
sudoedit /etc/nas-mover/config.toml
```

Use it explicitly. With one mergerfs pool, the mountpoint is auto-detected:

```bash
sudo /opt/nas-mover/.venv/bin/nas-mover \
  --config /etc/nas-mover/config.toml
```

For multiple mergerfs pools, set `mount_override` in the config or select one
for a single run:

```bash
sudo /opt/nas-mover/.venv/bin/nas-mover \
  --config /etc/nas-mover/config.toml \
  --mount /mnt/nas/data
```

CLI flags such as `--fstab`, `--mount`, `--scope`, and `--lock` override the
file for a single run. Keep test-only overrides out of the production config.

For later updates:

```bash
cd /opt/nas-mover
source .venv/bin/activate
git pull --ff-only origin initial-setup
python -m pip install -e .
```

## Test The NAS Integration

Run the complete local suite on the NAS first:

```bash
cd /opt/nas-mover
source .venv/bin/activate
python -m pytest
```

The suite uses real temporary files for transfer behavior and mocks Linux
commands in unit tests. The opt-in live test command below exercises the real
mounted mergerfs pool.

### One-command live test

Use a dedicated relative directory on every mergerfs data branch. The tested
NAS workflow uses `mover-test/source`:

```bash
sudo /opt/nas-mover/.venv/bin/nas-mover-test-suite \
  --config /etc/nas-mover/config.toml \
  --scope mover-test/source \
  --live
```

This command:

- Runs the full pytest suite.
- Discovers the real fstab pool, mounts, branches, and SSD/HDD types.
- Creates six named fixture files only in the scoped test directory on the
  first SSD branch.
- Plans only files under that relative scope.
- Prints the six planned moves.
- With `--live`, copies, verifies, hashes, and deletes the fixtures.
- Cleans the named fixture files from every branch even if verification fails.

The harness refuses to overwrite existing `test-*.bin` fixtures. Do not use a
scope containing production files. The `--live` flag is intentionally required.
The harness uses a zero watermark only for these six controlled fixtures;
that does not change the production default of `80%`.

To run the same setup and scoped dry run without moving files, omit `--live`:

```bash
sudo /opt/nas-mover/.venv/bin/nas-mover-test-suite \
  --scope mover-test/source
```

## Normal Operation

Always start with a dry run and review every proposed path:

```bash
sudo /opt/nas-mover/.venv/bin/nas-mover \
  --fstab /etc/fstab
```

For a scoped test directory, add `--scope mover-test/source`. The `--scope`
value is relative to every mergerfs branch; absolute paths and `..` traversal
are rejected.

Do not use `--watermark 0 --tolerance 0` for normal operation. Those overrides
exist only to force a controlled test plan with tiny fixture files.

This project does not currently install a systemd service or timer. Scheduling
should be added only after the production dry-run output, logging, alerting,
and SnapRAID sequencing have been designed and reviewed.

## Development And Coverage

The source uses a `src/` layout:

```text
src/nas_mover/models.py       domain data structures
src/nas_mover/policy.py       destination policies
src/nas_mover/planner.py      scanning and move planning
src/nas_mover/transfer.py     copy, verify, replace, delete
src/nas_mover/discovery.py    Linux fstab and device discovery
src/nas_mover/locking.py      POSIX process lock
src/nas_mover/config.py       validated defaults and parsing
src/nas_mover/cli.py          dry-run/live mover command
src/nas_mover/test_suite.py   NAS integration harness
```

Run the suite with branch coverage:

```bash
python -m pytest
```

The measured mover logic currently has a 100% statement and branch coverage
gate. The command-entry wrappers are excluded from coverage because they only
delegate into tested functions.
