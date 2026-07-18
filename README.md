# Kem Timelapse Studio

Kem Timelapse Studio is a local macOS app that turns long painting recordings into a three-video vertical Content Pack: TikTok Fast, Reels Aesthetic, and Shorts ASMR. It runs locally; source footage and project caches remain on the operator's Mac.

## Prerequisites

- macOS on Apple Silicon for the unsigned app build and VideoToolbox render path.
- Python 3.10 or later.
- [FFmpeg](https://ffmpeg.org/) and ffprobe: `brew install ffmpeg`.
- Optional: `pip install -e '.[deepfilter]'` to enable DeepFilterNet; FFmpeg denoise remains the local fallback.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/kem-timelapse --help
.venv/bin/kem-timelapse-desktop
```

Use the CLI for project diagnostics and automation:

```bash
.venv/bin/kem-timelapse inspect /path/to/project
.venv/bin/kem-timelapse analyze /path/to/project --source /path/to/recording.MOV
.venv/bin/kem-timelapse render /path/to/project
```

## Verification and unsigned build

```bash
.venv/bin/pytest -m 'not e2e' -q
.venv/bin/ruff check src tests tools
.venv/bin/mypy src/kem_timelapse
bash scripts/build_macos.sh
```

The build produces `dist/Kem Timelapse Studio.app`. It is intentionally unsigned: macOS may require the operator to explicitly open it from Finder after reviewing the local build. No source/test media is included in the bundle.

See [the operator guide](docs/operator-guide.md), [benchmarking instructions](docs/benchmarking.md), and [third-party license inventory](docs/third-party-licenses.md).
