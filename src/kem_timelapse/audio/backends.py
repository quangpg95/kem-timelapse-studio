from __future__ import annotations

import importlib
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from kem_timelapse.media.process import CompletedCommand


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand: ...


class DeepFilterBackend:
    """Lazy, process-wide DeepFilterNet model adapter."""

    _state_lock = threading.Lock()
    _model: Any = None
    _df_state: Any = None
    _enhance_module: Any = None

    @classmethod
    def _state(cls) -> tuple[Any, Any, Any]:
        with cls._state_lock:
            if cls._model is None:
                module = importlib.import_module("df.enhance")
                model, df_state, _ = module.init_df()
                cls._model = model
                cls._df_state = df_state
                cls._enhance_module = module
        return cls._model, cls._df_state, cls._enhance_module

    def process(self, input_wav: Path, output_wav: Path) -> None:
        model, df_state, module = self._state()
        audio, _ = module.load_audio(str(input_wav), sr=df_state.sr())
        enhanced = module.enhance(model, df_state, audio)
        module.save_audio(str(output_wav), enhanced, df_state.sr())


class FfmpegDenoiseBackend:
    FILTER = (
        "highpass=f=80,afftdn=nf=-25,equalizer=f=3000:t=q:w=1:g=2,"
        "equalizer=f=8000:t=q:w=1:g=1,"
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=120,"
        "alimiter=limit=0.891"
    )

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def process(self, input_wav: Path, output_wav: Path) -> None:
        result = self._runner.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(input_wav),
                "-af",
                self.FILTER,
                str(output_wav),
            ]
        )
        if result.returncode != 0 or not output_wav.is_file() or output_wav.stat().st_size == 0:
            output_wav.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg denoise did not create output: {result.stderr[-500:]}")
