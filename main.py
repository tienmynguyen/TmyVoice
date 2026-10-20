"""
Main Entry Point for AudioBoard Pro Desktop Application.
Includes administrator privilege verification, global exception handling, and clean shutdown.
"""

import ctypes
import os
import sys
import traceback
from tkinter import messagebox

from audio_engine import SoundboardEngine
from config_manager import ConfigManager
from hotkey_manager import HotkeyManager
from ui_app import SoundboardApp


def is_admin() -> bool:
    """Checks whether the application is running with Windows Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def main():
    print("=" * 60)
    print(" AUDIOBOARD PRO: Low-Latency Virtual Audio Routing & Soundboard")
    print("=" * 60)

    # Verify Windows OS
    if sys.platform != "win32":
        print("[Warning] This application is optimized for Windows audio subsystems (VB-Cable / PortAudio / DirectSound / WASAPI).")

    # Check and notify admin status
    admin_status = is_admin()
    if admin_status:
        print("[System] Running with Administrator privileges. Global hotkeys will work in all games & apps.")
    else:
        print("[System Notice] Running with standard privileges.")
        print("                Tip: Run as Administrator if global hotkeys do not respond while full-screen games are focused.")

    try:
        # Initialize Core Subsystems (Uses %APPDATA%/SoundboardPro/config.json)
        config_mgr = ConfigManager()
        audio_eng = SoundboardEngine(
            samplerate=config_mgr.get("samplerate", 48000),
            blocksize=config_mgr.get("blocksize", 1024),
            sfx_volume=config_mgr.get("sfx_volume", 1.0),
            monitor_volume=config_mgr.get("monitor_volume", 1.0),
            monitor_enabled=config_mgr.get("monitor_enabled", True),
            mic_mix=config_mgr.get("mic_mix", False),
        )
        hotkey_mgr = HotkeyManager()

        # Instantiate Modern GUI
        app = SoundboardApp(config_mgr, audio_eng, hotkey_mgr)

        # Handle window close protocol
        app.protocol("WM_DELETE_WINDOW", app.on_closing)

        # Run application event loop
        app.mainloop()

    except Exception as e:
        err_msg = f"Fatal error during execution:\n{e}\n\n{traceback.format_exc()}"
        print(f"[Fatal Error] {err_msg}")
        try:
            messagebox.showerror("AudioBoard Error", f"A fatal error occurred:\n{e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
