"""
ui/styles.py
Theme definitions and QSS stylesheet generator.
Two themes: dark (default DAW-style) and light (clean studio).
Neon accent: #00E5FF (cyan) for dark; #0066CC for light.
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor


DARK = {
    "bg_primary":      "#0D0D0D",
    "bg_secondary":    "#141414",
    "bg_panel":        "#1A1A1A",
    "bg_widget":       "#111111",
    "bg_input":        "#1E1E1E",
    "bg_hover":        "#222222",
    "border":          "#2A2A2A",
    "border_accent":   "#00E5FF",
    "text_primary":    "#E8E8E8",
    "text_secondary":  "#888888",
    "text_disabled":   "#444444",
    "accent":          "#00E5FF",
    "accent_dark":     "#007A8A",
    "accent_hover":    "#33EEFF",
    "success":         "#00FF88",
    "warning":         "#FFB300",
    "error":           "#FF3D3D",
    "speech_color":    "#00FF88",
    "noise_color":     "#FF3D3D",
    "waveform_color":  "#00B4CC",
    "threshold_color": "#FFB300",
    "scrollbar_bg":    "#0D0D0D",
    "scrollbar_handle":"#2A2A2A",
    "splitter":        "#1A1A1A",
    "tab_selected":    "#1A1A1A",
    "tab_bg":          "#111111",
    "progress_bg":     "#1A1A1A",
    "progress_chunk":  "#00E5FF",
    "slider_groove":   "#1A1A1A",
    "slider_handle":   "#00E5FF",
    "combo_bg":        "#1E1E1E",
    "log_bg":          "#0A0A0A",
    "log_text":        "#88CC88",
    "btn_primary_bg":  "#00E5FF",
    "btn_primary_text":"#000000",
    "btn_secondary_bg":"#1E1E1E",
    "btn_secondary_text":"#E8E8E8",
    "btn_danger_bg":   "#FF3D3D",
    "btn_danger_text": "#FFFFFF",
}

LIGHT = {
    "bg_primary":      "#F0F0F0",
    "bg_secondary":    "#E8E8E8",
    "bg_panel":        "#FFFFFF",
    "bg_widget":       "#F8F8F8",
    "bg_input":        "#FFFFFF",
    "bg_hover":        "#ECECEC",
    "border":          "#D0D0D0",
    "border_accent":   "#0066CC",
    "text_primary":    "#111111",
    "text_secondary":  "#555555",
    "text_disabled":   "#AAAAAA",
    "accent":          "#0066CC",
    "accent_dark":     "#004999",
    "accent_hover":    "#0077EE",
    "success":         "#007744",
    "warning":         "#CC8800",
    "error":           "#CC2222",
    "speech_color":    "#007744",
    "noise_color":     "#CC2222",
    "waveform_color":  "#0066CC",
    "threshold_color": "#CC8800",
    "scrollbar_bg":    "#E8E8E8",
    "scrollbar_handle":"#BBBBBB",
    "splitter":        "#D0D0D0",
    "tab_selected":    "#FFFFFF",
    "tab_bg":          "#E8E8E8",
    "progress_bg":     "#E0E0E0",
    "progress_chunk":  "#0066CC",
    "slider_groove":   "#D0D0D0",
    "slider_handle":   "#0066CC",
    "combo_bg":        "#FFFFFF",
    "log_bg":          "#F5F5F5",
    "log_text":        "#005533",
    "btn_primary_bg":  "#0066CC",
    "btn_primary_text":"#FFFFFF",
    "btn_secondary_bg":"#E8E8E8",
    "btn_secondary_text":"#111111",
    "btn_danger_bg":   "#CC2222",
    "btn_danger_text": "#FFFFFF",
}


def _build_qss(t: dict) -> str:
    return f"""
/* ═══════════════════════════════════════════════════════ */
/* InteractiveNoiseReducer — QSS Stylesheet                 */
/* ═══════════════════════════════════════════════════════ */

QMainWindow, QDialog, QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
    font-size: 12px;
}}

QFrame {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-radius: 4px;
}}

QFrame#panel {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px;
}}

QGroupBox {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 14px;
    padding: 8px 6px 6px 6px;
    font-weight: bold;
    color: {t['text_secondary']};
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {t['accent']};
    left: 10px;
}}

/* ── Buttons ────────────────────────────────────────────── */
QPushButton {{
    background-color: {t['btn_secondary_bg']};
    color: {t['btn_secondary_text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 7px 16px;
    font-family: "Consolas", monospace;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 0.5px;
    min-height: 28px;
}}

QPushButton:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['accent']};
    color: {t['accent']};
}}

QPushButton:pressed {{
    background-color: {t['accent_dark']};
    color: {t['btn_primary_text']};
}}

QPushButton:disabled {{
    background-color: {t['bg_secondary']};
    color: {t['text_disabled']};
    border-color: {t['border']};
}}

QPushButton#primary {{
    background-color: {t['accent']};
    color: {t['btn_primary_text']};
    border: none;
    font-weight: bold;
}}

