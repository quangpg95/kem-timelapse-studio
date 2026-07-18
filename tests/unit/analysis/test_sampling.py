from kem_timelapse.analysis.sampling import sampling_schedule


def test_sampling_schedule_is_sparse_except_near_candidates() -> None:
    schedule = sampling_schedule(
        duration_ms=3_000,
        candidate_ms=[1_000],
        sparse_ms=500,
        dense_ms=100,
    )

    assert 900 in schedule and 1_100 in schedule
    assert 100 not in schedule
    assert 500 in schedule and 2_500 in schedule
    assert schedule == sorted(set(schedule))
