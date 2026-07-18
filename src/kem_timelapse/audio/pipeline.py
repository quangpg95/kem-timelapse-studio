from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from kem_timelapse.audio.models import AudioMixPlan, AudioStem, DenoiseResult, SourceRange
from kem_timelapse.audio.ranges import ranges_from_timelines
from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Segment, SourceClip, Timeline, TimelineItem, Variant
from kem_timelapse.media.process import CommandRunner, CompletedCommand


class DenoiseBackend(Protocol):
    def process(self, input_wav: Path, output_wav: Path) -> None: ...


class Runner(Protocol):
    def run(self, args: Sequence[str], cancel_event: object | None = None) -> CompletedCommand: ...


class AudioPipeline:
    PRESET_VERSION = "audio-v1"

    def __init__(
        self,
        primary: DenoiseBackend,
        fallback: DenoiseBackend,
        runner: Runner | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._runner = runner or CommandRunner()

    def denoise(self, input_wav: Path, output_wav: Path) -> DenoiseResult:
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_wav.with_suffix(".partial.wav")
        temporary.unlink(missing_ok=True)
        warning: WarningCode | None = None
        try:
            self._primary.process(input_wav, temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            self._fallback.process(input_wav, temporary)
            warning = WarningCode.AUDIO_DENOISE_DEGRADED
        if not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("denoise backend did not create audio output")
        os.replace(temporary, output_wav)
        return DenoiseResult(path=output_wav, warning=warning)

    def prepare_variant(
        self,
        variant: Variant,
        timelines: Sequence[Timeline],
        segments: Mapping[str, Segment],
        sources: Mapping[str, SourceClip],
        cache_dir: Path,
        music_path: Path | None,
        rights_confirmed: bool,
    ) -> AudioMixPlan:
        timeline = self._select_timeline(variant, timelines)
        self._validate_music(music_path, rights_confirmed)
        cache_dir.mkdir(parents=True, exist_ok=True)

        warning_codes: list[WarningCode] = []
        stems = [
            stem
            for source_range in ranges_from_timelines(timelines, segments, join_gap_ms=100)
            if (
                stem := self._prepare_stem(
                    source_range,
                    sources,
                    cache_dir,
                    warning_codes,
                )
            )
            is not None
        ]
        effective_music = music_path if timeline.audio_mode in ("asmr_music", "music") else None
        filter_graph = _build_filter_graph(timeline, segments, stems, effective_music)
        mix_key = _digest(
            {
                "version": self.PRESET_VERSION,
                "variant": variant.value,
                "revision": timeline.revision,
                "mode": timeline.audio_mode,
                "stems": [stem.cache_key for stem in stems],
                "music": _path_fingerprint(effective_music),
                "filter": filter_graph,
            }
        )
        mix_path = cache_dir / f"{variant.value}-{mix_key}.wav"
        if not _valid_artifact(mix_path):
            self._render_mix(stems, effective_music, filter_graph, mix_path)
        return AudioMixPlan(
            variant=variant,
            mode=timeline.audio_mode,
            stem_paths=[stem.path for stem in stems],
            music_path=effective_music,
            filter_graph=filter_graph,
            mix_path=mix_path,
            warning_codes=list(dict.fromkeys(warning_codes)),
        )

    @staticmethod
    def _select_timeline(variant: Variant, timelines: Sequence[Timeline]) -> Timeline:
        matches = [timeline for timeline in timelines if timeline.variant is variant]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one timeline for {variant.value}")
        return matches[0]

    @staticmethod
    def _validate_music(music_path: Path | None, rights_confirmed: bool) -> None:
        if music_path is None:
            return
        if not music_path.is_file():
            raise ValueError("music_path must reference an existing file")
        if not rights_confirmed:
            raise ValueError("rights_confirmed=True is required for local music")

    def _prepare_stem(
        self,
        source_range: SourceRange,
        sources: Mapping[str, SourceClip],
        cache_dir: Path,
        warning_codes: list[WarningCode],
    ) -> AudioStem | None:
        try:
            source = sources[source_range.source_id]
        except KeyError as error:
            raise ValueError(f"unknown source: {source_range.source_id}") from error
        if not source.media.has_audio:
            warning_codes.append(WarningCode.NO_SOURCE_AUDIO)
            return None

        cache_key = _digest(
            {
                "fingerprint": source.fingerprint,
                "start_ms": source_range.start_ms,
                "end_ms": source_range.end_ms,
                "version": self.PRESET_VERSION,
                "backend": type(self._primary).__name__,
            }
        )
        raw_path = cache_dir / f"selected-{cache_key}.wav"
        clean_path = cache_dir / f"stem-{cache_key}.wav"
        degraded_marker = clean_path.with_suffix(".degraded")
        warning = (
            WarningCode.AUDIO_DENOISE_DEGRADED if degraded_marker.is_file() else None
        )
        if not _valid_artifact(clean_path):
            if not _valid_artifact(raw_path):
                self._extract_range(source, source_range, raw_path)
            result = self.denoise(raw_path, clean_path)
            warning = result.warning
            if warning is WarningCode.AUDIO_DENOISE_DEGRADED:
                degraded_marker.touch()
            else:
                degraded_marker.unlink(missing_ok=True)
        if warning is not None:
            warning_codes.append(warning)
        return AudioStem(
            source_range=source_range,
            path=clean_path,
            cache_key=cache_key,
            warning=warning,
        )

    def _extract_range(
        self,
        source: SourceClip,
        source_range: SourceRange,
        output_wav: Path,
    ) -> None:
        temporary = output_wav.with_suffix(".partial.wav")
        result = self._runner.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{source_range.start_ms / 1000:.3f}",
                "-i",
                str(source.path),
                "-t",
                f"{(source_range.end_ms - source_range.start_ms) / 1000:.3f}",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s24le",
                str(temporary),
            ]
        )
        if result.returncode != 0 or not _valid_artifact(temporary):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"selected-range extraction failed: {result.stderr[-500:]}")
        os.replace(temporary, output_wav)

    def _render_mix(
        self,
        stems: Sequence[AudioStem],
        music_path: Path | None,
        filter_graph: str,
        output_wav: Path,
    ) -> None:
        temporary = output_wav.with_suffix(".partial.wav")
        measurement = output_wav.with_suffix(".measure.wav")
        measurement_graph = filter_graph.replace(
            "loudnorm=I=-14:TP=-1:LRA=7",
            "loudnorm=I=-14:TP=-1:LRA=7:print_format=json",
        )
        measure_result = self._runner.run(
            self._mix_args(stems, music_path, measurement_graph, measurement, loglevel="info")
        )
        measured_graph = _apply_loudnorm_measurement(filter_graph, measure_result.stderr)
        measurement.unlink(missing_ok=True)
        result = self._runner.run(
            self._mix_args(stems, music_path, measured_graph, temporary, loglevel="error")
        )
        if result.returncode != 0 or not _valid_artifact(temporary):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"audio mix failed: {result.stderr[-500:]}")
        os.replace(temporary, output_wav)

    @staticmethod
    def _mix_args(
        stems: Sequence[AudioStem],
        music_path: Path | None,
        filter_graph: str,
        output_path: Path,
        *,
        loglevel: str,
    ) -> list[str]:
        args = ["ffmpeg", "-y", "-v", loglevel]
        for stem in stems:
            args.extend(["-i", str(stem.path)])
        if music_path is not None:
            args.extend(["-stream_loop", "-1", "-i", str(music_path)])
        args.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[outa]",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s24le",
                str(output_path),
            ]
        )
        return args


