from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from kem_timelapse.quality.report import QualityReport

RangeLabel = Literal["inactive", "important_detail", "deleted", "kept"]


class LabeledRange(BaseModel):
    source_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    label: RangeLabel

    @model_validator(mode="after")
    def validate_range(self) -> LabeledRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


def _duration(ranges: Sequence[LabeledRange]) -> int:
    return sum(item.end_ms - item.start_ms for item in ranges)


def _overlap_duration(
    expected: Sequence[LabeledRange],
    decisions: Sequence[LabeledRange],
) -> int:
    expected_by_source: dict[str, list[LabeledRange]] = defaultdict(list)
    decisions_by_source: dict[str, list[LabeledRange]] = defaultdict(list)
    for item in expected:
        expected_by_source[item.source_id].append(item)
    for item in decisions:
        decisions_by_source[item.source_id].append(item)

    overlap_ms = 0
    for source_id, source_expected in expected_by_source.items():
        source_decisions = decisions_by_source.get(source_id, [])
        left = sorted(source_expected, key=lambda item: (item.start_ms, item.end_ms))
        right = sorted(source_decisions, key=lambda item: (item.start_ms, item.end_ms))
        left_index = 0
        right_index = 0
        while left_index < len(left) and right_index < len(right):
            expected_range = left[left_index]
            decision_range = right[right_index]
            overlap_ms += max(
                0,
                min(expected_range.end_ms, decision_range.end_ms)
                - max(expected_range.start_ms, decision_range.start_ms),
            )
            if expected_range.end_ms <= decision_range.end_ms:
                left_index += 1
            else:
                right_index += 1
    return overlap_ms


def compute_quality(
    labels: Sequence[LabeledRange],
    decisions: Sequence[LabeledRange],
) -> QualityReport:
    inactive = [item for item in labels if item.label == "inactive"]
    important_detail = [item for item in labels if item.label == "important_detail"]
    deleted = [item for item in decisions if item.label == "deleted"]
    kept = [item for item in decisions if item.label == "kept"]

    inactive_ms = _duration(inactive)
    important_detail_ms = _duration(important_detail)
    if inactive_ms == 0:
        raise ValueError("inactive labels have zero duration")
    if important_detail_ms == 0:
        raise ValueError("important_detail labels have zero duration")

    inactivity_removed_ms = _overlap_duration(inactive, deleted)
    important_detail_retained_ms = _overlap_duration(important_detail, kept)
    inactivity_removed = inactivity_removed_ms / inactive_ms
    important_detail_retained = important_detail_retained_ms / important_detail_ms
    return QualityReport(
        inactivity_removed=inactivity_removed,
        important_detail_retained=important_detail_retained,
        inactivity_removed_ms=inactivity_removed_ms,
        inactivity_labeled_ms=inactive_ms,
        important_detail_retained_ms=important_detail_retained_ms,
        important_detail_labeled_ms=important_detail_ms,
        passes_quality_gate=(
            inactivity_removed >= 0.80 and important_detail_retained >= 0.90
        ),
    )
