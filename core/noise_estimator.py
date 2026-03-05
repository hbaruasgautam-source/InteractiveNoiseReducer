"""
core/noise_estimator.py
Adaptive noise floor estimation.

Strategy:
  1. Identify non-speech (silence) frames from the speech mask
  2. Build an average power spectrum from those frames (noise profile)
  3. Apply percentile smoothing for robustness against transient noise
  4. Fall back to first-N-frames estimate when no silence found
"""

import logging
import numpy as np
import librosa
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class NoiseProfile:
    power_spectrum: np.ndarray   # shape (n_fft//2+1,) — mean noise power per bin
    freqs: np.ndarray            # Hz for each bin
    sample_rate: int
    n_fft: int
    hop_length: int
    n_noise_frames: int          # how many silence frames were averaged


def estimate_noise_profile(
    y: np.ndarray,
    sr: int,
    speech_mask: np.ndarray,
    n_fft: int = 2048,
    hop_length: int = 512,
    percentile: float = 80.0,
) -> NoiseProfile:
    """
    Estimate the spectral noise floor from non-speech frames.

    Parameters
    ----------
    y            : mono float32 audio
    sr           : sample rate
    speech_mask  : bool array (frame-level), True = speech
    n_fft        : FFT size
    hop_length   : hop length in samples
    percentile   : percentile for noise profile smoothing (default 80)

    Returns
    -------
    NoiseProfile
    """
    log.debug("Estimating noise profile…")

    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    power = np.abs(stft) ** 2  # shape (n_bins, n_frames)
    n_bins, n_frames = power.shape

    # Align mask length to STFT frames
    mask = speech_mask[:n_frames]
    noise_indices = np.where(~mask)[0]

    if len(noise_indices) < 5:
        log.warning("Insufficient silence frames; using first 20 frames for noise estimate")
        n_seed = min(20, n_frames)
        noise_indices = np.arange(n_seed)

    noise_frames = power[:, noise_indices]  # (n_bins, n_noise_frames)
    # Percentile is more robust than mean against outlier transients
    noise_power = np.percentile(noise_frames, percentile, axis=1)
    # Light smoothing across frequency bins (3-point moving average)
    noise_power = np.convolve(noise_power, np.ones(3) / 3, mode="same")
    noise_power = np.maximum(noise_power, 1e-12)  # floor > 0

    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    log.info(
        f"Noise profile estimated from {len(noise_indices)} silence frames "
        f"(n_fft={n_fft}, hop={hop_length})"
    )

    return NoiseProfile(
        power_spectrum=noise_power,
        freqs=freqs,
        sample_rate=sr,
        n_fft=n_fft,
        hop_length=hop_length,
        n_noise_frames=len(noise_indices),
    )
