"""Manual Linux integration check: exhaust a private tmpfs, never the host disk.

Run as root in the Ubuntu VM after installing the VM Python environment:
  ~/forgepulse/.venv/bin/python tests/manual_real_disk_full.py
"""

import errno
import gc
import os
import shutil
import sqlite3
import subprocess
import tempfile

from shared.model import Measurement, utcnow
from vm.journal import Journal


def measurement(sequence: int) -> Measurement:
    return Measurement("disk-test", f"disk-test-{sequence}", sequence, utcnow(), sequence,
                       55.0, 7.0, 1, 0)


def main() -> None:
    mountpoint = tempfile.mkdtemp(prefix="factoredge-enospc-", dir="/tmp")
    mounted = False
    try:
        subprocess.run(["mount", "-t", "tmpfs", "-o", "size=2m", "tmpfs", mountpoint], check=True)
        mounted = True
        db_path = os.path.join(mountpoint, "journal.db")
        journal = Journal(db_path)
        journal.append(measurement(1))
        assert journal.next_sequence() == 2

        filler_path = os.path.join(mountpoint, "filler")
        fd = os.open(filler_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            while True:
                try:
                    os.write(fd, b"\0" * 4096)
                except OSError as exc:
                    if exc.errno != errno.ENOSPC:
                        raise
                    break
        finally:
            os.close(fd)

        failure = None
        try:
            journal.append(measurement(2))
        except (RuntimeError, OSError, sqlite3.Error) as exc:
            failure = type(exc).__name__
        assert failure is not None, "append unexpectedly succeeded on full tmpfs"

        os.unlink(filler_path)
        db = journal.db()
        try:
            rows = db.execute("SELECT seq,event_id FROM records ORDER BY seq").fetchall()
            last_sequence = db.execute("SELECT value FROM meta WHERE key='last_sequence'").fetchone()[0]
        finally:
            db.close()
        assert [(row[0], row[1]) for row in rows] == [(1, "disk-test-1")]
        assert last_sequence == 1
        print(f"REAL_ENOSPC_OK failure={failure} rows=1 last_sequence=1")
    finally:
        # sqlite3's connection context manager commits but does not close the connection.
        # Release any traceback-held connections before unmounting this test-only tmpfs.
        gc.collect()
        if mounted:
            subprocess.run(["umount", mountpoint], check=True)
        shutil.rmtree(mountpoint)


if __name__ == "__main__":
    main()
