"""
ui/main_window.py
Main application window.

Layout (top → bottom):
  ┌── MenuBar ─────────────────────────────────────────────────────┐
  │ File  View  Presets  Help                                       │
  ├── Toolbar (file load, extract, preview, export buttons) ───────┤
  │  [Load Video] [Extract Audio] ···· [▶ Original] [▶ Processed]  │
  │  [◼ Cancel]                          [Export Video] [Audio Only]│
  ├── Main content (splitter: left controls | right viz) ───────────┤
  │ LEFT PANEL                        RIGHT PANEL                   │
  │ ┌─ Noise Params ────────────┐   ┌─ Tab: Waveform │ Spectrogram ┐│
  │ │ Strength  ───────── [val] │   │  WaveformWidget              ││
  │ │ Attack    ───────── [val] │   │  SpectrogramWidget           ││
  │ │ Release   ───────── [val] │   └──────────────────────────────┘│
  │ │ Smoothing ───────── [val] │                                   │
  │ │ FFT Size  [combo]         │                                   │
  │ │ Hop Length [combo]        │                                   │
  │ │ Output Quality [combo]    │                                   │
  │ │ [Run Noise Reduction]     │                                   │
  │ └───────────────────────────┘                                   │
  ├── Progress Bar ────────────────────────────────────────────────┤
  ├── Log Console ─────────────────────────────────────────────────┤
  └── StatusBar ───────────────────────────────────────────────────┘
"""

import logging
import tempfile
import threading
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QSlider, QLabel, QComboBox, QGroupBox, QTabWidget,
    QTextEdit, QFileDialog, QProgressBar, QStatusBar, QCheckBox,
    QMessageBox, QMenuBar, QMenu, QInputDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QTextCursor, QColor

from core.config_manager import ConfigManager
from core.audio_extractor import extract_audio, AudioExtractionError
from core.speech_detector import detect_speech, resample_mask_to_samples
from core.noise_estimator import estimate_noise_profile
from core.noise_reducer import reduce_noise, ReducerParams
from core.video_renderer import render_video, export_audio_only, VideoRenderError
from ui.waveform_widget import WaveformWidget
from ui.spectrogram_widget import SpectrogramWidget
from ui.styles import apply_theme, get_color

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Worker thread wrappers
# ══════════════════════════════════════════════════════════════════════════════

class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str)
    finished = pyqtSignal(object)    # payload varies per task
    error = pyqtSignal(str)


class ExtractWorker(QThread):
    def __init__(self, video_path: Path, wav_path: Path, sr: int):
        super().__init__()
        self.signals = WorkerSignals()
        self._video = video_path
        self._wav = wav_path
        self._sr = sr
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.signals.log_msg.emit(f"Extracting audio from: {self._video.name}")
            result = extract_audio(
                self._video, self._wav, self._sr,
                progress_cb=self.signals.progress.emit,
                cancel_check=lambda: self._cancel,
            )
            self.signals.finished.emit(str(result))
        except Exception as exc:
            self.signals.error.emit(str(exc))


class AnalyseWorker(QThread):
    def __init__(self, wav_path: Path, n_fft: int, hop: int):
        super().__init__()
        self.signals = WorkerSignals()
        self._wav = wav_path
        self._n_fft = n_fft
        self._hop = hop

    def run(self):
        try:
            self.signals.log_msg.emit("Loading audio…")
            self.signals.progress.emit(5)
            y, sr = librosa.load(str(self._wav), sr=None, mono=True)
            self.signals.progress.emit(20)

            self.signals.log_msg.emit("Detecting speech regions…")
            det = detect_speech(y, sr, hop_length=self._hop, n_fft=self._n_fft)
            self.signals.progress.emit(60)

            self.signals.log_msg.emit("Estimating noise profile…")
            profile = estimate_noise_profile(y, sr, det.speech_mask, self._n_fft, self._hop)
            self.signals.progress.emit(90)

            sample_mask = resample_mask_to_samples(det.speech_mask, len(y), self._hop)
            self.signals.progress.emit(100)
            self.signals.finished.emit({
                "y": y, "sr": sr,
                "detection": det,
                "profile": profile,
                "sample_mask": sample_mask,
            })
        except Exception as exc:
            self.signals.error.emit(str(exc))


