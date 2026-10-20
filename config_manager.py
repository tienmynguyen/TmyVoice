"""
ConfigManager handles safe loading, saving, and querying of soundboard configuration.
Uses atomic writes to prevent corruption on sudden shutdowns.
"""

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_appdata_config_path() -> Path:
    """Returns the persistent config.json path inside %APPDATA%/SoundboardPro/config.json."""
    appdata = os.getenv("APPDATA")
    if appdata:
        base_dir = Path(appdata) / "SoundboardPro"
    else:
        base_dir = Path.home() / ".SoundboardPro"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "config.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "mic_device_name": "",
    "cable_device_name": "",
    "monitor_device_name": "",
    "samplerate": 48000,
    "blocksize": 1024,
    "sfx_volume": 1.0,
    "monitor_volume": 1.0,
    "monitor_enabled": True,
    "mic_mix": False,
    "stop_all_hotkey": "F12",
    "sounds": []
}


class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            self.config_path = str(get_appdata_config_path())
        else:
            self.config_path = os.path.abspath(config_path)
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        self._lock = threading.Lock()
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> Dict[str, Any]:
        """Loads configuration from JSON file. Merges with defaults if missing fields."""
        with self._lock:
            if not os.path.exists(self.config_path):
                self._data = dict(DEFAULT_CONFIG)
                self._save_unlocked()
                return self._data

            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge with default config to ensure all keys exist
                    merged = dict(DEFAULT_CONFIG)
                    merged.update(loaded)
                    self._data = merged
            except Exception as e:
                print(f"[ConfigManager] Error reading config from {self.config_path}: {e}. Restoring defaults.")
                self._data = dict(DEFAULT_CONFIG)
            return self._data

    def save(self) -> None:
        """Atomically saves current configuration to JSON file."""
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        """Internal atomic save helper."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        tmp_path = f"{self.config_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
            if os.path.exists(self.config_path):
                os.replace(tmp_path, self.config_path)
            else:
                shutil.move(tmp_path, self.config_path)
        except Exception as e:
            print(f"[ConfigManager] Failed to write config atomically: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        with self._lock:
            self._data[key] = value
            if auto_save:
                self._save_unlocked()

    def get_sounds(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("sounds", []))

    def add_sound(self, sound_item: Dict[str, Any]) -> None:
        with self._lock:
            sounds = self._data.setdefault("sounds", [])
            # If sound with same ID exists, update it instead
            for i, s in enumerate(sounds):
                if s.get("id") == sound_item.get("id"):
                    sounds[i] = sound_item
                    self._save_unlocked()
                    return
            sounds.append(sound_item)
            self._save_unlocked()

    def remove_sound(self, sound_id: str) -> None:
        with self._lock:
            sounds = self._data.setdefault("sounds", [])
            self._data["sounds"] = [s for s in sounds if s.get("id") != sound_id]
            self._save_unlocked()

    def update_sound(self, sound_id: str, updates: Dict[str, Any]) -> None:
        with self._lock:
            sounds = self._data.setdefault("sounds", [])
            for s in sounds:
                if s.get("id") == sound_id:
                    s.update(updates)
                    break
            self._save_unlocked()
