import cv2
import numpy as np

from kem_timelapse.analysis.features import brush_band_score, visual_metrics


def test_visual_metrics_separate_static_detail_and_broad_change() -> None:
    base = np.zeros((120, 160, 3), dtype=np.uint8)
    static = base.copy()
    detail = base.copy()
    cv2.line(detail, (70, 50), (90, 70), (255, 255, 255), 2)
    broad = base.copy()
    cv2.rectangle(broad, (20, 20), (140, 100), (255, 255, 255), -1)

    static_score = visual_metrics(base, static, None)
    detail_score = visual_metrics(base, detail, None)
    broad_score = visual_metrics(base, broad, None)

    assert static_score.changed_area < detail_score.changed_area < broad_score.changed_area
    assert detail_score.detail > static_score.detail
    assert broad_score.changed_area > 0.35


def test_brush_band_score_prefers_six_khz_over_low_hum() -> None:
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    brush = np.sin(2 * np.pi * 6_000 * time).astype(np.float32)
    hum = np.sin(2 * np.pi * 100 * time).astype(np.float32)

    assert brush_band_score(brush, sample_rate) > brush_band_score(hum, sample_rate)
