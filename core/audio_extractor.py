"""
core/audio_extractor.py
Fast, high-quality WAV audio extraction from video via FFmpeg.

Speed optimizations vs naive approach
──────────────────────────────────────
1. STREAM COPY when source audio is already PCM / lossless — zero re-encoding cost.
2. Native sample rate preserved by default (no forced resample unless requested).
   Librosa handles resampling in Python at load time with high-quality SRC.
3. `-threads 0` — FFmpeg auto-selects thread count matching CPU core count.
4. `-nostdin` — prevents FFmpeg from waiting on stdin (small but real speedup).
5. `-hide_banner -loglevel error` — eliminates verbose header parsing overhead.
6. Progress via timed wall-clock estimation instead of `-progress pipe:1`,
   which removed a full extra stdio stream + blocking per-line reads.
7. stderr collected in a background daemon thread — never blocks the poll loop.
8. `-fflags +fastseek` for container-level fast seeking (MP4/MOV benefit most).
9. Output to float32 PCM (`pcm_f32le`) — matches librosa's internal format,
   skipping the int16→float32 conversion librosa does on every load.
"""

import json
import shutil
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# Codecs that can be stream-copied into WAV without re-encoding
_LOSSLESS_CODECS = {
    "pcm_s16le", "pcm_s24le", "pcm_s32le",
    "pcm_f32le", "pcm_f64le", "pcm_u8",
    "pcm_s16be", "pcm_s24be",
}


class AudioExtractionError(RuntimeError):
    pass


# ── FFmpeg / ffprobe discovery ────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise AudioExtractionError(
            "FFmpeg not found. Install FFmpeg and ensure it is on your PATH.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg\n"
            "  Windows: winget install FFmpeg"
        )
    return path


def _find_ffprobe(ffmpeg: str) -> str:
    probe = shutil.which("ffprobe")
    if probe:
        return probe
    candidate = ffmpeg.replace("ffmpeg", "ffprobe")
    if shutil.which(candidate):
        return candidate
    return candidate


# ── Source audio probing ──────────────────────────────────────────────────────

def _probe(ffprobe: str, video_path: Path) -> dict:
    """
    Return dict: duration (float s), audio_codec (str), sample_rate (int Hz).
    Falls back to safe defaults on any error.
    """
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-select_streams", "a:0",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        info = json.loads(result.stdout)
        duration = float(info.get("format", {}).get("duration", 0) or 0)
        streams = info.get("streams", [])
        if streams:
            s = streams[0]
            codec = s.get("codec_name", "unknown")
            sr = int(s.get("sample_rate", 0) or 0)
        else:
            codec, sr = "unknown", 0
        log.debug(f"Probe: duration={duration:.2f}s  codec={codec}  sr={sr}")
        return {"duration": duration, "audio_codec": codec, "sample_rate": sr}
    except Exception as exc:
        log.warning(f"ffprobe failed ({exc}), using safe defaults")
        return {"duration": 0.0, "audio_codec": "unknown", "sample_rate": 0}


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_audio(
    video_path: Path,
    output_wav: Path,
    sample_rate: int | None = None,
    progress_cb: Callable[[int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    """
    Extract first audio track from *video_path* → *output_wav* (float32 WAV).

    Parameters
    ----------
    video_path  : source video
    output_wav  : destination .wav (created/overwritten)
    sample_rate : force output SR; None = keep native (faster, recommended)
    progress_cb : called with int 0..100
    cancel_check: return True to abort

    Returns output_wav on success; raises AudioExtractionError on failure.
    """
    ffmpeg = _find_ffmpeg()
    ffprobe = _find_ffprobe(ffmpeg)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    probe = _probe(ffprobe, video_path)
    duration = probe["duration"]
    src_codec = probe["audio_codec"]
    src_sr = probe["sample_rate"]

    # ── Decide codec strategy ─────────────────────────────────────────────
    can_copy = (
        src_codec in _LOSSLESS_CODECS
        and (sample_rate is None or sample_rate == src_sr)
    )

    if can_copy:
        log.info(f"Source is lossless PCM ({src_codec}) — stream copy (instant)")
        audio_codec_args = ["-c:a", "copy"]
        sr_args: list[str] = []
    else:
        log.info(f"Transcoding '{src_codec}' → pcm_f32le")
        audio_codec_args = ["-c:a", "pcm_f32le"]
        # Only force resample if explicitly requested AND source SR is known
        if sample_rate and src_sr and sample_rate != src_sr:
            sr_args = ["-ar", str(sample_rate)]
            log.debug(f"Resampling {src_sr} → {sample_rate} Hz")
        else:
            sr_args = []

    cmd = [
        ffmpeg,
        "-nostdin",             # never block waiting for stdin
        "-hide_banner",         # skip version/build info output
        "-loglevel", "error",   # only print actual errors
        "-fflags", "+fastseek", # fast container seeking (MP4/MOV)
        "-threads", "0",        # use ALL available CPU cores
        "-y",                   # overwrite without prompt
        "-i", str(video_path),
        "-vn",                  # skip video entirely — no frame decoding
        *audio_codec_args,
        *sr_args,
        str(output_wav),
    ]

    log.info(f"Extracting: {video_path.name} → {output_wav.name}")
    log.debug("FFmpeg: " + " ".join(cmd))

    if progress_cb:
        progress_cb(1)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,   # no stdout needed
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Drain stderr in background — prevents pipe buffer deadlock
        stderr_lines: list[str] = []

        def _drain_stderr():
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_lines.append(line)

        t_stderr = threading.Thread(target=_drain_stderr, daemon=True)
        t_stderr.start()

        # ── Progress estimation ───────────────────────────────────────────
        # Wall-clock time relative to known duration gives a smooth estimate
        # without needing -progress pipe (which doubled I/O overhead).
        t_start = time.monotonic()
        poll_interval = 0.1  # 100 ms — responsive without burning CPU

        while proc.poll() is None:
            if cancel_check and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise AudioExtractionError("Extraction cancelled by user")

            if duration > 0 and progress_cb:
                elapsed = time.monotonic() - t_start
                # Transcoding ~= real-time; copy = much faster.
                # Estimate caps at 95 until proc exits.
                speed_factor = 4.0 if can_copy else 1.05
                pct = min(95, int(100 * elapsed * speed_factor / duration))
                progress_cb(pct)

            time.sleep(poll_interval)

        t_stderr.join(timeout=3)
        proc.wait()

        if proc.returncode != 0:
            err = "".join(stderr_lines).strip()
            raise AudioExtractionError(
                f"FFmpeg exited {proc.returncode}:\n{err}"
            )

        if not output_wav.exists() or output_wav.stat().st_size == 0:
            raise AudioExtractionError(
                "Output WAV is empty — video may have no audio track."
            )

        elapsed = time.monotonic() - t_start
        size_mb = output_wav.stat().st_size / 1_048_576
        mode = "stream-copy" if can_copy else "transcode"
        log.info(
            f"Done in {elapsed:.2f}s  |  {size_mb:.1f} MB  |  mode={mode}"
        )

        if progress_cb:
            progress_cb(100)

        return output_wav

    except AudioExtractionError:
        raise
    except Exception as exc:
        raise AudioExtractionError(f"Unexpected extraction error: {exc}") from exc
