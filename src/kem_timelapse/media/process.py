from __future__ import annotations

import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CompletedCommand:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand:
        process = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        while process.poll() is None:
            if cancel_event is not None and cancel_event.wait(0.05):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise InterruptedError("command cancelled")
        stdout, stderr = process.communicate()
        return CompletedCommand(process.returncode, stdout, stderr)
