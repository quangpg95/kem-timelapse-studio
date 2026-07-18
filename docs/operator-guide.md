# Operator guide

## Before starting

Install FFmpeg with `brew install ffmpeg`, keep the source recordings connected and writable project storage available, then launch the desktop app. Confirm you own the footage and have rights to any local music before using it.

## One-click workflow

1. **Import** one or more MOV/MP4 recordings. The app orders clips deterministically and records a fingerprint; it never changes a source file.
2. **Analyze** to create local proxies, detect canvas activity, remove inactive passages, and compose TikTok Fast, Reels Aesthetic, and Shorts ASMR timelines.
3. **Preview & Render** the variants. Keep/remove segments, select speeds, and use the crop controls when a low-confidence canvas detection needs manual ROI confirmation. Render writes three 1080×1920 H.264/AAC files and `outputs/manifest.json`.

The default watermark is `@kem12032024` at 30% opacity. The renderer chooses a platform-safe low-saliency position and records a fallback warning when it cannot avoid the canvas.

## Warnings and recovery

- **LowRoiConfidence / TrackingLost:** confirm or adjust the canvas crop before render.
- **AudioDenoiseDegraded:** DeepFilterNet was unavailable or failed, so FFmpeg cleanup was used.
- **NoSourceAudio:** the selected source range has no audio; the output contains silence or allowed music.
- **RenderBackendUnavailable / SourceUnavailable:** check `ffmpeg -version`, `ffprobe -version`, cable/disk access, and retry.
- **OutputNotWritable / InsufficientDisk:** choose a writable project location with room for proxies, audio cache, and three outputs.

After a Force Quit, reopen the same project and run Analyze or Render again. Checkpoints in `project.json`, `analysis/`, `timelines/`, and `outputs/` let the job validate completed work and resume; incomplete `.partial` files are removed safely.

## Files and cleanup

Output names follow `painting_tiktok-fast.mp4`, `painting_reels-aesthetic.mp4`, and `painting_shorts-asmr.mp4` (with the project name converted to a safe slug). Keep `outputs/` and `manifest.json` for publishing provenance. You may delete `cache/proxy/` and `cache/audio/` after the pack is approved; a future analysis recreates them.

## Redacted diagnostics

For support, export `project.json`, timeline JSON files, `outputs/manifest.json`, and `logs/jobs.jsonl` after removing names/paths you do not wish to share. Do not send source media or private recordings. The benchmark report intentionally records source filenames rather than absolute paths.
