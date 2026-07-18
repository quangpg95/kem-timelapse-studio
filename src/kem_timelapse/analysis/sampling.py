from __future__ import annotations

from collections.abc import Sequence


def sampling_schedule(
    duration_ms: int,
    candidate_ms: Sequence[int],
    *,
    sparse_ms: int = 1_000,
    dense_ms: int = 100,
) -> list[int]:
    timestamps = set(range(0, duration_ms, sparse_ms))
    for candidate in candidate_ms:
        start = max(0, candidate - 500)
        end = min(duration_ms, candidate + 501)
        timestamps.update(range(start, end, dense_ms))
    return sorted(timestamps)
