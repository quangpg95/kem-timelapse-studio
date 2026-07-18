from kem_timelapse.domain.errors import ErrorCode, PipelineError, WarningCode


def test_pipeline_error_exposes_stable_code_and_context() -> None:
    error = PipelineError(
        ErrorCode.SOURCE_UNAVAILABLE,
        "Source cannot be read",
        context={"source_id": "clip-1"},
    )

    assert error.code.value == "SourceUnavailable"
    assert error.context == {"source_id": "clip-1"}
    assert WarningCode.TRACKING_LOST.value == "TrackingLost"
