"""Deterministic, causally related production signals."""
from dataclasses import dataclass


@dataclass
class Belt:
    produced: int = 0
    rejected: int = 0
    temperature_c: float = 22.0
    current_a: float = 0.0
    state: int = 0
    ticks: int = 0

    def step(self):
        self.ticks += 1
        target = {0: 22.0, 1: 55.0, 2: 105.0}[self.state]
        self.temperature_c += (target - self.temperature_c) * (0.12 if self.state else 0.045)
        if self.state == 1:
            self.produced += 3
            if self.ticks % 12 == 0:
                self.rejected += 1
            self.current_a = 7 + (self.ticks % 5) * 0.18
        elif self.state == 2:
            self.current_a = 11.5
        else:
            self.current_a = 0.04
        return self
