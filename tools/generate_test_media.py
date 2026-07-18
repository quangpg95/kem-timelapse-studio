#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import math
import shutil
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "tests" / "generated_media"
WIDTH = 960
HEIGHT = 540
FPS = 30
DURATION_SECONDS = 60


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{result.stderr[-2_000:]}")


def _base_canvas() -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), (42, 48, 55), dtype=np.uint8)
    cv2.rectangle(frame, (145, 55), (815, 500), (226, 220, 205), -1)
    cv2.rectangle(frame, (145, 55), (815, 500), (245, 245, 245), 4)
    return frame


def _frame_at(frame_index: int) -> np.ndarray:
    second = frame_index / FPS
    frame = _base_canvas()
    if second < 10:
        return frame

    if second < 25:
        progress = (second - 10) / 15
        right = 180 + round(600 * progress)
        cv2.rectangle(frame, (180, 95), (right, 460), (170, 120, 75), -1)
        return frame

    cv2.rectangle(frame, (180, 95), (780, 460), (170, 120, 75), -1)
    if second < 35:
        return frame

    detail_progress = min(1.0, (second - 35) / 15)
    stroke_count = round(24 * detail_progress)
    for index in range(stroke_count):
        x = 215 + (index % 8) * 72
        y = 140 + (index // 8) * 105
        cv2.line(frame, (x, y), (x + 45, y + 55), (35, 32, 28), 5, cv2.LINE_AA)
        cv2.circle(frame, (x + 45, y + 55), 8, (220, 185, 100), -1, cv2.LINE_AA)

    if second < 50:
        active = frame_index % FPS
        x = 215 + (stroke_count % 8) * 72 + min(active, 24) * 2
        y = 140 + (stroke_count // 8) * 105
        cv2.line(frame, (x, y), (x + 20, y + 25), (15, 15, 15), 3, cv2.LINE_AA)
    elif second < 55:
        cv2.rectangle(frame, (100, 20), (860, 520), (18, 18, 18), -1)
    return frame


def _write_visual(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MP4 writer is unavailable")
    try:
        for frame_index in range(DURATION_SECONDS * FPS):
            writer.write(_frame_at(frame_index))
    finally:
        writer.release()


def _write_audio(path: Path) -> None:
    sample_rate = 48_000
    amplitude = 4_000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        chunk_frames = 4_800
        for chunk_start in range(0, sample_rate * DURATION_SECONDS, chunk_frames):
            count = min(chunk_frames, sample_rate * DURATION_SECONDS - chunk_start)
            indexes = np.arange(chunk_start, chunk_start + count, dtype=np.float64)
            seconds = indexes / sample_rate
            burst = (
                (seconds >= 35.0)
                & (seconds < 50.0)
                & ((seconds % 1.0) < 0.12)
            )
            envelope = np.where(burst, 1.0 - (seconds % 1.0) / 0.12, 0.0)
            samples = (
                amplitude * envelope * np.sin(2.0 * math.pi * 6_000.0 * seconds)
            ).astype("<i2")
            stereo = np.column_stack((samples, samples)).reshape(-1)
            stream.writeframes(stereo.tobytes())


def generate(output_dir: Path, *, force: bool = False) -> list[Path]:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / "painting-60s.mp4"
    rotated = output_dir / "painting-rotation-90.mp4"
    no_audio = output_dir / "painting-no-audio.mp4"
    outputs = [source, rotated, no_audio]
    if all(path.is_file() for path in outputs) and not force:
        return outputs

    work_dir = output_dir / ".generation"
    work_dir.mkdir(parents=True, exist_ok=True)
    visual = work_dir / "visual.mp4"
    audio = work_dir / "brush.wav"
    _write_visual(visual)
    _write_audio(audio)
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(visual),
            "-i",
            str(audio),
            "-vf",
            "scale=3840:2160:flags=neighbor,fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "32",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(source),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-display_rotation:v:0",
            "90",
            "-i",
            str(source),
            "-map",
            "0",
            "-c",
            "copy",
            str(rotated),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            str(no_audio),
        ]
    )
    shutil.rmtree(work_dir)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic local media fixtures.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for path in generate(args.output_dir, force=args.force):
        print(f"{path.name}  sha256={_sha256(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
