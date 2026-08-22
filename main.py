import os
import sys
import time
import math
import tempfile
import threading
import wave
import ctypes
from array import array
from ctypes import wintypes

import pyaudio
import pyperclip
from groq import Groq
from pynput import keyboard as pkeyboard

import overlay

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
MIN_SECONDS = 0.4

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    print("GROQ_API_KEY is not set in this window.")
    print("Get a key at https://console.groq.com/keys")
    sys.exit(1)

client = Groq(api_key=api_key)

_recording = threading.Event()
_start_gate = threading.Event()
_stop_app = threading.Event()
_f8_down = threading.Event()
_pause_lock = threading.Lock()
_last_pause = 0.0

user32 = ctypes.WinDLL("user32", use_last_error=True)
VK_PAUSE = 0x13
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
MOD_NOREPEAT = 0x4000


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


def _start_recording(source):
    if _recording.is_set():
        return
    _recording.set()
    _start_gate.set()
    print(f"Recording ({source})...")


def _stop_recording(source):
    if not _recording.is_set():
        return
    _recording.clear()
    print(f"Stopped ({source}).")


def _toggle_pause():
    global _last_pause
    now = time.time()
    with _pause_lock:
        if now - _last_pause < 0.45:
            return
        _last_pause = now
        if _recording.is_set():
            _stop_recording("Pause")
        else:
            _start_recording("Pause")


def _on_press(key):
    if key == pkeyboard.Key.esc:
        _stop_app.set()
        _recording.clear()
        _start_gate.set()
        return False
    if key != pkeyboard.Key.f8:
        return
    # Ignore keyboard auto-repeat while F8 is held
    if _f8_down.is_set():
        return
    _f8_down.set()
    _start_recording("F8 hold")


def _on_release(key):
    if key != pkeyboard.Key.f8:
        return
    _f8_down.clear()
    _stop_recording("F8 release")


def _pause_hotkey_thread():
    registered = user32.RegisterHotKey(None, 1, MOD_NOREPEAT, VK_PAUSE)
    if not registered:
        registered = user32.RegisterHotKey(None, 1, 0, VK_PAUSE)
    if registered:
        print("Pause hotkey OK: press to start, press again to stop.")
    else:
        print(
            f"Pause hotkey failed (err={ctypes.get_last_error()}). "
            "Use F8 hold-to-talk instead."
        )
        return
    msg = MSG()
    try:
        while not _stop_app.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    _toggle_pause()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)
    finally:
        user32.UnregisterHotKey(None, 1)


_S16_MAX = 32768.0

def _normalized_level(data, peak):
    """RMS loudness 0..1 with adaptive peak follower. No per-sample Python
    objects: raw bytes -> memoryview of shorts, single pass."""
    n = len(data) // 2
    if n == 0:
        return 0.0, peak
    # array('h') already copies; iterating it was heaviest. Use memoryview for zero-copy.
    try:
        mv = memoryview(data).cast('h')  # little-endian shorts, native
    except Exception:
        return 0.0, peak
    if len(mv) == 0:
        return 0.0, peak
    s2 = 0
    for v in mv:
        s2 += v * v
    rms = math.sqrt(s2 / len(mv))
    peak = max(peak * 0.96, rms, 500.0)
    norm = rms / peak
    if norm < 0.08:
        return 0.0, peak
    return min(1.0, ((norm - 0.08) / 0.92) ** 0.75), peak


def record_audio(island):
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )
    _start_gate.clear()
    _recording.clear()
    print("Ready — Pause: start/stop. F8: hold to talk. Esc: quit.")
    _start_gate.wait()
    if _stop_app.is_set():
        stream.close()
        p.terminate()
        return None

    island.show_listening()
    frames = []
    peak = 500.0
    started = time.time()
    while _recording.is_set() or (time.time() - started < 0.12):
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            break
        if _recording.is_set():
            frames.append(data)
            level, peak = _normalized_level(data, peak)
            island.push_level(level)
        elif time.time() - started >= 0.12:
            break

    stream.stop_stream()
    stream.close()
    p.terminate()
    seconds = len(frames) * CHUNK / float(SAMPLE_RATE)
    print(f"Captured {seconds:.1f}s of audio.")
    if seconds < MIN_SECONDS:
        print(f"Too short (need at least {MIN_SECONDS}s). Ignoring.")
        return None
    return frames


def save_audio(frames):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        wf = wave.open(temp_audio.name, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
        wf.close()
        return temp_audio.name


def transcribe_audio(audio_file_path):
    try:
        with open(audio_file_path, "rb") as file:
            text = client.audio.transcriptions.create(
                file=(os.path.basename(audio_file_path), file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="en",
            )
        if not text:
            return None
        text = str(text).strip()
        # Drop Whisper echo of leftover prompt-like lines
        if "person dictating text at a computer" in text.lower():
            return None
        if len(text) < 2:
            return None
        return text
    except Exception as e:
        print(f"Transcription error: {e}")
        return None


def paste_text(text):
    pyperclip.copy(text)
    time.sleep(0.2)
    # keybd_event is more reliable here than SendInput packing on 64-bit Python
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    print("Copied to clipboard and sent Ctrl+V. If nothing appeared, press Ctrl+V.")


def _pipeline(island):
    """Record -> transcribe -> paste loop. Runs on a worker thread so the
    UI (voice island) can own the main thread."""
    try:
        while not _stop_app.is_set():
            frames = record_audio(island)
            if _stop_app.is_set():
                break
            if not frames:
                island.show_error("Too short")
                continue
            island.show_transcribing()
            path = save_audio(frames)
            print("Transcribing...")
            text = transcribe_audio(path)
            try:
                os.unlink(path)
            except OSError:
                pass
            if _stop_app.is_set():
                break
            if text:
                print("\n---")
                print(text)
                print("---")
                paste_text(text)
                island.show_success("Pasted")
            else:
                print("No usable transcription.")
                island.show_error("No speech found")
    finally:
        island.close()


def main():
    island = overlay.create_island()

    threading.Thread(target=_pause_hotkey_thread, daemon=True).start()
    listener = pkeyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()

    worker = threading.Thread(target=_pipeline, args=(island,), daemon=True)
    worker.start()
    island.show_status("Ready — Pause or F8")

    print("Groq Whisperer")
    print("  Pause = press to start, press again to stop")
    print("  F8    = hold to talk, release to stop")
    print("Click the text field before you speak.")

    island.run()          # blocks on the UI thread until Esc closes it

    _stop_app.set()
    _start_gate.set()
    _recording.clear()
    listener.stop()
    worker.join(timeout=3)


if __name__ == "__main__":
    main()
