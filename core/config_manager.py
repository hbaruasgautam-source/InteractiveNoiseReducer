"""
core/config_manager.py
Persistent JSON-backed configuration with defaults and type-safe access.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "last_input_dir": "",
    "last_output_dir": "",
    "noise_strength": 1.5,
    "attack_ms": 10.0,
    "release_ms": 100.0,
    "smoothing_factor": 0.5,
    "fft_size": 2048,
    "hop_length": 512,
    "threshold_db": -40.0,
    "output_quality": "high",
    "sample_rate": 44100,
    "presets": {},
}


class ConfigManager:
    def __init__(self, path: Path):
        self._path = path
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge: loaded values override defaults
                self._data.update(loaded)
                log.debug(f"Config loaded from {self._path}")
            except (json.JSONDecodeError, OSError) as exc:
                log.warning(f"Config load failed ({exc}), using defaults")
        else:
            self.save()

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            log.debug("Config saved")
        except OSError as exc:
            log.error(f"Config save failed: {exc}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def get_preset(self, name: str) -> dict | None:
        return self._data.get("presets", {}).get(name)

    def save_preset(self, name: str, params: dict):
        presets = self._data.setdefault("presets", {})
        presets[name] = params
        self.save()
        log.info(f"Preset '{name}' saved")

    def list_presets(self) -> list[str]:
        return list(self._data.get("presets", {}).keys())
