"""Short, cooperative POSIX transactions beside the configured application log."""

import errno
import math
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Read-only commands can still work on native Windows.
    fcntl = None


class LockBusy(TimeoutError):
    """Another writer kept the ledger locked past the deadline."""


class LockUnavailable(RuntimeError):
    """No supported POSIX locking backend is available."""


@contextmanager
def application_lock(log_path: Path, timeout: float = 10):
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("lock timeout must be a nonnegative finite number")
    if fcntl is None:
        raise LockUnavailable("application writes require POSIX flock; use Linux, macOS, or WSL2")
    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    path = log_path.with_name(log_path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("application lock must be a regular file")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockBusy("application log busy; retry later, do not delete the lock file") from None
                time.sleep(min(0.05, remaining))
        yield
    finally:
        # Never unlink the sidecar: another process may already be waiting on it.
        os.close(fd)