class ReduceWorker(QThread):
    def __init__(self, y, sr, profile, params: ReducerParams):
        super().__init__()
        self.signals = WorkerSignals()
        self._y = y
        self._sr = sr
        self._profile = profile
        self._params = params
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.signals.log_msg.emit("Running noise reduction…")
            y_clean = reduce_noise(
                self._y, self._sr, self._profile, self._params,
                progress_cb=self.signals.progress.emit,
                cancel_check=lambda: self._cancel,
            )
            self.signals.finished.emit(y_clean)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class RenderWorker(QThread):
    def __init__(self, video_path, y_clean, sr, out_path, quality):
        super().__init__()
        self.signals = WorkerSignals()
        self._video = video_path
        self._y_clean = y_clean
        self._sr = sr
        self._out = out_path
        self._quality = quality
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.signals.log_msg.emit(f"Rendering video → {self._out.name}")
            out = render_video(
                self._video, self._y_clean, self._sr, self._out, self._quality,
                progress_cb=self.signals.progress.emit,
                cancel_check=lambda: self._cancel,
            )
            self.signals.finished.emit(str(out))
        except Exception as exc:
            self.signals.error.emit(str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Log handler that emits to the GUI console
# ══════════════════════════════════════════════════════════════════════════════

class QtLogHandler(logging.Handler):
    def __init__(self, text_widget: QTextEdit):
        super().__init__()
        self._widget = text_widget
        self.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record):
        msg = self.format(record)
        level = record.levelno
        color = {
            logging.DEBUG:    "#555555",
            logging.INFO:     "#88CC88",
            logging.WARNING:  "#FFB300",
            logging.ERROR:    "#FF5555",
            logging.CRITICAL: "#FF3D3D",
        }.get(level, "#88CC88")
        self._widget.append(f'<span style="color:{color};">{msg}</span>')
        self._widget.moveCursor(QTextCursor.MoveOperation.End)


