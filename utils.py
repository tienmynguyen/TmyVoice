"""
Utility helper functions for AudioBoard Pro / TmyVoice:
- Safe resource resolution for bundled PyInstaller assets (sys._MEIPASS).
- Windows AppData storage directory resolution to avoid permission/working directory errors.
- Persistent user starter assets management.
"""

import os
import shutil
import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller frozen app.
    When frozen, PyInstaller extracts data to sys._MEIPASS.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.normpath(os.path.join(base_path, relative_path))


def get_app_data_dir() -> Path:
    """
    Returns the persistent application data directory:
    Path(os.getenv('APPDATA')) / "SoundboardPro"
    Creates the directory if it does not exist.
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        app_dir = Path(appdata) / "SoundboardPro"
    else:
        app_dir = Path.home() / ".SoundboardPro"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_config_path() -> Path:
    """Returns the persistent config.json path in AppData."""
    return get_app_data_dir() / "config.json"


def ensure_starter_sounds() -> str:
    """
    Copies bundled starter sounds from assets/sounds to the persistent
    AppData/SoundboardPro/sounds directory if not already present.
    Returns the persistent sounds directory path as a string.
    """
    target_sounds_dir = get_app_data_dir() / "sounds"
    target_sounds_dir.mkdir(parents=True, exist_ok=True)

    bundled_sounds_dir = resource_path(os.path.join("assets", "sounds"))
    if os.path.isdir(bundled_sounds_dir):
        for fname in os.listdir(bundled_sounds_dir):
            if fname.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                src = os.path.join(bundled_sounds_dir, fname)
                dst = target_sounds_dir / fname
                if not dst.exists() and os.path.isfile(src):
                    try:
                        shutil.copy2(src, dst)
                    except Exception as e:
                        print(f"[Utils] Error copying starter sound {fname}: {e}")

    return str(target_sounds_dir)
