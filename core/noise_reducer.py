"""
core/noise_reducer.py
Speech-preserving spectral gating noise reducer.

Algorithm overview
──────────────────
1. STFT analysis with Hann window
2. Per-frame adaptive gain computation via spectral gating:
     gain[bin,frame] = sigmoid_ramp(SNR[bin,frame], threshold, strength)
3. Gain smoothing in time (attack / release envelope) to avoid metallic artefacts
4. Optional harmonic preservation: boost gain around detected pitch harmonics
5. Overlap-add reconstruction (ISTFT)

The gain function is a soft-knee sigmoid ramp rather than a hard gate,
which eliminates the "underwater" distortion typical of naive spectral subtraction.
"""

import logging
import numpy as np
import librosa
import scipy.signal as signal
from dataclasses import dataclass
from typing import Callable

from core.noise_estimator import NoiseProfile

log = logging.getLogger(__name__)


@dataclass
class ReducerParams:
    noise_strength: float = 1.5       # multiplier on noise floor (1.0 = exact, 2.0 = aggressive)
    attack_ms: float = 10.0           # gain rise time (ms)
    release_ms: float = 100.0         # gain fall time (ms)
    smoothing_factor: float = 0.5     # temporal smoothing coefficient 0..1
    n_fft: int = 2048
    hop_length: int = 512
    preserve_harmonics: bool = True
    knee_width_db: float = 6.0        # soft-knee width


def reduce_noise(
    y: np.ndarray,
    sr: int,
    noise_profile: NoiseProfile,
    params: ReducerParams | None = None,
    progress_cb: Callable[[int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> np.ndarray:
    """
    Apply spectral gating noise reduction to audio *y*.

    Returns cleaned mono float32 signal.
    """
    if params is None:
        params = ReducerParams()

    log.info(
        f"Noise reduction: strength={params.noise_strength}, "
        f"attack={params.attack_ms}ms, release={params.release_ms}ms"
    )

    n_fft = params.n_fft
    hop_length = params.hop_length

    # ── STFT ──────────────────────────────────────────────────────────────
    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop_length, window="hann")
    magnitude = np.abs(stft)
    phase = np.angle(stft)
    power = magnitude ** 2

    n_bins, n_frames = magnitude.shape

    if progress_cb:
        progress_cb(10)

    # ── Noise power threshold ──────────────────────────────────────────────
    # Resample noise profile if n_fft differs
    noise_pwr = noise_profile.power_spectrum
    if len(noise_pwr) != n_bins:
        x_old = np.linspace(0, 1, len(noise_pwr))
        x_new = np.linspace(0, 1, n_bins)
        noise_pwr = np.interp(x_new, x_old, noise_pwr)

    noise_threshold = noise_pwr * (params.noise_strength ** 2)  # shape (n_bins,)

    if progress_cb:
        progress_cb(20)

    # ── Per-frame SNR and gain ─────────────────────────────────────────────
    # SNR in dB: positive means signal above noise floor
    eps = 1e-12
    snr_db = 10 * np.log10(power / (noise_threshold[:, None] + eps) + eps)

    # Soft-knee sigmoid gain: 0 below threshold, ramps to 1 above
    knee = params.knee_width_db
    gain = _soft_gate(snr_db, knee=knee)  # (n_bins, n_frames)

    if progress_cb:
        progress_cb(40)

    # ── Temporal smoothing: attack / release ──────────────────────────────
    gain = _apply_attack_release(
        gain,
        sr=sr,
        hop_length=hop_length,
        attack_ms=params.attack_ms,
        release_ms=params.release_ms,
    )

    # Additional per-bin temporal smoothing (avoids musical noise)
    alpha = float(np.clip(params.smoothing_factor, 0.0, 0.99))
    gain = _smooth_gain(gain, alpha=alpha)

    if progress_cb:
        progress_cb(60)

    # ── Harmonic preservation ─────────────────────────────────────────────
    if params.preserve_harmonics:
        gain = _boost_harmonics(gain, magnitude, sr=sr, n_fft=n_fft, hop_length=hop_length)

    if progress_cb:
        progress_cb(75)

    # ── Apply gain and reconstruct ─────────────────────────────────────────
    gain = np.clip(gain, 0.0, 1.0)
    stft_clean = gain * magnitude * np.exp(1j * phase)
    y_clean = librosa.istft(stft_clean, hop_length=hop_length, window="hann", length=len(y))

    # Normalise to prevent clipping
    peak = np.abs(y_clean).max()
    if peak > 0:
        y_clean = y_clean * (np.abs(y).max() / peak)

    if progress_cb:
        progress_cb(100)

    log.info("Noise reduction complete")
    return y_clean.astype(np.float32)


# ── Helper functions ──────────────────────────────────────────────────────────

def _soft_gate(snr_db: np.ndarray, knee: float = 6.0) -> np.ndarray:
    """
    Smooth gain transition:
      snr < -knee/2  → 0
      snr > +knee/2  → 1
      in between     → sigmoid ramp
    """
    x = snr_db / max(knee, 0.1)  # normalise
    # Logistic sigmoid, shifted so gate opens around 0 dB SNR
    gain = 1.0 / (1.0 + np.exp(-4.0 * x))
    return gain


def _apply_attack_release(
    gain: np.ndarray,
    sr: int,
    hop_length: int,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    """
    First-order IIR envelope follower applied column-by-column.
    attack_coeff controls rise time; release_coeff controls fall time.
    """
    frame_period = hop_length / sr
    a_att = np.exp(-1.0 / max(attack_ms / 1000 / frame_period, 1e-6))
    a_rel = np.exp(-1.0 / max(release_ms / 1000 / frame_period, 1e-6))

    out = np.empty_like(gain)
    prev = gain[:, 0].copy()
    out[:, 0] = prev

    for t in range(1, gain.shape[1]):
        current = gain[:, t]
        rising = current >= prev
        coeff = np.where(rising, a_att, a_rel)
        prev = coeff * prev + (1.0 - coeff) * current
        out[:, t] = prev

    return out


def _smooth_gain(gain: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """
    Simple temporal IIR smoothing per frequency bin.
    alpha=0: no smoothing; alpha→1: heavy smoothing.
    """
    if alpha <= 0:
        return gain
    out = np.empty_like(gain)
    out[:, 0] = gain[:, 0]
    for t in range(1, gain.shape[1]):
        out[:, t] = alpha * out[:, t - 1] + (1.0 - alpha) * gain[:, t]
    return out


def _boost_harmonics(
    gain: np.ndarray,
    magnitude: np.ndarray,
    sr: int,
    n_fft: int,
    hop_length: int,
    f0_min: float = 80.0,
    f0_max: float = 400.0,
    n_harmonics: int = 5,
) -> np.ndarray:
    """
    Detect fundamental frequency (F0) per frame and ensure gain at harmonic
    multiples is at least 0.5 to preserve speech intelligibility.
    """
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    f0_bins_min = np.searchsorted(freqs, f0_min)
    f0_bins_max = np.searchsorted(freqs, f0_max)

    for t in range(magnitude.shape[1]):
        frame = magnitude[:, t]
        # Rough F0 estimation: peak in f0 range
        peak_bin = f0_bins_min + np.argmax(frame[f0_bins_min:f0_bins_max])
        if peak_bin == f0_bins_min:  # no clear peak
            continue
        f0 = freqs[peak_bin]
        for h in range(1, n_harmonics + 1):
            fh = h * f0
            if fh >= sr / 2:
                break
            bh = np.searchsorted(freqs, fh)
            if bh < len(gain):
                gain[bh, t] = max(gain[bh, t], 0.5)

    return gain
