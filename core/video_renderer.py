"""
core/video_renderer.py
Re-encodes the original video with a replacement audio track.

Workflow:
  1. Convert processed float32 WAV to 16-bit PCM WAV temp file
  2. Use FFmpeg to mux: original video stream + new audio stream
  3. Respect output quality settings
  4. Preserve all metadata / subtitles from original
"""

import subprocess
import shutil
import tempfile
import logging
import numpy as np
import scipy.io.wavfile as wavfile
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

QUALITY_PRESETS = {
    "low":    {"video_crf": "28", "audio_br": "128k"},
    "medium": {"video_crf": "23", "audio_br": "192k"},
    "high":   {"video_crf": "18", "audio_br": "256k"},
    "lossless": {"video_crf": "0",  "audio_br": "320k"},
}


class VideoRenderError(RuntimeError):
    pass


def render_video(
    original_video: Path,
    cleaned_audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
    quality: str = "high",
    progress_cb: Callable[[int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    """
    Merge *cleaned_audio* back into *original_video* and save to *output_path*.

    Parameters
    ----------
    original_video : source video file
    cleaned_audio  : float32 mono array
    sample_rate    : audio sample rate
    output_path    : destination path (mp4 recommended)
    quality        : one of low / medium / high / lossless
    progress_cb    : called with 0..100 int
    cancel_check   : called each iteration; if True → cancel

    Returns
    -------
    output_path on success
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoRenderError("FFmpeg not found on PATH")

    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write cleaned audio to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)

    try:
        # Normalise and convert to int16
        audio_int16 = _float_to_int16(cleaned_audio)
        wavfile.write(str(tmp_wav), sample_rate, audio_int16)
        log.debug(f"Temp WAV written: {tmp_wav}")

        if progress_cb:
            progress_cb(10)

        if cancel_check and cancel_check():
            raise VideoRenderError("Render cancelled by user")

        # Determine output extension / codec
        suffix = output_path.suffix.lower()
        if suffix in (".mp4", ""):
            vcodec = "libx264"
            acodec = "aac"
        elif suffix == ".mkv":
            vcodec = "libx264"
            acodec = "libmp3lame"
        elif suffix == ".webm":
            vcodec = "libvpx-vp9"
            acodec = "libopus"
        else:
            vcodec = "copy"
            acodec = "aac"

        cmd = [
            ffmpeg, "-y",
            "-i", str(original_video),   # original video (V+A)
            "-i", str(tmp_wav),           # cleaned audio
            "-map", "0:v:0",              # take video from input 0
            "-map", "1:a:0",              # take audio from input 1
            "-c:v", vcodec,
            "-crf", preset["video_crf"],
            "-preset", "fast",
            "-c:a", acodec,
            "-b:a", preset["audio_br"],
            "-ar", str(sample_rate),
            "-ac", "1",
            "-shortest",
            "-progress", "pipe:1",
            str(output_path),
        ]

        if vcodec == "copy":
            # remove crf/preset for copy mode
            cmd = [c for c in cmd if c not in ["-crf", preset["video_crf"], "-preset", "fast"]]

        log.info(f"Rendering: {original_video.name} → {output_path.name} [{quality}]")

        # Get source duration for progress
        duration = _probe_duration(ffmpeg, original_video)

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

        while True:
            if cancel_check and cancel_check():
                proc.terminate()
                raise VideoRenderError("Render cancelled by user")

            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line.startswith("out_time_ms="):
                try:
                    ms = int(line.strip().split("=")[1])
                    t = ms / 1_000_000
                    if duration > 0 and progress_cb:
                        pct = min(99, 10 + int(89 * t / duration))
                        progress_cb(pct)
                except ValueError:
                    pass

        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read()
            raise VideoRenderError(f"FFmpeg render failed (code {proc.returncode}): {err}")

        if not output_path.exists():
            raise VideoRenderError("Output file not created")

        if progress_cb:
            progress_cb(100)

        log.info(f"Render complete → {output_path}")
        return output_path

    finally:
        if tmp_wav.exists():
            tmp_wav.unlink()


def export_audio_only(
    cleaned_audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
) -> Path:
    """Export cleaned audio as WAV file (no video)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_int16 = _float_to_int16(cleaned_audio)
    wavfile.write(str(output_path), sample_rate, audio_int16)
    log.info(f"Audio exported → {output_path}")
    return output_path


def _float_to_int16(audio: np.ndarray) -> np.ndarray:
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767).astype(np.int16)


def _probe_duration(ffmpeg: str, path: Path) -> float:
    ffprobe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        import json
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0