def _build_filter_graph(
    timeline: Timeline,
    segments: Mapping[str, Segment],
    stems: Sequence[AudioStem],
    music_path: Path | None,
) -> str:
    duration_s = sum(
        (item.trim_out_ms - item.trim_in_ms) / item.speed / 1000
        for item in timeline.items
        if item.keep
    )
    chains: list[str] = []
    item_labels: list[str] = []
    for item_index, item in enumerate(item for item in timeline.items if item.keep):
        segment = segments[item.segment_id]
        stem_index = _containing_stem_index(stems, segment.source_id, item)
        label = f"item{item_index}"
        item_duration = (item.trim_out_ms - item.trim_in_ms) / item.speed / 1000
        if stem_index is None:
            chains.append(f"anullsrc=r=48000:cl=mono:d={item_duration:.6f}[{label}]")
        else:
            stem_range = stems[stem_index].source_range
            relative_start = (item.trim_in_ms - stem_range.start_ms) / 1000
            relative_end = (item.trim_out_ms - stem_range.start_ms) / 1000
            tempo = ",".join(f"atempo={part:g}" for part in _tempo_parts(item.speed))
            chains.append(
                f"[{stem_index}:a]atrim=start={relative_start:.6f}:end={relative_end:.6f},"
                f"asetpts=PTS-STARTPTS,{tempo}[{label}]"
            )
        item_labels.append(f"[{label}]")

    if item_labels:
        chains.append(f"{''.join(item_labels)}concat=n={len(item_labels)}:v=0:a=1[asmr]")
    else:
        chains.append(f"anullsrc=r=48000:cl=mono:d={duration_s:.6f}[asmr]")

    mode = timeline.audio_mode
    music_index = len(stems)
    if mode == "silent":
        chains.append(f"anullsrc=r=48000:cl=stereo:d={duration_s:.6f}[premaster]")
    elif mode == "music" and music_path is not None:
        gain, _, _, _ = _mix_policy(timeline.variant)
        chains.append(
            f"[{music_index}:a]atrim=duration={duration_s:.6f},asetpts=PTS-STARTPTS,"
            f"volume={gain}dB[premaster]"
        )
    elif mode == "asmr_music" and music_path is not None:
        gain, duck_ratio, attack, release = _mix_policy(timeline.variant)
        chains.append(
            f"[{music_index}:a]atrim=duration={duration_s:.6f},asetpts=PTS-STARTPTS,"
            f"volume={gain}dB[music]"
        )
        chains.append(
            f"[music][asmr]sidechaincompress=threshold=0.03:ratio={duck_ratio}:"
            f"attack={attack}:release={release}[ducked]"
        )
        chains.append("[asmr][ducked]amix=inputs=2:normalize=0[premaster]")
    else:
        chains.append("[asmr]aformat=channel_layouts=stereo[premaster]")
    chains.append(
        "[premaster]pan=stereo|c0=c0|c1=c0,"
        "loudnorm=I=-14:TP=-1:LRA=7,alimiter=limit=0.891:level=false[outa]"
    )
    return ";".join(chains)