QPushButton#primary:hover {{
    background-color: {t['accent_hover']};
    color: {t['btn_primary_text']};
}}

QPushButton#danger {{
    background-color: {t['btn_danger_bg']};
    color: {t['btn_danger_text']};
    border: none;
}}

QPushButton#danger:hover {{
    opacity: 0.85;
}}

/* ── Sliders ────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {t['slider_groove']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {t['slider_handle']};
    border: 2px solid {t['accent']};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background: {t['accent_hover']};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 2px;
}}

/* ── Progress Bar ───────────────────────────────────────── */
QProgressBar {{
    background-color: {t['progress_bg']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    height: 12px;
    text-align: center;
    color: {t['text_primary']};
    font-size: 10px;
}}

QProgressBar::chunk {{
    background-color: {t['progress_chunk']};
    border-radius: 3px;
}}

/* ── Labels ─────────────────────────────────────────────── */
QLabel {{
    color: {t['text_primary']};
    background: transparent;
    border: none;
}}

QLabel#title {{
    font-size: 18px;
    font-weight: bold;
    color: {t['accent']};
    letter-spacing: 2px;
}}

QLabel#subtitle {{
    font-size: 11px;
    color: {t['text_secondary']};
    letter-spacing: 1px;
}}

QLabel#value {{
    color: {t['accent']};
    font-weight: bold;
}}

/* ── ComboBox ───────────────────────────────────────────── */
QComboBox {{
    background-color: {t['combo_bg']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 5px 8px;
    color: {t['text_primary']};
    min-height: 24px;
}}

QComboBox:hover {{
    border-color: {t['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {t['text_secondary']};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['combo_bg']};
    border: 1px solid {t['accent']};
    selection-background-color: {t['accent_dark']};
    color: {t['text_primary']};
    outline: 0;
}}

/* ── Splitter ───────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {t['splitter']};
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:vertical {{
    height: 3px;
}}

/* ── Scrollbars ─────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t['scrollbar_bg']};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {t['scrollbar_handle']};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {t['scrollbar_bg']};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {t['scrollbar_handle']};
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Tab Widget ─────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {t['border']};
    background-color: {t['bg_panel']};
    border-radius: 4px;
}}

QTabBar::tab {{
    background: {t['tab_bg']};
    color: {t['text_secondary']};
    border: 1px solid {t['border']};
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-size: 11px;
    letter-spacing: 0.5px;
}}

QTabBar::tab:selected {{
    background: {t['tab_selected']};
    color: {t['accent']};
    border-bottom-color: {t['tab_selected']};
}}

QTabBar::tab:hover:!selected {{
    color: {t['text_primary']};
    border-color: {t['accent']};
}}

/* ── TextEdit (Log Console) ─────────────────────────────── */
QTextEdit#log_console {{
    background-color: {t['log_bg']};
    color: {t['log_text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 4px;
}}

/* ── Line Edit ──────────────────────────────────────────── */
QLineEdit {{
    background-color: {t['bg_input']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 5px 8px;
    color: {t['text_primary']};
    selection-background-color: {t['accent_dark']};
}}

QLineEdit:focus {{
    border-color: {t['accent']};
}}

/* ── Tooltip ────────────────────────────────────────────── */
QToolTip {{
    background-color: {t['bg_panel']};
    color: {t['text_primary']};
    border: 1px solid {t['accent']};
    padding: 4px 8px;
    border-radius: 3px;
    font-size: 11px;
}}

/* ── Status Bar ─────────────────────────────────────────── */
QStatusBar {{
    background-color: {t['bg_secondary']};
    color: {t['text_secondary']};
    border-top: 1px solid {t['border']};
    font-size: 11px;
}}

/* ── Menu Bar ───────────────────────────────────────────── */
QMenuBar {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border-bottom: 1px solid {t['border']};
}}

QMenuBar::item:selected {{
    background-color: {t['accent_dark']};
}}

QMenu {{
    background-color: {t['bg_panel']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
}}

QMenu::item:selected {{
    background-color: {t['accent_dark']};
    color: {t['accent']};
}}

/* ── Spin Box ───────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background-color: {t['bg_input']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 4px 6px;
    color: {t['text_primary']};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t['accent']};
}}

/* ── CheckBox ───────────────────────────────────────────── */
QCheckBox {{
    color: {t['text_primary']};
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t['border']};
    border-radius: 3px;
    background-color: {t['bg_input']};
}}

QCheckBox::indicator:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}
"""


THEMES = {"dark": DARK, "light": LIGHT}
_current_theme = "dark"


def apply_theme(app: QApplication, theme_name: str):
    global _current_theme
    _current_theme = theme_name
    t = THEMES.get(theme_name, DARK)
    app.setStyleSheet(_build_qss(t))


def get_color(key: str, theme: str | None = None) -> str:
    t_name = theme or _current_theme
    return THEMES.get(t_name, DARK).get(key, "#FFFFFF")
