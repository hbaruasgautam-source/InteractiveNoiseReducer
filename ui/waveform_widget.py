"""
ui/waveform_widget.py
Interactive waveform display with:
  - Zoomable / pannable waveform plot (PyQtGraph)
  - Color-coded speech (green) / noise (red) regions
  - Draggable horizontal threshold line
  - Playhead cursor
  - Selection region for segment playback
"""

import logging
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor

from ui.styles import get_color

log = logging.getLogger(__name__)


class WaveformWidget(QWidget):
    """
    Waveform display with a draggable threshold line.

    Signals
    -------
    threshold_changed(float)  — new threshold value in linear amplitude (0..1)
    region_selected(float, float)  — start/end time in seconds
    """

    threshold_changed = pyqtSignal(float)
    region_selected = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sr = 44100
        self._y: np.ndarray | None = None
        self._speech_mask: np.ndarray | None = None  # sample-level bool
        self._frame_times: np.ndarray | None = None
        self._threshold_linear = 0.05
        self._duration = 0.0
        self._playhead_pos = 0.0
        self._setup_ui()

    # ── Setup ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Info bar
        info_bar = QHBoxLayout()
        self._lbl_duration = QLabel("Duration: —")
        self._lbl_duration.setObjectName("subtitle")
        self._lbl_sr = QLabel("SR: —")
        self._lbl_sr.setObjectName("subtitle")
        self._lbl_threshold = QLabel("Threshold: —")
        self._lbl_threshold.setObjectName("value")
        info_bar.addWidget(self._lbl_duration)
        info_bar.addSpacing(20)
        info_bar.addWidget(self._lbl_sr)
        info_bar.addStretch()
        info_bar.addWidget(self._lbl_threshold)
        layout.addLayout(info_bar)

        # PyQtGraph plot widget
        pg.setConfigOptions(antialias=True, background=get_color("bg_widget"))
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setMinimumHeight(180)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self._plot_widget.setLabel("left", "Amplitude", color=get_color("text_secondary"))
        self._plot_widget.setLabel("bottom", "Time (s)", color=get_color("text_secondary"))
        self._plot_widget.getAxis("left").setTextPen(get_color("text_secondary"))
        self._plot_widget.getAxis("bottom").setTextPen(get_color("text_secondary"))
        self._plot_widget.setMouseEnabled(x=True, y=False)
        layout.addWidget(self._plot_widget)

        # Plot items
        self._speech_regions: list[pg.LinearRegionItem] = []
        self._waveform_plot = self._plot_widget.plot(
            pen=pg.mkPen(color=get_color("waveform_color"), width=1)
        )

        # Threshold line (draggable)
        self._threshold_line = pg.InfiniteLine(
            pos=self._threshold_linear,
            angle=0,
            pen=pg.mkPen(color=get_color("threshold_color"), width=2, style=Qt.PenStyle.DashLine),
            movable=True,
            label="Threshold",
            labelOpts={"color": get_color("threshold_color"), "position": 0.98, "anchors": [(0, 1), (0, 1)]},
        )
        self._threshold_line.sigPositionChanged.connect(self._on_threshold_dragged)
        self._plot_widget.addItem(self._threshold_line)

        # Playhead
        self._playhead = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen(color="#FFFFFF", width=1),
            movable=False,
        )
        self._plot_widget.addItem(self._playhead)

        # Selection region
        self._selection = pg.LinearRegionItem(
            values=(0, 0),
            brush=pg.mkBrush(color=(255, 255, 255, 20)),
            pen=pg.mkPen(color="#FFFFFF", width=1),
            movable=True,
        )
        self._selection.sigRegionChanged.connect(self._on_region_changed)
        self._plot_widget.addItem(self._selection)
        self._selection.setVisible(False)

    # ── Public API ────────────────────────────────────────────────────────

    def load_audio(
        self,
        y: np.ndarray,
        sr: int,
        speech_mask: np.ndarray | None = None,
    ):
        """
        Load audio data and render waveform.

        Parameters
        ----------
        y            : float32 mono audio
        sr           : sample rate
        speech_mask  : optional sample-level bool mask (True = speech)
        """
        self._y = y.astype(np.float32)
        self._sr = sr
        self._speech_mask = speech_mask
        self._duration = len(y) / sr

        self._lbl_duration.setText(f"Duration: {self._duration:.2f}s")
        self._lbl_sr.setText(f"SR: {sr} Hz")

        self._render_waveform()
        self._render_speech_regions()
        self._update_threshold_label()

    def set_threshold(self, linear_value: float):
        """Set threshold line position (linear amplitude 0..1)."""
        self._threshold_linear = float(np.clip(linear_value, 0.0, 1.0))
        self._threshold_line.setPos(self._threshold_linear)
        self._update_threshold_label()

    def set_playhead(self, time_s: float):
        self._playhead_pos = time_s
        self._playhead.setPos(time_s)

    def enable_selection(self, enable: bool):
        self._selection.setVisible(enable)

    def get_selection(self) -> tuple[float, float]:
        r = self._selection.getRegion()
        return float(r[0]), float(r[1])

    def zoom_reset(self):
        if self._y is not None:
            self._plot_widget.setXRange(0, self._duration)
            self._plot_widget.setYRange(-1.0, 1.0)

    def zoom_in(self):
        vb = self._plot_widget.getViewBox()
        vb.scaleBy((0.5, 1.0))

    def zoom_out(self):
        vb = self._plot_widget.getViewBox()
        vb.scaleBy((2.0, 1.0))

    # ── Internal rendering ────────────────────────────────────────────────

    def _render_waveform(self):
        if self._y is None:
            return

        # Downsample for display performance (target ~8000 points)
        y = self._y
        n_target = 8000
        step = max(1, len(y) // n_target)
        y_ds = y[::step]
        t_ds = np.linspace(0, self._duration, len(y_ds))

        self._waveform_plot.setData(t_ds, y_ds)
        self._plot_widget.setXRange(0, self._duration, padding=0)
        self._plot_widget.setYRange(-1.1, 1.1, padding=0)
        self._threshold_line.setBounds((-1.0, 1.0))

    def _render_speech_regions(self):
        # Remove old regions
        for r in self._speech_regions:
            self._plot_widget.removeItem(r)
        self._speech_regions.clear()

        if self._speech_mask is None or self._y is None:
            return

        # Find contiguous speech segments
        mask = self._speech_mask
        n = len(mask)
        sr = self._sr

        in_speech = False
        seg_start = 0

        for i in range(n):
            if mask[i] and not in_speech:
                in_speech = True
                seg_start = i
            elif not mask[i] and in_speech:
                in_speech = False
                self._add_speech_region(seg_start / sr, i / sr)

        if in_speech:
            self._add_speech_region(seg_start / sr, n / sr)

    def _add_speech_region(self, t_start: float, t_end: float):
        speech_color = get_color("speech_color")
        r, g, b = _hex_to_rgb(speech_color)
        region = pg.LinearRegionItem(
            values=(t_start, t_end),
            brush=pg.mkBrush(color=(r, g, b, 35)),
            pen=pg.mkPen(None),
            movable=False,
        )
        self._plot_widget.addItem(region)
        self._speech_regions.append(region)

    def _on_threshold_dragged(self):
        pos = float(self._threshold_line.getPos()[1])
        self._threshold_linear = float(np.clip(pos, 0.0, 1.0))
        self._update_threshold_label()
        self.threshold_changed.emit(self._threshold_linear)

    def _on_region_changed(self):
        r = self._selection.getRegion()
        self.region_selected.emit(float(r[0]), float(r[1]))

    def _update_threshold_label(self):
        db = 20 * np.log10(max(self._threshold_linear, 1e-12))
        self._lbl_threshold.setText(f"Threshold: {self._threshold_linear:.4f} ({db:.1f} dB)")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