def _containing_stem_index(
    stems: Sequence[AudioStem], source_id: str, item: TimelineItem
) -> int | None:
    return next(
        (
            index
            for index, stem in enumerate(stems)
            if stem.source_range.source_id == source_id
            and stem.source_range.start_ms <= item.trim_in_ms
            and stem.source_range.end_ms >= item.trim_out_ms
        ),
        None,
    )


def _tempo_parts(speed: int) -> list[float]:
    remaining = float(speed)
    parts: list[float] = []
    while remaining > 2:
        parts.append(2.0)
        remaining /= 2
    parts.append(remaining)
    return parts


def _mix_policy(variant: Variant) -> tuple[int, int, int, int]:
    if variant is Variant.TIKTOK_FAST:
        return (-18, 6, 20, 250)
    if variant is Variant.REELS_AESTHETIC:
        return (-21, 4, 40, 400)
    return (-28, 3, 40, 400)


def _valid_artifact(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _path_fingerprint(path: Path | None) -> str | None:
    if path is None:
        return None
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def _apply_loudnorm_measurement(filter_graph: str, stderr: str) -> str:
    blocks = [
        match.group(0)
        for match in re.finditer(r"\{[^{}]*\}", stderr, flags=re.DOTALL)
    ]
    for block in reversed(blocks):
        try:
            measured = json.loads(block)
            values = {
                "I": float(measured["input_i"]),
                "LRA": float(measured["input_lra"]),
                "TP": float(measured["input_tp"]),
                "thresh": float(measured["input_thresh"]),
                "offset": float(measured["target_offset"]),
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        second_pass = (
            "loudnorm=I=-14:TP=-1:LRA=7:"
            f"measured_I={values['I']}:measured_LRA={values['LRA']}:"
            f"measured_TP={values['TP']}:measured_thresh={values['thresh']}:"
            f"offset={values['offset']}:linear=true"
        )
        return filter_graph.replace("loudnorm=I=-14:TP=-1:LRA=7", second_pass)
    return filter_graph
