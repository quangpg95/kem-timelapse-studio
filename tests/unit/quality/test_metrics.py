import pytest
from pydantic import ValidationError

from kem_timelapse.quality.metrics import LabeledRange, compute_quality


def test_quality_uses_duration_overlap_not_segment_count() -> None:
    labels = [
        LabeledRange(source_id="a", start_ms=0, end_ms=10_000, label="inactive"),
        LabeledRange(source_id="a", start_ms=10_000, end_ms=20_000, label="important_detail"),
    ]
    decisions = [
        LabeledRange(source_id="a", start_ms=0, end_ms=8_000, label="deleted"),
        LabeledRange(source_id="a", start_ms=10_000, end_ms=19_000, label="kept"),
    ]

    report = compute_quality(labels, decisions)

    assert report.inactivity_removed == 0.80
    assert report.important_detail_retained == 0.90
    assert report.passes_quality_gate is True
    assert report.inactivity_removed_ms == 8_000
    assert report.inactivity_labeled_ms == 10_000
    assert report.important_detail_retained_ms == 9_000
    assert report.important_detail_labeled_ms == 10_000


def test_quality_isolated_by_source_id() -> None:
    labels = [
        LabeledRange(source_id="a", start_ms=0, end_ms=1_000, label="inactive"),
        LabeledRange(source_id="b", start_ms=0, end_ms=1_000, label="important_detail"),
    ]
    decisions = [
        LabeledRange(source_id="b", start_ms=0, end_ms=1_000, label="deleted"),
        LabeledRange(source_id="a", start_ms=0, end_ms=1_000, label="kept"),
    ]

    report = compute_quality(labels, decisions)

    assert report.inactivity_removed == 0.0
    assert report.important_detail_retained == 0.0


def test_quality_rejects_a_zero_denominator() -> None:
    labels = [LabeledRange(source_id="a", start_ms=0, end_ms=1_000, label="inactive")]
    decisions = [LabeledRange(source_id="a", start_ms=0, end_ms=1_000, label="deleted")]

    with pytest.raises(ValueError, match="important_detail"):
        compute_quality(labels, decisions)


def test_labeled_range_validates_range_and_label() -> None:
    with pytest.raises(ValidationError, match="end_ms must be greater"):
        LabeledRange(source_id="a", start_ms=1_000, end_ms=1_000, label="inactive")

    with pytest.raises(ValidationError):
        LabeledRange(source_id="a", start_ms=0, end_ms=1_000, label="unknown")
