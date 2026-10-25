"""Pure alarm and period calculations; no transport assumptions."""
from datetime import datetime


def alarm_transition(active, temperature, measured_at, now, threshold, hysteresis, max_age=15):
    try:
        age = (datetime.fromisoformat(now) - datetime.fromisoformat(measured_at)).total_seconds()
        if age < -2 or age > max_age or temperature is None:
            return active
        t = float(temperature)
    except (TypeError, ValueError):
        return active
    if active and t <= threshold - hysteresis:
        return False
    if not active and t >= threshold:
        return True
    return active


def period_metrics(rows, start, end, stale_after=10):
    """Counters include all units, including rejected units. Unknown time is separate."""
    duration = max(0, end - start)
    running = known = 0.0
    produced = rejected = 0
    counter_segments = 0
    for previous, current in zip(rows, rows[1:]):
        a, b = previous["epoch"], current["epoch"]
        span = max(0, min(b, end, a + stale_after) - max(a, start))
        if span:
            known += span
            if previous["state"] == 1:
                running += span
        dp = current["produced"] - previous["produced"]
        dr = current["rejected"] - previous["rejected"]
        if 0 <= dp <= 100000 and 0 <= dr <= dp:
            produced += dp
            rejected += dr
            counter_segments += 1
    known = min(duration, known)
    return {
        "running_ratio": running / known if known else None,
        "reject_ratio": rejected / produced if produced else None,
        "known_seconds": known,
        "unknown_seconds": duration - known,
        "coverage_ratio": known / duration if duration else None,
        "produced_delta": produced,
        "rejected_delta": rejected,
        "valid_counter_segments": counter_segments,
    }
