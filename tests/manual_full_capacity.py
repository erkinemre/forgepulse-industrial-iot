"""Accelerated Linux VM check of the documented 86,400-row source buffer.

This exercises the full row count without waiting 24 wall-clock hours. It does not
claim to validate a 24-hour powered runtime or minimum free disk space.
"""

import gc
import tempfile
import time
from pathlib import Path

from shared.model import Measurement, utcnow
from vm.journal import Journal


def main() -> None:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="factoredge-capacity-") as path:
        journal = Journal(str(Path(path) / "source.db"))
        for sequence in range(1, 86_401):
            journal.append(Measurement("capacity-test", f"capacity-{sequence}",
                                       sequence, utcnow(), sequence, 55.0, 7.0, 1, 0))
            if sequence % 10_000 == 0:
                print(f"CAPACITY_PROGRESS {sequence}", flush=True)
        assert not journal.has_capacity()
        assert journal.next_sequence() == 86_401
        try:
            journal.append(Measurement("capacity-test", "capacity-86401", 86_401,
                                       utcnow(), 86_401, 55.0, 7.0, 1, 0))
        except RuntimeError as exc:
            assert "full" in str(exc)
        else:
            raise AssertionError("full journal accepted one extra record")
        assert journal.next_sequence() == 86_401
        tail = journal.after(86_395)
        assert [row["sequence"] for row in tail] == [86_396, 86_397, 86_398, 86_399, 86_400]
        journal.acknowledge_through(86_400)
        assert journal.has_capacity()
        gc.collect()
        print(f"FULL_CAPACITY_OK rows=86400 overflow_rejected=1 elapsed_seconds={time.monotonic()-started:.1f}")


if __name__ == "__main__":
    main()
