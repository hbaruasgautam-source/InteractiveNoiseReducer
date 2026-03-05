"""
core/speech_detector.py
Multi-feature speech / voice activity detector.

Uses a combination of:
  1. Short-time energy (RMS)
  2. Zero-crossing rate
  3. Spectral centroid
  4. Spectral flux

Each feature is normalised, combined with learned weights, and thresholded
to produce a boolean frame-level speech mask, which is then smoothed with
morphological operations (dilation + erosion) to reduce fragmentation.
"""

import logging
import numpy as np
import librosa
from scipy.ndimage import binary_dilation, binary_erosion
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SpeechDetectionResult:
    speech_mask: np.ndarray          # bool array, one entry per frame
    frame_times: np.ndarray          # seconds, one entry per frame
    rms: np.ndarray                  # RMS energy per frame
    zcr: np.ndarray                  # zero crossing rate per frame
    spectral_centroid: np.ndarray    # centroid (Hz) per frame
    combined_score: np.ndarray       # 0..1 combined feature score
    threshold: float                 # threshold used for mask
    sample_rate: int
    hop_length: int


def detect_speech(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512,
    n_fft: int = 2048,
    threshold: float | None = None,
    min_speech_duration_ms: float = 80.0,
    min_silence_duration_ms: float = 60.0,
) -> SpeechDetectionResult:
    """
    Detect speech frames in audio signal *y*.

    Parameters
    ----------
    y : np.ndarray  — mono float32 audio
    sr : int        — sample rate
    hop_length : int — STFT hop length in samples
    n_fft : int     — FFT size
    threshold : float | None — override auto threshold (0..1)
    min_speech_duration_ms : float — merge gaps shorter than this
    min_silence_duration_ms : float — merge speech shorter than this

    Returns
    -------
    SpeechDetectionResult
    """
    log.debug(f"Speech detection: {len(y)/sr:.2f}s audio, sr={sr}, hop={hop_length}")

    # ── Feature extraction ────────────────────────────────────────────────
    rms = librosa.feature.rms(y=y, frame_length=n_fft, hop_length=hop_length)[0]
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=n_fft, hop_length=hop_length)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)[0]

    # Spectral flux (frame-to-frame spectral change)
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length))
    flux = np.concatenate([[0], np.sqrt(np.sum(np.diff(S, axis=1) ** 2, axis=0))])
    flux = flux[: len(rms)]  # align lengths

    n_frames = min(len(rms), len(zcr), len(centroid), len(flux))
    rms = rms[:n_frames]
    zcr = zcr[:n_frames]
    centroid = centroid[:n_frames]
    flux = flux[:n_frames]

    def _norm(x: np.ndarray) -> np.ndarray:
        lo, hi = x.min(), x.max()
        if hi == lo:
            return np.zeros_like(x)
        return (x - lo) / (hi - lo)

    rms_n = _norm(rms)
    zcr_n = _norm(zcr)
    centroid_n = _norm(centroid)
    flux_n = _norm(flux)

    # Weighted combination: energy and flux are dominant cues for speech
    combined = (
        0.40 * rms_n
        + 0.15 * zcr_n
        + 0.25 * centroid_n
        + 0.20 * flux_n
    )

    # ── Threshold ─────────────────────────────────────────────────────────
    if threshold is None:
        # Otsu-like: find threshold that maximises between-class variance
        threshold = _otsu_threshold(combined)
        log.debug(f"Auto threshold (Otsu): {threshold:.3f}")

    speech_mask = combined > threshold

    # ── Morphological smoothing ───────────────────────────────────────────
    hop_s = hop_length / sr
    min_speech_frames = max(1, int(min_speech_duration_ms / 1000 / hop_s))
    min_silence_frames = max(1, int(min_silence_duration_ms / 1000 / hop_s))

    speech_mask = binary_dilation(speech_mask, structure=np.ones(min_speech_frames))
    speech_mask = binary_erosion(speech_mask, structure=np.ones(min_silence_frames))

    frame_times = librosa.frames_to_time(
        np.arange(n_frames), sr=sr, hop_length=hop_length
    )

    n_speech = speech_mask.sum()
    log.info(
        f"Speech detection complete: {n_speech}/{n_frames} frames "
        f"= {100*n_speech/max(n_frames,1):.1f}% speech"
    )

    return SpeechDetectionResult(
        speech_mask=speech_mask,
        frame_times=frame_times,
        rms=rms,
        zcr=zcr,
        spectral_centroid=centroid,
        combined_score=combined,
        threshold=threshold,
        sample_rate=sr,
        hop_length=hop_length,
    )


def _otsu_threshold(values: np.ndarray, n_bins: int = 256) -> float:
    hist, bin_edges = np.histogram(values, bins=n_bins, range=(0.0, 1.0))
    hist = hist.astype(float)
    total = hist.sum()
    if total == 0:
        return 0.5
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    best_thresh = 0.5
    best_var = -1.0
    w0 = 0.0
    sum0 = 0.0
    total_mean = np.dot(hist, bin_centers) / total

    for i, (h, c) in enumerate(zip(hist, bin_centers)):
        w0 += h / total
        w1 = 1.0 - w0
        if w0 == 0 or w1 == 0:
            continue
        sum0 += h * c / total
        mu0 = sum0 / w0
        mu1 = (total_mean - sum0) / w1 if w1 > 0 else 0
        var_between = w0 * w1 * (mu0 - mu1) ** 2
        if var_between > best_var:
            best_var = var_between
            best_thresh = bin_edges[i + 1]

    return float(np.clip(best_thresh, 0.1, 0.9))


def resample_mask_to_samples(
    speech_mask: np.ndarray,
    n_samples: int,
    hop_length: int,
) -> np.ndarray:
    """
    Expand frame-level boolean mask to sample-level for waveform highlighting.
    """
    sample_mask = np.zeros(n_samples, dtype=bool)
    for i, val in enumerate(speech_mask):
        start = i * hop_length
        end = min(start + hop_length, n_samples)
        sample_mask[start:end] = val
    return sample_mask