# ══════════════════════════════════════════════════════════════════════════════
# Main Window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self._config = config
        self._theme = config.get("theme", "dark")

        # State
        self._video_path: Path | None = None
        self._wav_path: Path | None = None
        self._y: np.ndarray | None = None
        self._y_clean: np.ndarray | None = None
        self._sr: int = 44100
        self._noise_profile = None
        self._speech_detection = None
        self._worker: QThread | None = None

        # Audio playback
        self._playback_timer = QTimer()
        self._playback_timer.setInterval(50)
        self._playback_pos = 0.0
        self._is_playing = False

        self.setWindowTitle("InteractiveNoiseReducer v1.0")
        self.setMinimumSize(1200, 780)
        self.resize(1440, 900)

        self._build_menu()
        self._build_ui()
        self._connect_signals()

        log.info("InteractiveNoiseReducer ready")

    # ── Menu ──────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("File")
        a = QAction("Open Video…", self); a.setShortcut("Ctrl+O"); a.triggered.connect(self._open_video); file_menu.addAction(a)
        a = QAction("Export Cleaned Video…", self); a.setShortcut("Ctrl+E"); a.triggered.connect(self._export_video); file_menu.addAction(a)
        a = QAction("Export Audio Only…", self); a.triggered.connect(self._export_audio_only); file_menu.addAction(a)
        file_menu.addSeparator()
        a = QAction("Quit", self); a.setShortcut("Ctrl+Q"); a.triggered.connect(self.close); file_menu.addAction(a)

        # View
        view_menu = mb.addMenu("View")
        a = QAction("Toggle Dark / Light Theme", self); a.triggered.connect(self._toggle_theme); view_menu.addAction(a)
        a = QAction("Reset Zoom", self); a.triggered.connect(self._reset_zoom); view_menu.addAction(a)
        a = QAction("Clear Log", self); a.triggered.connect(lambda: self._log_console.clear()); view_menu.addAction(a)

        # Presets
        preset_menu = mb.addMenu("Presets")
        a = QAction("Save Current Preset…", self); a.triggered.connect(self._save_preset); preset_menu.addAction(a)
        a = QAction("Load Preset…", self); a.triggered.connect(self._load_preset); preset_menu.addAction(a)

        # Help
        help_menu = mb.addMenu("Help")
        a = QAction("About", self); a.triggered.connect(self._show_about); help_menu.addAction(a)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(8, 6, 8, 6)

        # ── Title bar ──────────────────────────────────────────
        title_row = QHBoxLayout()
        lbl_title = QLabel("INTERACTIVE NOISE REDUCER")
        lbl_title.setObjectName("title")
        lbl_sub = QLabel("Speech-Preserving Background Noise Reduction System")
        lbl_sub.setObjectName("subtitle")
        title_row.addWidget(lbl_title)
        title_row.addSpacing(16)
        title_row.addWidget(lbl_sub)
        title_row.addStretch()
        self._lbl_status_file = QLabel("No file loaded")
        self._lbl_status_file.setObjectName("subtitle")
        title_row.addWidget(self._lbl_status_file)
        root.addLayout(title_row)

        # ── Toolbar ────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._btn_open = QPushButton("📂  Open Video")
        self._btn_extract = QPushButton("⚡  Extract Audio")
        self._btn_extract.setEnabled(False)
        self._btn_analyse = QPushButton("🔍  Analyse")
        self._btn_analyse.setEnabled(False)
        self._btn_run = QPushButton("▶  Reduce Noise")
        self._btn_run.setObjectName("primary")
        self._btn_run.setEnabled(False)
        self._btn_cancel = QPushButton("◼  Cancel")
        self._btn_cancel.setObjectName("danger")
        self._btn_cancel.setEnabled(False)

        toolbar.addWidget(self._btn_open)
        toolbar.addWidget(self._btn_extract)
        toolbar.addWidget(self._btn_analyse)
        toolbar.addWidget(self._btn_run)
        toolbar.addWidget(self._btn_cancel)
        toolbar.addSpacing(20)

        self._btn_play_orig = QPushButton("▶ Original")
        self._btn_play_orig.setEnabled(False)
        self._btn_play_clean = QPushButton("▶ Processed")
        self._btn_play_clean.setEnabled(False)
        self._btn_stop = QPushButton("■ Stop")
        self._btn_stop.setEnabled(False)
        toolbar.addWidget(self._btn_play_orig)
        toolbar.addWidget(self._btn_play_clean)
        toolbar.addWidget(self._btn_stop)
        toolbar.addStretch()

        self._btn_export_video = QPushButton("💾  Export Video")
        self._btn_export_video.setObjectName("primary")
        self._btn_export_video.setEnabled(False)
        self._btn_export_audio = QPushButton("🎵  Audio Only")
        self._btn_export_audio.setEnabled(False)
        toolbar.addWidget(self._btn_export_video)
        toolbar.addWidget(self._btn_export_audio)
        root.addLayout(toolbar)

        # ── Main splitter ──────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left: control panel
        left_panel = self._build_left_panel()
        splitter.addWidget(left_panel)

        # Right: visualisation
        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 920])
        root.addWidget(splitter, stretch=1)

        # ── Progress bar ───────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(14)
        self._progress.setTextVisible(True)
        self._progress.setFormat(" %p%")
        root.addWidget(self._progress)

        # ── Log console ────────────────────────────────────────
        log_group = QGroupBox("PROCESSING LOG")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self._log_console = QTextEdit()
        self._log_console.setObjectName("log_console")
        self._log_console.setReadOnly(True)
        self._log_console.setMaximumHeight(140)
        log_layout.addWidget(self._log_console)
        root.addWidget(log_group)

        # Attach GUI log handler
        gui_handler = QtLogHandler(self._log_console)
        gui_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(gui_handler)

        # Status bar
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ── Noise Reduction Parameters ─────────────────────────
        nr_group = QGroupBox("NOISE REDUCTION")
        nr_layout = QVBoxLayout(nr_group)
        nr_layout.setSpacing(6)

        self._row_strength, self._sld_strength, self._lbl_strength = self._make_slider(
            "Strength", 10, 50, int(self._config.get("noise_strength", 1.5) * 10),
            lambda v: f"{v/10:.1f}×"
        )
        self._row_attack, self._sld_attack, self._lbl_attack = self._make_slider(
            "Attack (ms)", 1, 200, int(self._config.get("attack_ms", 10)),
            lambda v: f"{v} ms"
        )
        self._row_release, self._sld_release, self._lbl_release = self._make_slider(
            "Release (ms)", 10, 500, int(self._config.get("release_ms", 100)),
            lambda v: f"{v} ms"
        )
        self._row_smooth, self._sld_smooth, self._lbl_smooth = self._make_slider(
            "Smoothing", 0, 99, int(self._config.get("smoothing_factor", 0.5) * 100),
            lambda v: f"{v/100:.2f}"
        )

        for row_widget in [self._row_strength, self._row_attack, self._row_release, self._row_smooth]:
            nr_layout.addWidget(row_widget)

        # FFT / Hop combos
        fft_row = QHBoxLayout()
        fft_row.addWidget(QLabel("FFT Size"))
        self._combo_fft = QComboBox()
        self._combo_fft.addItems(["512", "1024", "2048", "4096"])
        self._combo_fft.setCurrentText(str(self._config.get("fft_size", 2048)))
        fft_row.addWidget(self._combo_fft)
        nr_layout.addLayout(fft_row)

        hop_row = QHBoxLayout()
        hop_row.addWidget(QLabel("Hop Length"))
        self._combo_hop = QComboBox()
        self._combo_hop.addItems(["128", "256", "512", "1024"])
        self._combo_hop.setCurrentText(str(self._config.get("hop_length", 512)))
        hop_row.addWidget(self._combo_hop)
        nr_layout.addLayout(hop_row)

        self._chk_harmonics = QCheckBox("Preserve Harmonics")
        self._chk_harmonics.setChecked(True)
        nr_layout.addWidget(self._chk_harmonics)

        layout.addWidget(nr_group)

        # ── Output Settings ────────────────────────────────────
        out_group = QGroupBox("OUTPUT SETTINGS")
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(6)

        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel("Quality"))
        self._combo_quality = QComboBox()
        self._combo_quality.addItems(["low", "medium", "high", "lossless"])
        self._combo_quality.setCurrentText(self._config.get("output_quality", "high"))
        qual_row.addWidget(self._combo_quality)
        out_layout.addLayout(qual_row)

        layout.addWidget(out_group)

        # ── Zoom Controls ──────────────────────────────────────
        zoom_group = QGroupBox("ZOOM")
        zoom_layout = QHBoxLayout(zoom_group)
        zoom_layout.setSpacing(4)
        btn_zi = QPushButton("🔍+")
        btn_zo = QPushButton("🔍−")
        btn_zr = QPushButton("Reset")
        btn_zi.clicked.connect(lambda: self._waveform.zoom_in())
        btn_zo.clicked.connect(lambda: self._waveform.zoom_out())
        btn_zr.clicked.connect(self._reset_zoom)
        zoom_layout.addWidget(btn_zi)
        zoom_layout.addWidget(btn_zo)
        zoom_layout.addWidget(btn_zr)
        layout.addWidget(zoom_group)

        # ── Selection ──────────────────────────────────────────
        sel_group = QGroupBox("SEGMENT PLAYBACK")
        sel_layout = QVBoxLayout(sel_group)
        self._chk_selection = QCheckBox("Enable Selection Region")
        self._chk_selection.toggled.connect(lambda v: self._waveform.enable_selection(v))
        sel_layout.addWidget(self._chk_selection)
        self._btn_play_segment = QPushButton("▶ Play Segment")
        self._btn_play_segment.setEnabled(False)
        sel_layout.addWidget(self._btn_play_segment)
        layout.addWidget(sel_group)

        layout.addStretch()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Waveform tab
        wf_tab = QWidget()
        wf_layout = QVBoxLayout(wf_tab)
        wf_layout.setContentsMargins(4, 4, 4, 4)
        self._waveform = WaveformWidget()
        wf_layout.addWidget(self._waveform)
        tabs.addTab(wf_tab, "🔊  WAVEFORM")

        # Spectrogram tab
        sp_tab = QWidget()
        sp_layout = QVBoxLayout(sp_tab)
        sp_layout.setContentsMargins(4, 4, 4, 4)
        self._spectrogram = SpectrogramWidget()
        sp_layout.addWidget(self._spectrogram)
        tabs.addTab(sp_tab, "🎛  SPECTROGRAM")

        layout.addWidget(tabs)
        return panel

    # ── Slider helper ─────────────────────────────────────────────────────

    def _make_slider(self, label_text, lo, hi, initial, fmt_fn):
        """
        Build a labelled slider row.
        Returns (container_widget, slider, value_label).
        Caller must add container_widget to a layout — this keeps it alive.
        """
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        lbl_name = QLabel(label_text)
        lbl_name.setMinimumWidth(90)
        lbl_name.setObjectName("subtitle")

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(initial)
        slider.setTickInterval(max(1, (hi - lo) // 10))

        lbl_val = QLabel(fmt_fn(initial))
        lbl_val.setObjectName("value")
        lbl_val.setMinimumWidth(60)
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        slider.valueChanged.connect(lambda v, f=fmt_fn, l=lbl_val: l.setText(f(v)))

        row.addWidget(lbl_name)
        row.addWidget(slider, stretch=1)
        row.addWidget(lbl_val)

        return container, slider, lbl_val

    # ── Signal connections ────────────────────────────────────────────────

    def _connect_signals(self):
        self._btn_open.clicked.connect(self._open_video)
        self._btn_extract.clicked.connect(self._extract_audio)
        self._btn_analyse.clicked.connect(self._analyse_audio)
        self._btn_run.clicked.connect(self._run_noise_reduction)
        self._btn_cancel.clicked.connect(self._cancel_worker)
        self._btn_export_video.clicked.connect(self._export_video)
        self._btn_export_audio.clicked.connect(self._export_audio_only)
        self._btn_play_orig.clicked.connect(lambda: self._play_audio(original=True))
        self._btn_play_clean.clicked.connect(lambda: self._play_audio(original=False))
        self._btn_stop.clicked.connect(self._stop_audio)
        self._btn_play_segment.clicked.connect(self._play_segment)
        self._chk_selection.toggled.connect(
            lambda v: self._btn_play_segment.setEnabled(v and self._y is not None)
        )
        self._waveform.threshold_changed.connect(self._on_threshold_changed)

    # ── Actions ───────────────────────────────────────────────────────────

    def _open_video(self):
        last = self._config.get("last_input_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", last,
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv);;All Files (*)"
        )
        if not path:
            return
        self._video_path = Path(path)
        self._config.set("last_input_dir", str(self._video_path.parent))
        self._lbl_status_file.setText(f"📹 {self._video_path.name}")
        self._btn_extract.setEnabled(True)
        self._statusbar.showMessage(f"Loaded: {self._video_path.name}")
        log.info(f"Video loaded: {self._video_path}")

    def _extract_audio(self):
        if not self._video_path:
            return
        tmp_dir = Path(tempfile.gettempdir()) / "InteractiveNoiseReducer"
        tmp_dir.mkdir(exist_ok=True)
        self._wav_path = tmp_dir / (self._video_path.stem + "_extracted.wav")

        sr = self._config.get("sample_rate", 44100)
        self._worker = ExtractWorker(self._video_path, self._wav_path, sr)
        self._connect_worker(self._worker)
        self._worker.signals.finished.connect(self._on_extract_done)
        self._set_busy(True, "Extracting audio…")
        self._worker.start()

    def _on_extract_done(self, result):
        self._set_busy(False)
        self._btn_analyse.setEnabled(True)
        self._statusbar.showMessage("Audio extracted — click Analyse")
        log.info(f"Extraction done: {result}")

    def _analyse_audio(self):
        if not self._wav_path:
            return
        n_fft = int(self._combo_fft.currentText())
        hop = int(self._combo_hop.currentText())
        self._worker = AnalyseWorker(self._wav_path, n_fft, hop)
        self._connect_worker(self._worker)
        self._worker.signals.finished.connect(self._on_analyse_done)
        self._set_busy(True, "Analysing audio…")
        self._worker.start()

    def _on_analyse_done(self, result: dict):
        self._y = result["y"]
        self._sr = result["sr"]
        self._noise_profile = result["profile"]
        self._speech_detection = result["detection"]

        # Update waveform
        self._waveform.load_audio(self._y, self._sr, result["sample_mask"])
        # Update spectrogram
        n_fft = int(self._combo_fft.currentText())
        hop = int(self._combo_hop.currentText())
        self._spectrogram.load_audio(self._y, self._sr, n_fft, hop)

        det = self._speech_detection
        n_speech = det.speech_mask.sum()
        pct = 100 * n_speech / max(len(det.speech_mask), 1)
        log.info(f"Analysis complete — {pct:.1f}% speech detected")

        self._btn_run.setEnabled(True)
        self._btn_play_orig.setEnabled(True)
        self._set_busy(False)
        self._statusbar.showMessage(f"Analysis done — {pct:.1f}% speech detected")

    def _run_noise_reduction(self):
        if self._y is None or self._noise_profile is None:
            return

        params = ReducerParams(
            noise_strength=self._sld_strength.value() / 10,
            attack_ms=self._sld_attack.value(),
            release_ms=self._sld_release.value(),
            smoothing_factor=self._sld_smooth.value() / 100,
            n_fft=int(self._combo_fft.currentText()),
            hop_length=int(self._combo_hop.currentText()),
            preserve_harmonics=self._chk_harmonics.isChecked(),
        )
        # Save to config
        self._config.set("noise_strength", params.noise_strength)
        self._config.set("attack_ms", params.attack_ms)
        self._config.set("release_ms", params.release_ms)
        self._config.set("smoothing_factor", params.smoothing_factor)

        self._worker = ReduceWorker(self._y, self._sr, self._noise_profile, params)
        self._connect_worker(self._worker)
        self._worker.signals.finished.connect(self._on_reduce_done)
        self._set_busy(True, "Reducing noise…")
        self._worker.start()

    def _on_reduce_done(self, y_clean: np.ndarray):
        self._y_clean = y_clean
        # Save to temp WAV for playback
        tmp_dir = Path(tempfile.gettempdir()) / "InteractiveNoiseReducer"
        self._clean_wav = tmp_dir / "cleaned.wav"
        sf.write(str(self._clean_wav), y_clean, self._sr)

        self._btn_play_clean.setEnabled(True)
        self._btn_export_video.setEnabled(True)
        self._btn_export_audio.setEnabled(True)
        self._set_busy(False)
        log.info("Noise reduction complete — ready to export")
        self._statusbar.showMessage("Noise reduction done — export available")

    def _export_video(self):
        if self._y_clean is None or self._video_path is None:
            QMessageBox.warning(self, "Not Ready", "Run noise reduction first")
            return
        last = self._config.get("last_output_dir", "")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Cleaned Video", last,
            "MP4 Video (*.mp4);;MKV Video (*.mkv);;All Files (*)"
        )
        if not path:
            return
        out_path = Path(path)
        self._config.set("last_output_dir", str(out_path.parent))
        quality = self._combo_quality.currentText()
        self._worker = RenderWorker(self._video_path, self._y_clean, self._sr, out_path, quality)
        self._connect_worker(self._worker)
        self._worker.signals.finished.connect(
            lambda p: (self._set_busy(False), self._statusbar.showMessage(f"Exported: {p}"),
                       QMessageBox.information(self, "Export Complete", f"Saved to:\n{p}"))
        )
        self._set_busy(True, "Rendering video…")
        self._worker.start()

    def _export_audio_only(self):
        if self._y_clean is None:
            QMessageBox.warning(self, "Not Ready", "Run noise reduction first")
            return
        last = self._config.get("last_output_dir", "")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Cleaned Audio", last,
            "WAV Audio (*.wav);;All Files (*)"
        )
        if not path:
            return
        out = export_audio_only(self._y_clean, self._sr, Path(path))
        QMessageBox.information(self, "Export Complete", f"Audio saved to:\n{out}")

    def _cancel_worker(self):
        if self._worker and hasattr(self._worker, "cancel"):
            self._worker.cancel()
            log.warning("Cancellation requested")

    # ── Audio playback (via sounddevice) ─────────────────────────────────

    def _play_audio(self, original: bool = True):
        y = self._y if original else self._y_clean
        if y is None:
            return
        try:
            import sounddevice as sd
            sd.stop()
            sd.play(y, self._sr)
            self._btn_stop.setEnabled(True)
            label = "Original" if original else "Processed"
            self._statusbar.showMessage(f"Playing {label}…")
        except Exception as exc:
            log.error(f"Playback error: {exc}")
            self._statusbar.showMessage(f"Playback error: {exc}")

    def _play_segment(self):
        if self._y is None:
            return
        t0, t1 = self._waveform.get_selection()
        t0, t1 = max(0, t0), min(len(self._y) / self._sr, t1)
        if t1 <= t0:
            return
        s0, s1 = int(t0 * self._sr), int(t1 * self._sr)
        y_seg = self._y[s0:s1]
        try:
            import sounddevice as sd
            sd.stop()
            sd.play(y_seg, self._sr)
            self._btn_stop.setEnabled(True)
        except Exception as exc:
            log.error(f"Segment playback error: {exc}")

    def _stop_audio(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        self._btn_stop.setEnabled(False)
        self._statusbar.showMessage("Playback stopped")

    # ── Threshold ─────────────────────────────────────────────────────────

    def _on_threshold_changed(self, linear: float):
        if self._speech_detection is None or self._y is None:
            return
        # Recompute threshold in normalised combined score space
        det = self._speech_detection
        # Map amplitude threshold to combined score threshold via percentile
        # (rough heuristic: energy is the dominant cue)
        score_thresh = float(np.clip(linear * 3.0, 0.0, 0.95))
        new_mask = det.combined_score > score_thresh

        from scipy.ndimage import binary_dilation, binary_erosion
        hop_s = det.hop_length / det.sample_rate
        min_frames = max(1, int(80 / 1000 / hop_s))
        new_mask = binary_dilation(new_mask, structure=np.ones(min_frames))
        new_mask = binary_erosion(new_mask, structure=np.ones(min_frames // 2 + 1))

        sample_mask = resample_mask_to_samples(new_mask, len(self._y), det.hop_length)
        self._waveform.load_audio(self._y, self._sr, sample_mask)
        self._speech_detection.speech_mask = new_mask

        n_speech = new_mask.sum()
        pct = 100 * n_speech / max(len(new_mask), 1)
        self._statusbar.showMessage(f"Threshold updated — {pct:.1f}% speech")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _connect_worker(self, worker):
        worker.signals.progress.connect(self._progress.setValue)
        worker.signals.log_msg.connect(lambda m: log.info(m))
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.finished.connect(lambda _: None)  # handled per-task

    def _on_worker_error(self, msg: str):
        self._set_busy(False)
        log.error(f"Worker error: {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _set_busy(self, busy: bool, message: str = ""):
        self._btn_extract.setEnabled(not busy and self._video_path is not None)
        self._btn_analyse.setEnabled(not busy and self._wav_path is not None)
        self._btn_run.setEnabled(not busy and self._y is not None)
        self._btn_cancel.setEnabled(busy)
        self._btn_export_video.setEnabled(not busy and self._y_clean is not None)
        self._btn_export_audio.setEnabled(not busy and self._y_clean is not None)
        if busy and message:
            self._statusbar.showMessage(message)
        elif not busy:
            self._progress.setValue(0)

    def _reset_zoom(self):
        self._waveform.zoom_reset()

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self._config.set("theme", self._theme)
        from PyQt6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), self._theme)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name.strip():
            return
        params = {
            "noise_strength": self._sld_strength.value() / 10,
            "attack_ms": self._sld_attack.value(),
            "release_ms": self._sld_release.value(),
            "smoothing_factor": self._sld_smooth.value() / 100,
            "fft_size": self._combo_fft.currentText(),
            "hop_length": self._combo_hop.currentText(),
            "preserve_harmonics": self._chk_harmonics.isChecked(),
        }
        self._config.save_preset(name.strip(), params)
        QMessageBox.information(self, "Preset Saved", f"Preset '{name}' saved.")

    def _load_preset(self):
        presets = self._config.list_presets()
        if not presets:
            QMessageBox.information(self, "No Presets", "No presets saved yet.")
            return
        name, ok = QInputDialog.getItem(self, "Load Preset", "Select preset:", presets, 0, False)
        if not ok:
            return
        p = self._config.get_preset(name)
        if not p:
            return
        self._sld_strength.setValue(int(p.get("noise_strength", 1.5) * 10))
        self._sld_attack.setValue(int(p.get("attack_ms", 10)))
        self._sld_release.setValue(int(p.get("release_ms", 100)))
        self._sld_smooth.setValue(int(p.get("smoothing_factor", 0.5) * 100))
        self._combo_fft.setCurrentText(str(p.get("fft_size", 2048)))
        self._combo_hop.setCurrentText(str(p.get("hop_length", 512)))
        self._chk_harmonics.setChecked(p.get("preserve_harmonics", True))
        log.info(f"Preset '{name}' loaded")

    def _show_about(self):
        QMessageBox.about(
            self, "About InteractiveNoiseReducer",
            "<b>InteractiveNoiseReducer v1.0</b><br>"
            "Speech-Preserving Background Noise Reduction System<br><br>"
            "Stack: Python · PyQt6 · Librosa · NumPy · SciPy · FFmpeg<br>"
            "Algorithm: Adaptive Spectral Gating with Harmonic Preservation"
        )

    def closeEvent(self, event):
        self._stop_audio()
        if self._worker and self._worker.isRunning():
            if hasattr(self._worker, "cancel"):
                self._worker.cancel()
            self._worker.wait(3000)
        self._config.save()
        event.accept()
