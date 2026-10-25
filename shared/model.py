"""Common source independent measurement contract."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Measurement:
    source_id: str
    event_id: str
    sequence: int
    source_time: str
    produced: int
    temperature_c: float
    current_a: float
    state: int
    rejected: int

    def validate(self):
        timestamp = datetime.fromisoformat(self.source_time.replace("Z", "+00:00"))
        if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError("source_time must be UTC")
        if self.state not in (0, 1, 2) or min(self.produced, self.rejected, self.sequence) < 0:
            raise ValueError("invalid counters/state")
        if not math.isfinite(self.temperature_c) or not math.isfinite(self.current_a):
            raise ValueError("non-finite reading")
        if self.rejected > self.produced:
            raise ValueError("rejected exceeds total production")
        return self

    def json(self):
        return asdict(self)
