from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisPreset:
    version: str
    active_enter: float
    active_exit: float
    broad_area: float
    detail_score: float
    asmr_score: float
    minimum_inactive_ms: int
    merge_gap_ms: int
    handle_ms: int


BOOTSTRAP_PRESET = AnalysisPreset(
    version="heuristic-v1-bootstrap",
    active_enter=0.12,
    active_exit=0.08,
    broad_area=0.35,
    detail_score=0.18,
    asmr_score=0.55,
    minimum_inactive_ms=1_500,
    merge_gap_ms=500,
    handle_ms=250,
)
