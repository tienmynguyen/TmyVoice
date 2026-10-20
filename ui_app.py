"""
AudioBoard Pro GUI Application (CustomTkinter)
Modern Dark Mode Desktop Interface for Low-Latency Virtual Audio Routing & SFX Triggering.
"""

import os
import threading
import time
import uuid
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from audio_engine import SoundboardEngine
from config_manager import ConfigManager
from hotkey_manager import HotkeyManager
from utils import ensure_starter_sounds, resource_path


# Custom Color Palette
BG_COLOR = "#0D0E11"
SURFACE_COLOR = "#16181D"
CARD_COLOR = "#1F222A"
CARD_BORDER = "#2B2F3A"
ACCENT_CYAN = "#06B6D4"
ACCENT_HOVER = "#0891B2"
SUCCESS_GREEN = "#10B981"
DANGER_RED = "#EF4444"
DANGER_HOVER = "#DC2626"
WARNING_AMBER = "#F59E0B"
TEXT_PRIMARY = "#F3F4F6"
TEXT_MUTED = "#9CA3AF"


class SetHotkeyModal(ctk.CTkToplevel):
    """Modern modal dialog to capture a global hotkey via keyboard press or preset selection."""

    def __init__(self, parent, sound_name: str, current_key: str, on_save_callback):
        super().__init__(parent)
        self.title("Assign Global Hotkey")
        self.geometry("420x320")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE_COLOR)

        self.transient(parent)
        self.grab_set()

        self.sound_name = sound_name
        self.current_key = current_key
        self.on_save_callback = on_save_callback
        self.captured_key: Optional[str] = None
        self._is_recording = True

        self._build_ui()
        self._start_listening()

    def _build_ui(self):
        # Header
        ctk.CTkLabel(
            self,
            text="Assign Hotkey",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(18, 4))

        ctk.CTkLabel(
            self,
            text=f"Target: {self.sound_name}",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=ACCENT_CYAN,
        ).pack(pady=(0, 14))

        # Key Display Box
        self.key_box = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        self.key_box.pack(padx=30, pady=5, fill="x")

        self.lbl_status = ctk.CTkLabel(
            self.key_box,
            text="PRESS ANY KEY COMBINATION...",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=WARNING_AMBER,
        )
        self.lbl_status.pack(pady=16)

        ctk.CTkLabel(
            self,
            text="Examples: F1 to F12, Ctrl+1, Alt+S, Num 7",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(pady=(4, 14))

        # Quick Select Dropdown for convenience
        quick_frame = ctk.CTkFrame(self, fg_color="transparent")
        quick_frame.pack(fill="x", padx=30, pady=(0, 16))

        ctk.CTkLabel(
            quick_frame,
            text="Or select preset:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        presets = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "Ctrl+1", "Ctrl+2", "Ctrl+3"]
        self.preset_menu = ctk.CTkOptionMenu(
            quick_frame,
            values=presets,
            command=self._on_preset_chosen,
            fg_color=CARD_COLOR,
            button_color=ACCENT_CYAN,
            text_color=TEXT_PRIMARY,
            width=110,
        )
        self.preset_menu.pack(side="right")

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=(6, 12))

        ctk.CTkButton(
            btn_frame,
            text="Clear Key",
            command=self._clear_key,
            fg_color="#374151",
            hover_color="#4B5563",
            width=100,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self._cancel,
            fg_color="#2B2F3A",
            hover_color="#374151",
            width=80,
        ).pack(side="left", padx=10)

        self.btn_confirm = ctk.CTkButton(
            btn_frame,
            text="Confirm",
            command=self._confirm,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_HOVER,
            width=110,
            state="disabled",
        )
        self.btn_confirm.pack(side="right")

    def _start_listening(self):
        """Asynchronously listens for key combination."""
        try:
            import keyboard
            def _worker():
                try:
                    key = keyboard.read_hotkey(suppress=False)
                    if self._is_recording and key:
                        self.after(0, lambda k=key: self._on_key_captured(k))
                except Exception as e:
                    print(f"[HotkeyModal] Key listener exception: {e}")

            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            self.lbl_status.configure(text="Use preset dropdown below", text_color=TEXT_MUTED)

    def _on_key_captured(self, raw_key: str):
        if not self._is_recording:
            return
        if raw_key.lower() in ("esc", "escape"):
            self._cancel()
            return

        parts = [p.capitalize() if p.lower().startswith("f") and len(p) <= 3 else p.title() for p in raw_key.split("+")]
        formatted = "+".join(parts)
        self.captured_key = formatted
        self.lbl_status.configure(text=f"[ {formatted} ]", text_color=SUCCESS_GREEN)
        self.btn_confirm.configure(state="normal")

    def _on_preset_chosen(self, value: str):
        self._is_recording = False
        self.captured_key = value
        self.lbl_status.configure(text=f"[ {value} ]", text_color=SUCCESS_GREEN)
        self.btn_confirm.configure(state="normal")

    def _clear_key(self):
        self._is_recording = False
        self.captured_key = ""
        self.lbl_status.configure(text="[ NO HOTKEY ]", text_color=TEXT_MUTED)
        self.btn_confirm.configure(state="normal")

    def _confirm(self):
        self._is_recording = False
        if self.captured_key is not None:
            self.on_save_callback(self.captured_key)
        self.destroy()

    def _cancel(self):
        self._is_recording = False
        self.destroy()


class SoundboardApp(ctk.CTk):
    def __init__(self, config_manager: ConfigManager, engine: SoundboardEngine, hotkey_mgr: HotkeyManager):
        super().__init__()
        self.config = config_manager
        self.engine = engine
        self.hotkeys = hotkey_mgr

        # GUI appearance & geometry
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("AUDIOBOARD PRO  //  Virtual Audio Cable & Low-Latency Soundboard")
        self.geometry("1060x800")
        self.minsize(920, 680)
        self.configure(fg_color=BG_COLOR)

        # State data
        self.input_devices: List[Dict[str, Any]] = []
        self.output_devices: List[Dict[str, Any]] = []
        self.sound_cards: Dict[str, ctk.CTkFrame] = {}

        # Wire up engine callbacks
        self.engine.on_state_change = self._on_engine_state_change
        self.engine.on_sfx_finished = self._on_sfx_finished

        # Build UI layout
        self._build_top_bar()
        self._build_device_panel()
        self._build_soundboard_panel()
        self._build_bottom_bar()

        # Initialize devices and sound library
        self._refresh_audio_devices()
        self._load_and_bind_sounds()
        self._register_emergency_stop_hotkey()

        # Start periodic GUI updater loop
        self._update_playback_ui()

    # =========================================================================
    # UI Building
    # =========================================================================

    def _build_top_bar(self):
        """Top brand bar with status LED and engine specs."""
        top_bar = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, height=56, corner_radius=0)
        top_bar.pack(fill="x", side="top")

        # Brand / Title
        brand_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand_frame.pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(
            brand_frame,
            text="AUDIOBOARD",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            brand_frame,
            text="PRO",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=ACCENT_CYAN,
        ).pack(side="left", padx=(4, 12))

        # Engine Status Pill Badge
        self.status_badge = ctk.CTkButton(
            top_bar,
            text="● ENGINE STOPPED",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#374151",
            text_color="#9CA3AF",
            hover=False,
            height=28,
            corner_radius=14,
            width=170,
        )
        self.status_badge.pack(side="left", padx=8)

        # Engine Quick Specs Pill
        specs_lbl = ctk.CTkLabel(
            top_bar,
            text="48.0 kHz  |  1024 Samples  |  ~21ms Latency",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        )
        specs_lbl.pack(side="right", padx=20)

    def _build_device_panel(self):
        """Top Settings Panel: Device selection dropdowns, engine toggle, and volume sliders."""
        panel = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        panel.pack(fill="x", padx=18, pady=(14, 8))

        # Row 1: Device Dropdowns
        row1 = ctk.CTkFrame(panel, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(14, 8))

        # 1. Microphone Input
        mic_box = ctk.CTkFrame(row1, fg_color="transparent")
        mic_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(
            mic_box,
            text="🎤 Physical Microphone (Input):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))
        self.mic_dropdown = ctk.CTkOptionMenu(
            mic_box,
            values=["Searching input devices..."],
            command=self._on_device_selection_changed,
            fg_color=CARD_COLOR,
            button_color=ACCENT_CYAN,
            text_color=TEXT_PRIMARY,
            height=32,
        )
        self.mic_dropdown.pack(fill="x")

        # 2. Virtual Cable Output
        cable_box = ctk.CTkFrame(row1, fg_color="transparent")
        cable_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(
            cable_box,
            text="📡 Virtual Cable Output (Meet / Discord):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))
        self.cable_dropdown = ctk.CTkOptionMenu(
            cable_box,
            values=["Searching output devices..."],
            command=self._on_device_selection_changed,
            fg_color=CARD_COLOR,
            button_color=ACCENT_CYAN,
            text_color=TEXT_PRIMARY,
            height=32,
        )
        self.cable_dropdown.pack(fill="x")

        # 3. Monitor Output (Headphones)
        mon_box = ctk.CTkFrame(row1, fg_color="transparent")
        mon_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            mon_box,
            text="🎧 Monitor Output (Headphones / Self-Listen):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))
        self.monitor_dropdown = ctk.CTkOptionMenu(
            mon_box,
            values=["Searching monitor devices..."],
            command=self._on_device_selection_changed,
            fg_color=CARD_COLOR,
            button_color=ACCENT_CYAN,
            text_color=TEXT_PRIMARY,
            height=32,
        )
        self.monitor_dropdown.pack(fill="x")

        # Refresh devices button
        btn_refresh = ctk.CTkButton(
            row1,
            text="🔄",
            width=36,
            height=32,
            fg_color=CARD_COLOR,
            hover_color=CARD_BORDER,
            text_color=TEXT_PRIMARY,
            command=self._refresh_audio_devices,
        )
        btn_refresh.pack(side="left", pady=(18, 0))

        # Row 2: Engine Switch + Volumes + Options
        row2 = ctk.CTkFrame(panel, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(6, 14))

        # Engine Toggle Button / Switch
        self.btn_engine_toggle = ctk.CTkButton(
            row2,
            text="▶ START AUDIO ENGINE",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._toggle_engine,
            fg_color=SUCCESS_GREEN,
            hover_color="#059669",
            text_color="#FFFFFF",
            height=36,
            width=210,
            corner_radius=8,
        )
        self.btn_engine_toggle.pack(side="left", padx=(0, 20))

        # SFX Cable Volume Slider
        vol_cable_box = ctk.CTkFrame(row2, fg_color="transparent")
        vol_cable_box.pack(side="left", padx=(0, 20))
        self.lbl_sfx_vol = ctk.CTkLabel(
            vol_cable_box,
            text=f"Cable SFX Vol: {int(self.config.get('sfx_volume', 1.0) * 100)}%",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_sfx_vol.pack(anchor="w")
        self.slider_sfx_vol = ctk.CTkSlider(
            vol_cable_box,
            from_=0.0,
            to=2.0,
            number_of_steps=40,
            command=self._on_sfx_vol_changed,
            width=130,
            progress_color=ACCENT_CYAN,
            button_color=ACCENT_CYAN,
        )
        self.slider_sfx_vol.set(self.config.get("sfx_volume", 1.0))
        self.slider_sfx_vol.pack()

        # Monitor Volume Slider
        vol_mon_box = ctk.CTkFrame(row2, fg_color="transparent")
        vol_mon_box.pack(side="left", padx=(0, 20))
        self.lbl_mon_vol = ctk.CTkLabel(
            vol_mon_box,
            text=f"Monitor Vol: {int(self.config.get('monitor_volume', 1.0) * 100)}%",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_mon_vol.pack(anchor="w")
        self.slider_mon_vol = ctk.CTkSlider(
            vol_mon_box,
            from_=0.0,
            to=2.0,
            number_of_steps=40,
            command=self._on_mon_vol_changed,
            width=130,
            progress_color=ACCENT_CYAN,
            button_color=ACCENT_CYAN,
        )
        self.slider_mon_vol.set(self.config.get("monitor_volume", 1.0))
        self.slider_mon_vol.pack()

        # Checkboxes for Monitoring and Mic Mix
        chk_box = ctk.CTkFrame(row2, fg_color="transparent")
        chk_box.pack(side="left", padx=(4, 0))

        self.chk_monitoring = ctk.CTkCheckBox(
            chk_box,
            text="Self-Listening Monitor",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_monitor_toggle_changed,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_HOVER,
        )
        if self.config.get("monitor_enabled", True):
            self.chk_monitoring.select()
        else:
            self.chk_monitoring.deselect()
        self.chk_monitoring.pack(anchor="w", pady=(0, 3))

        self.chk_mic_mix = ctk.CTkCheckBox(
            chk_box,
            text="Mic Mix (Don't mute mic)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_mic_mix_changed,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_HOVER,
        )
        if self.config.get("mic_mix", False):
            self.chk_mic_mix.select()
        else:
            self.chk_mic_mix.deselect()
        self.chk_mic_mix.pack(anchor="w")

    def _build_soundboard_panel(self):
        """Center Soundboard Grid / List with Sound Clips."""
        container = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        container.pack(fill="both", expand=True, padx=18, pady=(4, 8))

        # Soundboard Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=12)

        self.lbl_sound_count = ctk.CTkLabel(
            header,
            text="🎵 Soundboard Tracks (0)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_sound_count.pack(side="left")

        btn_add = ctk.CTkButton(
            header,
            text="+ Add Sound File (.wav, .mp3, .ogg, .flac)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._add_sound_file_dialog,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_HOVER,
            height=32,
            corner_radius=6,
        )
        btn_add.pack(side="right")

        # Scrollable Sound Item Frame
        self.sounds_scroll = ctk.CTkScrollableFrame(
            container,
            fg_color="transparent",
            corner_radius=0,
        )
        self.sounds_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Empty State Message Container
        self.empty_state_frame = ctk.CTkFrame(self.sounds_scroll, fg_color=CARD_COLOR, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        lbl_empty_icon = ctk.CTkLabel(
            self.empty_state_frame,
            text="📁",
            font=ctk.CTkFont(size=36),
        )
        lbl_empty_icon.pack(pady=(24, 6))

        lbl_empty_text = ctk.CTkLabel(
            self.empty_state_frame,
            text="No audio clips added yet.\nClick '+ Add Sound File' to load your favorite sounds!",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_MUTED,
            justify="center",
        )
        lbl_empty_text.pack(pady=(0, 24))

    def _build_bottom_bar(self):
        """Bottom Emergency Controls & Real-Time Playback Progress Bar."""
        bottom_bar = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, height=72, corner_radius=0)
        bottom_bar.pack(fill="x", side="bottom")

        inner = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=10)

        # Global STOP ALL SFX Button
        stop_hotkey = self.config.get("stop_all_hotkey", "F12")
        self.btn_stop_all = ctk.CTkButton(
            inner,
            text=f"⏹ STOP ALL SFX  [{stop_hotkey}]",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._on_stop_all_clicked,
            fg_color=DANGER_RED,
            hover_color=DANGER_HOVER,
            width=220,
            height=40,
            corner_radius=8,
        )
        self.btn_stop_all.pack(side="left", padx=(0, 20))

        # Real-time Playback Status and Progress Container
        status_box = ctk.CTkFrame(inner, fg_color="transparent")
        status_box.pack(side="left", fill="both", expand=True)

        info_row = ctk.CTkFrame(status_box, fg_color="transparent")
        info_row.pack(fill="x", pady=(0, 4))

        self.lbl_playback_status = ctk.CTkLabel(
            info_row,
            text="Status: Engine Stopped",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self.lbl_playback_status.pack(side="left")

        self.lbl_playback_time = ctk.CTkLabel(
            info_row,
            text="00.0s / 00.0s",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        )
        self.lbl_playback_time.pack(side="right")

        # Smooth Dynamic Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            status_box,
            fg_color=CARD_COLOR,
            progress_color=ACCENT_CYAN,
            height=8,
            corner_radius=4,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x")

    # =========================================================================
    # Device Management & Selection Logic
    # =========================================================================

    def _refresh_audio_devices(self):
        """Scans host audio devices and populates dropdowns."""
        self.input_devices = SoundboardEngine.get_input_devices()
        self.output_devices = SoundboardEngine.get_output_devices()

        in_labels = [d["label"] for d in self.input_devices] or ["No input devices found"]
        out_labels = [d["label"] for d in self.output_devices] or ["No output devices found"]

        self.mic_dropdown.configure(values=in_labels)
        self.cable_dropdown.configure(values=out_labels)
        self.monitor_dropdown.configure(values=out_labels)

        # 1. Select Microphone
        saved_mic = self.config.get("mic_device_name", "")
        matched_mic = self._find_matching_device_label(in_labels, saved_mic)
        if not matched_mic:
            def_mic_id = SoundboardEngine.find_default_mic_device()
            matched_mic = next((d["label"] for d in self.input_devices if d["id"] == def_mic_id), in_labels[0])
        self.mic_dropdown.set(matched_mic)

        # 2. Select Virtual Cable Output (Auto-detect 'CABLE Input' if present)
        saved_cable = self.config.get("cable_device_name", "")
        matched_cable = self._find_matching_device_label(out_labels, saved_cable)
        if not matched_cable:
            cable_id = SoundboardEngine.find_default_cable_device()
            if cable_id is not None:
                matched_cable = next((d["label"] for d in self.output_devices if d["id"] == cable_id), None)
            if not matched_cable and out_labels:
                matched_cable = out_labels[0]
        if matched_cable:
            self.cable_dropdown.set(matched_cable)

        # 3. Select Monitor Output (Headphones / Speakers)
        saved_mon = self.config.get("monitor_device_name", "")
        matched_mon = self._find_matching_device_label(out_labels, saved_mon)
        if not matched_mon:
            selected_cable_id = self._parse_device_id_from_label(self.cable_dropdown.get())
            mon_id = SoundboardEngine.find_default_monitor_device(exclude_id=selected_cable_id)
            matched_mon = next((d["label"] for d in self.output_devices if d["id"] == mon_id), out_labels[-1])
        if matched_mon:
            self.monitor_dropdown.set(matched_mon)

    def _find_matching_device_label(self, labels: List[str], saved_name: str) -> Optional[str]:
        if not saved_name:
            return None
        for lbl in labels:
            if saved_name in lbl:
                return lbl
        return None

    def _parse_device_id_from_label(self, label: str) -> Optional[int]:
        try:
            if label.startswith("[") and "]" in label:
                return int(label[1:label.index("]")])
        except Exception:
            pass
        return None

    def _on_device_selection_changed(self, _choice: str = ""):
        """Saves chosen devices to config and restarts engine if running."""
        self.config.set("mic_device_name", self.mic_dropdown.get())
        self.config.set("cable_device_name", self.cable_dropdown.get())
        self.config.set("monitor_device_name", self.monitor_dropdown.get())

        if self.engine._is_engine_running:
            self._start_engine_with_selected_devices()

    # =========================================================================
    # Engine Control
    # =========================================================================

    def _toggle_engine(self):
        """Starts or stops the real-time audio routing engine."""
        if self.engine._is_engine_running:
            self.engine.stop_engine()
        else:
            self._start_engine_with_selected_devices()

    def _start_engine_with_selected_devices(self):
        mic_id = self._parse_device_id_from_label(self.mic_dropdown.get())
        cable_id = self._parse_device_id_from_label(self.cable_dropdown.get())
        mon_id = self._parse_device_id_from_label(self.monitor_dropdown.get())

        if mic_id is None or cable_id is None:
            messagebox.showerror(
                "Audio Device Error",
                "Please select both a valid Physical Microphone and a Virtual Cable Output device."
            )
            return

        success, msg = self.engine.start_engine(
            mic_device_id=mic_id,
            cable_device_id=cable_id,
            monitor_device_id=mon_id,
        )

        if not success:
            messagebox.showerror("Audio Engine Error", f"Unable to start audio engine:\n{msg}")

    def _on_engine_state_change(self, state: str, sound_name: Optional[str]):
        """Thread-safe state change handler from audio engine."""
        self.after(0, lambda: self._apply_engine_state_ui(state, sound_name))

    def _apply_engine_state_ui(self, state: str, sound_name: Optional[str]):
        if state == SoundboardEngine.STATE_STOPPED:
            self.status_badge.configure(
                text="● ENGINE STOPPED",
                fg_color="#374151",
                text_color="#9CA3AF",
            )
            self.btn_engine_toggle.configure(
                text="▶ START AUDIO ENGINE",
                fg_color=SUCCESS_GREEN,
                hover_color="#059669",
            )
            self.lbl_playback_status.configure(
                text="Status: Engine Stopped",
                text_color=TEXT_MUTED,
            )
        elif state == SoundboardEngine.STATE_RUNNING:
            self.status_badge.configure(
                text="● ENGINE RUNNING",
                fg_color="#064E3B",
                text_color=SUCCESS_GREEN,
            )
            self.btn_engine_toggle.configure(
                text="⏹ STOP AUDIO ENGINE",
                fg_color=DANGER_RED,
                hover_color=DANGER_HOVER,
            )
            self.lbl_playback_status.configure(
                text="✔ Passthrough Active: Physical Mic routing to Virtual Cable",
                text_color=SUCCESS_GREEN,
            )
        elif state == SoundboardEngine.STATE_PLAYING_SFX:
            name = sound_name or "SFX Clip"
            self.status_badge.configure(
                text="● SFX BROADCASTING",
                fg_color="#78350F",
                text_color=WARNING_AMBER,
            )
            self.lbl_playback_status.configure(
                text=f"▶ Broadcasting: {name} (Mic suppressed on Virtual Cable)",
                text_color=WARNING_AMBER,
            )

    def _on_sfx_vol_changed(self, value: float):
        self.lbl_sfx_vol.configure(text=f"Cable SFX Vol: {int(value * 100)}%")
        self.engine.set_sfx_volume(value)
        self.config.set("sfx_volume", value)

    def _on_mon_vol_changed(self, value: float):
        self.lbl_mon_vol.configure(text=f"Monitor Vol: {int(value * 100)}%")
        self.engine.set_monitor_volume(value)
        self.config.set("monitor_volume", value)

    def _on_monitor_toggle_changed(self):
        val = bool(self.chk_monitoring.get())
        self.engine.set_monitor_enabled(val)
        self.config.set("monitor_enabled", val)

    def _on_mic_mix_changed(self):
        val = bool(self.chk_mic_mix.get())
        self.engine.set_mic_mix(val)
        self.config.set("mic_mix", val)

    # =========================================================================
    # Soundboard Card Management & Pre-Caching
    # =========================================================================

    def _load_and_bind_sounds(self):
        """Loads sounds from config, pre-caches their buffers in memory, and renders cards."""
        sounds = self.config.get_sounds()

        # If empty, ensure starter sounds are available in persistent AppData
        if not sounds:
            persistent_dir = ensure_starter_sounds()
            if os.path.exists(persistent_dir):
                defaults = [
                    ("Stadium Airhorn", "airhorn.wav", "F9"),
                    ("Gentle Chime", "chime.wav", "F10"),
                    ("Game Over", "game_over.wav", "F11"),
                ]
                for title, filename, key in defaults:
                    fpath = os.path.join(persistent_dir, filename)
                    if os.path.exists(fpath):
                        self.config.add_sound({
                            "id": str(uuid.uuid4()),
                            "name": title,
                            "path": fpath,
                            "hotkey": key,
                            "duration": 0.0,
                        })
                sounds = self.config.get_sounds()

        # Preload buffers and render cards
        for item in sounds:
            sid = item["id"]
            path = item["path"]
            success, dur, msg = self.engine.preload_sound(sid, path)
            if success:
                item["duration"] = dur
                self.config.update_sound(sid, {"duration": dur})
            self._render_sound_card(item)

        self._update_sound_count_label()

    def _render_sound_card(self, sound_item: Dict[str, Any]):
        """Renders an individual audio clip card in the scrollable view."""
        self.empty_state_frame.pack_forget()

        sid = sound_item["id"]
        name = sound_item.get("name", "Audio Clip")
        dur = sound_item.get("duration", 0.0)
        hk = sound_item.get("hotkey", "")

        card = ctk.CTkFrame(
            self.sounds_scroll,
            fg_color=CARD_COLOR,
            corner_radius=10,
            border_width=1,
            border_color=CARD_BORDER,
            height=60,
        )
        card.pack(fill="x", pady=4, padx=6)
        self.sound_cards[sid] = card

        # Left: Icon & Sound Name + Duration
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", padx=14, pady=10)

        ctk.CTkLabel(
            info_frame,
            text="🔊",
            font=ctk.CTkFont(size=18),
        ).pack(side="left", padx=(0, 10))

        title_box = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_box.pack(side="left")

        ctk.CTkLabel(
            title_box,
            text=name,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text=f"Duration: {dur:.1f}s",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

        # Right: Action Buttons
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.pack(side="right", padx=12, pady=10)

        # Hotkey Badge Pill
        btn_hotkey = ctk.CTkButton(
            actions_frame,
            text=f"[ {hk} ]" if hk else "[ Set Hotkey ]",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#374151" if hk else CARD_BORDER,
            hover_color="#4B5563",
            text_color=ACCENT_CYAN if hk else TEXT_MUTED,
            width=110,
            height=30,
            corner_radius=6,
            command=lambda s=sound_item: self._open_hotkey_modal(s),
        )
        btn_hotkey.pack(side="left", padx=6)
        card.btn_hotkey = btn_hotkey

        # Play / Test Button
        btn_play = ctk.CTkButton(
            actions_frame,
            text="▶ Play",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_HOVER,
            width=75,
            height=30,
            corner_radius=6,
            command=lambda s=sound_item: self._play_sound(s),
        )
        btn_play.pack(side="left", padx=6)
        card.btn_play = btn_play

        # Delete Button
        btn_del = ctk.CTkButton(
            actions_frame,
            text="🗑",
            font=ctk.CTkFont(size=13),
            fg_color="#374151",
            hover_color=DANGER_RED,
            text_color=TEXT_PRIMARY,
            width=36,
            height=30,
            corner_radius=6,
            command=lambda s=sound_item: self._delete_sound(s),
        )
        btn_del.pack(side="left", padx=(2, 0))

        # Register hotkey system-wide if assigned
        if hk:
            self._register_sound_hotkey(sound_item)

    def _update_sound_count_label(self):
        sounds = self.config.get_sounds()
        self.lbl_sound_count.configure(text=f"🎵 Soundboard Tracks ({len(sounds)})")
        if not sounds:
            self.empty_state_frame.pack(fill="x", pady=20, padx=10)

    def _add_sound_file_dialog(self):
        """Opens file dialog and pre-loads chosen sound file."""
        file_path = filedialog.askopenfilename(
            title="Select Sound File",
            filetypes=[
                ("Audio Files", "*.wav;*.mp3;*.ogg;*.flac"),
                ("WAV Files", "*.wav"),
                ("MP3 Files", "*.mp3"),
                ("OGG Files", "*.ogg"),
                ("FLAC Files", "*.flac"),
            ],
        )
        if not file_path:
            return

        sound_id = str(uuid.uuid4())
        name = os.path.splitext(os.path.basename(file_path))[0]

        # Pre-cache in audio engine
        success, duration, msg = self.engine.preload_sound(sound_id, file_path)
        if not success:
            messagebox.showerror("Audio Load Error", f"Failed to load audio file:\n{msg}")
            return

        sound_item = {
            "id": sound_id,
            "name": name,
            "path": file_path,
            "hotkey": "",
            "duration": duration,
        }

        self.config.add_sound(sound_item)
        self._render_sound_card(sound_item)
        self._update_sound_count_label()

    def _delete_sound(self, sound_item: Dict[str, Any]):
        sid = sound_item["id"]
        # Unbind hotkey
        hk = sound_item.get("hotkey", "")
        if hk:
            self.hotkeys.unregister_hotkey(hk)

        # Remove from engine cache
        self.engine.remove_sound_from_cache(sid)

        # Remove card widget
        if sid in self.sound_cards:
            self.sound_cards[sid].destroy()
            del self.sound_cards[sid]

        # Remove from config
        self.config.remove_sound(sid)
        self._update_sound_count_label()

    # =========================================================================
    # Playback & Hotkey Binding
    # =========================================================================

    def _play_sound(self, sound_item: Dict[str, Any]):
        """Triggers sound playback through the engine."""
        if not self.engine._is_engine_running:
            # Auto-start engine if not running
            self._start_engine_with_selected_devices()
            if not self.engine._is_engine_running:
                return

        sid = sound_item["id"]
        name = sound_item["name"]
        self.engine.play_sound(sid, name)

    def _on_sfx_finished(self, _sound_id: str):
        """Asynchronous notification when sound finishes playing."""
        pass

    def _on_stop_all_clicked(self):
        """Emergency stop button handler."""
        self.engine.stop_sfx()

    def _register_emergency_stop_hotkey(self):
        hk = self.config.get("stop_all_hotkey", "F12")
        if hk:
            self.hotkeys.register_hotkey(hk, self.engine.stop_sfx)

    def _register_sound_hotkey(self, sound_item: Dict[str, Any]):
        hk = sound_item.get("hotkey", "")
        if not hk:
            return

        def _trigger():
            self.after(0, lambda: self._play_sound(sound_item))

        self.hotkeys.register_hotkey(hk, _trigger)

    def _open_hotkey_modal(self, sound_item: Dict[str, Any]):
        """Opens modal to capture a new key combination."""
        sid = sound_item["id"]
        name = sound_item["name"]
        current = sound_item.get("hotkey", "")

        def _on_save(new_key: str):
            # Unregister previous key
            if current:
                self.hotkeys.unregister_hotkey(current)

            # Update sound item & config
            sound_item["hotkey"] = new_key
            self.config.update_sound(sid, {"hotkey": new_key})

            # Update button text on card
            card = self.sound_cards.get(sid)
            if card and hasattr(card, "btn_hotkey"):
                card.btn_hotkey.configure(
                    text=f"[ {new_key} ]" if new_key else "[ Set Hotkey ]",
                    fg_color="#374151" if new_key else CARD_BORDER,
                    text_color=ACCENT_CYAN if new_key else TEXT_MUTED,
                )

            # Register new global hotkey
            if new_key:
                self._register_sound_hotkey(sound_item)

        SetHotkeyModal(self, name, current, _on_save)

    # =========================================================================
    # High-Frequency Smooth UI Updater Loop (~30 FPS)
    # =========================================================================

    def _update_playback_ui(self):
        """Periodic loop to smoothly update progress bar and status without blocking audio."""
        status = self.engine.get_playback_status()
        is_playing = status["is_playing_sfx"]
        prog = status["progress"]
        cur = status["current_sec"]
        tot = status["total_sec"]
        name = status["sound_name"]

        if is_playing and tot > 0:
            self.progress_bar.set(prog)
            self.lbl_playback_time.configure(text=f"{cur:04.1f}s / {tot:04.1f}s")
            self.lbl_playback_status.configure(
                text=f"▶ Streaming SFX: {name} ({int(prog * 100)}%)",
                text_color=WARNING_AMBER,
            )
        else:
            self.progress_bar.set(0.0)
            if status["is_engine_running"]:
                self.lbl_playback_time.configure(text="00.0s / 00.0s")
                self.lbl_playback_status.configure(
                    text="✔ Passthrough Active: Physical Mic routing to Virtual Cable",
                    text_color=SUCCESS_GREEN,
                )

        # Schedule next update in 35ms (~28-30 FPS smooth rendering)
        self.after(35, self._update_playback_ui)

    def on_closing(self):
        """Safe cleanup on window close."""
        try:
            self.engine.stop_engine()
        except Exception:
            pass

        try:
            self.hotkeys.unregister_all()
        except Exception:
            pass

        try:
            self.config.save()
        except Exception:
            pass

        self.destroy()
