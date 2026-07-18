import numpy as np

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.framing.watermark import choose_watermark_placement


def test_watermark_chooses_low_saliency_corner_outside_canvas() -> None:
    saliency = np.zeros((10, 10), dtype=np.float32)
    saliency[0:3, 0:3] = 1.0

    placement = choose_watermark_placement(
        saliency,
        canvas_box=(0.2, 0.1, 0.9, 0.65),
        text="@kem12032024",
        opacity=0.30,
    )

    assert placement.corner == "bottom-left"
    assert placement.opacity == 0.30
    assert placement.warning is None


def test_all_blocked_corners_use_deterministic_fallback() -> None:
    saliency = np.ones((10, 10), dtype=np.float32)

    result = choose_watermark_placement(
        saliency,
        canvas_box=(0.0, 0.0, 1.0, 1.0),
        text="@kem12032024",
        opacity=0.30,
    )

    assert result.corner == "bottom-left"
    assert result.warning is WarningCode.WATERMARK_PLACEMENT_FALLBACK
