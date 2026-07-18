from __future__ import annotations

import pytest

from kem_timelapse.domain.models import Timeline, TimelineItem, Variant
from kem_timelapse.editing.session import EditingSession


@pytest.fixture
def editing_sessions() -> dict[Variant, EditingSession]:
    return {
        variant: EditingSession(
            Timeline(
                variant=variant,
                revision=0,
                audio_mode="asmr_music" if variant is not Variant.SHORTS_ASMR else "asmr",
                items=[
                    TimelineItem(
                        id=f"{variant.value}-body-shared-0",
                        role="body",
                        segment_id="shared",
                        trim_in_ms=0,
                        trim_out_ms=4_000,
                        speed=4,
                    )
                ],
            )
        )
        for variant in Variant
    }
