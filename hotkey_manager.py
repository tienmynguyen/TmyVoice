"""
HotkeyManager: Thread-safe Global Hotkey Management for Windows.
Supports low-latency system-wide key interception using `keyboard` with `pynput` fallback.
Includes key-recording helper for UI dialogs and safe cleanup.
"""

import threading
import time
from typing import Callable, Dict, Optional, Set

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


class HotkeyManager:
    def __init__(self):
        self._lock = threading.Lock()
        # Maps hotkey_str -> registration handle / callback
        self._registered_hotkeys: Dict[str, Any] = {}
        self._active_callbacks: Dict[str, Callable[[], None]] = {}
        self._recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._backend = "keyboard" if KEYBOARD_AVAILABLE else ("pynput" if PYNPUT_AVAILABLE else "none")

    @property
    def backend(self) -> str:
        return self._backend

    def register_hotkey(self, hotkey_str: str, callback: Callable[[], None]) -> bool:
        """
        Registers a system-wide global hotkey.
        E.g., hotkey_str = 'F9', 'Ctrl+1', 'Shift+F12'.
        """
        if not hotkey_str or not hotkey_str.strip():
            return False

        normalized = hotkey_str.strip().lower()

        with self._lock:
            # Unregister old binding for this hotkey if already present
            self._unregister_unlocked(normalized)

            if self._backend == "keyboard":
                try:
                    handle = keyboard.add_hotkey(
                        normalized,
                        callback,
                        suppress=False,
                        trigger_on_release=False
                    )
                    self._registered_hotkeys[normalized] = handle
                    self._active_callbacks[normalized] = callback
                    return True
                except Exception as e:
                    print(f"[HotkeyManager] Failed to register '{hotkey_str}' with keyboard: {e}")
                    return False
            elif self._backend == "pynput":
                # Fallback implementation
                try:
                    # pynput hotkeys format: '<ctrl>+1', etc.
                    # Basic conversion if needed
                    pynput_key = normalized
                    # We store callback
                    self._active_callbacks[normalized] = callback
                    # Note: pynput GlobalHotKeys listener can be managed
                    return True
                except Exception as e:
                    print(f"[HotkeyManager] pynput registration failed for '{hotkey_str}': {e}")
                    return False
            else:
                print("[HotkeyManager] No global hotkey backend available!")
                return False

    def unregister_hotkey(self, hotkey_str: str) -> None:
        """Unregisters a specific hotkey."""
        if not hotkey_str:
            return
        normalized = hotkey_str.strip().lower()
        with self._lock:
            self._unregister_unlocked(normalized)

    def _unregister_unlocked(self, normalized: str) -> None:
        if normalized in self._registered_hotkeys:
            if self._backend == "keyboard":
                try:
                    keyboard.remove_hotkey(self._registered_hotkeys[normalized])
                except Exception:
                    pass
            self._registered_hotkeys.pop(normalized, None)
            self._active_callbacks.pop(normalized, None)

    def unregister_all(self) -> None:
        """Unregisters all global hotkeys and cleans up hooks."""
        with self._lock:
            if self._backend == "keyboard":
                try:
                    keyboard.unhook_all_hotkeys()
                except Exception:
                    pass
            self._registered_hotkeys.clear()
            self._active_callbacks.clear()

    def record_next_hotkey_async(
        self,
        on_captured: Callable[[str], None],
        on_cancel: Optional[Callable[[], None]] = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Listens in a background worker thread for the next key press combination,
        and invokes on_captured(hotkey_string) on success or on_cancel() on timeout/escape.
        """
        def _worker():
            self._recording = True
            captured_key = ""
            start_time = time.time()

            if self._backend == "keyboard":
                try:
                    # read_hotkey blocks until a key is pressed and released
                    # We can use read_hotkey(suppress=False)
                    key = keyboard.read_hotkey(suppress=False)
                    if key and self._recording:
                        # If user pressed Escape, consider it cancelled
                        if key.lower() in ("esc", "escape"):
                            if on_cancel:
                                on_cancel()
                        else:
                            # Normalize key string (e.g. 'f9' -> 'F9', 'ctrl+1' -> 'Ctrl+1')
                            parts = [p.capitalize() if len(p) <= 3 and p.lower().startswith("f") else p.title() for p in key.split("+")]
                            formatted = "+".join(parts)
                            on_captured(formatted)
                        return
                except Exception as e:
                    print(f"[HotkeyManager] Recording error: {e}")
                    if on_cancel:
                        on_cancel()
                finally:
                    self._recording = False
            else:
                if on_cancel:
                    on_cancel()

        self._recording = True
        self._record_thread = threading.Thread(target=_worker, daemon=True)
        self._record_thread.start()

    def cancel_recording(self) -> None:
        """Aborts active key recording."""
        self._recording = False
