# InteractiveNoiseReducer

> **Speech-Preserving Background Noise Reduction System**  
> Professional-grade desktop application for interactive audio noise reduction from video files.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Running the Application](#running-the-application)
6. [Usage Guide](#usage-guide)
7. [Configuration & Presets](#configuration--presets)
8. [Building an Executable](#building-an-executable)
9. [Troubleshooting](#troubleshooting)
10. [Performance Tips](#performance-tips)
11. [Architecture](#architecture)

---

## Overview

InteractiveNoiseReducer is a desktop application that removes background noise from video files while preserving speech intelligibility. It uses adaptive spectral gating with harmonic preservation to avoid the "metallic" artefacts produced by naive spectral subtraction.

The application provides real-time waveform and spectrogram visualisation, an interactive draggable threshold line, and full control over all noise-reduction parameters.

---

## Features

- **Video → Audio extraction** via FFmpeg
- **Multi-feature speech detection** (energy + ZCR + spectral centroid + spectral flux)
- **Adaptive noise profile estimation** from silence frames
- **Spectral gating** with soft-knee gain function
- **Attack / Release envelope** for natural transitions
- **Harmonic preservation** to keep speech clarity
- **Interactive waveform** with draggable threshold line (PyQtGraph)
- **Mel spectrogram** display
- **Before / After audio preview** (sounddevice)
- **Segment selection playback**
- **Preset management** (save / load parameter sets)
- **Dark and Light theme**
- **Export** cleaned video or audio-only WAV
- **JSON config persistence**
- **Structured file logging**

---

## Requirements

### System

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| FFmpeg | 4.0+ | Must be on `PATH` |
| PortAudio | any | For `sounddevice` playback |

### Python packages

See `requirements.txt` — all installed via pip.

---

## Installation

### 1. Install FFmpeg

**Windows:**
```
winget install FFmpeg
```
or download from https://ffmpeg.org/download.html and add to `PATH`.

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt update && sudo apt install ffmpeg portaudio19-dev
```

### 2. Install PortAudio (for audio playback)

**Windows:** Bundled with the `sounddevice` wheel — no extra step.

**macOS:**
```bash
brew install portaudio
```

**Linux:**
```bash
sudo apt install portaudio19-dev
```

### 3. Clone / extract the project

```bash
# If using git:
git clone <repo-url>
cd InteractiveNoiseReducer

# Or simply extract the ZIP and cd into the folder:
cd InteractiveNoiseReducer
```

### 4. Create a virtual environment

```bash
python3 -m venv .venv
```

**Activate:**

| Platform | Command |
|---|---|
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

### 5. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Running the Application

```bash
python main.py
```

On **Windows**, if you want to suppress the console window:
```bash
pythonw main.py
```

---

## Usage Guide

### Basic Workflow

1. **Open Video** — Click `📂 Open Video` or use `File → Open Video…`
2. **Extract Audio** — Click `⚡ Extract Audio` to pull the WAV from the video via FFmpeg
3. **Analyse** — Click `🔍 Analyse` to detect speech regions and estimate the noise floor
4. **Adjust Parameters** — Use the left panel sliders to tune noise reduction
5. **Preview** — Drag the threshold line on the waveform to update speech detection interactively
6. **Reduce Noise** — Click `▶ Reduce Noise` to process
7. **Compare** — Use `▶ Original` and `▶ Processed` buttons to A/B compare
8. **Export** — Click `💾 Export Video` or `🎵 Audio Only`

### Parameter Guide

| Parameter | Description | Recommended Range |
|---|---|---|
| **Strength** | Multiplier on the estimated noise floor | 1.2–2.0 |
| **Attack (ms)** | How quickly gain rises when signal appears | 5–20 ms |
| **Release (ms)** | How slowly gain falls after signal ends | 60–200 ms |
| **Smoothing** | Temporal smoothing of gain (reduces musical noise) | 0.3–0.7 |
| **FFT Size** | Frequency resolution (larger = finer) | 2048 |
| **Hop Length** | Time resolution (smaller = smoother) | 256–512 |

### Interactive Threshold

The **horizontal dashed line** on the waveform is draggable. Moving it up/down re-classifies frames as speech (green regions) or noise (red/empty) in real time, giving immediate visual feedback before you commit to a noise reduction run.

### Segment Playback

1. Enable **Enable Selection Region** checkbox
2. Drag the white region handles on the waveform to select a segment
3. Click **▶ Play Segment** to audition that section

---

## Configuration & Presets

Settings are auto-saved to `config.json` after every change.

**Presets** (built-in):

| Preset | Use Case |
|---|---|
| Gentle | Light hiss removal, preserve all detail |
| Aggressive | Heavy HVAC / traffic noise |
| Voice Clarity | Podcast / voice-over optimisation |

**Save a custom preset:** `Presets → Save Current Preset…`

**Load a preset:** `Presets → Load Preset…`

---

## Building an Executable

### Prerequisites

```bash
pip install pyinstaller
```

### Windows (.exe)

```bash
pyinstaller ^
  --onedir ^
  --windowed ^
  --name "InteractiveNoiseReducer" ^
  --icon assets/icons/app.ico ^
  --add-data "config.json;." ^
  --add-data "assets;assets" ^
  --hidden-import "librosa" ^
  --hidden-import "soundfile" ^
  --hidden-import "sounddevice" ^
  --hidden-import "pyqtgraph" ^
  main.py
```

Output: `dist/InteractiveNoiseReducer/InteractiveNoiseReducer.exe`

### macOS (.app)

```bash
pyinstaller \
  --onedir \
  --windowed \
  --name "InteractiveNoiseReducer" \
  --add-data "config.json:." \
  --add-data "assets:assets" \
  --hidden-import "librosa" \
  --hidden-import "soundfile" \
  --hidden-import "sounddevice" \
  --hidden-import "pyqtgraph" \
  main.py
```

Output: `dist/InteractiveNoiseReducer.app`

### Linux (binary)

```bash
pyinstaller \
  --onefile \
  --name "InteractiveNoiseReducer" \
  --add-data "config.json:." \
  --add-data "assets:assets" \
  --hidden-import "librosa" \
  --hidden-import "soundfile" \
  --hidden-import "sounddevice" \
  --hidden-import "pyqtgraph" \
  main.py
```

Output: `dist/InteractiveNoiseReducer`

> **Note:** FFmpeg must still be available on the end-user's `PATH` when running the packaged application. To bundle it, download the static build and place `ffmpeg` / `ffmpeg.exe` into the `assets/` folder, then add `--add-binary "assets/ffmpeg;."` to the PyInstaller command.

---

## Troubleshooting

### "FFmpeg not found"
Ensure `ffmpeg` is on your system `PATH`:
```bash
ffmpeg -version
```
If not found, reinstall FFmpeg and restart your terminal.

### No audio playback
- Ensure PortAudio is installed (see Installation)
- Try: `pip install sounddevice --force-reinstall`
- On Linux: `sudo apt install portaudio19-dev python3-dev`

### PyQt6 import errors on Linux
```bash
sudo apt install libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0
```

### Application opens but waveform is blank
The audio must be extracted first. Click `⚡ Extract Audio` before `🔍 Analyse`.

### Processed audio has artefacts
- Lower the **Strength** slider (try 1.2–1.5)
- Increase the **Release** time (150–250 ms)
- Enable **Preserve Harmonics**
- Use a larger **FFT Size** (4096)

### Memory usage is high for long files
- Use a larger **Hop Length** (1024) to reduce STFT frames
- Process in shorter segments using the selection feature

---

## Performance Tips

- **Long files (>30 min):** Use FFT Size 4096, Hop Length 1024 to reduce memory usage
- **Fast preview:** Run analysis with Hop Length 1024, then switch to 256 for final export
- **Best quality:** Strength 1.5, Attack 8ms, Release 120ms, Smoothing 0.5, FFT 2048
- **Batch processing:** Open multiple terminal instances and run `python main.py` for each file
- **GPU:** librosa uses NumPy which can leverage OpenBLAS/MKL automatically on most platforms

---

## Architecture

```
InteractiveNoiseReducer/
│
├── main.py                   ← Entry point: logging, config, Qt init
│
├── ui/
│   ├── main_window.py        ← QMainWindow: layout, toolbar, worker threads
│   ├── waveform_widget.py    ← PyQtGraph waveform + draggable threshold line
│   ├── spectrogram_widget.py ← PyQtGraph mel spectrogram ImageItem
│   └── styles.py             ← QSS theme generator (dark / light)
│
├── core/
│   ├── config_manager.py     ← JSON config read/write with defaults
│   ├── audio_extractor.py    ← FFmpeg subprocess audio extraction
│   ├── speech_detector.py    ← Multi-feature VAD + Otsu threshold
│   ├── noise_estimator.py    ← Percentile noise profile from silence frames
│   ├── noise_reducer.py      ← Spectral gating + attack/release + harmonics
│   └── video_renderer.py     ← FFmpeg video re-mux with cleaned audio
│
├── assets/icons/             ← Application icon assets
├── logs/                     ← Rotating log files (auto-created)
├── config.json               ← Persistent user settings + presets
├── requirements.txt
└── README.md
```

### Data flow

```
Video File
    │
    ▼ audio_extractor.py (FFmpeg)
WAV File
    │
    ▼ speech_detector.py (librosa features + Otsu)
Speech Mask + Detection Results
    │
    ├──▶ waveform_widget.py  (green regions)
    ├──▶ spectrogram_widget.py
    │
    ▼ noise_estimator.py (percentile on silence frames)
Noise Power Profile
    │
    ▼ noise_reducer.py (spectral gating + attack/release)
Cleaned Audio (float32)
    │
    ├──▶ sounddevice playback (A/B preview)
    ├──▶ WAV export
    └──▶ video_renderer.py (FFmpeg mux)
         │
         ▼
    Output Video File
```

---
## Download

Download the latest version:

https://github.com/hbaruasgautam-source/InteractiveNoiseReducer/releases
*Built with Python · PyQt6 · Librosa · NumPy · SciPy · FFmpeg*
