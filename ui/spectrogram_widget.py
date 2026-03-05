"""
ui/spectrogram_widget.py
Spectrogram display using PyQtGraph ImageItem with custom colormap.
Shows frequency (Y) vs time (X) with intensity mapped to a neon color ramp.
"""

import logging
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

import librosa

from ui.styles import get_color

log = logging.getLogger(__name__)


class SpectrogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sr = 44100
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Info bar
        info_bar = QHBoxLayout()
        self._lbl_info = QLabel("Spectrogram — load audio to view")
        self._lbl_info.setObjectName("subtitle")
        info_bar.addWidget(self._lbl_info)
        info_bar.addStretch()

        self._lbl_freq = QLabel("")
        self._lbl_freq.setObjectName("value")
        info_bar.addWidget(self._lbl_freq)
        layout.addLayout(info_bar)

        pg.setConfigOptions(antialias=False)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setMinimumHeight(180)
        self._plot_widget.setLabel("left", "Frequency (Hz)", color=get_color("text_secondary"))
        self._plot_widget.setLabel("bottom", "Time (s)", color=get_color("text_secondary"))
        self._plot_widget.getAxis("left").setTextPen(get_color("text_secondary"))
        self._plot_widget.getAxis("bottom").setTextPen(get_color("text_secondary"))

        self._image_item = pg.ImageItem()
        self._plot_widget.addItem(self._image_item)
        layout.addWidget(self._plot_widget)

    def load_audio(self, y: np.ndarray, sr: int, n_fft: int = 2048, hop_length: int = 512):
        """Compute and display mel spectrogram."""
        self._sr = sr
        log.debug("Computing spectrogram…")

        # Mel spectrogram in dB
        S = librosa.feature.melspectrogram(
            y=y.astype(np.float32),
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=128,
            fmax=min(sr // 2, 8000),
        )
        S_db = librosa.power_to_db(S, ref=np.max)

        # Normalise to 0..1
        S_norm = (S_db - S_db.min()) / (S_db.max() - S_db.min() + 1e-12)

        # Apply neon colormap (dark blue → cyan → white)
        img_data = _apply_colormap_neon(S_norm)  # (n_mels, n_frames, 4) RGBA uint8

        duration = len(y) / sr
        freq_max = min(sr // 2, 8000)

        # Set transform: map image pixels → time/frequency axes
        self._image_item.setImage(
            img_data.transpose(1, 0, 2),  # PyQtGraph expects (width, height, channels)
            autoLevels=False,
        )
        tr = pg.QtGui.QTransform()
        tr.scale(duration / S_norm.shape[1], freq_max / S_norm.shape[0])
        self._image_item.setTransform(tr)

        self._plot_widget.setXRange(0, duration, padding=0)
        self._plot_widget.setYRange(0, freq_max, padding=0)

        self._lbl_info.setText(
            f"Mel Spectrogram — {S_norm.shape[1]} frames × {S_norm.shape[0]} mels"
        )
        log.info("Spectrogram rendered")


def _apply_colormap_neon(data: np.ndarray) -> np.ndarray:
    """
    Map normalised 0..1 values to RGBA using a neon cyan colormap.
    Black (0,0,0) → Dark Blue (0,0,80) → Cyan (0,229,255) → White (255,255,255)
    """
    n_mels, n_frames = data.shape
    rgba = np.zeros((n_mels, n_frames, 4), dtype=np.uint8)

    x = data  # 0..1

    # Red channel: 0 until x>0.7, then rises to 255
    rgba[:, :, 0] = np.clip((x - 0.7) / 0.3 * 255, 0, 255).astype(np.uint8)

    # Green channel: 0 until x>0.5, rises to 255
    rgba[:, :, 1] = np.clip((x - 0.5) / 0.5 * 255, 0, 255).astype(np.uint8)

    # Blue channel: rises steeply from 0, peaks at ~0.6, then stays at 255
    rgba[:, :, 2] = np.clip(x / 0.6 * 255, 0, 255).astype(np.uint8)

    # Alpha: fully opaque
    rgba[:, :, 3] = 255

    return rgba
