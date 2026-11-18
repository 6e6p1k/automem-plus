"""A lock that gives up instead of hanging, so a hook never waits behind a slow sync."""

import contextlib
import os
import time

from automem import state

try:
    import fcntl
except ImportError:  # no fcntl on Windows: fall back to a lock file that is created exclusively
    fcntl = None

POLL_SECONDS = 0.2
STALE_LOCK_SECONDS = 600  # a fallback lock file older than this was left by a process that died


class Lock:
    """An exclusive lock on a file in the state folder. acquire returns False after wait seconds."""

    def __init__(self, name, wait=10.0):
        self.path = os.path.join(state.state_dir(), name + ".lock")
        self.wait = wait
        self.file = None
        self.held_by_file = False

    def acquire(self):
        deadline = time.time() + self.wait
        while not (self._try_flock() if fcntl else self._try_lock_file()):
            if time.time() >= deadline:
                return False
            time.sleep(POLL_SECONDS)
        return True

    def release(self):
        if self.file:
            fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()
            self.file = None
        if self.held_by_file:
            self.held_by_file = False
            with contextlib.suppress(OSError):
                os.remove(self.path)

    def _try_flock(self):
        """The operating system drops this lock when the process ends, so it can't go stale."""
        handle = open(self.path, "w")  # noqa: SIM115 - held open for as long as the lock is
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self.file = handle
        return True

    def _try_lock_file(self):
        try:
            os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - os.path.getmtime(self.path) > STALE_LOCK_SECONDS:
                    os.remove(self.path)
            return False
        self.held_by_file = True
        return True
