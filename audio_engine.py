"""
SoundboardEngine: High-Performance, Dual-Stream Real-Time Audio Routing Engine.

Features:
- Primary Stream (sd.Stream): Routes Physical Microphone -> Virtual Audio Cable (e.g., VB-Cable) with low latency.
- Secondary Stream (sd.OutputStream): Routes SFX -> Physical Headphones/Speakers for zero-echo self-listening.
- Passthrough Mode: Mic directly passed to Virtual Cable.
- SFX Trigger Mode: Streams pre-loaded audio buffer to Virtual Cable and Monitor simultaneously.
- Auto-Mute / Mic-Mix: Suppresses Mic on Virtual Cable during SFX (or mixes if enabled).
- Auto-Resume: Automatically restores mic passthrough the instant SFX completes.
- In-memory pre-decoding, auto-resampling (scipy.signal), stereo-to-mono conversion, peak normalization.
"""

import math
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import scipy.signal
import sounddevice as sd
import soundfile as sf


class SoundboardEngine:
    # Engine state constants
    STATE_STOPPED = "STOPPED"
    STATE_RUNNING = "RUNNING"
    STATE_PLAYING_SFX = "PLAYING_SFX"

    def __init__(
        self,
        samplerate: int = 48000,
        blocksize: int = 1024,
        sfx_volume: float = 1.0,
        monitor_volume: float = 1.0,
        monitor_enabled: bool = True,
        mic_mix: bool = False,
    ):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.sfx_volume = max(0.0, min(2.0, sfx_volume))
        self.monitor_volume = max(0.0, min(2.0, monitor_volume))
        self.monitor_enabled = monitor_enabled
        self.mic_mix = mic_mix

        # Device IDs or device query info
        self.mic_device_id: Optional[int] = None
        self.cable_device_id: Optional[int] = None
        self.monitor_device_id: Optional[int] = None

        # Streams
        self._cable_stream: Optional[sd.Stream] = None
        self._monitor_stream: Optional[sd.OutputStream] = None

        # Channel configurations
        self._mic_channels = 1
        self._cable_channels = 2
        self._monitor_channels = 2

        # Thread synchronization
        self._lock = threading.Lock()

        # Engine state
        self._is_engine_running = False
        self._is_playing_sfx = False

        # In-memory audio buffer cache: sound_id -> np.ndarray (1D float32)
        self._sound_cache: Dict[str, np.ndarray] = {}
        self._sound_info: Dict[str, Dict[str, Any]] = {}

        # Current playback tracking
        self._current_sound_id: Optional[str] = None
        self._current_sound_name: Optional[str] = None
        self._current_buffer: Optional[np.ndarray] = None
        self._total_frames = 0
        self._cable_pos = 0
        self._monitor_pos = 0

        # Callbacks for UI updates
        self.on_state_change: Optional[Callable[[str, Optional[str]], None]] = None
        self.on_sfx_finished: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    # =========================================================================
    # Device Discovery & Utilities
    # =========================================================================

    @staticmethod
    def query_devices() -> List[Dict[str, Any]]:
        """Returns all queried host audio devices from sounddevice."""
        try:
            return list(sd.query_devices())
        except Exception as e:
            print(f"[SoundboardEngine] Error querying devices: {e}")
            return []

    @staticmethod
    def get_input_devices() -> List[Dict[str, Any]]:
        """Returns input devices (microphones/line-in) with friendly formatted labels."""
        devices = []
        hostapis = {i: api["name"] for i, api in enumerate(sd.query_hostapis())}
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                api_name = hostapis.get(dev.get("hostapi", -1), "")
                label = f"[{idx}] {dev['name']} ({api_name})"
                devices.append({
                    "id": idx,
                    "name": dev["name"],
                    "api": api_name,
                    "label": label,
                    "channels": dev["max_input_channels"],
                    "default_samplerate": dev.get("default_samplerate", 48000)
                })
        return devices

    @staticmethod
    def get_output_devices() -> List[Dict[str, Any]]:
        """Returns output devices (speakers, virtual cables, headphones)."""
        devices = []
        hostapis = {i: api["name"] for i, api in enumerate(sd.query_hostapis())}
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_output_channels", 0) > 0:
                api_name = hostapis.get(dev.get("hostapi", -1), "")
                label = f"[{idx}] {dev['name']} ({api_name})"
                devices.append({
                    "id": idx,
                    "name": dev["name"],
                    "api": api_name,
                    "label": label,
                    "channels": dev["max_output_channels"],
                    "default_samplerate": dev.get("default_samplerate", 48000)
                })
        return devices

    @classmethod
    def find_default_cable_device(cls) -> Optional[int]:
        """Auto-detects VB-Audio Cable Input or virtual cable device."""
        outputs = cls.get_output_devices()
        keywords = ["cable input", "vb-audio", "virtual cable", "cable-a", "cable-b"]
        for kw in keywords:
            for dev in outputs:
                if kw in dev["name"].lower():
                    return dev["id"]
        return None

    @classmethod
    def find_default_monitor_device(cls, exclude_id: Optional[int] = None) -> Optional[int]:
        """Detects physical headphones or default output for monitoring."""
        try:
            default_out = sd.default.device[1]
            if default_out is not None and default_out >= 0 and default_out != exclude_id:
                return default_out
        except Exception:
            pass

        outputs = cls.get_output_devices()
        # Prefer headphones or speakers that aren't virtual cable
        for dev in outputs:
            name_lower = dev["name"].lower()
            if dev["id"] != exclude_id and "cable" not in name_lower:
                if "headphone" in name_lower or "speaker" in name_lower:
                    return dev["id"]
        if outputs:
            return outputs[0]["id"]
        return None

    @classmethod
    def find_default_mic_device(cls) -> Optional[int]:
        """Detects default microphone input device."""
        try:
            default_in = sd.default.device[0]
            if default_in is not None and default_in >= 0:
                return default_in
        except Exception:
            pass
        inputs = cls.get_input_devices()
        if inputs:
            return inputs[0]["id"]
        return None

    # =========================================================================
    # Audio File Loading, Conversion, & Caching
    # =========================================================================

    def preload_sound(self, sound_id: str, filepath: str) -> Tuple[bool, float, str]:
        """
        Loads an audio file into memory, converts to mono, resamples to engine samplerate,
        normalizes peak, and caches the buffer. Returns (success, duration_seconds, message).
        """
        if not os.path.isfile(filepath):
            return False, 0.0, f"File not found: {filepath}"

        try:
            data, file_sr = sf.read(filepath, dtype="float32")
        except Exception as e:
            return False, 0.0, f"SoundFile error loading {os.path.basename(filepath)}: {e}"

        try:
            # 1. Convert multi-channel to mono
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            # 2. Resample if sample rate doesn't match engine active samplerate
            target_sr = self.samplerate
            if file_sr != target_sr:
                num_target_samples = int(round(len(data) * float(target_sr) / float(file_sr)))
                if num_target_samples > 0:
                    # scipy.signal.resample performs FFT resampling
                    data = scipy.signal.resample(data, num_target_samples).astype(np.float32)

            # 3. Normalize peak amplitude to prevent digital clipping
            peak = float(np.max(np.abs(data))) if len(data) > 0 else 0.0
            if peak > 0.98:
                data = data * (0.95 / peak)

            duration = len(data) / float(target_sr) if target_sr > 0 else 0.0

            with self._lock:
                self._sound_cache[sound_id] = data
                self._sound_info[sound_id] = {
                    "path": filepath,
                    "duration": duration,
                    "samples": len(data),
                    "original_sr": file_sr,
                }

            return True, duration, "Loaded successfully"
        except Exception as e:
            return False, 0.0, f"Processing error: {e}"

    def remove_sound_from_cache(self, sound_id: str) -> None:
        """Removes sound buffer from cache."""
        with self._lock:
            if self._current_sound_id == sound_id:
                self._stop_sfx_unlocked()
            self._sound_cache.pop(sound_id, None)
            self._sound_info.pop(sound_id, None)

    # =========================================================================
    # Audio Stream Callbacks (Real-time thread - ZERO disk I/O, ZERO locks)
    # =========================================================================

    def _cable_stream_callback(self, indata, outdata, frames, time_info, status):
        """
        Primary Duplex Stream Callback:
        - Reads Physical Mic (indata)
        - Writes to Virtual Cable (outdata)
        - If SFX playing: mutes mic (or mixes if mic_mix enabled), outputs SFX buffer.
        - If EOF reached: seamlessly resumes mic passthrough.
        """
        # Read atomic/volatile state variables without blocking lock
        is_playing = self._is_playing_sfx
        buffer = self._current_buffer
        sfx_vol = self.sfx_volume
        cable_channels = self._cable_channels
        mic_channels = self._mic_channels
        mic_mix = self.mic_mix

        if is_playing and buffer is not None:
            pos = self._cable_pos
            total = self._total_frames
            remaining = total - pos

            if remaining <= 0:
                # SFX has completed! Auto-resume mic passthrough immediately
                self._is_playing_sfx = False
                self._current_buffer = None
                sfx_ended_id = self._current_sound_id
                self._current_sound_id = None

                # Asynchronously notify UI that track finished
                if self.on_sfx_finished and sfx_ended_id:
                    threading.Thread(
                        target=self.on_sfx_finished,
                        args=(sfx_ended_id,),
                        daemon=True
                    ).start()

                # Passthrough mic for the current block
                self._copy_mic_to_output(indata, outdata, frames, mic_channels, cable_channels)
            else:
                n = min(frames, remaining)
                sfx_chunk = buffer[pos : pos + n] * sfx_vol
                self._cable_pos = pos + n

                if mic_mix:
                    # Mix mic input with SFX
                    mic_signal = indata[:n, 0] if indata.ndim > 1 else indata[:n]
                    mixed = mic_signal + sfx_chunk
                else:
                    # Suppress/mute mic completely during SFX
                    mixed = sfx_chunk

                # Write to output channels
                if cable_channels == 1:
                    outdata[:n, 0] = mixed
                else:
                    outdata[:n, 0] = mixed
                    outdata[:n, 1] = mixed

                # If SFX ended mid-block, fill remaining with mic passthrough
                if n < frames:
                    rem_frames = frames - n
                    self._copy_mic_to_output(
                        indata[n:], outdata[n:], rem_frames, mic_channels, cable_channels
                    )
        else:
            # Default: Seamless Physical Microphone Passthrough Mode
            self._copy_mic_to_output(indata, outdata, frames, mic_channels, cable_channels)

    def _copy_mic_to_output(self, indata, outdata, frames, mic_ch, out_ch):
        """Helper to copy mic input to output with channel adaptation."""
        if frames <= 0:
            return
        if mic_ch >= 1 and out_ch == 1:
            outdata[:frames, 0] = indata[:frames, 0]
        elif mic_ch == 1 and out_ch >= 2:
            outdata[:frames, 0] = indata[:frames, 0]
            outdata[:frames, 1] = indata[:frames, 0]
        elif mic_ch >= 2 and out_ch >= 2:
            outdata[:frames, 0] = indata[:frames, 0]
            outdata[:frames, 1] = indata[:frames, 1]

    def _monitor_stream_callback(self, outdata, frames, time_info, status):
        """
        Secondary Monitor Stream Callback:
        - Outputs SFX audio to user's headphones/speakers.
        - NEVER outputs user's mic (preventing self-echo).
        - Silenced when monitor is disabled or no SFX is playing.
        """
        if not self.monitor_enabled or not self._is_playing_sfx or self._current_buffer is None:
            outdata.fill(0.0)
            return

        buffer = self._current_buffer
        pos = self._monitor_pos
        total = self._total_frames
        remaining = total - pos
        mon_vol = self.monitor_volume
        mon_ch = self._monitor_channels

        if remaining <= 0:
            outdata.fill(0.0)
            return

        n = min(frames, remaining)
        chunk = buffer[pos : pos + n] * mon_vol
        self._monitor_pos = pos + n

        if mon_ch == 1:
            outdata[:n, 0] = chunk
        else:
            outdata[:n, 0] = chunk
            outdata[:n, 1] = chunk

        if n < frames:
            outdata[n:].fill(0.0)

    # =========================================================================
    # Playback Controls
    # =========================================================================

    def play_sound(self, sound_id: str, sound_name: Optional[str] = None) -> bool:
        """
        Triggers playback of the specified sound_id.
        Streams immediately to Virtual Cable and Monitor with zero disk latency.
        """
        with self._lock:
            if not self._is_engine_running:
                return False

            buffer = self._sound_cache.get(sound_id)
            if buffer is None or len(buffer) == 0:
                print(f"[SoundboardEngine] Sound '{sound_id}' not loaded in cache!")
                return False

            self._current_sound_id = sound_id
            self._current_sound_name = sound_name or sound_id
            self._current_buffer = buffer
            self._total_frames = len(buffer)
            self._cable_pos = 0
            self._monitor_pos = 0
            self._is_playing_sfx = True

        if self.on_state_change:
            self.on_state_change(self.STATE_PLAYING_SFX, self._current_sound_name)

        return True

    def stop_sfx(self) -> None:
        """Immediately stops any currently playing SFX and restores mic passthrough."""
        with self._lock:
            self._stop_sfx_unlocked()

        if self.on_state_change and self._is_engine_running:
            self.on_state_change(self.STATE_RUNNING, None)

    def _stop_sfx_unlocked(self) -> None:
        self._is_playing_sfx = False
        self._current_sound_id = None
        self._current_sound_name = None
        self._current_buffer = None
        self._total_frames = 0
        self._cable_pos = 0
        self._monitor_pos = 0

    def get_playback_status(self) -> Dict[str, Any]:
        """Queries current playback status for smooth GUI progress bar & labels."""
        total = self._total_frames
        pos = self._cable_pos
        is_playing = self._is_playing_sfx
        sr = self.samplerate

        if is_playing and total > 0 and sr > 0:
            current_sec = min(pos / sr, total / sr)
            total_sec = total / sr
            progress = min(1.0, max(0.0, pos / total))
        else:
            current_sec = 0.0
            total_sec = 0.0
            progress = 0.0

        return {
            "is_engine_running": self._is_engine_running,
            "is_playing_sfx": is_playing,
            "sound_id": self._current_sound_id,
            "sound_name": self._current_sound_name,
            "progress": progress,
            "current_sec": current_sec,
            "total_sec": total_sec,
        }

    # =========================================================================
    # Engine Lifecycle (Start / Stop)
    # =========================================================================

    def start_engine(
        self,
        mic_device_id: int,
        cable_device_id: int,
        monitor_device_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Starts the primary duplex stream (Mic -> Cable) and secondary monitor stream (Monitor).
        Returns (success, message).
        """
        self.stop_engine()

        self.mic_device_id = mic_device_id
        self.cable_device_id = cable_device_id
        self.monitor_device_id = monitor_device_id

        # Query channel capabilities for the selected devices
        try:
            mic_info = sd.query_devices(mic_device_id)
            cable_info = sd.query_devices(cable_device_id)
        except Exception as e:
            return False, f"Failed to query selected devices: {e}"

        # Choose channels safely
        self._mic_channels = min(2, max(1, mic_info.get("max_input_channels", 1)))
        self._cable_channels = min(2, max(1, cable_info.get("max_output_channels", 2)))

        # Determine monitor channels if applicable
        if monitor_device_id is not None and monitor_device_id >= 0:
            try:
                mon_info = sd.query_devices(monitor_device_id)
                self._monitor_channels = min(2, max(1, mon_info.get("max_output_channels", 2)))
            except Exception:
                self._monitor_channels = 2

        # 1. Open Primary Duplex Stream (Mic -> Virtual Cable)
        try:
            self._cable_stream = sd.Stream(
                device=(self.mic_device_id, self.cable_device_id),
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype="float32",
                channels=(self._mic_channels, self._cable_channels),
                callback=self._cable_stream_callback,
            )
            self._cable_stream.start()
        except Exception as e:
            self.stop_engine()
            return False, f"Failed to start Primary Stream (Mic -> Cable): {e}"

        # 2. Open Secondary Monitor Stream (if monitor device is valid and not identical to cable)
        if (
            self.monitor_enabled
            and self.monitor_device_id is not None
            and self.monitor_device_id >= 0
            and self.monitor_device_id != self.cable_device_id
        ):
            try:
                self._monitor_stream = sd.OutputStream(
                    device=self.monitor_device_id,
                    samplerate=self.samplerate,
                    blocksize=self.blocksize,
                    dtype="float32",
                    channels=self._monitor_channels,
                    callback=self._monitor_stream_callback,
                )
                self._monitor_stream.start()
            except Exception as e:
                print(f"[SoundboardEngine] Notice: Monitor stream could not open ({e}). Audio passthrough continues.")
                self._monitor_stream = None

        self._is_engine_running = True

        if self.on_state_change:
            self.on_state_change(self.STATE_RUNNING, None)

        return True, "Audio engine started successfully"

    def stop_engine(self) -> None:
        """Stops and closes all active streams safely."""
        with self._lock:
            self._stop_sfx_unlocked()
            self._is_engine_running = False

        if self._cable_stream is not None:
            try:
                self._cable_stream.stop()
                self._cable_stream.close()
            except Exception:
                pass
            self._cable_stream = None

        if self._monitor_stream is not None:
            try:
                self._monitor_stream.stop()
                self._monitor_stream.close()
            except Exception:
                pass
            self._monitor_stream = None

        if self.on_state_change:
            self.on_state_change(self.STATE_STOPPED, None)

    # =========================================================================
    # Property Setters
    # =========================================================================

    def set_sfx_volume(self, vol: float) -> None:
        self.sfx_volume = max(0.0, min(2.0, float(vol)))

    def set_monitor_volume(self, vol: float) -> None:
        self.monitor_volume = max(0.0, min(2.0, float(vol)))

    def set_monitor_enabled(self, enabled: bool) -> None:
        self.monitor_enabled = bool(enabled)

    def set_mic_mix(self, mix: bool) -> None:
        self.mic_mix = bool(mix)
