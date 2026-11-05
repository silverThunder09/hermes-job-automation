import os
import time
from pathlib import Path


class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            try:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise RuntimeError("ANOTHER_RUN_IS_ACTIVE") from exc
        else:
            import fcntl

            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise RuntimeError("ANOTHER_RUN_IS_ACTIVE") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write("{} {}".format(os.getpid(), int(time.time())).encode("ascii"))
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.handle:
            return
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            try:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None
