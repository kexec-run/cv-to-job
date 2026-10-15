"""Verified, non-overwriting directory copy for private backups and restoration.

Run with `uv run python -m cv_job.workspace_copy --source PATH --destination PATH`.
No files are removed, including staging data left by a failed verification.
"""

import argparse
import hashlib
import os
import shutil
import stat
from pathlib import Path


def manifest(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError("workspace contains a symlink or special file; review it before copying")
        digest = None
        if stat.S_ISREG(mode):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result[str(path.relative_to(root))] = (stat.S_IMODE(mode), stat.S_ISDIR(mode), digest)
    return result


def copy_verified(source: Path, destination: Path) -> None:
    source = source.expanduser().absolute()
    destination = destination.expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be an existing directory, not a symlink")
    # Resolve parent paths but never resolve away a conflicting destination symlink.
    source = source.resolve()
    destination = destination.parent.resolve(strict=True) / destination.name
    staging = destination.with_name(destination.name + ".copying")
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("source and destination must be separate, non-nested directories")
    for path in (destination, staging):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"refusing existing destination or staging path: {path}")
    before = manifest(source)
    previous_umask = os.umask(0o077)
    try:
        # Keep the copy private while copying; restore each child entry's source mode.
        staging.mkdir(mode=0o700)
        for child in source.iterdir():
            if child.is_dir():
                shutil.copytree(child, staging / child.name, symlinks=True)
            else:
                shutil.copy2(child, staging / child.name, follow_symlinks=False)
        if before != manifest(staging) or before != manifest(source):
            raise ValueError("copy verification failed or source changed; staging copy retained")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("destination appeared during copy; staging copy retained")
        staging.rename(destination)
    finally:
        os.umask(previous_umask)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        copy_verified(args.source, args.destination)
    except (OSError, ValueError):
        # No arbitrary filenames/content in errors: a workspace may contain credentials.
        parser.exit(1, "error: copy refused or verification failed; preserve any .copying directory and inspect paths\n")
    print("verified copy complete; source unchanged; destination root is owner-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
