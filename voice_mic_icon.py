#!/usr/bin/env python3
"""VoiNoi (Voi Noi): noi tieng Viet thanh chu vao dung o dang chon, doc to tai lieu, tro chuyen bang giong noi."""

from __future__ import annotations

import ctypes
import concurrent.futures
import contextlib
import hashlib
import json
import math
import msvcrt
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import warnings
import winsound
from ctypes import wintypes
from pathlib import Path

import os
import sys
import tempfile
import wave

warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*audioop.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*pkg_resources.*")

import audioop
import speech_recognition as sr

_faster_whisper = None
_whisper = None
try:
    import webrtcvad
except Exception:
    webrtcvad = None

try:
    from pywinauto import Desktop
except Exception:
    Desktop = None


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STATE_FILE = APP_DIR / "mic-position.json"
TARGETS_FILE = APP_DIR / "voice-targets.json"
SETTINGS_FILE = APP_DIR / "voice-mic-settings.json"
LOCAL_SETTINGS_FILE = APP_DIR / "voice-mic-settings.local.json"
CONTEXT_FILE = APP_DIR / "voice-context.json"
LOCAL_CONTEXT_FILE = APP_DIR / "voice-context.local.json"
LOG_FILE = APP_DIR / "voice-mic.log"
LOCK_FILE = APP_DIR / "voice-mic.lock"
LAST_TRANSCRIPT_FILE = APP_DIR / "voice-last.txt"
TRANSCRIPT_HISTORY_FILE = APP_DIR / "voice-transcripts.jsonl"
LAST_AUDIO_FILE = APP_DIR / "voice-last.wav"
APP_TITLE = "VoiNoi"
APP_VERSION = "2.0.0"
APP_BUILD = "voinoi-2026-09-26"
SIZE = 38
CORE = 26
HUD_WIDTH = 220
HUD_HEIGHT = 44
HUD_GAP = 8
PARTICLE_EFFECT_WIDTH = 250   # nut tron nho + nhan trang thai + the ket qua
PARTICLE_EFFECT_HEIGHT = 160
ORB_RADIUS = 30
RESULT_SHOW_MS = 4000
PARTICLE_EFFECT_DEFAULT_COUNT = 180
PARTICLE_EFFECT_GAP = 8
HIDE_FLOATING_MIC_BUTTON = True
SHOW_FLOATING_MIC_ICON = False
STREAM_PHRASE_SECONDS = 7
MAX_SPEECH_CHUNK_SECONDS = 18.0
MIN_SPEECH_CHUNK_SECONDS = 0.45
SILENCE_END_SECONDS = 2.0
MAX_UNRECOGNIZED_BEFORE_STOP = 3
VOICE_START_FRAMES = 2
VAD_MIN_THRESHOLD = 220
VAD_NOISE_MULTIPLIER = 1.35
VAD_NOISE_MARGIN = 160
VAD_P90_MARGIN = 60
VAD_MAX_THRESHOLD = 1800
VAD_ACTIVITY_MARGIN = 80
VAD_ACTIVITY_MULTIPLIER = 1.12
WEBRTC_RMS_MIN_GATE = 220
WEBRTC_RMS_NOISE_RATIO = 0.65
WEBRTC_VAD_AGGRESSIVENESS = 2
WEBRTC_VAD_SAMPLE_RATE = 16000
WEBRTC_SHORT_VOICE_END_SECONDS = 1.8
RMS_SHORT_VOICE_END_SECONDS = 2.0
LONG_VOICE_AFTER_SECONDS = 9.0
WEBRTC_VOICE_END_SECONDS = 1.7
RMS_VOICE_END_SECONDS = 1.9
MIN_CAPTURE_BEFORE_AUTO_STOP_SECONDS = 1.2
MIN_CAPTURE_BEFORE_SILENCE_STOP_SECONDS = 3.0
VAD_SOFT_ACTIVITY_MARGIN = 120
VAD_SOFT_ACTIVITY_MULTIPLIER = 1.08
GOOGLE_RECOGNITION_TIMEOUT_SECONDS = 10.0
GOOGLE_SINGLE_PASS_MAX_SECONDS = 10.0
GOOGLE_LONG_CHUNK_SECONDS = 9.0
GOOGLE_CHUNK_BOUNDARY_SEARCH_SECONDS = 2.5
GOOGLE_CHUNK_MIN_SECONDS = 5.0
GOOGLE_CHUNK_MIN_TAIL_SECONDS = 4.5
GOOGLE_MIN_RETRY_CHUNK_SECONDS = 4.0
GOOGLE_LOW_CONFIDENCE_FALLBACK_THRESHOLD = 0.82
WHISPER_VERIFY_LONG_AUDIO_SECONDS = 12.0
WHISPER_SELECTION_MARGIN = 0.04
LOW_COVERAGE_WPM = 92  # Google tra ve it hon muc nay (tu/phut) cho doan dai => nghi roi chu (~5% doan); setting low_coverage_wpm, 0 = tat
LOW_COVERAGE_MIN_CHUNK_SECONDS = 5.0
MIN_VOICED_SECONDS_FOR_WHISPER = 0.6  # Google khong nghe ra va tieng nguoi that it hon muc nay: bo qua, khong doi Whisper
VOICE_CONTEXT_MAX_TERMS = 300
VOICE_CONTEXT_MAX_PHRASES = 220
TRANSPARENT = "#ff00ff"
LISTEN_CHUNK_SECONDS = 8
LISTEN_TIMEOUT_SECONDS = 8.0
AUTO_LISTEN_TIMEOUT_SECONDS = 18.0
AUTO_AFTER_SPEECH_TIMEOUT_SECONDS = 2.8
AUTO_PHRASE_LIMIT_SECONDS = 300
INITIAL_NO_SPEECH_TIMEOUT_SECONDS = 12.0
AUTO_CLICK_POLL_SECONDS = 0.035
AUTO_CLICK_COOLDOWN_SECONDS = 0.8
CLICK_DETECT_RETRY_MS = (90, 220, 420, 700)
CHAT_BOTTOM_FRACTION = 0.14
CHAT_BOTTOM_MAX_HEIGHT = 110
CHAT_HINT_FRACTION = 0.25
STRICT_CHAT_BOTTOM_MAX_HEIGHT = 110
STRICT_CHAT_WIDTH_FRACTION = 0.65
CARET_CLICK_RADIUS = 60
LEARNED_TARGET_RADIUS = 80
ERROR_ALREADY_EXISTS = 183
SINGLE_INSTANCE_MUTEX_NAME = "Local\\VietnameseVoiceMicSingleInstance"
SINGLE_INSTANCE_MUTEX_HANDLE = None
SINGLE_INSTANCE_LOCK_FILE_HANDLE = None

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
UIA_DESKTOP = Desktop(backend="uia") if Desktop else None

HWND_TOPMOST = wintypes.HWND(-1)
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_M = 0x4D
VK_V = 0x56
VK_C = 0x43
VK_LBUTTON = 0x01
VK_BACK = 0x08
VK_1 = 0x31
VK_2 = 0x32
VK_F2 = 0x71
VK_ESCAPE = 0x1B
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SHORT_COMMAND_MAX_SECONDS = 4.0
RADIAL_TIMEOUT_SECONDS = 10.0  # vong tron tu dong neu khong chon gi
RADIAL_SIZE = 220              # khung ve (vong tron 92px + cho cho hieu ung phong/vien sang)
RADIAL_OUTER = 92
RADIAL_INNER = 30
RADIAL_ACTIVE = "#c2410c"      # mau cam cho o dang tro chuot
RADIAL_IDLE = "#141c2b"
RADIAL_GLOW = "#fb923c"        # vien sang quanh o dang chon
RADIAL_OPEN_SECONDS = 0.16     # thoi gian hien len (phong to + ro dan)
RADIAL_CLOSE_SECONDS = 0.11    # thoi gian thu nho + mo di khi chon xong
RADIAL_FRAME_MS = 16
# (ma, nhan, dong phu, goc bat dau Tk: do, nguoc chieu kim dong ho tinh tu huong 3 gio)
RADIAL_OPTIONS = (
    ("dictation", "Gõ chữ", "voice to text", 45),
    ("reader", "Đọc", "đoạn đã copy", 135),
    ("cancel", "Huỷ", "", 225),
    ("chat", "Nói", "trò chuyện", 315),
)

if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_longlong):
    user32.GetWindowLongPtrW.restype = ctypes.c_longlong
    user32.SetWindowLongPtrW.restype = ctypes.c_longlong
else:
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.restype = ctypes.c_long

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL


try:
    user32.SetProcessDPIAware()
except Exception:
    pass


def load_position() -> tuple[int, int]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return int(data.get("x", 900)), int(data.get("y", 895))
    except Exception:
        return 900, 895


def save_position(x: int, y: int) -> None:
    try:
        STATE_FILE.write_text(json.dumps({"x": x, "y": y}), encoding="utf-8")
    except Exception:
        return


def load_voice_targets() -> dict[str, tuple[int, int]]:
    try:
        data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
        targets: dict[str, tuple[int, int]] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                targets[str(key)] = (int(value["x"]), int(value["y"]))
        return targets
    except Exception:
        return {}


def save_voice_targets(targets: dict[str, tuple[int, int]]) -> None:
    try:
        data = {key: {"x": point[0], "y": point[1]} for key, point in targets.items()}
        TARGETS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        return


_JSON_CACHE: dict[Path, tuple[tuple[int, int], object]] = {}
_JSON_CACHE_LOCK = threading.Lock()


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def read_json_cached(path: Path) -> object:
    """Doc JSON, chi doc lai dia khi file doi. Truoc day moi lan lam sach cau doc lai file ca nghin lan (~3 giay)."""
    signature = file_signature(path)
    if signature is None:
        return None
    with _JSON_CACHE_LOCK:
        cached = _JSON_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    with _JSON_CACHE_LOCK:
        _JSON_CACHE[path] = (signature, data)
    return data


def load_settings() -> dict[str, object]:
    settings: dict[str, object] = {}
    for path in (SETTINGS_FILE, LOCAL_SETTINGS_FILE):
        try:
            data = read_json_cached(path)
            if isinstance(data, dict):
                settings.update(data)
        except Exception as exc:
            log(f"settings load skipped | path={path.name} | {type(exc).__name__}: {exc}")
    return settings


def microphone_name_score(name: str) -> int:
    lower = name.lower()
    score = 0
    if any(word in lower for word in ("microphone", "mic", "input", "capture")):
        score += 20
    if "headset" in lower and "hands-free" in lower:
        score += 10
    if any(word in lower for word in ("headphones", "speakers", "output", "nvidia", "stereo")):
        score -= 50
    return score


def first_matching_microphone(names: list[str], needle: str) -> tuple[int, str] | None:
    matches = [
        (microphone_name_score(name), index, name)
        for index, name in enumerate(names)
        if needle in name.lower()
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1]))
    _score, index, name = matches[0]
    return index, name


def select_microphone_device(settings: dict[str, object], names: list[str] | None = None) -> tuple[int | None, str]:
    preferred = str(settings.get("preferred_microphone", "") or "").strip().lower()
    fallback_hints = settings.get("microphone_name_hints", ["Microphone", "Headset", "USB Audio Device", "External Microphone"])
    hints = [str(h).lower() for h in fallback_hints if str(h).strip()]
    if names is None:
        names = AUDIO_DEVICES.refresh()

    if preferred:
        match = first_matching_microphone(names, preferred)
        if match:
            return match

    for hint in hints:
        match = first_matching_microphone(names, hint)
        if match:
            return match

    return None, "system default"


def microphone_device_candidates(settings: dict[str, object], names: list[str] | None = None) -> list[tuple[int | None, str]]:
    if names is None:
        names = AUDIO_DEVICES.refresh()
    preferred = str(settings.get("preferred_microphone", "") or "").strip().lower()
    fallback_hints = settings.get("microphone_name_hints", ["Microphone", "Headset", "USB Audio Device", "External Microphone"])
    hints = [str(h).lower() for h in fallback_hints if str(h).strip()]
    candidates: list[tuple[int | None, str]] = []
    seen: set[int | None] = set()

    def add(index: int | None, name: str) -> None:
        if index in seen:
            return
        seen.add(index)
        candidates.append((index, name))

    selected_index, selected_name = select_microphone_device(settings, names)
    add(selected_index, selected_name)

    needles = [needle for needle in [preferred, *hints] if needle]
    scored: list[tuple[int, int, str]] = []
    for index, name in enumerate(names):
        lower = name.lower()
        if needles and not any(needle in lower for needle in needles):
            continue
        score = microphone_name_score(name)
        if score <= -20:
            continue
        scored.append((score, index, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    for _score, index, name in scored:
        add(index, name)

    add(None, "system default")
    return candidates


def set_clipboard_text(text: str) -> None:
    data = text.encode("utf-16-le") + b"\x00\x00"
    hglob = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not hglob:
        raise OSError("GlobalAlloc failed")
    locked = kernel32.GlobalLock(hglob)
    if not locked:
        kernel32.GlobalFree(hglob)
        raise OSError("GlobalLock failed")
    ctypes.memmove(locked, data, len(data))
    kernel32.GlobalUnlock(hglob)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(hglob)
        raise OSError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, hglob):
            kernel32.GlobalFree(hglob)
            raise OSError("SetClipboardData failed")
        hglob = None
    finally:
        user32.CloseClipboard()


def get_clipboard_text() -> str:
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text_retry(text: str, attempts: int = 8, delay: float = 0.08) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            set_clipboard_text(text)
            return True
        except OSError as exc:
            log(f"clipboard set retry | attempt={attempt} | {exc}")
            time.sleep(delay)
    return False


def keybd(vk: int, flags: int = 0) -> None:
    user32.keybd_event(vk, 0, flags, 0)


def send_ctrl_v() -> None:
    keybd(VK_CONTROL)
    time.sleep(0.02)
    keybd(VK_V)
    time.sleep(0.03)
    keybd(VK_V, KEYEVENTF_KEYUP)
    time.sleep(0.02)
    keybd(VK_CONTROL, KEYEVENTF_KEYUP)


def focus_locked_target(target_hwnd: int, target_point: tuple[int, int] | None, click_to_focus: bool = True) -> int:
    if target_hwnd:
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
    if click_to_focus and target_point:
        user32.SetCursorPos(target_point[0], target_point[1])
        time.sleep(0.02)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)
    return foreground_window()


def beep_async(kind: str) -> None:
    patterns = {
        "start": ((1200, 60),),
        "chunk": ((980, 35),),
        "tick": ((1500, 12),),
        "done": ((880, 70), (1180, 45)),
        "stop": ((620, 55),),
        "error": ((400, 80), (300, 80)),
    }

    def worker() -> None:
        for freq, duration in patterns.get(kind, patterns["chunk"]):
            winsound.Beep(freq, duration)
            time.sleep(0.025)

    threading.Thread(target=worker, daemon=True).start()


def log(message: str) -> None:
    try:
        now = time.time()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + f".{int(now * 1000) % 1000:03d}"
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(f"{stamp} {message}\n")
    except Exception:
        return


def save_last_transcript(text: str, metadata: dict[str, object] | None = None) -> None:
    text = text.strip()
    if not text:
        return
    metadata = metadata or {}
    record = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "text": text,
        **metadata,
    }
    try:
        LAST_TRANSCRIPT_FILE.write_text(text, encoding="utf-8")
    except Exception as exc:
        log(f"last transcript save error: {type(exc).__name__}: {exc}")
    try:
        with TRANSCRIPT_HISTORY_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        log(f"transcript history save error: {type(exc).__name__}: {exc}")


def save_last_audio(audio: sr.AudioData, metadata: dict[str, object] | None = None) -> None:
    metadata = metadata or {}
    try:
        with wave.open(str(LAST_AUDIO_FILE), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(audio.sample_width)
            wav.setframerate(audio.sample_rate)
            wav.writeframes(audio.frame_data)
        log(
            f"last audio saved | path={LAST_AUDIO_FILE.name} | "
            f"bytes={len(audio.frame_data)} | metadata={metadata}"
        )
    except Exception as exc:
        log(f"last audio save error: {type(exc).__name__}: {exc}")


LAST_OWN_CLIPBOARD_SEQ = [0]  # so thu tu clipboard luc Voice Mic tu dat transcript vao (de khong doc nham)


def clipboard_sequence() -> int:
    return int(user32.GetClipboardSequenceNumber())


READER_URL = "http://127.0.0.1:8767"


def reader_request(path: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{READER_URL}/api/{path}", data=data, headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def doc_reader_command(*args: str) -> list[str]:
    """Lenh chay Tro ly doc: ban .exe tu goi lai chinh no voi --doc-reader, ban nguon chay doc_reader.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--doc-reader", *args]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else sys.executable), "-X", "utf8", str(APP_DIR / "doc_reader.py"), *args]


def reader_import_clipboard() -> dict:
    """Dua noi dung clipboard (chu, link hoac duong dan file) vao Tro ly doc; tu bat may chu neu chua chay."""
    try:
        reader_request("ping", timeout=1.5)
    except Exception:
        subprocess.Popen(
            doc_reader_command("--no-browser"),
            cwd=str(APP_DIR), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 15
        while True:
            time.sleep(0.4)
            try:
                reader_request("ping", timeout=1.0)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
    try:
        return reader_request("import", {"kind": "clipboard"}, timeout=40)
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8")).get("error") or str(exc)
        except Exception:
            message = str(exc)
        raise RuntimeError(message) from exc


def keep_transcript_on_clipboard(text: str, reason: str) -> bool:
    ok = set_clipboard_text_retry(text)
    if ok:
        LAST_OWN_CLIPBOARD_SEQ[0] = clipboard_sequence()
        log(f"recovery clipboard set | reason={reason} | text={text[:80]}")
    else:
        log(f"recovery clipboard failed | reason={reason} | text={text[:80]}")
    return ok


def acquire_single_instance_lock() -> bool:
    global SINGLE_INSTANCE_MUTEX_HANDLE, SINGLE_INSTANCE_LOCK_FILE_HANDLE
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX_NAME)
    last_error = ctypes.get_last_error()
    if not handle:
        log("single instance mutex failed; falling back to file lock")
    elif last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        log("another VoiNoi instance is already running; exiting")
        return False
    else:
        SINGLE_INSTANCE_MUTEX_HANDLE = handle

    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_file = LOCK_FILE.open("a+b")
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()).encode("ascii"))
        lock_file.flush()
        SINGLE_INSTANCE_LOCK_FILE_HANDLE = lock_file
    except OSError:
        if SINGLE_INSTANCE_MUTEX_HANDLE:
            kernel32.CloseHandle(SINGLE_INSTANCE_MUTEX_HANDLE)
            SINGLE_INSTANCE_MUTEX_HANDLE = None
        log("another VoiNoi instance is already running; exiting via file lock")
        return False

    return True


class AudioDevices:
    """Mot PyAudio dung chung cho moi phien nghe.

    sr.Microphone khoi tao PortAudio 3-4 lan moi phien (liet ke thiet bi, kiem tra, mo) mat ~1 giay truoc khi
    nghe duoc. Giu san mot ban thi mo mic chi con ~30 ms. Danh sach thiet bi lam moi khi cu hoac khi mo loi
    (cam/rut mic)."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.pa = None
        self.names: list[str] = []
        self.loaded_at = 0.0
        self.open_streams = 0

    def refresh(self, force: bool = False, max_age: float | None = None) -> list[str]:
        with self.lock:
            stale = (
                self.pa is None
                or force
                or (max_age is not None and time.monotonic() - self.loaded_at > max_age)
            )
            if stale and (self.open_streams == 0 or self.pa is None):
                import pyaudio

                if self.pa is not None:
                    try:
                        self.pa.terminate()
                    except Exception:
                        pass
                    self.pa = None
                pa = pyaudio.PyAudio()
                names: list[str] = []
                for index in range(pa.get_device_count()):
                    try:
                        names.append(str(pa.get_device_info_by_index(index).get("name", "")))
                    except Exception:
                        names.append("")
                self.pa = pa
                self.names = names
                self.loaded_at = time.monotonic()
            return list(self.names)

    def prewarm(self, max_age: float = 30.0) -> None:
        threading.Thread(target=self._prewarm, args=(max_age,), daemon=True, name="mic-prewarm").start()

    def _prewarm(self, max_age: float) -> None:
        try:
            self.refresh(max_age=max_age)
        except Exception as exc:
            log(f"mic prewarm error: {type(exc).__name__}: {exc}")

    def open(self, index: int | None) -> "FastMicSource":
        with self.lock:
            if self.pa is None:
                self.refresh()
            source = FastMicSource(self.pa, index)
            self.open_streams += 1
            return source

    def close(self, source: "FastMicSource") -> None:
        source.close()
        with self.lock:
            self.open_streams = max(0, self.open_streams - 1)


class FastMicSource:
    """Giong sr.Microphone (stream, CHUNK, SAMPLE_RATE, SAMPLE_WIDTH) nhung dung PyAudio co san."""

    CHUNK = 1024

    def __init__(self, pa: object, index: int | None) -> None:
        import pyaudio

        info = pa.get_device_info_by_index(index) if index is not None else pa.get_default_input_device_info()
        if int(info.get("maxInputChannels", 0) or 0) < 1:
            raise OSError(f"device {index} has no input channels")
        self.SAMPLE_RATE = int(info["defaultSampleRate"])
        self.SAMPLE_WIDTH = pyaudio.get_sample_size(pyaudio.paInt16)
        self.stream = pa.open(
            input_device_index=index,
            channels=1,
            format=pyaudio.paInt16,
            rate=self.SAMPLE_RATE,
            frames_per_buffer=self.CHUNK,
            input=True,
        )

    def close(self) -> None:
        try:
            if not self.stream.is_stopped():
                self.stream.stop_stream()
        except Exception:
            pass
        try:
            self.stream.close()
        except Exception:
            pass


AUDIO_DEVICES = AudioDevices()
MIC_DEVICE_MAX_AGE_SECONDS = 300.0


def read_audio_chunk(stream: object, chunk_size: int) -> bytes:
    try:
        return stream.read(chunk_size, exception_on_overflow=False)
    except TypeError:
        return stream.read(chunk_size)


def create_voice_vad(sample_rate: int, sample_width: int) -> dict[str, object] | None:
    if webrtcvad is None or sample_width != 2:
        return None
    return {
        "vad": webrtcvad.Vad(WEBRTC_VAD_AGGRESSIVENESS),
        "source_rate": sample_rate,
        "target_rate": WEBRTC_VAD_SAMPLE_RATE,
        "resample_state": None,
        "pending": b"",
    }


def vad_detects_speech(vad_state: dict[str, object] | None, data: bytes, sample_width: int) -> bool | None:
    if vad_state is None:
        return None
    target_rate = int(vad_state["target_rate"])
    source_rate = int(vad_state["source_rate"])
    payload = data
    if source_rate != target_rate:
        try:
            payload, vad_state["resample_state"] = audioop.ratecv(
                data,
                sample_width,
                1,
                source_rate,
                target_rate,
                vad_state.get("resample_state"),
            )
        except Exception:
            return None
    pending = bytes(vad_state.get("pending", b"")) + payload
    frame_bytes = int(target_rate * 30 / 1000) * sample_width
    if frame_bytes <= 0 or len(pending) < frame_bytes:
        vad_state["pending"] = pending
        return None
    hits = 0
    total = 0
    consumed = 0
    vad = vad_state["vad"]
    for start in range(0, len(pending) - frame_bytes + 1, frame_bytes):
        frame = pending[start:start + frame_bytes]
        try:
            if vad.is_speech(frame, target_rate):
                hits += 1
            total += 1
            consumed = start + frame_bytes
        except Exception:
            return None
    vad_state["pending"] = pending[consumed:]
    if total == 0:
        return None
    return hits > 0


def calculate_vad_threshold(noise_samples: list[int]) -> tuple[int, int, int, int]:
    if not noise_samples:
        return VAD_MIN_THRESHOLD, 140, 50, 50
    samples = sorted(noise_samples)
    median = samples[len(samples) // 2]
    p90 = samples[min(len(samples) - 1, int(len(samples) * 0.9))]
    threshold = max(
        VAD_MIN_THRESHOLD,
        int(median * VAD_NOISE_MULTIPLIER),
        median + VAD_NOISE_MARGIN,
        p90 + VAD_P90_MARGIN,
    )
    threshold = min(threshold, VAD_MAX_THRESHOLD)
    activity_threshold = max(
        140,
        int(median * VAD_ACTIVITY_MULTIPLIER),
        median + VAD_ACTIVITY_MARGIN,
    )
    activity_threshold = min(activity_threshold, max(VAD_MIN_THRESHOLD, threshold - 80))
    return threshold, activity_threshold, median, p90


def calculate_webrtc_rms_gate(noise_floor: int, speech_threshold: int) -> int:
    noise_gate = int(max(0, noise_floor) * WEBRTC_RMS_NOISE_RATIO)
    return max(WEBRTC_RMS_MIN_GATE, min(speech_threshold, noise_gate))


def count_transcript_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def format_speech_stats(text: str, duration_seconds: float) -> tuple[int, int, int, float]:
    words = count_transcript_words(text)
    chars = len(text)
    duration = max(0.1, duration_seconds)
    words_per_minute = int(round(words * 60 / duration)) if words else 0
    return words_per_minute, words, chars, duration


def parse_version(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(version or ""))
    return tuple(int(part) for part in parts[:4]) or (0,)


def is_newer_version(remote: str, current: str) -> bool:
    left = parse_version(remote)
    right = parse_version(current)
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def read_update_manifest(manifest_url: str) -> dict[str, object]:
    manifest_url = manifest_url.strip()
    if not manifest_url:
        return {}
    if re.match(r"^https?://", manifest_url, flags=re.IGNORECASE):
        with urllib.request.urlopen(manifest_url, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    path = Path(manifest_url.replace("file:///", "")).expanduser()
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_update_url(manifest_url: str, zip_url: str) -> str:
    if re.match(r"^https?://", zip_url, flags=re.IGNORECASE):
        return zip_url
    if re.match(r"^https?://", manifest_url, flags=re.IGNORECASE):
        return urllib.parse.urljoin(manifest_url, zip_url)
    manifest_path = Path(manifest_url.replace("file:///", "")).expanduser()
    return str((manifest_path.parent / zip_url).resolve())


def download_update_zip(zip_url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if re.match(r"^https?://", zip_url, flags=re.IGNORECASE):
        with urllib.request.urlopen(zip_url, timeout=60) as response, destination.open("wb") as file:
            shutil.copyfileobj(response, file)
        return
    shutil.copy2(Path(zip_url).expanduser(), destination)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_window_long(hwnd: int, index: int) -> int:
    if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_longlong):
        return int(user32.GetWindowLongPtrW(hwnd, index))
    return int(user32.GetWindowLongW(hwnd, index))


def set_window_long(hwnd: int, index: int, value: int) -> None:
    if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_longlong):
        user32.SetWindowLongPtrW(hwnd, index, value)
    else:
        user32.SetWindowLongW(hwnd, index, value)


def mix_color(start: str, end: str, t: float) -> str:
    """Pha tron hai mau hex theo ti le t (0..1), de chuyen mau muot."""
    t = max(0.0, min(1.0, t))
    a = [int(start[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(end[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **options: object) -> int:
    """Hinh chu nhat bo tron goc tren canvas Tk (da giac lam muot)."""
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **options)


def find_window_by_title(fragment: str) -> int:
    """Tim cua so dang hien co tieu de chua doan chu nay (vi du cua so Tro ly doc)."""
    found: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if fragment in buffer.value:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return found[0] if found else 0


def make_tool_window(hwnd: int) -> None:
    ex_style = get_window_long(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_TOOLWINDOW
    ex_style &= ~WS_EX_APPWINDOW
    set_window_long(hwnd, GWL_EXSTYLE, ex_style)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def paste_to_focused_field(
    text: str,
    root: tk.Tk,
    target_hwnd: int = 0,
    target_point: tuple[int, int] | None = None,
    restore_root: bool = True,
) -> None:
    text = text.strip()
    if not text:
        return
    if target_hwnd and not window_exists(target_hwnd):
        keep_transcript_on_clipboard(text, "target-closed")
        log(f"paste skipped: target window closed | hwnd={target_hwnd} | text={text[:120]}")
        return
    try:
        set_clipboard_text(text)
        time.sleep(0.08)
        log(f"clipboard set: {get_clipboard_text()[:80]}")
        root.withdraw()
        root.update_idletasks()
        time.sleep(0.12)
        focused_hwnd = focus_locked_target(target_hwnd, target_point, click_to_focus=True)
        send_ctrl_v()
        log(f"paste sent | hwnd={target_hwnd} | focused={focused_hwnd} | point={target_point}")
    finally:
        time.sleep(0.12)
        keep_transcript_on_clipboard(text, "after-paste")
        if restore_root:
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)


def left_button_down() -> bool:
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


HOTKEY_KEY_CODES = {"ctrl": VK_CONTROL, "control": VK_CONTROL, "alt": VK_MENU, "shift": 0x10,
                    "win": 0x5B, "space": 0x20, "enter": 0x0D, "tab": 0x09}


def parse_hotkey(text: str) -> tuple[int, ...]:
    """'ctrl+alt+v' -> (VK_CONTROL, VK_MENU, 0x56). Chuoi rong hoac sai thi tat phim tat."""
    codes: list[int] = []
    for part in text.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in HOTKEY_KEY_CODES:
            codes.append(HOTKEY_KEY_CODES[part])
        elif len(part) == 1 and part.isalnum():
            codes.append(ord(part.upper()))
        elif re.fullmatch(r"f([1-9]|1[0-2])", part):
            codes.append(0x70 + int(part[1:]) - 1)
        else:
            return ()
    return tuple(codes) if len(codes) >= 2 else ()


def voice_hotkey_down() -> bool:
    return key_down(VK_CONTROL) and key_down(VK_MENU) and key_down(VK_M)


def foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def window_exists(hwnd: int) -> bool:
    return bool(hwnd and user32.IsWindow(hwnd))


def window_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def stable_target_key(hwnd: int, point: tuple[int, int]) -> str:
    """Key á»•n Ä‘á»‹nh qua restart: class cá»­a sá»• + vá»‹ trÃ­ snap 40px."""
    cls = window_class_name(hwnd)
    sx, sy = (point[0] // 40) * 40, (point[1] // 40) * 40
    return f"{cls}|{sx}|{sy}"


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def virtual_screen_rect() -> tuple[int, int, int, int]:
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        return 0, 0, 1920, 1080
    return left, top, left + width, top + height


def get_caret_screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    thread_id = user32.GetWindowThreadProcessId(hwnd, None)
    if not thread_id:
        return None

    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)) or not info.hwndCaret:
        return None

    left_top = wintypes.POINT(info.rcCaret.left, info.rcCaret.top)
    right_bottom = wintypes.POINT(info.rcCaret.right, info.rcCaret.bottom)
    if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(left_top)):
        return None
    if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(right_bottom)):
        return None

    left, top = int(left_top.x), int(left_top.y)
    right, bottom = int(right_bottom.x), int(right_bottom.y)
    if left == right and top == bottom:
        return None
    return left, top, right, bottom


def rect_center(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = rect
    return (left + right) // 2, (top + bottom) // 2


def point_near_rect(point: tuple[int, int], rect: tuple[int, int, int, int], radius: int) -> bool:
    x, y = point
    left, top, right, bottom = rect
    nearest_x = min(max(x, left), right)
    nearest_y = min(max(y, top), bottom)
    return math.hypot(x - nearest_x, y - nearest_y) <= radius


def point_in_bottom_chat_zone(point: tuple[int, int], hwnd: int) -> bool:
    rect = window_rect(hwnd)
    if not rect:
        return False
    x, y = point
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width < 260 or height < 180:
        return False
    zone_height = min(int(height * CHAT_BOTTOM_FRACTION), CHAT_BOTTOM_MAX_HEIGHT)
    zone_top = bottom - zone_height
    return left <= x <= right and zone_top <= y <= bottom


def point_in_chat_hint_zone(point: tuple[int, int], hwnd: int) -> bool:
    rect = window_rect(hwnd)
    if not rect:
        return False
    x, y = point
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width < 260 or height < 180:
        return False
    zone_top = bottom - int(height * CHAT_HINT_FRACTION)
    return left <= x <= right and zone_top <= y <= bottom


def point_in_strict_chat_zone(point: tuple[int, int], hwnd: int) -> bool:
    rect = window_rect(hwnd)
    if not rect:
        return False
    x, y = point
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width < 260 or height < 180:
        return False
    zone_top = bottom - min(int(height * CHAT_BOTTOM_FRACTION), STRICT_CHAT_BOTTOM_MAX_HEIGHT)
    center = (left + right) / 2
    half_width = width * STRICT_CHAT_WIDTH_FRACTION / 2
    return center - half_width <= x <= center + half_width and zone_top <= y <= bottom


def best_paste_point(
    clicked_point: tuple[int, int],
    caret_rect: tuple[int, int, int, int] | None,
) -> tuple[int, int]:
    if caret_rect and point_near_rect(clicked_point, caret_rect, CARET_CLICK_RADIUS):
        return rect_center(caret_rect)
    return clicked_point


_RICH_INPUT_CLASSES = frozenset({
    "prosemirror", "tiptap", "ql-editor", "codemirror", "cm-content",
    "monaco-editor", "ace_editor", "notranslate", "public-draftstyleditor",
    "draftstyleditorroot",
})

_RICH_INPUT_CONTROL_TYPES = frozenset({"edit"})

# Class cá»­a sá»• Chrome/Electron â€” Ã´ chat náº±m á»Ÿ Ä‘Ã¡y
_BROWSER_WIN_CLASSES = frozenset({"Chrome_WidgetWin_1", "Chrome_WidgetWin_0"})
# Tá»« khÃ³a trong tÃªn UIA element gá»£i Ã½ Ä‘Ã¢y lÃ  Ã´ nháº­p liá»‡u
_INPUT_NAME_HINTS = frozenset({
    "write", "message", "compose", "type here", "input", "send", "prompt",
    "nhập", "soạn", "chat", "reply", "your message",
})


def is_browser_bottom_input(hwnd: int, point: tuple[int, int]) -> bool:
    """Heuristic: click á»Ÿ 22% Ä‘Ã¡y cá»­a sá»• Chrome/Electron â†’ kháº£ nÄƒng cao lÃ  Ã´ chat."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    if buf.value not in _BROWSER_WIN_CLASSES:
        return False
    rect = window_rect(hwnd)
    if not rect:
        return False
    left, top, right, bottom = rect
    h = bottom - top
    if h <= 0:
        return False
    zone_top = bottom - int(h * 0.22)
    return zone_top <= point[1] <= bottom and left <= point[0] <= right


def uia_is_likely_input(point: tuple[int, int]) -> tuple[bool, str]:
    """Stricter check: only trigger on edit/document control types or known rich-text classes."""
    if UIA_DESKTOP is None:
        return False, "uia=unavailable"
    try:
        wrapper = UIA_DESKTOP.from_point(point[0], point[1])
        chain: list[str] = []
        current = wrapper
        for _ in range(8):
            info = current.element_info
            control_type = str(getattr(info, "control_type", "") or "").lower()
            class_name = str(getattr(info, "class_name", "") or "")
            name = str(getattr(info, "name", "") or "")
            auto_id = str(getattr(info, "automation_id", "") or "")
            chain.append(f"{control_type}:{class_name}:{name[:28]}:{auto_id[:28]}")
            # Match known rich input class substrings (case-insensitive)
            class_lower = class_name.lower()
            name_lower = name.lower()
            if control_type in _RICH_INPUT_CONTROL_TYPES:
                return True, " > ".join(chain)
            if any(rc in class_lower for rc in _RICH_INPUT_CLASSES):
                return True, " > ".join(chain)
            if any(hint in name_lower for hint in _INPUT_NAME_HINTS):
                return True, " > ".join(chain)
            parent = current.parent()
            if parent is None:
                break
            current = parent
        return False, " > ".join(chain)
    except Exception as exc:
        return False, f"uia-error={type(exc).__name__}"


def _init_uia_thread() -> None:
    try:
        import comtypes

        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except Exception:
        pass


# UI Automation co khi mat 2-5 giay (Chrome, terminal) va Microsoft khuyen khong goi tu luong giao dien:
# goi tren luong rieng de vong tron, HUD, phim tat khong bao gio bi treo.
_UIA_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia", initializer=_init_uia_thread)


def uia_probe(point: tuple[int, int], timeout: float = 1.5) -> tuple[bool, str]:
    """Goi tu luong phu. Qua han thi coi nhu khong phai o nhap (luot doc cham van chay xong o nen)."""
    future = _UIA_POOL.submit(uia_is_likely_input, point)
    try:
        return future.result(timeout)
    except concurrent.futures.TimeoutError:
        return False, f"uia-timeout>{timeout:.1f}s"
    except Exception as exc:
        return False, f"uia-error={type(exc).__name__}"


def ellipsize(text: str, limit: int = 86) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


_MOJIBAKE_MARKERS = ("Ãƒ", "Ã„", "Ã‚", "Ã¡Âº", "Ã¡Â»", "Ã†")
_TECH_TERM_PATTERNS = (
    (r"\bclau(?:de|d)?\s+code\b", "Claude Code"),
    (r"\bcode(?:x|ex)\b", "Codex"),
    (r"\bchat\s*gpt\b", "ChatGPT"),
    (r"\bopen\s*ai\b", "OpenAI"),
    (r"\bapi\b", "API"),
    (r"\bhtml\b", "HTML"),
    (r"\bcss\b", "CSS"),
    (r"\bjavascript\b|\bjava script\b", "JavaScript"),
    (r"\bpython\b", "Python"),
    (r"\bfast\s*api\b", "FastAPI"),
    (r"\bwhisper\b", "Whisper"),
    (r"\bvad\b", "VAD"),
    (r"\bwebrtc\b|\bweb rtc\b", "WebRTC"),
    (r"\bgoogle\b", "Google"),
    (r"\bfrontend\b|\bfront end\b|\bphá» ron ten\b", "frontend"),
    (r"\bbackend\b|\bback end\b|\bbÃ¡ch ken\b", "backend"),
    (r"\bworkflow\b|\bwork flow\b|\buá»‘c flow\b|\buá»‘t flow\b", "workflow"),
    (r"\bprompt\b|\bprÃ´m\b|\bprÃ´m pá»\b", "prompt"),
    (r"\bagent\b|\bÃ¢y giáº§n\b|\bÃ¢y dáº§n\b", "agent"),
    (r"\btemplate\b|\btem pá» lÃ©t\b|\btem plate\b", "template"),
    (r"\bformat\b|\bpho mÃ¡t\b|\bpho mat\b", "format"),
    (r"\bvoice\s*mic\b", "Voice Mic"),
    (r"\bspeech\s*to\s*text\b", "speech-to-text"),
)
_VIETNAMESE_COMMAND_TERMS = (
    "app",
    "codex",
    "voice mic",
    "chatgpt",
    "google",
    "whisper",
    "prompt",
    "workflow",
    "template",
    "format",
    "frontend",
    "backend",
    "api",
    "html",
    "css",
    "javascript",
    "python",
    "d\u1ef1 \u00e1n",
    "giao di\u1ec7n",
    "t\u00ednh n\u0103ng",
    "nh\u1eadn di\u1ec7n",
    "gi\u1ecdng n\u00f3i",
    "micro",
    "l\u1ec7nh",
    "ra l\u1ec7nh",
    "ki\u1ec3m tra",
    "ki\u1ec3m tra k\u1ef9",
    "ch\u1ec9nh",
    "ch\u1ec9nh s\u1eeda",
    "s\u1eeda",
    "fix",
    "fix l\u1ea1i",
    "t\u1ed1i \u01b0u",
    "b\u1ed5 sung",
    "c\u1eadp nh\u1eadt",
    "kh\u1edfi \u0111\u1ed9ng",
    "m\u1edf",
    "\u0111\u00f3ng",
    "k\u00e9o",
    "thu nh\u1ecf",
    "m\u1edf r\u1ed9ng",
    "ch\u00ednh x\u00e1c",
)
_PERSONAL_PHRASE_SEEDS = (
    "ki\u1ec3m tra k\u1ef9",
    "xem l\u1ea1i k\u1ef9",
    "ch\u1ec9nh s\u1eeda l\u1ea1i cho t\u00f4i",
    "b\u1ed5 sung ph\u1ea7n n\u00e0y",
    "t\u1ed1i \u01b0u ph\u1ea7n n\u00e0y",
    "kh\u1edfi \u0111\u1ed9ng l\u1ea1i",
    "cho t\u00f4i xem n\u00e0o",
    "theo \u0111\u00fang m\u1ee5c ti\u00eau",
    "kh\u00f4ng \u0111\u00fang m\u1ee5c ti\u00eau",
    "giao kh\u00f4ng \u0111\u00fang m\u1ee5c ti\u00eau",
    "kh\u00f4ng b\u1ecb c\u1eaft x\u00e9n",
    "hi\u1ec3n th\u1ecb \u0111\u1ea7y \u0111\u1ee7",
    "m\u1edf r\u1ed9ng b\u00ean tr\u00ean",
    "m\u1edf r\u1ed9ng b\u00ean d\u01b0\u1edbi",
    "thu nh\u1ecf l\u1ea1i",
    "k\u00e9o l\u00ean k\u00e9o xu\u1ed1ng",
    "c\u1eadp nh\u1eadt th\u1ef1c t\u1ebf",
    "b\u00e1o c\u00e1o ch\u00ednh x\u00e1c",
    "c\u00e1ch t\u00f4i n\u00f3i chuy\u1ec7n",
    "c\u00e1ch t\u00f4i ra vi\u1ec7c",
    "t\u1eeb \u0111i\u1ec3n c\u00e1 nh\u00e2n",
)
_PHRASE_LEARN_PATTERNS = (
    r"\b(?:ki\u1ec3m tra|xem l\u1ea1i|ch\u1ec9nh|ch\u1ec9nh s\u1eeda|s\u1eeda|fix|b\u1ed5 sung|t\u1ed1i \u01b0u|c\u1eadp nh\u1eadt|kh\u1edfi \u0111\u1ed9ng|thu nh\u1ecf|m\u1edf r\u1ed9ng|k\u00e9o|hi\u1ec3n th\u1ecb|b\u00e1o c\u00e1o)\b(?:\s+\S+){0,6}",
    r"\b(?:kh\u00f4ng b\u1ecb|kh\u00f4ng ph\u1ea3i|kh\u00f4ng \u0111\u00fang|theo \u0111\u00fang|cho t\u00f4i|c\u1ee7a t\u00f4i)\b(?:\s+\S+){0,7}",
    r"\b(?:c\u00e1ch t\u00f4i|t\u1eeb \u0111i\u1ec3n|ng\u00f4n t\u1eeb|ng\u00f4n ng\u1eef|m\u1ee5c ti\u00eau)\b(?:\s+\S+){0,7}",
)
_CONTEXT_PHRASE_BLOCKLIST = {
    "cho tôi",
    "cho tôi đi",
    "cho tôi nào",
    "của tôi",
    "đúng không",
    "ví dụ",
    "ví dụ như",
    "như vậy",
    "cái này",
    "cái kia",
    "phần này",
    "mục này",
    "xem nào",
}
_VIETNAMESE_CLEANUP_PATTERNS = (
    (r"\bcon\s+ap\b", "con app"),
    (r"\b\u00e1p\b", "app"),
    (r"\b\u1ed1p\b", "app"),
    (r"\bth\u00edch\s+l\u1ea1i\b", "fix l\u1ea1i"),
    (r"\bt\u1ed1i\s+v\u1ec1\b", "t\u1ed1i \u01b0u v\u1ec1"),
    (r"\bt\u1ed1i\s+v\u00e0\b", "t\u1ed1i \u01b0u"),
    (r"\bki\u1ec3m\s+tra\s+k\u00fd\b", "ki\u1ec3m tra k\u1ef9"),
    (r"\bxem\s+l\u1ea1i\s+k\u00fd\b", "xem l\u1ea1i k\u1ef9"),
    (r"\bcheck\s+l\u1ea1i\s+(?:k\u00fd|k\u0129|k\u1ef9)\b", "ki\u1ec3m tra k\u1ef9"),
    (r"\bcheck\s+(?:k\u00fd|k\u0129|k\u1ef9)\b", "ki\u1ec3m tra k\u1ef9"),
    (r"\b(?:akmin|adminn|atmin)\b", "Admin"),
    (r"\b(\d+)\s+\u0111\u1ea7n\b", r"\1 lần"),
    (r"\b(?:t\u0103ng|t\u00ean t\u0103ng|t\u1ef1a \u0111ang)\s+nh\u1eadp\b", "\u0111\u0103ng nh\u1eadp"),
    (r"\b(?:app|áp)\s+d\u1ee5ng\b", "\u00e1p d\u1ee5ng"),
    (r"\b\u0111\u00e1\s+ta\b", "data"),
    (r"\bv\u01a1\s+va\s+v\u1eadn\b", "v\u1edb va v\u1edb v\u1ea9n"),
    (r"\bki\u1ec3m\s+tra\s+k\u00ed\b", "ki\u1ec3m tra k\u1ef9"),
    (r"\bt\u1eb7ng\s+website\b", "th\u1eb3ng website"),
    (r"\bt\u1ea3ng\s+website\b", "th\u1eb3ng website"),
    (r"\bxe\s+m\u00e1y\s+t\u00ed\b", "xem l\u1ea1i k\u1ef9"),
    (r"\bskill\s+m\u00e1t\b", "skill map"),
    (r"\bsql\s+m\u00e1t\b", "skill map"),
    (r"\bskinaz\b", "skill map"),
    (r"\bmaplestory\b", "map"),
)
_CONTEXT_TERM_BLOCKLIST = {
    "again",
    "anh",
    "ban",
    "build",
    "cao",
    "check",
    "cho",
    "click",
    "copy",
    "data",
    "demo",
    "download",
    "face",
    "hay",
    "hoa",
    "icon",
    "key",
    "khi",
    "keyword",
    "lai",
    "lan",
    "lau",
    "like",
    "line",
    "link",
    "live",
    "mai",
    "map",
    "min",
    "nam",
    "nghe",
    "nhanh",
    "note",
    "open",
    "plan",
    "play",
    "sai",
    "sao",
    "sau",
    "sit",
    "tab",
    "text",
    "thanh",
    "thay",
    "thu",
    "translate",
    "view",
    "voice",
    "website",
    "win",
    "xem",
    "xong",
}


def repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text
    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text
    return fixed if fixed.count("ï¿½") <= text.count("ï¿½") else text


def normalize_technical_terms(text: str) -> str:
    for pattern, replacement in _TECH_TERM_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def load_speech_cleanup_replacements() -> list[dict[str, object]]:
    try:
        settings = load_settings()
        replacements = settings.get("speech_cleanup_replacements", [])
        if isinstance(replacements, list):
            return [item for item in replacements if isinstance(item, dict)]
    except Exception:
        pass
    return []


def apply_custom_replacements(text: str) -> str:
    for item in load_speech_cleanup_replacements():
        pattern = str(item.get("pattern", "") or "")
        replacement = str(item.get("replacement", "") or "")
        if not pattern:
            continue
        try:
            if bool(item.get("regex", False)):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            else:
                text = text.replace(pattern, replacement)
        except re.error as exc:
            log(f"cleanup replacement ignored | pattern={pattern!r} | error={exc}")
    return text


_CONTEXT_CACHE: dict[str, object] = {}


def context_cache_key() -> tuple[object, ...]:
    # stat 4 file moi lan lam sach cau cung ton; kiem tra lai toi da 2 lan/giay
    now = time.monotonic()
    cached = _CONTEXT_CACHE.get("key")
    if cached and now - cached[0] < 0.5:
        return cached[1]
    key = tuple(file_signature(path) for path in (SETTINGS_FILE, LOCAL_SETTINGS_FILE, CONTEXT_FILE, LOCAL_CONTEXT_FILE))
    _CONTEXT_CACHE["key"] = (now, key)
    return key


def invalidate_context_cache() -> None:
    _CONTEXT_CACHE.pop("key", None)


def load_voice_context_data() -> dict[str, dict[str, int]]:
    key = context_cache_key()
    cached = _CONTEXT_CACHE.get("data")
    if cached and cached[0] == key:
        terms, phrases = cached[1]
        return {"terms": dict(terms), "phrases": dict(phrases)}
    merged_terms: dict[str, int] = {}
    merged_phrases: dict[str, int] = {}
    for path in (CONTEXT_FILE, LOCAL_CONTEXT_FILE):
        try:
            data = read_json_cached(path)
            if data is None:
                continue
            if not isinstance(data, dict):
                continue
            terms = data.get("terms", {})
            phrases = data.get("phrases", {})
            if isinstance(terms, dict):
                for key, value in terms.items():
                    clean = str(key).strip()
                    if clean:
                        merged_terms[clean] = max(merged_terms.get(clean, 0), int(value))
            if isinstance(phrases, dict):
                for key, value in phrases.items():
                    clean = str(key).strip()
                    if clean:
                        merged_phrases[clean] = max(merged_phrases.get(clean, 0), int(value))
        except Exception as exc:
            log(f"voice context load skipped | path={path.name} | {type(exc).__name__}: {exc}")
    _CONTEXT_CACHE["data"] = (key, (dict(merged_terms), dict(merged_phrases)))
    return {"terms": merged_terms, "phrases": merged_phrases}


def load_local_voice_context_data() -> dict[str, dict[str, int]]:
    try:
        data = json.loads(LOCAL_CONTEXT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            terms = data.get("terms", {})
            phrases = data.get("phrases", {})
            return {
                "terms": {str(k): int(v) for k, v in terms.items() if str(k).strip()} if isinstance(terms, dict) else {},
                "phrases": {str(k): int(v) for k, v in phrases.items() if str(k).strip()} if isinstance(phrases, dict) else {},
            }
    except Exception:
        pass
    return {"terms": {}, "phrases": {}}


def load_voice_context() -> dict[str, int]:
    return load_voice_context_data()["terms"]


def load_voice_phrases() -> dict[str, int]:
    return load_voice_context_data()["phrases"]


def save_voice_context_data(terms: dict[str, int], phrases: dict[str, int]) -> None:
    try:
        sorted_terms = dict(sorted(terms.items(), key=lambda item: (-item[1], item[0]))[:VOICE_CONTEXT_MAX_TERMS])
        merged_phrases: dict[str, int] = {}
        phrase_keys: dict[str, str] = {}
        for phrase, count in phrases.items():
            clean = cleanup_pass(str(phrase))
            if not context_phrase_allowed(clean):
                continue
            key = clean.lower()
            existing = phrase_keys.get(key)
            if existing:
                merged_phrases[existing] += int(count)
            else:
                phrase_keys[key] = clean
                merged_phrases[clean] = int(count)
        sorted_phrases = dict(sorted(merged_phrases.items(), key=lambda item: (-item[1], item[0]))[:VOICE_CONTEXT_MAX_PHRASES])
        LOCAL_CONTEXT_FILE.write_text(
            json.dumps({"terms": sorted_terms, "phrases": sorted_phrases}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        invalidate_context_cache()
    except Exception as exc:
        log(f"voice context save error: {type(exc).__name__}: {exc}")


def save_voice_context(terms: dict[str, int]) -> None:
    data = load_local_voice_context_data()
    save_voice_context_data(terms, data["phrases"])


def save_voice_phrases(phrases: dict[str, int]) -> None:
    data = load_local_voice_context_data()
    save_voice_context_data(data["terms"], phrases)


def configured_context_terms() -> list[str]:
    settings = load_settings()
    if not bool(settings.get("enable_context_memory", True)):
        return []
    terms = settings.get("speech_context_terms", [])
    if isinstance(terms, list):
        return [repair_mojibake(str(term).strip()) for term in terms if str(term).strip()]
    return []


def context_phrase_allowed(phrase: str) -> bool:
    phrase = cleanup_pass(phrase)
    if any(marker in phrase for marker in _MOJIBAKE_MARKERS):
        phrase = repair_mojibake(phrase)
    lower = phrase.lower()
    if lower in _CONTEXT_PHRASE_BLOCKLIST:
        return False
    if not 6 <= len(phrase) <= 90:
        return False
    words = phrase.split()
    if not 3 <= len(words) <= 9 and phrase.lower() not in {"kiểm tra kỹ", "xem lại kỹ", "khởi động lại", "thu nhỏ lại"}:
        return False
    if words[-1].lower() in {"về", "để", "có", "phân", "mô", "là", "cái", "và", "như", "kiểu"}:
        return False
    return count_transcript_words(phrase) >= 2


def configured_context_phrases() -> list[str]:
    settings = load_settings()
    if not bool(settings.get("enable_context_memory", True)):
        return []
    phrases = settings.get("speech_context_phrases", [])
    configured = [repair_mojibake(str(phrase).strip()) for phrase in phrases if str(phrase).strip()] if isinstance(phrases, list) else []
    return list(_PERSONAL_PHRASE_SEEDS) + configured


def context_phrases(limit: int = 80) -> list[str]:
    key = ("phrases", limit, context_cache_key())
    cached = _CONTEXT_CACHE.get(f"phrases{limit}")
    if cached and cached[0] == key:
        return list(cached[1])
    merged = _context_phrases_uncached(limit)
    _CONTEXT_CACHE[f"phrases{limit}"] = (key, tuple(merged))
    return merged


def _context_phrases_uncached(limit: int) -> list[str]:
    if not bool(load_settings().get("enable_context_memory", True)):
        return []
    learned = load_voice_phrases()
    ranked = [phrase for phrase, _count in sorted(learned.items(), key=lambda item: (-item[1], item[0]))]
    merged: list[str] = []
    seen: set[str] = set()
    for phrase in configured_context_phrases() + ranked:
        clean = cleanup_pass(phrase)
        key = clean.lower()
        if key not in seen and context_phrase_allowed(clean):
            seen.add(key)
            merged.append(clean)
        if len(merged) >= limit:
            break
    return merged


def context_terms(limit: int = 80) -> list[str]:
    key = ("terms", limit, context_cache_key())
    cached = _CONTEXT_CACHE.get(f"terms{limit}")
    if cached and cached[0] == key:
        return list(cached[1])
    merged = _context_terms_uncached(limit)
    _CONTEXT_CACHE[f"terms{limit}"] = (key, tuple(merged))
    return merged


def _context_terms_uncached(limit: int) -> list[str]:
    if not bool(load_settings().get("enable_context_memory", True)):
        return []
    learned = load_voice_context()
    ranked = [term for term, _count in sorted(learned.items(), key=lambda item: (-item[1], item[0]))]
    merged: list[str] = []
    seen: set[str] = set()
    for term in configured_context_terms() + ranked:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            merged.append(term)
        if len(merged) >= limit:
            break
    return merged


def context_term_patterns() -> list[tuple[str, re.Pattern[str], str]]:
    terms = context_terms()
    cached = _CONTEXT_CACHE.get("term_patterns")
    if cached and cached[0] == terms:
        return cached[1]
    patterns = [
        (term.lower(), re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE), term)
        for term in terms
        if context_term_allowed(term) and len(term) >= 2
    ]
    _CONTEXT_CACHE["term_patterns"] = (terms, patterns)
    return patterns


def apply_context_terms(text: str) -> str:
    for lower_term, pattern, term in context_term_patterns():
        if lower_term in text.lower():
            text = pattern.sub(term, text)
    return text


def apply_vietnamese_cleanup_patterns(text: str) -> str:
    for pattern, replacement in _VIETNAMESE_CLEANUP_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def context_term_allowed(term: str) -> bool:
    key = term.strip().lower()
    if not key or key in _CONTEXT_TERM_BLOCKLIST:
        return False
    if len(term.strip()) < 3:
        return False
    return True


def should_learn_context_word(term: str) -> bool:
    if not context_term_allowed(term):
        return False
    if re.search(r"[0-9+#.-]", term):
        return True
    if term.isupper() and len(term) >= 2:
        return True
    if any(ch.isupper() for ch in term[1:]):
        return True
    return False


def extract_personal_phrases(text: str) -> set[str]:
    clean_text = clean_transcript(text)
    candidates: set[str] = set()
    lower = clean_text.lower()
    for phrase in configured_context_phrases():
        if phrase.lower() in lower:
            candidates.add(phrase)
    for pattern in _PHRASE_LEARN_PATTERNS:
        for match in re.finditer(pattern, clean_text, flags=re.IGNORECASE):
            phrase = re.sub(r"\s+", " ", match.group(0)).strip(" .,!?;:")
            phrase = re.sub(r"\b(?:đúng không|nhé|nha|đấy|ấy|thì|vậy)$", "", phrase, flags=re.IGNORECASE).strip()
            if context_phrase_allowed(phrase):
                candidates.add(phrase)
    return candidates


def learn_context_phrases(text: str) -> None:
    if not bool(load_settings().get("enable_context_memory", True)):
        return
    candidates = extract_personal_phrases(text)
    if not candidates:
        return
    phrases = load_voice_phrases()
    for phrase in candidates:
        clean = cleanup_pass(phrase)
        if context_phrase_allowed(clean):
            phrases[clean] = phrases.get(clean, 0) + 1
    save_voice_phrases(phrases)


def learn_context_terms(text: str) -> None:
    if not bool(load_settings().get("enable_context_memory", True)):
        return
    learn_context_phrases(text)
    candidates: set[str] = set()
    configured = configured_context_terms()
    for term in configured:
        if re.search(r"\b" + re.escape(term) + r"\b", text, flags=re.IGNORECASE):
            candidates.add(term)
    for match in re.finditer(r"(?<!\w)[A-Za-z][A-Za-z0-9+#.-]*(?!\w)", text):
        term = match.group(0).strip(" .,!?;:")
        if should_learn_context_word(term):
            candidates.add(term)
    for term in re.findall(r"\b(?:API|HTML|CSS|JavaScript|Python|Whisper|Google|VAD|WebRTC|OpenAI|ChatGPT|Codex|Claude Code|FastAPI|workflow|prompt|agent|template|format|frontend|backend|Voice Mic|speech-to-text|Google Speech Recognition)\b", text, flags=re.IGNORECASE):
        candidates.add(normalize_technical_terms(term))
    if not candidates:
        return
    terms = load_voice_context()
    for term in candidates:
        clean = cleanup_pass(term)
        if 2 <= len(clean) <= 48 and context_term_allowed(clean):
            terms[clean] = terms.get(clean, 0) + 1
    save_voice_context(terms)


def whisper_initial_prompt() -> str:
    terms = ", ".join(context_terms(60))
    phrases = ", ".join(context_phrases(35))
    base = (
        "L\u1eddi n\u00f3i ti\u1ebfng Vi\u1ec7t t\u1ef1 nhi\u00ean, "
        "c\u00f3 th\u1ec3 xen k\u1ebd ti\u1ebfng Anh/k\u1ef9 thu\u1eadt. "
        "Gi\u1eef \u0111\u00fang thu\u1eadt ng\u1eef, t\u00ean c\u00f4ng c\u1ee5 "
        "v\u00e0 ch\u00ednh t\u1ea3 ti\u1ebfng Vi\u1ec7t. "
        "Ng\u01b0\u1eddi n\u00f3i hay giao vi\u1ec7c b\u1eb1ng c\u00e1c c\u1ee5m l\u1ec7nh l\u1eb7p l\u1ea1i."
    )
    extras: list[str] = []
    if terms:
        extras.append(f"T\u1eeb kh\u00f3a hay d\u00f9ng: {terms}.")
    if phrases:
        extras.append(f"C\u1ee5m l\u1ec7nh hay d\u00f9ng: {phrases}.")
    if extras:
        return f"{base} {' '.join(extras)}"
    return base


# Cau Whisper hay "bia" khi gap tieng on / im lang (hoc tu phu de YouTube). Chi loc tren ket qua Whisper:
# Google khong bia cau, va anh co the that su doc "dang ky kenh" khi viet noi dung.
_WHISPER_HALLUCINATION = re.compile(
    r"subscribe|ghi\u1ec1n m\u00ec g\u00f5|la la school|kh\u00f4ng b\u1ecf l\u1ee1 nh\u1eefng video|"
    r"c\u1ea3m \u01a1n c\u00e1c b\u1ea1n \u0111\u00e3 (theo d\u00f5i|xem)|"
    r"h\u1eb9n g\u1eb7p l\u1ea1i c\u00e1c b\u1ea1n|like v\u00e0 share|b\u1ea5m chu\u00f4ng",
    re.IGNORECASE,
)


def strip_whisper_hallucinations(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [sentence for sentence in sentences if not _WHISPER_HALLUCINATION.search(sentence)]
    if len(kept) != len(sentences):
        log(f"whisper hallucination removed | text={text[:120]}")
    return " ".join(kept).strip()


def cleanup_pass(text: str) -> str:
    text = normalize_technical_terms(text)
    text = apply_vietnamese_cleanup_patterns(text)
    text = apply_custom_replacements(text)
    text = apply_context_terms(text)
    text = re.sub(r"\b(\u00e0|\u1edd|\u1eeb|\u1eebm|\u1eddm)\b[ ,]*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(m\u00e1y|m\u00e0y)\s+(?=l\u00e0m|t\u1ea1o|vi\u1ebft|ki\u1ec3m|th\u1eed|ch\u00e8n|g\u1eedi|ph\u00e2n|xem|cho)\b",
        "h\u00e3y ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(\w{2,})(?:\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=\S)", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_transcript(text: str) -> str:
    text = repair_mojibake(text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=\S)", r"\1 ", text)
    text = text.strip(" \t\r\n\"'")

    junk_phrases = (
        "c\u1ea3m \u01a1n c\u00e1c b\u1ea1n \u0111\u00e3 theo d\u00f5i",
        "h\u00e3y subscribe cho k\u00eanh",
        "h\u00e3y \u0111\u0103ng k\u00fd k\u00eanh",
        "l\u1eddi n\u00f3i ti\u1ebfng vi\u1ec7t c\u00f3 d\u1ea5u",
        "l\u1eddi n\u00f3i ti\u1ebfng vi\u1ec7t t\u1ef1 nhi\u00ean ch\u00ednh t\u1ea3 ti\u1ebfng vi\u1ec7t c\u00f3 d\u1ea5u",
    )
    normalized = text.strip(" .,!?:;").lower()
    if normalized in junk_phrases:
        return ""
    if re.search(r"\b(?:subscribe|đăng ký kênh|không bỏ lỡ.*video|video hấp dẫn|la school)\b", normalized):
        if count_transcript_words(normalized) <= 18:
            return ""
    if normalized and all(phrase in normalized for phrase in ("ti\u1ebfng vi\u1ec7t c\u00f3 d\u1ea5u", "\u00f4 chat")):
        return ""

    return cleanup_pass(text)


def audio_byte_rate(audio: sr.AudioData) -> int:
    return max(1, audio.sample_rate * audio.sample_width)


def align_audio_byte(position: int, sample_width: int) -> int:
    width = max(1, sample_width)
    return max(0, position - (position % width))


def quiet_chunk_boundary(
    frame_data: bytes,
    sample_rate: int,
    sample_width: int,
    target: int,
    lower: int,
    upper: int,
) -> int:
    byte_rate = max(1, sample_rate * sample_width)
    window = align_audio_byte(int(byte_rate * 0.16), sample_width)
    step = align_audio_byte(int(byte_rate * 0.06), sample_width)
    if window <= 0 or step <= 0:
        return align_audio_byte(target, sample_width)

    start = align_audio_byte(max(lower, target - int(byte_rate * GOOGLE_CHUNK_BOUNDARY_SEARCH_SECONDS)), sample_width)
    end = align_audio_byte(min(upper - window, target + int(byte_rate * GOOGLE_CHUNK_BOUNDARY_SEARCH_SECONDS)), sample_width)
    if end <= start:
        return align_audio_byte(target, sample_width)

    best_pos = start
    best_score = float("inf")
    for pos in range(start, end + 1, step):
        sample = frame_data[pos:pos + window]
        if len(sample) < window:
            continue
        rms = audioop.rms(sample, sample_width)
        distance_penalty = abs(pos - target) / byte_rate * 12.0
        score = rms + distance_penalty
        if score < best_score:
            best_score = score
            best_pos = pos
    return align_audio_byte(best_pos, sample_width)


def google_audio_chunks(audio: sr.AudioData) -> list[tuple[int, sr.AudioData, float, float]]:
    byte_rate = audio_byte_rate(audio)
    max_bytes = align_audio_byte(int(byte_rate * GOOGLE_LONG_CHUNK_SECONDS), audio.sample_width)
    min_bytes = align_audio_byte(int(byte_rate * GOOGLE_CHUNK_MIN_SECONDS), audio.sample_width)
    min_tail_bytes = align_audio_byte(int(byte_rate * GOOGLE_CHUNK_MIN_TAIL_SECONDS), audio.sample_width)
    if max_bytes <= 0:
        return []

    ranges: list[tuple[int, int]] = []
    start = 0
    total_bytes = len(audio.frame_data)
    while total_bytes - start > max_bytes:
        target = start + max_bytes
        lower = min(total_bytes, start + min_bytes)
        upper = total_bytes - min_tail_bytes
        boundary = quiet_chunk_boundary(audio.frame_data, audio.sample_rate, audio.sample_width, target, lower, upper)
        if boundary <= start + min_bytes or boundary >= total_bytes:
            boundary = align_audio_byte(target, audio.sample_width)
        ranges.append((start, boundary))
        start = boundary

    if start < total_bytes:
        ranges.append((start, total_bytes))

    if len(ranges) > 1:
        last_start, last_end = ranges[-1]
        if last_end - last_start < min_tail_bytes:
            prev_start, _prev_end = ranges[-2]
            ranges[-2] = (prev_start, last_end)
            ranges.pop()

    chunks: list[tuple[int, sr.AudioData, float, float]] = []
    for index, (start_byte, end_byte) in enumerate(ranges, start=1):
        frame_data = audio.frame_data[start_byte:end_byte]
        if not frame_data:
            continue
        chunks.append(
            (
                index,
                sr.AudioData(frame_data, audio.sample_rate, audio.sample_width),
                start_byte / byte_rate,
                end_byte / byte_rate,
            )
        )
    return chunks


def normalized_merge_token(token: str) -> str:
    return re.sub(r"[^\w]+", "", token.lower(), flags=re.UNICODE)


def merge_transcript_parts(parts: list[str]) -> str:
    merged_words: list[str] = []
    for part in parts:
        words = clean_transcript(part).split()
        if not words:
            continue
        if not merged_words:
            merged_words.extend(words)
            continue
        normalized_merged = [normalized_merge_token(word) for word in merged_words]
        normalized_words = [normalized_merge_token(word) for word in words]
        max_overlap = min(10, len(normalized_merged), len(normalized_words))
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if normalized_merged[-size:] == normalized_words[:size]:
                overlap = size
                break
        merged_words.extend(words[overlap:])
    return clean_transcript(" ".join(merged_words))


def google_response_alternatives(response: object) -> list[tuple[str, float | None]]:
    if not isinstance(response, dict):
        return []
    alternatives = response.get("alternative", [])
    if not isinstance(alternatives, list):
        return []
    results: list[tuple[str, float | None]] = []
    for item in alternatives:
        if not isinstance(item, dict):
            continue
        transcript = str(item.get("transcript", "") or "").strip()
        if not transcript:
            continue
        confidence_raw = item.get("confidence")
        confidence: float | None = None
        if isinstance(confidence_raw, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        results.append((transcript, confidence))
    return results


def transcript_context_score(text: str) -> float:
    lower = text.lower()
    score = 0.0
    seen: set[str] = set()
    for term in list(_VIETNAMESE_COMMAND_TERMS) + [term.lower() for term in context_terms(50)]:
        key = term.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", lower, flags=re.IGNORECASE):
            score += 0.018 if len(key) < 6 else 0.028
    for phrase in context_phrases(50):
        key = phrase.strip().lower()
        if key and key not in seen and key in lower:
            seen.add(key)
            score += 0.04
    return min(score, 0.24)


def transcript_quality_penalty(text: str) -> float:
    lower = text.lower()
    penalty = 0.0
    if any(marker.lower() in lower for marker in _MOJIBAKE_MARKERS):
        penalty += 0.12
    if re.search(r"\b(\w{2,})(?:\s+\1\b){2,}", lower, flags=re.IGNORECASE):
        penalty += 0.06
    words = count_transcript_words(text)
    if words <= 2:
        penalty += 0.04
    filler_count = len(re.findall(r"\b(?:\u00e0|\u1edd|\u1eeb|\u1eebm|\u1eddm|uh|um)\b", lower, flags=re.IGNORECASE))
    if words:
        penalty += min(0.06, filler_count / max(1, words) * 0.18)
    return penalty


_DICTATION_SUSPICIOUS_PATTERNS = (
    r"\b\u00f4ng\s+\u0111\u1ecba\b",
    r"\bn\u1ea1p\s+pin\b",
    r"\bph\u00e1t\s+bi\u1ec3u\s+l\u00e0m\s+v\u00f2ng\b",
    r"\bth\u1ebf\s+k\u1ef7\b",
    r"\bh\u00f3a\s+h\u1ecdc\b",
    r"\bmotor\b",
    r"\bqu\u1ed1c\s+xai\b",
    r"\bt\u00e1c\s+kh\u00e1c\b",
    r"\bb\u1eaft\s+\u0111\u01b0\u1ee3c\s+nh\u1ea7m\b",
    r"\bc\u00e1i\s+bu\u1ed9c\s+n\u00e0y\b",
    r"\bsau\s+ti\u00eau\s+kh\u00f4ng\b",
    r"\bxung\s+to\u00e0n\b",
    r"\bgi\u1ea5u\s+v\u01a1\s+va\s+v\u1eadn\b",
    r"\bgi\u1ea5u\s+ki\u1ec3u\b",
    r"\bgi\u1ea5u\s+\u0111\u1ea7u\b",
    r"\bki\u1ec3m\s+tra\s+k\u00ed\s+h\u01b0\s+kh\u00f4ng\b",
    r"\b(?:lu\u1eadn|lu\u1ed3ng)\s+kh\u00e1c\s+\u0111\u01b0\u1ee3c\s+ch\u01b0a\b",
)


def transcript_suspicion_penalty(text: str) -> float:
    lower = text.lower()
    hits = sum(1 for pattern in _DICTATION_SUSPICIOUS_PATTERNS if re.search(pattern, lower, flags=re.IGNORECASE))
    return min(0.24, hits * 0.06)


def transcript_selection_score(text: str) -> float:
    words = count_transcript_words(text)
    return (
        min(0.14, words * 0.003)
        + transcript_context_score(text)
        - transcript_quality_penalty(text)
        - transcript_suspicion_penalty(text)
    )


def choose_google_alternative(response: object) -> tuple[str, float | None, int]:
    alternatives = google_response_alternatives(response)
    if not alternatives:
        return "", None, 0
    best_raw = ""
    best_clean = ""
    best_confidence: float | None = None
    best_score = -1.0
    for raw, confidence in alternatives:
        clean = clean_transcript(raw)
        if not clean:
            continue
        confidence_score = confidence if confidence is not None else 0.55
        length_score = min(0.08, count_transcript_words(clean) * 0.002)
        context_score = transcript_context_score(clean)
        penalty = transcript_quality_penalty(clean)
        score = confidence_score + length_score + context_score - penalty
        if score > best_score:
            best_raw = raw
            best_clean = clean
            best_confidence = confidence
            best_score = score
    return best_clean or clean_transcript(best_raw), best_confidence, len(alternatives)


def audio_speech_level(audio: sr.AudioData) -> int:
    """Muc to cua phan co tieng noi (phan vi 80 cua do to tung 100ms), de biet doan nao chi la im lang."""
    data = audio.frame_data
    width = audio.sample_width
    step = max(width, int(audio.sample_rate * 0.1) * width)
    levels = sorted(audioop.rms(data[i:i + step], width) for i in range(0, len(data) - width, step))
    if not levels:
        return 0
    return levels[min(len(levels) - 1, int(len(levels) * 0.8))]


def google_transcripts(audio: sr.AudioData, language: str) -> list[str]:
    """Moi cach nghe Google tra ve cho doan am thanh (dung de bat lenh ngan nhu "voice")."""
    recognizer = sr.Recognizer()
    recognizer.operation_timeout = GOOGLE_RECOGNITION_TIMEOUT_SECONDS
    try:
        response = recognizer.recognize_google(audio, language=language, show_all=True)
    except Exception:
        return []
    return [text for text, _confidence in google_response_alternatives(response) if text]


def format_confidence_percent(confidence: float | None) -> str:
    if confidence is None:
        return "n/a"
    return f"{confidence * 100:.0f}%"


class MicIconApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.root.resizable(False, False)

        x, y = load_position()
        self.root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root,
            width=SIZE,
            height=SIZE,
            highlightthickness=0,
            bd=0,
            bg=TRANSPARENT,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self.drag_start: tuple[int, int, int, int] | None = None
        self.dragged = False
        self.listening = False
        self.processing = False
        # "dictation" = noi thanh chu, "conversation" = tro chuyen voi tro ly giong nam (lenh "voice")
        self.session_mode = "dictation"
        self.conversation = None
        self.visual_state = "idle"
        self.hud_state = "idle"
        self.settings = load_settings()
        self.hud_message = ""
        self.hud_visible = False
        self.hud_hide_after_id: str | None = None
        self.hud_anchor_point: tuple[int, int] | None = None
        self.particle_effect_enabled = bool(self.settings_value("enable_particle_effect", True))
        self.particle_effect_visible = False
        self.particle_anchor_point: tuple[int, int] | None = None
        self.particle_count = max(40, min(360, int(self.settings_value("particle_effect_count", PARTICLE_EFFECT_DEFAULT_COUNT))))
        self.particles = self.build_particles(self.particle_count)
        self.audio_level = 0.0
        self.audio_level_target = 0.0
        self.particle_result_text = ""
        self.particle_result_stats = ""
        self.particle_result_visible = False
        self.anim_tick = 0
        self.app_hwnd = 0
        self.hud_hwnd = 0
        self.last_target_hwnd = 0
        self.last_click_point: tuple[int, int] | None = None
        self.active_target_hwnd = 0
        self.active_target_point: tuple[int, int] | None = None
        self.pinned_target_hwnd = 0
        self.pinned_target_point: tuple[int, int] | None = None
        self.capture_clicks = False
        self.stop_requested = False
        self.stop_reason = ""
        self.session_counter = 0
        self.active_session_id = 0
        self.auto_was_down = False
        self.mouse_down_had_alt = False
        self.microphone_device_index, self.microphone_device_name = select_microphone_device(self.settings)
        self.voice_targets = load_voice_targets()
        self.escape_was_down = key_down(VK_ESCAPE)
        self.last_auto_started_at = 0.0
        self._alt_click_token = 0
        self.discard_session_id = 0
        self.last_transcript_whisper_only = False
        self.last_google_alternatives: list[str] = []
        self.voice_chat_hotkey = parse_hotkey(str(self.settings.get("voice_chat_hotkey", "ctrl+alt+v") or ""))
        self.voice_chat_hotkey_was_down = False
        self.command_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-command")
        self._alt_click_triggered = False
        self._alt_click_probing = False
        self.learn_lock = threading.Lock()
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = GOOGLE_RECOGNITION_TIMEOUT_SECONDS
        self.google_confidence_scores: list[float] = []
        self.whisper_model = None
        self.whisper_backend = ""
        self.enable_whisper_fallback = bool(self.settings.get("enable_whisper_fallback", False))
        self.whisper_model_name = str(self.settings.get("whisper_model", "base") or "base")
        self.whisper_compute_type = str(self.settings.get("whisper_compute_type", "int8") or "int8")
        # Whisper chi nap khi bat dau noi, tu nha sau whisper_idle_unload_minutes khong dung
        # (26/09/2026: nap san tu luc khoi dong giu ~2 GB RAM ca ngay).
        self.whisper_loader: threading.Thread | None = None
        self.whisper_last_used = 0.0
        self.whisper_idle_unload_seconds = 60 * float(self.settings.get("whisper_idle_unload_minutes", 15) or 0)
        if self.enable_whisper_fallback:
            log(f"whisper loads on first speech, unloads after {self.whisper_idle_unload_seconds / 60:.0f} min idle")
        else:
            log("whisper disabled by settings; google speech recognition only")
        log(
            f"app started | version={APP_VERSION} | build={APP_BUILD} | "
            f"trigger=Alt+left-click | mic_index={self.microphone_device_index} | mic={self.microphone_device_name} | "
            f"whisper={self.enable_whisper_fallback}:{self.whisper_model_name}:{self.whisper_compute_type}"
        )

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", self.handle_escape_key)

        self.hud = tk.Toplevel(self.root)
        self.hud.title(f"{APP_TITLE} Status")
        self.hud.overrideredirect(True)
        self.hud.attributes("-topmost", True)
        self.hud.attributes("-alpha", 0.93)
        self.hud.configure(bg=TRANSPARENT)
        self.hud.wm_attributes("-transparentcolor", TRANSPARENT)
        self.hud.resizable(False, False)
        self.hud.withdraw()
        self.hud_canvas = tk.Canvas(
            self.hud,
            width=HUD_WIDTH,
            height=HUD_HEIGHT,
            highlightthickness=0,
            bd=0,
            bg=TRANSPARENT,
            cursor="arrow",
        )
        self.hud_canvas.pack(fill="both", expand=True)

        self.particle = tk.Toplevel(self.root)
        self.particle.title(f"{APP_TITLE} AI Aura")
        self.particle.overrideredirect(True)
        self.particle.attributes("-topmost", True)
        self.particle.attributes("-alpha", 0.9)
        self.particle.configure(bg=TRANSPARENT)
        self.particle.wm_attributes("-transparentcolor", TRANSPARENT)
        self.particle.resizable(False, False)
        self.particle.withdraw()
        self.particle_canvas = tk.Canvas(
            self.particle,
            width=PARTICLE_EFFECT_WIDTH,
            height=PARTICLE_EFFECT_HEIGHT,
            highlightthickness=0,
            bd=0,
            bg=TRANSPARENT,
            cursor="arrow",
        )
        self.particle_canvas.pack(fill="both", expand=True)

        # Vong tron chon che do (Alt + giu chuot): Go chu / Tro chuyen / Doc tai lieu / Huy
        self.radial = tk.Toplevel(self.root)
        self.radial.title(f"{APP_TITLE} Menu")
        self.radial.overrideredirect(True)
        self.radial.attributes("-topmost", True)
        self.radial.attributes("-alpha", 0.96)
        self.radial.configure(bg=TRANSPARENT)
        self.radial.wm_attributes("-transparentcolor", TRANSPARENT)
        self.radial.resizable(False, False)
        self.radial.withdraw()
        self.radial_canvas = tk.Canvas(
            self.radial, width=RADIAL_SIZE, height=RADIAL_SIZE, highlightthickness=0, bd=0, bg=TRANSPARENT, cursor="arrow",
        )
        self.radial_canvas.pack(fill="both", expand=True)
        self.radial_open = False
        self.radial_closing = False
        self.radial_animating = False
        self.radial_closed_at = 0.0
        self.radial_hover: dict[str, float] = {}
        self.radial_choice: str | None = None
        self.radial_center: tuple[int, int] = (0, 0)  # tam vong tron tren man hinh
        self.radial_anchor: tuple[int, int] = (0, 0)
        self.radial_opened_at = 0.0
        self.radial_press_inside = False
        self.radial_dragging = False
        self.radial_target_hwnd = 0
        self.reading = None  # dang doc to doan anh chon "Doc"

        self.draw("idle")
        self.animate()
        self.root.update_idletasks()
        self.app_hwnd = int(self.root.winfo_id())
        self.hud_hwnd = int(self.hud.winfo_id())
        self.particle_hwnd = int(self.particle.winfo_id())
        make_tool_window(self.app_hwnd)
        make_tool_window(self.hud_hwnd)
        make_tool_window(self.particle_hwnd)
        self.radial_hwnd = int(self.radial.winfo_id())
        make_tool_window(self.radial_hwnd)
        # bam vao vong tron khong cuop focus cua khung chat (de go chu van dan dung cho)
        for hwnd in {self.radial_hwnd, int(user32.GetParent(self.radial_hwnd) or 0)} - {0}:
            set_window_long(hwnd, GWL_EXSTYLE, get_window_long(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE)
        if HIDE_FLOATING_MIC_BUTTON:
            self.root.withdraw()
        self.update_hud_position()
        self.monitor_target_window()
        self.monitor_global_clicks()
        self.monitor_voice_hotkeys()
        self.keep_topmost()
        self.check_for_updates_on_start()
        self.root.after(60_000, self.unload_idle_whisper)
        self.root.after(4000, self.prefetch_voice_brain)

    def prefetch_voice_brain(self) -> None:
        """Do san bo nao AI cho che do "Noi" o nen, bam "Noi" la chao ngay."""
        preference = str(self.settings.get("voice_chat_backend") or "auto")
        ollama_model = str(self.settings.get("voice_chat_ollama_model") or "")
        voice = str(self.settings.get("voice_chat_voice") or "")
        rate = str(self.settings.get("voice_chat_rate") or "")

        def worker() -> None:
            try:
                from reader.assistant import prefetch_brain

                prefetch_brain(preference, ollama_model, voice, rate)
            except Exception as exc:
                log(f"voice brain prefetch error: {type(exc).__name__}: {exc}")

        threading.Thread(target=worker, daemon=True, name="brain-prefetch-import").start()

    def settings_value(self, key: str, default: object) -> object:
        try:
            return self.settings.get(key, default)
        except Exception:
            return default

    def build_particles(self, count: int) -> list[tuple[float, float, float, float, float]]:
        particles: list[tuple[float, float, float, float, float]] = []
        golden_angle = math.pi * (3 - math.sqrt(5))
        for i in range(count):
            t = (i + 0.5) / count
            radius = math.sqrt(t)
            phase = i * golden_angle
            speed = 0.012 + ((i % 11) * 0.0028)
            wobble = 0.45 + ((i * 7) % 13) / 18
            depth = 0.35 + ((i * 17) % 100) / 100
            particles.append((phase, radius, speed, wobble, depth))
        return particles

    def keep_topmost(self) -> None:
        try:
            hwnd = self.app_hwnd or int(self.root.winfo_id())
            make_tool_window(hwnd)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            hud_hwnd = int(self.hud.winfo_id())
            make_tool_window(hud_hwnd)
            user32.SetWindowPos(hud_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            particle_hwnd = int(self.particle.winfo_id())
            make_tool_window(particle_hwnd)
            user32.SetWindowPos(particle_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass
        self.root.after(1200, self.keep_topmost)

    def check_for_updates_on_start(self) -> None:
        if not bool(self.settings.get("auto_update_enabled", False)):
            return
        if not getattr(sys, "frozen", False):
            log("auto update skipped: source mode")
            return
        manifest_url = str(self.settings.get("update_manifest_url", "") or "").strip()
        if not manifest_url:
            log("auto update skipped: update_manifest_url is empty")
            return
        threading.Thread(target=self.update_worker, args=(manifest_url,), daemon=True).start()

    def update_worker(self, manifest_url: str) -> None:
        try:
            manifest = read_update_manifest(manifest_url)
            remote_version = str(manifest.get("version", "") or "")
            if not is_newer_version(remote_version, APP_VERSION):
                log(f"auto update: current version ok | current={APP_VERSION} | remote={remote_version}")
                return
            zip_url_value = str(manifest.get("zip_url", "") or "")
            if not zip_url_value:
                log("auto update skipped: manifest missing zip_url")
                return
            zip_url = resolve_update_url(manifest_url, zip_url_value)
            update_dir = Path(tempfile.gettempdir()) / "VoiNoi-update"
            zip_path = update_dir / "VoiNoi-windows.zip"
            log(f"auto update downloading | version={remote_version} | url={zip_url}")
            download_update_zip(zip_url, zip_path)
            expected_sha = str(manifest.get("sha256", "") or "").strip().lower()
            if expected_sha:
                actual_sha = sha256_file(zip_path)
                if actual_sha.lower() != expected_sha:
                    log(f"auto update hash mismatch | expected={expected_sha} | actual={actual_sha}")
                    return
            self.root.after(0, lambda: self.show_hud("busy", f"C\u1eadp nh\u1eadt {remote_version}", None))
            self.launch_updater(zip_path)
        except Exception as exc:
            log(f"auto update error: {type(exc).__name__}: {exc}")

    def launch_updater(self, zip_path: Path) -> None:
        updater = APP_DIR / "updater.ps1"
        if not updater.exists():
            log(f"auto update skipped: updater missing | path={updater}")
            return
        exe_name = Path(sys.executable).name
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(updater),
            "-AppPid",
            str(os.getpid()),
            "-ZipPath",
            str(zip_path),
            "-AppDir",
            str(APP_DIR),
            "-ExeName",
            exe_name,
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(args, creationflags=flags)
        log(f"auto update launched updater | zip={zip_path}")
        self.root.after(700, self.root.destroy)

    def monitor_target_window(self) -> None:
        try:
            if not self.listening:
                hwnd = foreground_window()
                if hwnd and hwnd not in {self.app_hwnd, self.hud_hwnd}:
                    self.last_target_hwnd = hwnd
        except Exception:
            pass
        self.root.after(200, self.monitor_target_window)

    def monitor_global_clicks(self) -> None:
        try:
            down = left_button_down()
            pressed = down and not self.auto_was_down
            released = self.auto_was_down and not down
            point = cursor_position()
            if pressed:
                if self.radial_open:
                    if self.point_in_radial(point):
                        self.radial_press_inside = True  # chon khi tha chuot
                    else:
                        self.close_radial_menu("click-outside")  # click ra ngoai: dong, click van toi app
                elif key_down(VK_MENU):
                    self.handle_alt_press(point)
            if self.radial_open:
                self.update_radial_menu(point)
                if time.monotonic() - self.radial_opened_at > RADIAL_TIMEOUT_SECONDS and not down:
                    self.close_radial_menu("timeout")
            if released and self.radial_open and (self.radial_press_inside or self.radial_dragging):
                choice = self.radial_choice
                self.radial_press_inside = False
                self.radial_dragging = False
                if choice is not None:
                    # keo toi o roi tha (Alt + giu keo), hoac click vao o: chay lua chon
                    self.close_radial_menu(f"choice:{choice}")
                    self.run_radial_choice(choice, self.radial_anchor)
                # tha o giua ma chua chon: vong tron van mo de anh di chuot toi o roi click
            self.auto_was_down = down
        except Exception as exc:
            log(f"auto click monitor error: {type(exc).__name__}: {exc}")
        self.root.after(int(AUTO_CLICK_POLL_SECONDS * 1000), self.monitor_global_clicks)

    def monitor_voice_hotkeys(self) -> None:
        try:
            escape_down = key_down(VK_ESCAPE)
            if self.radial_open:
                # thanh chon dang mo: chi chon bang chuot (phim so se go lan chu vao khung chat), Esc de huy
                if escape_down and not self.escape_was_down:
                    self.close_radial_menu("escape")
                self.escape_was_down = escape_down
                self.root.after(35, self.monitor_voice_hotkeys)
                return
            if escape_down and not self.escape_was_down and self.reading is not None:
                self.reading.stop()
            elif escape_down and not self.escape_was_down and self.conversation is not None:
                # Esc trong luc tro chuyen: ket thuc han che do voice
                self.conversation.stop()
                if self.listening:
                    self.request_stop("escape")
            elif escape_down and not self.escape_was_down and self.listening:
                self.request_stop("escape")
            self.escape_was_down = escape_down

            # Phim tat mo/tat che do tro chuyen (mac dinh Ctrl+Alt+V), khong can noi lenh
            if self.voice_chat_hotkey:
                hotkey_down = all(key_down(code) for code in self.voice_chat_hotkey)
                if hotkey_down and not self.voice_chat_hotkey_was_down:
                    self.toggle_voice_conversation_hotkey()
                self.voice_chat_hotkey_was_down = hotkey_down

        except Exception as exc:
            log(f"hotkey monitor error: {type(exc).__name__}: {exc}")
        self.root.after(35, self.monitor_voice_hotkeys)

    def is_near_learned_target(self, hwnd: int, point: tuple[int, int]) -> bool:
        key = stable_target_key(hwnd, point)
        if key in self.voice_targets:
            return True
        cls = window_class_name(hwnd)
        for saved_key, saved_point in self.voice_targets.items():
            if not saved_key.startswith(f"{cls}|"):
                continue
            if math.hypot(point[0] - saved_point[0], point[1] - saved_point[1]) <= LEARNED_TARGET_RADIUS:
                return True
        return False

    def remember_voice_target(self, hwnd: int, point: tuple[int, int] | None) -> None:
        if not hwnd or not point:
            return
        key = stable_target_key(hwnd, point)
        self.voice_targets[key] = (point[0], point[1])
        save_voice_targets(self.voice_targets)
        log(f"voice target learned | key={key} | point={point}")

    def pin_voice_target(self, hwnd: int, point: tuple[int, int] | None) -> None:
        if not hwnd or not point:
            return
        self.pinned_target_hwnd = hwnd
        self.pinned_target_point = point
        self.last_target_hwnd = hwnd
        self.last_click_point = point
        self.show_icon_near(point)
        self.draw("armed")
        self.show_hud("armed", "Mic \u0111\u00e3 ghim", 1200)
        log(f"voice target pinned | hwnd={hwnd} | point={point}")

    def handle_escape_key(self, _event: tk.Event) -> None:
        if self.listening:
            self.request_stop("escape")
            return
        if self.processing:
            self.draw("busy")
            self.show_hud("busy", "\u0110ang nh\u1eadn di\u1ec7n...", None)
            return
        self.root.destroy()

    def request_stop(self, reason: str) -> None:
        if not self.listening:
            if self.processing:
                self.draw("busy")
                self.show_hud("busy", "\u0110ang nh\u1eadn di\u1ec7n...", None)
            return
        self.stop_reason = reason
        self.stop_requested = True
        self.draw("busy")
        self.show_hud("busy", "\u0110ang d\u1eebng...", None)
        beep_async("stop")
        log(f"stop requested | reason={reason} | session={self.active_session_id}")

    def try_alt_click_listen_from_click(self, point: tuple[int, int]) -> None:
        conversation = self.conversation
        if conversation is not None and conversation.active and not self.listening:
            # dang tro chuyen: Alt+click de noi tiep khi tam dung, hoac ngat loi tro ly
            if conversation.paused:
                log("voice chat resumed by alt-click")
                conversation.resume()
            elif conversation.speaking:
                conversation.interrupt()
                log("voice chat interrupted by alt-click")
            return

        if self.listening:
            self.request_stop("alt-click")
            log(f"alt-click stops listening | session={self.active_session_id} | point={point}")
            return
        if self.processing:
            log(f"alt-click ignored: session processing | point={point}")
            return
        if not HIDE_FLOATING_MIC_BUTTON and self.point_inside_icon(*point):
            return

        hwnd = foreground_window()
        if not hwnd or hwnd in {self.app_hwnd, self.hud_hwnd}:
            return

        self.last_target_hwnd = hwnd
        self._alt_click_triggered = False
        self._alt_click_token += 1
        token = self._alt_click_token
        for delay in CLICK_DETECT_RETRY_MS:
            self.root.after(
                delay,
                lambda original_hwnd=hwnd, original_point=point, click_token=token:
                    self.maybe_start_alt_click_listen(original_hwnd, original_point, click_token),
            )

    def maybe_start_alt_click_listen(self, hwnd: int, point: tuple[int, int], token: int) -> None:
        """Do xem cho vua click co phai o nhap chu khong. Phan do cham (UI Automation) chay o luong phu."""
        if token != self._alt_click_token:
            return
        if self.listening or self.processing or self._alt_click_triggered or self._alt_click_probing:
            return
        focused_hwnd = foreground_window()
        target_hwnd = focused_hwnd if focused_hwnd and focused_hwnd not in {self.app_hwnd, self.hud_hwnd} else hwnd
        near_learned_target = self.is_near_learned_target(target_hwnd, point)
        strict_chat = point_in_strict_chat_zone(point, target_hwnd)
        browser_bottom = is_browser_bottom_input(target_hwnd, point) and strict_chat
        if near_learned_target or browser_bottom:
            # o da hoc / day cua so trinh duyet: khong can hoi UI Automation, nghe ngay
            reason = "learned-zone" if near_learned_target else "browser-bottom"
            self.begin_alt_click_listen(target_hwnd, point, reason, "skipped")
            return

        self._alt_click_probing = True

        def probe() -> None:
            caret_rect = None
            has_uia_text_input, uia_details = False, ""
            try:
                caret_rect = get_caret_screen_rect(target_hwnd)
                has_uia_text_input, uia_details = uia_probe(point)
            except Exception as exc:
                uia_details = f"probe-error={type(exc).__name__}"
            self.root.after(0, lambda: finish(caret_rect, has_uia_text_input, uia_details))

        def finish(caret_rect: tuple[int, int, int, int] | None, has_uia_text_input: bool, uia_details: str) -> None:
            self._alt_click_probing = False
            if token != self._alt_click_token or self.listening or self.processing or self._alt_click_triggered:
                return
            has_text_caret = bool(caret_rect and point_near_rect(point, caret_rect, CARET_CLICK_RADIUS))
            if not has_uia_text_input and not has_text_caret:
                log(
                    f"alt-click ignored | hwnd={target_hwnd} | point={point} | "
                    f"strict={strict_chat} | caret={caret_rect} | uia={uia_details}"
                )
                return
            self.begin_alt_click_listen(target_hwnd, point, "uia-edit" if has_uia_text_input else "caret", uia_details)

        threading.Thread(target=probe, daemon=True, name="alt-click-probe").start()

    def begin_alt_click_listen(self, target_hwnd: int, point: tuple[int, int], reason: str, details: str = "") -> None:
        self._alt_click_triggered = True
        self._alt_click_token += 1  # bo cac lan do con xep hang
        self.last_auto_started_at = time.monotonic()
        self.pin_voice_target(target_hwnd, point)
        self.start_listening(auto_stop_after_phrase=True, target_hwnd=target_hwnd, target_point=point)
        log(f"alt-click listen started: {reason} | hwnd={target_hwnd} | point={point} | uia={details}")

    def start_dictation_from_radial(self, point: tuple[int, int]) -> None:
        """Anh da chon "Go chu" tren vong tron nghia la cho vua Alt+click la o nhap: nghe ngay, khong do lai.
        (Ban cu do lai bang UI Automation ngay luc vong tron con tren man hinh: do nham chinh vong tron,
        treo giao dien 2-15 giay va co luc bo qua luon.)"""
        if self.listening:
            self.request_stop("alt-click")
            return
        if self.processing:
            self.show_hud("busy", "Đang nhận diện...", 1200)
            log(f"radial dictation ignored: session processing | point={point}")
            return
        hwnd = self.radial_target_hwnd
        if not hwnd or not window_exists(hwnd):
            hwnd = foreground_window()
        if not hwnd or hwnd in {self.app_hwnd, self.hud_hwnd, self.particle_hwnd, self.radial_hwnd}:
            log(f"radial dictation ignored: no target window | point={point}")
            return
        self.begin_alt_click_listen(hwnd, point, "radial")

    def animate(self) -> None:
        if self.visual_state in {"armed", "listen", "busy", "error"}:
            self.anim_tick += 1
            self.draw()
        if self.hud_visible:
            self.draw_hud()
        if self.particle_effect_visible:
            self.draw_particle_effect()
        self.root.after(80, self.animate)

    def draw(self, state: str | None = None) -> None:
        if state is not None:
            self.visual_state = state
        state = self.visual_state
        self.canvas.delete("all")
        palette = {
            "idle": ("#070a10", "#121826", "#29e6b8"),
            "armed": ("#07182b", "#123d69", "#45c7ff"),
            "listen": ("#05251f", "#087b6f", "#5ff4d3"),
            "busy": ("#111322", "#4637c8", "#c4b5fd"),
            "done": ("#07170d", "#15803d", "#86efac"),
            "error": ("#2a0707", "#9f1f1f", "#fecaca"),
        }
        base, mid, accent = palette.get(state, palette["idle"])
        cx = cy = SIZE // 2
        pulse = (math.sin(self.anim_tick / 2.7) + 1) / 2

        if state in {"armed", "listen"}:
            for i, alpha_color in enumerate(("#134e7a", "#0f766e")):
                offset = 2 + i * 5 + int(pulse * 4)
                self.canvas.create_oval(
                    offset,
                    offset,
                    SIZE - offset,
                    SIZE - offset,
                    outline=alpha_color if state == "armed" else "#0f766e",
                    width=1,
                )

        if state == "busy":
            for i in range(6):
                angle = (self.anim_tick * 0.32) + (i * math.tau / 6)
                r = 31
                x = cx + math.cos(angle) * r
                y = cy + math.sin(angle) * r
                dot = 2 + (i % 2)
                self.canvas.create_oval(x - dot, y - dot, x + dot, y + dot, fill="#c4b5fd", outline="")

        if state == "error":
            self.canvas.create_oval(3, 3, SIZE - 3, SIZE - 3, outline="#ef4444", width=2)

        left = (SIZE - CORE) // 2
        top = (SIZE - CORE) // 2
        right = left + CORE
        bottom = top + CORE

        # Scale mic body to CORE size
        self.canvas.create_oval(left + 2, top + 3, right, bottom + 1, fill="#020617", outline="")
        self.canvas.create_oval(left, top, right, bottom, fill=base, outline="#020617", width=1)
        self.canvas.create_oval(left + 2, top + 2, right - 2, bottom - 2, fill=mid, outline=accent, width=1)

        # Mic shape scaled for small icon
        mw = max(3, CORE // 7)
        mh_top = cy - CORE // 2 + 2
        mh_bot = cy - 1
        self.canvas.create_oval(cx - mw, mh_top, cx + mw, mh_top + mw * 2, fill="#f8fafc", outline="")
        self.canvas.create_rectangle(cx - mw, mh_top + mw, cx + mw, mh_bot, fill="#f8fafc", outline="")
        self.canvas.create_oval(cx - mw, mh_bot - mw, cx + mw, mh_bot + mw, fill="#f8fafc", outline="")
        arc_r = CORE // 4
        self.canvas.create_arc(cx - arc_r, cy - arc_r // 2, cx + arc_r, cy + arc_r, start=200, extent=140, style="arc", outline="#f8fafc", width=2)
        self.canvas.create_line(cx, cy + arc_r // 2, cx, cy + arc_r + 2, fill="#f8fafc", width=2, capstyle="round")
        self.canvas.create_line(cx - mw, cy + arc_r + 2, cx + mw, cy + arc_r + 2, fill="#f8fafc", width=2, capstyle="round")

        if state in {"armed", "listen", "busy"}:
            dot_r = max(3, CORE // 8)
            self.canvas.create_oval(cx + CORE // 4, top, cx + CORE // 4 + dot_r * 2, top + dot_r * 2, fill=accent, outline="")

        if state == "listen":
            bar_y = bottom + 3
            heights = [3, 5, 7, 5, 3]
            for i, h in enumerate(heights):
                live = h + int(math.sin((self.anim_tick / 1.5) + i) * 2)
                x = cx - 8 + i * 4
                self.canvas.create_line(x, bar_y - live, x, bar_y + live, fill=accent, width=2, capstyle="round")

    def update_hud_position(self) -> None:
        try:
            screen_left, screen_top, screen_right, screen_bottom = virtual_screen_rect()
            if self.hud_anchor_point:
                anchor_x, anchor_y = self.hud_anchor_point
                x = anchor_x + HUD_GAP
                if x + HUD_WIDTH > screen_right - 8:
                    x = anchor_x - HUD_WIDTH - HUD_GAP
                y = anchor_y - HUD_HEIGHT - HUD_GAP
                if y < screen_top + 8:
                    y = anchor_y + HUD_GAP
            else:
                icon_x = self.root.winfo_x()
                icon_y = self.root.winfo_y()
                x = icon_x + SIZE + HUD_GAP
                if x + HUD_WIDTH > screen_right - 8:
                    x = icon_x - HUD_WIDTH - HUD_GAP
                y = icon_y + (SIZE - HUD_HEIGHT) // 2
            x = max(screen_left + 8, min(x, screen_right - HUD_WIDTH - 8))
            y = max(screen_top + 8, min(y, screen_bottom - HUD_HEIGHT - 8))
            self.hud.geometry(f"{HUD_WIDTH}x{HUD_HEIGHT}+{x}+{y}")
        except Exception:
            pass

    def show_hud(self, state: str, message: str, auto_hide_ms: int | None = None) -> None:
        # HUD Ä‘Ã£ bá»‹ áº©n â€” tráº¡ng thÃ¡i biá»ƒu thá»‹ qua mÃ u sáº¯c icon mic
        self.hud_state = state
        self.hud_message = ellipsize(message)
        try:
            if self.hud_hide_after_id:
                self.root.after_cancel(self.hud_hide_after_id)
                self.hud_hide_after_id = None
            if state in {"listen", "busy", "speak"} and self.particle_effect_enabled:
                self.hide_hud()
                anchor = self.active_target_point or self.particle_anchor_point or self.last_click_point or cursor_position()
                if self.particle_effect_visible and not self.particle_result_visible:
                    self.draw_particle_effect()
                else:
                    self.show_particle_effect(anchor)
                return
            if state == "done" and self.particle_effect_enabled and self.particle_result_visible:
                self.hide_hud()
                return
            self.update_hud_position()
            self.hud_visible = True
            self.hud.deiconify()
            self.hud.lift()
            self.draw_hud()
            if auto_hide_ms:
                self.hud_hide_after_id = self.root.after(auto_hide_ms, self.hide_hud)
        except Exception:
            pass

    def hide_hud(self) -> None:
        try:
            self.hud_visible = False
            self.hud.withdraw()
            self.hud_hide_after_id = None
        except Exception:
            pass

    def show_particle_effect(self, point: tuple[int, int] | None) -> None:
        if not self.particle_effect_enabled:
            return
        if point is None:
            self.hide_particle_effect()
            return
        try:
            self.particle_anchor_point = point
            self.audio_level = 0.12
            self.audio_level_target = 0.18
            self.particle_result_text = ""
            self.particle_result_stats = ""
            self.particle_result_visible = False
            self.update_particle_position()
            self.particle_effect_visible = True
            self.particle.deiconify()
            self.particle.lift()
            self.draw_particle_effect()
        except Exception as exc:
            log(f"particle effect show error: {type(exc).__name__}: {exc}")

    def hide_particle_effect(self) -> None:
        try:
            self.particle_effect_visible = False
            self.audio_level = 0.0
            self.audio_level_target = 0.0
            self.particle_result_visible = False
            self.particle.withdraw()
            self.particle_canvas.delete("all")
        except Exception:
            pass

    def show_particle_result(self, text: str, stats: str, point: tuple[int, int] | None, auto_hide_ms: int = 2600) -> None:
        if not self.particle_effect_enabled:
            return
        if point is None:
            return
        try:
            self.visual_state = "done"
            self.particle_anchor_point = point
            self.particle_result_text = ellipsize(text, 58)
            self.particle_result_stats = stats
            self.particle_result_visible = True
            self.audio_level_target = 0.0
            self.update_particle_position()
            self.particle_effect_visible = True
            self.particle.deiconify()
            self.particle.lift()
            self.draw_particle_effect()
            self.root.after(auto_hide_ms, self.hide_particle_effect)
        except Exception as exc:
            log(f"particle result show error: {type(exc).__name__}: {exc}")

    def update_particle_position(self) -> None:
        try:
            screen_left, screen_top, screen_right, screen_bottom = virtual_screen_rect()
            point = self.particle_anchor_point
            if point is None:
                self.hide_particle_effect()
                return
            x = point[0] - PARTICLE_EFFECT_WIDTH // 2
            y = point[1] - PARTICLE_EFFECT_HEIGHT - PARTICLE_EFFECT_GAP + (0 if self.particle_result_visible else 60)
            if y < screen_top + 8:
                y = point[1] + PARTICLE_EFFECT_GAP
            x = max(screen_left + 8, min(x, screen_right - PARTICLE_EFFECT_WIDTH - 8))
            y = max(screen_top + 8, min(y, screen_bottom - PARTICLE_EFFECT_HEIGHT - 8))
            self.particle.geometry(f"{PARTICLE_EFFECT_WIDTH}x{PARTICLE_EFFECT_HEIGHT}+{x}+{y}")
        except Exception:
            pass

    def draw_particle_effect(self) -> None:
        """Nut tron nho: song am nhay theo giong anh, nhan trang thai ben duoi, the ket qua khi xong.

        Moi chu deu ve tren nen dac (khong ve thang len nen trong suot) de khong bi vien hong.
        """
        if not self.particle_effect_enabled:
            return
        canvas = self.particle_canvas
        canvas.delete("all")
        state = "speak" if self.hud_state == "speak" and self.visual_state != "done" else self.visual_state
        if state not in {"listen", "busy", "done", "speak"}:
            return
        W = PARTICLE_EFFECT_WIDTH
        cx, cy, r = W / 2, 44, ORB_RADIUS
        accent, deep = {
            "listen": ("#5eead4", "#0f766e"),
            "busy": ("#c4b5fd", "#6d28d9"),
            "speak": ("#fcd34d", "#b45309"),
            "done": ("#86efac", "#15803d"),
        }[state]
        self.audio_level += (self.audio_level_target - self.audio_level) * 0.3
        if state in {"busy", "speak"}:
            self.audio_level = max(self.audio_level * 0.9, 0.25 + math.sin(self.anim_tick / 3.0) * 0.08)
        if state == "done":
            self.audio_level *= 0.7
        level = max(0.0, min(1.0, self.audio_level))

        # vong sang mo rong theo do lon giong noi
        halo = r + 4 + level * 9 + math.sin(self.anim_tick / 4.0) * 1.2
        canvas.create_oval(cx - halo, cy - halo, cx + halo, cy + halo, outline=deep, width=2)
        if state == "listen" and level > 0.15:
            outer = halo + 5 + level * 5
            canvas.create_oval(cx - outer, cy - outer, cx + outer, cy + outer, outline=accent, width=1)
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#0b1220", outline=accent, width=2)

        # song am ben trong nut tron (xong thi hien dau tick)
        if state == "done":
            canvas.create_line(cx - 11, cy + 1, cx - 3, cy + 9, cx + 12, cy - 8, fill=accent, width=4,
                               capstyle="round", joinstyle="round")
        else:
            bars = 7
            for i in range(bars):
                offset = i - (bars - 1) / 2
                envelope = 1 - abs(offset) / (bars / 2 + 0.5)
                live = math.sin(self.anim_tick / 1.6 + i * 0.9) * 0.5 + 0.5
                height = 5 + envelope * (6 + 22 * level) + live * (3 + 5 * level)
                if state in {"busy", "speak"}:
                    height = 6 + envelope * 12 + live * 6
                height = min(height, r * 1.25)
                x = cx + offset * 6
                canvas.create_line(x, cy - height / 2, x, cy + height / 2,
                                   fill="#f8fafc" if abs(offset) < 1 else accent, width=3, capstyle="round")

        # nhan trang thai (co dau) tren nen dac
        default_labels = {"listen": "Đang nghe", "busy": "Đang nhận diện", "speak": "Trợ lý đang nói", "done": "Đã có chữ"}
        message = re.sub(r"\s*#\d+$", "", self.hud_message or "").strip()
        label = message if message and self.hud_state == state else default_labels[state]
        if state == "done":
            label = default_labels["done"]
        label = ellipsize(label, 34)
        pill_w = min(W - 8, 18 + len(label) * 6.4)
        pill_y = cy + r + 14
        round_rect(canvas, cx - pill_w / 2, pill_y - 10, cx + pill_w / 2, pill_y + 10, 10, fill="#0b1220", outline=deep)
        canvas.create_text(cx, pill_y, text=label, fill="#f1f5f9", font=("Segoe UI", 8, "bold"))

        # the ket qua: cau vua nhan dien + so ky tu
        if state == "done" and self.particle_result_visible:
            top = pill_y + 16
            round_rect(canvas, 4, top, W - 4, top + 44, 10, fill="#0b1220", outline=deep)
            canvas.create_text(cx, top + 14, text=ellipsize(self.particle_result_text, 40), fill="#f8fafc",
                               font=("Segoe UI", 8), width=W - 20)
            canvas.create_text(cx, top + 31, text=self.particle_result_stats, fill=accent,
                               font=("Segoe UI", 8, "bold"), width=W - 16)

    def draw_hud(self) -> None:
        canvas = self.hud_canvas
        canvas.delete("all")
        state = self.hud_state
        palettes = {
            "armed": ("#08111f", "#102a43", "#38bdf8", "#f8fafc"),
            "listen": ("#061512", "#0f766e", "#5eead4", "#ecfeff"),
            "busy": ("#10101f", "#4338ca", "#c4b5fd", "#f5f3ff"),
            "done": ("#07170d", "#15803d", "#86efac", "#f0fdf4"),
            "error": ("#210909", "#991b1b", "#fecaca", "#fff1f2"),
            "speak": ("#1c1206", "#b45309", "#fcd34d", "#fffbeb"),
        }
        bg, mid, accent, text_color = palettes.get(state, palettes["listen"])
        pulse = (math.sin(self.anim_tick / 2.2) + 1) / 2
        W, H = HUD_WIDTH, HUD_HEIGHT
        r = H // 2 - 2

        # Pill background
        canvas.create_rectangle(r + 2, 2, W - r - 2, H - 2, fill=bg, outline="")
        canvas.create_oval(2, 2, H - 2, H - 2, fill=bg, outline="")
        canvas.create_oval(W - H + 2, 2, W - 2, H - 2, fill=bg, outline="")
        canvas.create_rectangle(r + 2, 2, W - r - 2, H - 2, fill=bg, outline="", width=0)
        # Border
        canvas.create_rectangle(r + 2, 2, W - r - 2, 3, fill=accent, outline="")
        canvas.create_rectangle(r + 2, H - 3, W - r - 2, H - 2, fill=accent, outline="")
        canvas.create_arc(2, 2, H - 2, H - 2, start=90, extent=180, outline=accent, width=1, style="arc")
        canvas.create_arc(W - H + 2, 2, W - 2, H - 2, start=270, extent=180, outline=accent, width=1, style="arc")

        # Small mic dot indicator on left
        dot_x, dot_y = r + 2, H // 2
        if state in {"listen", "armed"}:
            ring_r = 9 + int(pulse * 4)
            canvas.create_oval(dot_x - ring_r, dot_y - ring_r, dot_x + ring_r, dot_y + ring_r, outline=accent, width=1)
        canvas.create_oval(dot_x - 9, dot_y - 9, dot_x + 9, dot_y + 9, fill=mid, outline=accent, width=1)
        # mini mic shape
        canvas.create_oval(dot_x - 3, dot_y - 7, dot_x + 3, dot_y - 1, fill="#f8fafc", outline="")
        canvas.create_rectangle(dot_x - 3, dot_y - 4, dot_x + 3, dot_y + 1, fill="#f8fafc", outline="")
        canvas.create_arc(dot_x - 6, dot_y - 1, dot_x + 6, dot_y + 7, start=200, extent=140, style="arc", outline="#f8fafc", width=2)
        canvas.create_line(dot_x, dot_y + 6, dot_x, dot_y + 9, fill="#f8fafc", width=2, capstyle="round")

        # Status icon on right side
        icon_x = W - r - 2
        if state == "listen":
            bars = 5
            for i in range(bars):
                live = 5 + int((math.sin(self.anim_tick / 1.5 + i * 0.8) + 1) * 7)
                x = icon_x - 20 + i * 8
                canvas.create_line(x, dot_y - live // 2, x, dot_y + live // 2, fill=accent, width=3, capstyle="round")
        elif state == "busy":
            for i in range(5):
                angle = self.anim_tick * 0.35 + i * math.tau / 5
                x = icon_x - 12 + math.cos(angle) * 9
                y = dot_y + math.sin(angle) * 7
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=accent, outline="")
        elif state == "done":
            canvas.create_line(icon_x - 16, dot_y + 2, icon_x - 8, dot_y + 10, fill=accent, width=3, capstyle="round")
            canvas.create_line(icon_x - 8, dot_y + 10, icon_x + 6, dot_y - 8, fill=accent, width=3, capstyle="round")
        elif state == "error":
            canvas.create_line(icon_x - 12, dot_y - 8, icon_x + 4, dot_y + 8, fill=accent, width=3, capstyle="round")
            canvas.create_line(icon_x + 4, dot_y - 8, icon_x - 12, dot_y + 8, fill=accent, width=3, capstyle="round")
        elif state == "armed":
            canvas.create_text(icon_x - 6, dot_y, text="1/2", fill=accent, font=("Segoe UI", 8, "bold"))

        # Label text
        labels = {
            "armed": "Nh\u1ea5n 1 mic / 2 b\u00e0n ph\u00edm",
            "listen": "\u0110ang nghe...",
            "busy": "\u0110ang x\u1eed l\u00fd...",
            "done": self.hud_message or "Xong",
            "error": "Th\u1eed l\u1ea1i",
        }
        label = labels.get(state, self.hud_message or "")
        if len(label) > 32:
            label = label[:30] + "..."
        tx = dot_x + 14
        max_text_w = icon_x - tx - 30
        canvas.create_text(tx, dot_y, anchor="w", text=label, fill=text_color, font=("Segoe UI", 9, "bold"), width=max_text_w)

    def on_press(self, event: tk.Event) -> None:
        self.drag_start = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.dragged = False

    def on_drag(self, event: tk.Event) -> None:
        if not self.drag_start:
            return
        start_x, start_y, win_x, win_y = self.drag_start
        dx = event.x_root - start_x
        dy = event.y_root - start_y
        if abs(dx) + abs(dy) > 3:
            self.dragged = True
        if self.dragged:
            x = win_x + dx
            y = win_y + dy
            self.root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")
            self.update_hud_position()

    def on_release(self, _event: tk.Event) -> None:
        save_position(self.root.winfo_x(), self.root.winfo_y())
        self.drag_start = None
        if not self.dragged:
            self.listen_now()

    def listen_now(self) -> None:
        if self.listening:
            self.request_stop("mic-button")
            return
        if self.processing:
            self.draw("busy")
            self.show_hud("busy", "\u0110ang nh\u1eadn di\u1ec7n...", None)
            return
        if self.pinned_target_hwnd and self.pinned_target_point:
            self.start_listening(
                auto_stop_after_phrase=True,
                target_hwnd=self.pinned_target_hwnd,
                target_point=self.pinned_target_point,
            )
            return
        self.start_listening(auto_stop_after_phrase=False)

    def show_icon_near(self, point: tuple[int, int] | None) -> None:
        try:
            screen_left, screen_top, screen_right, screen_bottom = virtual_screen_rect()
            if point:
                self.hud_anchor_point = point
                x = point[0] - SIZE // 2
                y = point[1] - SIZE - 10
                x = max(screen_left + 4, min(x, screen_right - SIZE - 4))
                y = max(screen_top + 4, min(y, screen_bottom - SIZE - 4))
                self.root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")
            self.update_hud_position()
            if not SHOW_FLOATING_MIC_ICON:
                self.root.withdraw()
                return
            self.root.deiconify()
            self.root.lift()
            make_tool_window(self.app_hwnd)
        except Exception:
            pass

    def start_listening(
        self,
        auto_stop_after_phrase: bool,
        target_hwnd: int = 0,
        target_point: tuple[int, int] | None = None,
        mode: str = "dictation",
    ) -> None:
        if self.listening or self.processing:
            return
        self.session_mode = mode
        self.listening = True
        self.processing = False
        self.capture_clicks = not auto_stop_after_phrase
        self.stop_requested = False
        self.stop_reason = ""
        self.session_counter += 1
        self.active_session_id = self.session_counter
        self.last_click_point = target_point
        self.active_target_hwnd = target_hwnd
        self.active_target_point = target_point
        if target_hwnd:
            self.last_target_hwnd = target_hwnd
        self.draw("listen")
        self.show_icon_near(target_point)
        self.show_particle_effect(target_point)
        self.show_hud("listen", "Em \u0111ang nghe anh..." if mode == "conversation" else "\u0110ang nghe...", None)
        beep_async("start")
        log(f"session start | id={self.active_session_id} | locked_hwnd={target_hwnd} | locked_point={target_point}")
        self.ensure_whisper()   # nap Whisper trong luc anh dang noi
        if self.capture_clicks:
            threading.Thread(target=self.capture_target_click_worker, daemon=True).start()
        threading.Thread(target=self.listen_worker, args=(auto_stop_after_phrase, self.active_session_id), daemon=True).start()

    def open_microphone_source(self, session_id: int) -> tuple[FastMicSource, int | None, str]:
        last_error: Exception | None = None
        names = AUDIO_DEVICES.refresh(max_age=MIC_DEVICE_MAX_AGE_SECONDS)
        attempt = 0
        for round_index in range(2):
            if round_index == 1:
                # mic vua cam/rut: liet ke lai thiet bi roi thu lai mot luot
                log(f"mic devices re-scanned after open failure | session={session_id}")
                names = AUDIO_DEVICES.refresh(force=True)
            for index, name in microphone_device_candidates(self.settings, names):
                attempt += 1
                try:
                    source = AUDIO_DEVICES.open(index)
                except Exception as exc:
                    last_error = exc
                    log(
                        f"mic open failed | session={session_id} | attempt={attempt} | "
                        f"index={index} | name={name} | {type(exc).__name__}: {exc}"
                    )
                    continue
                if index != self.microphone_device_index or name != self.microphone_device_name:
                    log(
                        f"mic reselected | session={session_id} | "
                        f"old_index={self.microphone_device_index} | old_name={self.microphone_device_name} | "
                        f"new_index={index} | new_name={name}"
                    )
                    self.microphone_device_index = index
                    self.microphone_device_name = name
                if attempt > 1:
                    log(f"mic recovered | session={session_id} | attempt={attempt} | index={index} | name={name}")
                return source, index, name

        if last_error:
            raise OSError(f"no microphone could be opened; last error: {type(last_error).__name__}: {last_error}")
        raise OSError("no microphone devices found")

    @contextlib.contextmanager
    def microphone_source_context(self, session_id: int):
        source, index, name = self.open_microphone_source(session_id)
        try:
            yield source, index, name
        finally:
            AUDIO_DEVICES.close(source)

    def capture_target_click_worker(self) -> None:
        was_down = left_button_down()
        while self.capture_clicks:
            down = left_button_down()
            if down and not was_down:
                x, y = cursor_position()
                if not self.point_inside_icon(x, y):
                    self.last_click_point = (x, y)
            was_down = down
            time.sleep(0.02)

    def point_inside_icon(self, x: int, y: int) -> bool:
        left = self.root.winfo_x()
        top = self.root.winfo_y()
        return left <= x <= left + SIZE and top <= y <= top + SIZE

    def ensure_whisper(self, wait: float = 0.0) -> None:
        """Bat dau nap Whisper neu chua co; wait > 0 thi doi toi da chung do giay cho nap xong."""
        if not self.enable_whisper_fallback:
            return
        self.whisper_last_used = time.time()
        if self.whisper_model is not None:
            return
        loader = self.whisper_loader
        if loader is None or not loader.is_alive():
            loader = threading.Thread(target=self._load_whisper_model, daemon=True)
            self.whisper_loader = loader
            loader.start()
        if wait > 0:
            loader.join(wait)

    def unload_idle_whisper(self) -> None:
        try:
            idle = time.time() - self.whisper_last_used
            if (
                self.whisper_model is not None
                and self.whisper_idle_unload_seconds > 0
                and idle >= self.whisper_idle_unload_seconds
                and not self.listening
                and not self.processing
            ):
                self.whisper_model = None
                import gc
                gc.collect()
                log(f"whisper unloaded after {idle / 60:.0f} min idle (loads again on next speech)")
        except Exception as exc:
            log(f"whisper idle unload error: {type(exc).__name__}: {exc}")
        self.root.after(60_000, self.unload_idle_whisper)

    def _load_whisper_model(self) -> None:
        global _faster_whisper, _whisper
        if _faster_whisper is None:
            try:
                from faster_whisper import WhisperModel
                _faster_whisper = WhisperModel
            except Exception as exc:
                log(f"faster-whisper unavailable; trying openai-whisper | {type(exc).__name__}: {exc}")
        if _faster_whisper is not None:
            try:
                log(
                    f"loading faster-whisper {self.whisper_model_name} model "
                    f"cpu/{self.whisper_compute_type}..."
                )
                self.whisper_model = _faster_whisper(
                    self.whisper_model_name,
                    device="cpu",
                    compute_type=self.whisper_compute_type,
                )
                self.whisper_backend = "faster"
                log(f"faster-whisper {self.whisper_model_name} model loaded")
                return
            except Exception as exc:
                log(f"faster-whisper load error; trying openai-whisper | {type(exc).__name__}: {exc}")

        if _whisper is None:
            try:
                import whisper as whisper_module
                _whisper = whisper_module
            except Exception:
                log("whisper unavailable; google speech recognition only")
                return
        if _whisper is None:
            log("whisper unavailable; google speech recognition only")
            return
        try:
            log(f"loading whisper {self.whisper_model_name} model...")
            self.whisper_model = _whisper.load_model(self.whisper_model_name)
            self.whisper_backend = "openai"
            log(f"whisper {self.whisper_model_name} model loaded")
        except Exception as exc:
            log(f"whisper load error: {exc}")

    def _audio_duration_seconds(self, audio: sr.AudioData) -> float:
        bytes_per_second = max(1, audio.sample_rate * audio.sample_width)
        return len(audio.frame_data) / bytes_per_second

    def _transcribe_google_once(self, audio: sr.AudioData) -> str:
        recognizer = sr.Recognizer()
        recognizer.operation_timeout = GOOGLE_RECOGNITION_TIMEOUT_SECONDS
        response = recognizer.recognize_google(audio, language="vi-VN", show_all=True)
        # giu lai moi cach nghe cua Google de do lenh ngan ("voice" hay bi nghe thanh chu khac)
        self.last_google_alternatives = [text for text, _confidence in google_response_alternatives(response)]
        google_text, confidence, alternative_count = choose_google_alternative(response)
        if not google_text:
            raise sr.UnknownValueError()
        if confidence is not None:
            self.google_confidence_scores.append(confidence)
        log(
            f"google confidence={format_confidence_percent(confidence)} | "
            f"alternatives={alternative_count} | text={google_text[:80]}"
        )
        return google_text

    def _slice_audio(self, audio: sr.AudioData, start_byte: int, end_byte: int) -> sr.AudioData:
        width = max(1, audio.sample_width)
        start_byte -= start_byte % width
        end_byte -= end_byte % width
        return sr.AudioData(audio.frame_data[start_byte:end_byte], audio.sample_rate, audio.sample_width)

    def _transcribe_google_attempt(self, audio: sr.AudioData, label: str, attempt: int) -> str:
        duration = self._audio_duration_seconds(audio)
        try:
            text = self._transcribe_google_once(audio).strip()
        except sr.UnknownValueError:
            log(f"google {label} unrecognized | attempt={attempt} | duration={duration:.1f}s")
            raise
        except Exception as exc:
            log(f"google {label} error | attempt={attempt} | duration={duration:.1f}s | {type(exc).__name__}: {exc}")
            raise
        if not text:
            log(f"google {label} empty | attempt={attempt} | duration={duration:.1f}s")
            raise sr.UnknownValueError()
        return text

    def _transcribe_google_resilient(self, audio: sr.AudioData, label: str, depth: int = 0) -> str:
        """Google tra ve khong on dinh: gui lai y nguyen thuong ra chu (~40% lan theo log).

        Ban cu thu lai roi chia doi TUAN TU (toi da 14 lan goi, 10-15 giay cho mot doan hong). Gio lan hai
        chay SONG SONG: gui lai ca doan + hai nua doan cung luc, lay ket qua tot nhat (~2 lan goi mang)."""
        try:
            return self._transcribe_google_attempt(audio, label, 1)
        except Exception as exc:
            first_error = exc

        duration = self._audio_duration_seconds(audio)
        midpoint = len(audio.frame_data) // 2
        midpoint -= midpoint % max(1, audio.sample_width)
        can_split = depth == 0 and duration > GOOGLE_MIN_RETRY_CHUNK_SECONDS and 0 < midpoint < len(audio.frame_data)
        if not isinstance(first_error, sr.UnknownValueError):
            time.sleep(0.25)  # loi mang: nghi mot nhip roi moi gui lai
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="google-retry")
        try:
            retry = executor.submit(self._transcribe_google_attempt, audio, label, 2)
            halves = []
            if can_split:
                log(f"google {label} retry + split in parallel | duration={duration:.1f}s")
                halves = [
                    executor.submit(self._transcribe_google_attempt, self._slice_audio(audio, 0, midpoint), f"{label}a", 1),
                    executor.submit(
                        self._transcribe_google_attempt,
                        self._slice_audio(audio, midpoint, len(audio.frame_data)),
                        f"{label}b",
                        1,
                    ),
                ]
            try:
                return retry.result()
            except Exception as exc:
                last_error: Exception = exc
            if halves:
                parts: list[str] = []
                for future in halves:
                    try:
                        parts.append(future.result())
                    except Exception as exc:
                        last_error = exc
                        parts = []
                        break
                if parts:
                    log(f"google {label} recovered from halves")
                    return clean_transcript(" ".join(parts))
        finally:
            executor.shutdown(wait=False)  # co ket qua roi thi khong doi cac luot con lai
        raise last_error

    def _recover_chunk_with_whisper(
        self, chunk_audio: sr.AudioData, index: int, total: int, speech_level: int
    ) -> tuple[str, str]:
        """Google bo sot doan nay: cho Whisper nghe lai rieng doan do, tru khi doan do chi la im lang.

        Tra ve (chu, trang thai); trang thai "quiet" = doan chi co tieng on, khong tinh la mat chu."""
        duration = self._audio_duration_seconds(chunk_audio)
        level = audio_speech_level(chunk_audio)
        if level < max(120, speech_level * 0.45):
            log(f"whisper chunk {index}/{total} skipped: quiet | level={level} | speech_level={speech_level}")
            return "", "quiet"
        self.ensure_whisper(wait=60)
        if self.whisper_model is None:
            return "", "unavailable"
        try:
            text = self._transcribe_whisper(chunk_audio, vad=True).strip()
        except Exception as exc:
            log(f"whisper chunk {index}/{total} failed | {type(exc).__name__}: {exc}")
            return "", "failed"
        words = count_transcript_words(text)
        wpm = words / max(0.1, duration / 60)
        if not text or wpm < 30 or wpm > 330:
            log(f"whisper chunk {index}/{total} rejected | wpm={wpm:.0f} | text={text[:60]}")
            return "", "rejected"
        log(f"whisper chunk {index}/{total} recovered | chars={len(text)} | text={text[:80]}")
        return text, "whisper"

    def _fill_low_coverage_chunk(
        self, chunk_audio: sr.AudioData, google_text: str, index: int, total: int, speech_level: int
    ) -> str:
        """Google hay lam roi mat vai cau o dau doan (tra ve 13 chu cho 8 giay noi). Doan nao qua it chu so voi
        do dai thi cho Whisper nghe rieng doan do va lay ban day du hon. Chi ton them vai giay cho dung doan do."""
        duration = self._audio_duration_seconds(chunk_audio)
        google_words = count_transcript_words(google_text)
        google_wpm = google_words / max(0.1, duration / 60)
        if (
            not self.enable_whisper_fallback
            or duration < LOW_COVERAGE_MIN_CHUNK_SECONDS
            or google_wpm >= float(self.settings_value("low_coverage_wpm", LOW_COVERAGE_WPM) or 0)
            or audio_speech_level(chunk_audio) < max(120, speech_level * 0.6)
        ):
            return google_text
        log(f"google chunk {index}/{total} low coverage | wpm={google_wpm:.0f} | words={google_words} | checking whisper")
        whisper_text, _status = self._recover_chunk_with_whisper(chunk_audio, index, total, speech_level)
        whisper_words = count_transcript_words(whisper_text)
        if whisper_text and whisper_words >= google_words * 1.3 + 2:
            log(f"google chunk {index}/{total} filled by whisper | google={google_words} | whisper={whisper_words} words")
            return whisper_text
        return google_text

    def _transcribe_google_chunked(self, audio: sr.AudioData) -> str:
        chunks = google_audio_chunks(audio)
        if not chunks:
            raise sr.UnknownValueError()

        total = len(chunks)
        for index, chunk_audio, start_sec, end_sec in chunks:
            log(
                f"google smart chunk {index}/{total} | "
                f"range={start_sec:.1f}-{end_sec:.1f}s | duration={self._audio_duration_seconds(chunk_audio):.1f}s"
            )

        speech_level = audio_speech_level(audio)

        def transcribe_chunk(item: tuple[int, sr.AudioData, float, float]) -> tuple[int, str, str]:
            index, chunk_audio, _start_sec, _end_sec = item
            try:
                chunk_text = self._transcribe_google_resilient(chunk_audio, f"chunk {index}/{total}").strip()
                if chunk_text:
                    return index, self._fill_low_coverage_chunk(chunk_audio, chunk_text, index, total, speech_level), "ok"
                status = "empty"
            except sr.UnknownValueError:
                status = "unrecognized"
            except Exception as exc:
                status = f"error:{type(exc).__name__}: {exc}"
            log(f"google chunk {index}/{total} {status}")
            # Whisper nghe lai ngay trong luong nay, song song voi cac doan khac (truoc day doi het moi lam)
            whisper_text, whisper_status = self._recover_chunk_with_whisper(chunk_audio, index, total, speech_level)
            if whisper_text:
                return index, whisper_text, "whisper"
            return index, "", "quiet" if whisper_status == "quiet" else status

        parts: list[str] = []
        errors = 0
        workers = min(5, max(1, len(chunks)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(transcribe_chunk, chunks))

        recovered = 0
        quiet = 0
        for index, chunk_text, status in sorted(results, key=lambda item: item[0]):
            if status == "ok":
                parts.append(chunk_text)
                log(f"google chunk {index}/{total} ok | chars={len(chunk_text)} | text={chunk_text[:80]}")
                continue
            if status == "whisper":
                parts.append(chunk_text)
                recovered += 1
                self.google_confidence_scores.append(0.85)
                continue
            if status == "quiet":
                # doan chi co tieng on (thuong la cuoi cau): khong mat chu nao, khong keo tut do tin cay.
                # Truoc day tinh la 0% -> do tin cay < 82% -> Whisper nghe lai CA doan dai (~18 giay).
                quiet += 1
                continue
            errors += 1
            # Missing audio is a real accuracy loss. Count it in the session
            # confidence instead of reporting a misleadingly high average
            # based only on chunks Google happened to recognize.
            self.google_confidence_scores.append(0.0)

        text = merge_transcript_parts(parts)
        if text:
            log(
                f"transcribe engine=google-chunked | chunks={len(parts)}/{total} | "
                f"whisper_recovered={recovered} | quiet={quiet} | errors={errors} | workers={workers} | text={text[:80]}"
            )
            return text
        raise sr.UnknownValueError()

    def _transcribe_google_candidate(self, audio: sr.AudioData, duration: float) -> tuple[str, float | None]:
        self.google_confidence_scores.clear()
        if duration > GOOGLE_SINGLE_PASS_MAX_SECONDS:
            log(f"long audio detected; using google chunks | duration={duration:.1f}s")
            google_text = self._transcribe_google_chunked(audio)
        else:
            google_text = self._transcribe_google_once(audio)
        avg_confidence = (
            sum(self.google_confidence_scores) / len(self.google_confidence_scores)
            if self.google_confidence_scores
            else None
        )
        log(
            f"transcribe engine=google | confidence_avg={format_confidence_percent(avg_confidence)} | "
            f"text={google_text[:80]}"
        )
        return google_text, avg_confidence

    def _choose_hybrid_transcript(
        self,
        google_text: str,
        google_confidence: float | None,
        whisper_text: str,
        duration: float,
    ) -> str:
        google_score = transcript_selection_score(google_text)
        whisper_score = transcript_selection_score(whisper_text)
        if google_confidence is not None:
            google_score += min(0.035, max(0.0, google_confidence - 0.86) * 0.16)
        google_words = count_transcript_words(google_text)
        whisper_words = count_transcript_words(whisper_text)
        if google_words and whisper_words:
            ratio = min(google_words, whisper_words) / max(google_words, whisper_words)
            if ratio < 0.45:
                if google_words > whisper_words:
                    google_score += 0.04
                else:
                    whisper_score += 0.04
        log(
            f"strict hybrid score | google={google_score:.3f} | whisper={whisper_score:.3f} | "
            f"google_confidence={format_confidence_percent(google_confidence)} | duration={duration:.1f}s"
        )
        if whisper_text and whisper_score >= google_score + WHISPER_SELECTION_MARGIN:
            log(f"strict hybrid selected whisper | text={whisper_text[:100]}")
            return whisper_text
        if google_text:
            log(f"strict hybrid selected google | text={google_text[:100]}")
            return google_text
        return whisper_text

    def _transcribe_strict_hybrid(self, audio: sr.AudioData, duration: float) -> str:
        google_text = ""
        google_confidence: float | None = None
        whisper_text = ""

        def google_job() -> tuple[str, float | None]:
            return self._transcribe_google_candidate(audio, duration)

        def whisper_job() -> str:
            return self._transcribe_whisper(audio)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            google_future = executor.submit(google_job)
            whisper_future = executor.submit(whisper_job)
            try:
                whisper_text = whisper_future.result()
            except sr.UnknownValueError:
                log("strict hybrid whisper unrecognized")
            except Exception as exc:
                log(f"strict hybrid whisper error | {type(exc).__name__}: {exc}")
            try:
                google_text, google_confidence = google_future.result()
            except sr.UnknownValueError:
                log("strict hybrid google unrecognized")
            except Exception as exc:
                log(f"strict hybrid google error | {type(exc).__name__}: {exc}")

        if google_text and whisper_text:
            return self._choose_hybrid_transcript(google_text, google_confidence, whisper_text, duration)
        if whisper_text:
            log(f"strict hybrid only whisper | text={whisper_text[:100]}")
            return whisper_text
        if google_text:
            log(f"strict hybrid only google | text={google_text[:100]}")
            return google_text
        raise sr.UnknownValueError()

    def _transcribe_audio(self, audio: sr.AudioData) -> str:
        """Transcribe Vietnamese speech quickly; verify with Whisper only when Google looks risky."""
        duration = self._audio_duration_seconds(audio)
        google_candidate = ""
        google_avg_confidence: float | None = None
        self.last_transcript_whisper_only = False
        self.last_google_alternatives: list[str] = []

        try:
            google_text, avg_confidence = self._transcribe_google_candidate(audio, duration)
            if google_text:
                google_candidate = google_text
                google_avg_confidence = avg_confidence
                should_try_whisper = (
                    self.whisper_model is not None
                    and (
                        transcript_suspicion_penalty(google_text) > 0
                        or (
                            avg_confidence is not None
                            and avg_confidence < GOOGLE_LOW_CONFIDENCE_FALLBACK_THRESHOLD
                        )
                    )
                )
                if should_try_whisper:
                    log(
                        f"whisper verification requested | duration={duration:.1f}s | "
                        f"google_confidence={format_confidence_percent(avg_confidence)} | "
                        f"suspicion={transcript_suspicion_penalty(google_text):.2f}"
                    )
                else:
                    return google_text
                if (
                    avg_confidence is not None
                    and avg_confidence < GOOGLE_LOW_CONFIDENCE_FALLBACK_THRESHOLD
                    and self.whisper_model is not None
                ):
                    log(
                        f"google confidence below fallback threshold | "
                        f"confidence={format_confidence_percent(avg_confidence)} | "
                        f"threshold={GOOGLE_LOW_CONFIDENCE_FALLBACK_THRESHOLD * 100:.0f}%"
                    )
        except sr.UnknownValueError:
            voiced = getattr(self, "session_voiced_seconds", 99.0)
            if voiced < MIN_VOICED_SECONDS_FOR_WHISPER:
                # chi la tieng dong (go phim, click chuot): Whisper se mat ~5-9 giay roi cung chi doan bua
                log(f"google unrecognized; too little voice for whisper | voiced={voiced:.2f}s")
                raise
            log(f"google unrecognized; falling back to whisper | voiced={voiced:.1f}s")
        except Exception as exc:
            log(f"google transcribe error: {type(exc).__name__}: {exc}")
            if duration > GOOGLE_MIN_RETRY_CHUNK_SECONDS:
                try:
                    log(f"retrying google with chunks after error | duration={duration:.1f}s")
                    google_text = self._transcribe_google_chunked(audio)
                    if google_text:
                        google_candidate = google_text
                        return google_text
                except Exception as retry_exc:
                    log(f"google chunk retry failed: {type(retry_exc).__name__}: {retry_exc}")
            log("falling back to whisper")

        self.ensure_whisper(wait=60)
        if self.whisper_model is None:
            if google_candidate:
                return google_candidate
            raise sr.UnknownValueError()

        whisper_text = self._transcribe_whisper(audio, google_candidate)
        if google_candidate:
            google_score = transcript_selection_score(google_candidate)
            whisper_score = transcript_selection_score(whisper_text)
            log(
                f"hybrid score | google={google_score:.3f} | whisper={whisper_score:.3f} | "
                f"google_confidence={format_confidence_percent(google_avg_confidence)}"
            )
            if whisper_text and whisper_score >= google_score + WHISPER_SELECTION_MARGIN:
                log(f"hybrid selected whisper | text={whisper_text[:100]}")
                return whisper_text
            log(f"hybrid kept google | text={google_candidate[:100]}")
            return google_candidate
        # Google khong nghe ra chu nao, chi con Whisper doan: danh dau de chan cau doan bua
        self.last_transcript_whisper_only = True
        return whisper_text

    def _transcribe_whisper(self, audio: sr.AudioData, google_candidate: str = "", vad: bool = False) -> str:
        model = self.whisper_model   # giu tham chieu: bo nha luc ranh co the dat self.whisper_model = None
        if model is None:
            raise sr.UnknownValueError()
        self.whisper_last_used = time.time()
        wav_data = audio.get_wav_data()
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            try:
                tmp.write(wav_data)
                tmp.close()
                if self.whisper_backend == "faster":
                    segments, info = model.transcribe(
                        tmp.name,
                        language="vi",
                        beam_size=5,
                        vad_filter=vad,
                        condition_on_previous_text=False,
                        temperature=0,
                    )
                    whisper_text = strip_whisper_hallucinations(
                        clean_transcript(" ".join(segment.text.strip() for segment in segments))
                    )
                    log(
                        f"faster-whisper language={getattr(info, 'language', 'n/a')} | "
                        f"prob={getattr(info, 'language_probability', 0):.2f} | text={whisper_text[:80]}"
                    )
                    if not whisper_text:
                        raise sr.UnknownValueError()
                    return whisper_text

                result = model.transcribe(
                    tmp.name,
                    language="vi",
                    task="transcribe",
                    fp16=False,
                    condition_on_previous_text=False,
                    temperature=0,
                    beam_size=5,
                    best_of=5,
                    no_speech_threshold=0.75,
                    logprob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                )
                # Ignore likely Whisper hallucination when it is not confident that speech exists.
                segments = result.get("segments", [])
                if segments:
                    avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
                    log(f"whisper no_speech_prob={avg_no_speech:.2f}")
                    if avg_no_speech > 0.75:
                        raise sr.UnknownValueError()
                elif not result["text"].strip():
                    raise sr.UnknownValueError()
                whisper_raw = str(result["text"])
                whisper_text = strip_whisper_hallucinations(clean_transcript(whisper_raw))
                if whisper_text and whisper_text != whisper_raw.strip():
                    log(f"cleanup | raw={whisper_raw[:100]} | clean={whisper_text[:100]}")
                return whisper_text
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        except Exception as exc:
            if google_candidate:
                log(f"whisper fallback failed; keeping google text | {type(exc).__name__}: {exc}")
                return google_candidate
            raise

    def listen_worker(self, auto_stop_after_phrase: bool = False, session_id: int = 0) -> None:
        target_hwnd = self.active_target_hwnd or self.last_target_hwnd
        target_point = self.active_target_point or self.last_click_point
        session_mode = self.session_mode
        listen_started = time.monotonic()
        last_activity_at = listen_started
        stop_reason = "completed"
        audio_frames: list[bytes] = []
        pre_roll: list[bytes] = []
        speech_started = False
        speech_started_at = 0.0
        capture_finished_at = listen_started
        voice_frame_count = 0
        voiced_frames = 0  # so khung co tieng nguoi that (VAD), de phan biet loi noi voi tieng dong
        chunk_size = 1024
        sample_rate = 16000
        sample_width = 2
        particle_result_scheduled = False
        try:
            with self.microphone_source_context(session_id) as (source, mic_index, mic_name):
                self.recognizer.energy_threshold = 120
                self.recognizer.dynamic_energy_threshold = False
                self.recognizer.pause_threshold = 1.2
                self.recognizer.non_speaking_duration = 0.55
                sample_rate = source.SAMPLE_RATE
                sample_width = source.SAMPLE_WIDTH
                chunk_size = source.CHUNK
                voice_vad = create_voice_vad(sample_rate, sample_width)

                log(
                    f"mic open | session={session_id} | index={mic_index} | "
                    f"name={mic_name} | energy={self.recognizer.energy_threshold:.0f} | "
                    f"sample_rate={sample_rate} | vad={'webrtc@16000' if voice_vad else 'rms'}"
                )

                # Measure noise briefly so speech right after activation is not treated as background.
                noise_until = time.monotonic() + 0.2
                noise_samples: list[int] = []
                while time.monotonic() < noise_until and not self.stop_requested:
                    data = read_audio_chunk(source.stream, source.CHUNK)
                    noise_samples.append(audioop.rms(data, source.SAMPLE_WIDTH))
                speech_threshold, activity_threshold, noise_floor, noise_p90 = calculate_vad_threshold(noise_samples)
                webrtc_rms_gate = calculate_webrtc_rms_gate(noise_floor, speech_threshold)
                log(
                    f"rms vad ready | session={session_id} | noise={noise_floor} | "
                    f"p90={noise_p90} | speech_threshold={speech_threshold} | "
                    f"activity_threshold={activity_threshold} | webrtc_rms_gate={webrtc_rms_gate}"
                )

                while not self.stop_requested:
                    data = read_audio_chunk(source.stream, source.CHUNK)
                    rms = audioop.rms(data, source.SAMPLE_WIDTH)
                    vad_voice = vad_detects_speech(voice_vad, data, sample_width)
                    now = time.monotonic()
                    level_floor = max(1, noise_floor)
                    level_span = max(250, speech_threshold * 2)
                    self.audio_level_target = max(0.04, min(1.0, (rms - level_floor) / level_span))
                    if vad_voice is not None:
                        rms_voice = rms >= activity_threshold
                        strong_rms_voice = rms >= speech_threshold
                        start_voice = (bool(vad_voice) and rms >= webrtc_rms_gate) or strong_rms_voice
                        active_voice = (bool(vad_voice) and rms >= webrtc_rms_gate) or rms_voice
                    else:
                        start_voice = rms >= speech_threshold
                        active_voice = rms >= activity_threshold
                    soft_activity_threshold = max(
                        int(noise_floor * VAD_SOFT_ACTIVITY_MULTIPLIER),
                        noise_floor + VAD_SOFT_ACTIVITY_MARGIN,
                    )
                    soft_voice = speech_started and rms >= soft_activity_threshold
                    if (speech_started or start_voice) and (
                        (bool(vad_voice) and rms >= webrtc_rms_gate) if vad_voice is not None else rms >= speech_threshold
                    ):
                        voiced_frames += 1

                    if start_voice:
                        voice_frame_count += 1
                        if not speech_started and voice_frame_count >= VOICE_START_FRAMES:
                            speech_started = True
                            speech_started_at = now
                            audio_frames.extend(pre_roll)
                            pre_roll.clear()
                            last_activity_at = now
                            self.root.after(0, lambda sid=session_id: self.show_hud("listen", f"\u0110ang nghe #{sid}", None))
                            log(
                                f"voice start | session={session_id} | rms={rms} | "
                                f"speech_threshold={speech_threshold} | webrtc_rms_gate={webrtc_rms_gate} | vad={vad_voice}"
                            )
                        if speech_started:
                            audio_frames.append(data)
                            last_activity_at = now
                    else:
                        voice_frame_count = 0
                        if speech_started:
                            audio_frames.append(data)
                            if active_voice or soft_voice:
                                last_activity_at = now
                        else:
                            pre_roll.append(data)
                            if len(pre_roll) > 6:
                                pre_roll.pop(0)

                    if not speech_started and now - listen_started > INITIAL_NO_SPEECH_TIMEOUT_SECONDS:
                        stop_reason = "no-speech"
                        log(f"vad: initial no speech timeout | id={session_id}")
                        break
                    capture_age = now - speech_started_at
                    if capture_age >= LONG_VOICE_AFTER_SECONDS:
                        trailing_timeout = WEBRTC_VOICE_END_SECONDS if voice_vad else RMS_VOICE_END_SECONDS
                    else:
                        trailing_timeout = WEBRTC_SHORT_VOICE_END_SECONDS if voice_vad else RMS_SHORT_VOICE_END_SECONDS
                    silence_age = now - last_activity_at
                    can_auto_stop = (
                        now - speech_started_at >= MIN_CAPTURE_BEFORE_AUTO_STOP_SECONDS
                        and (
                            capture_age >= MIN_CAPTURE_BEFORE_SILENCE_STOP_SECONDS
                            or silence_age >= max(trailing_timeout, 2.0)
                        )
                    )
                    if speech_started and can_auto_stop and silence_age > trailing_timeout:
                        stop_reason = "silence"
                        log(
                            f"auto stop after trailing silence | id={session_id} | "
                            f"timeout={trailing_timeout:.1f}s | age={capture_age:.1f}s | "
                            f"last_rms={rms} | soft_threshold={soft_activity_threshold} | "
                            f"frames={len(audio_frames)}"
                        )
                        break
                    if auto_stop_after_phrase and now - listen_started > AUTO_PHRASE_LIMIT_SECONDS:
                        stop_reason = "max-time"
                        log(f"vad: max phrase time | frames={len(audio_frames)}")
                        break
                capture_finished_at = time.monotonic()
                self.audio_level_target = 0.0

            self.listening = False
            self.capture_clicks = False
            self.processing = bool(audio_frames)
            log(
                f"capture complete | id={session_id} | frames={len(audio_frames)} | "
                f"reason={stop_reason} | processing={self.processing}"
            )

            if self.stop_requested and audio_frames:
                stop_reason = self.stop_reason or "requested"
                capture_finished_at = time.monotonic()
                log(f"finish requested; transcribing captured audio | id={session_id} | frames={len(audio_frames)}")

            if self.discard_session_id == session_id:
                # phien bi huy vi anh Alt + bam dup de mo tro chuyen
                self.discard_session_id = 0
                log(f"session discarded | id={session_id} | frames={len(audio_frames)}")
                return

            if session_mode == "conversation":
                conversation = self.conversation
                if conversation is None or not conversation.active:
                    log(f"voice chat listen discarded: conversation ended | id={session_id}")
                    return
                if not audio_frames:
                    log(f"voice chat silence | id={session_id} | reason={stop_reason}")
                    conversation.handle_silence()
                    return

            if not audio_frames:
                self.root.after(0, lambda: self.draw("idle"))
                self.root.after(0, lambda r=stop_reason: self.show_hud("done", f"D\u1eebng: {r}", 900))
                self.root.after(900, self.hide_hud)
                self.root.after(900, self.root.withdraw)
                log(f"session stopped | id={session_id} | frames=0 | hwnd={target_hwnd} | reason={stop_reason}")
                return

            t_api = time.monotonic()
            self.session_voiced_seconds = voiced_frames * chunk_size / max(1, sample_rate)
            self.root.after(0, lambda: self.draw("busy"))
            self.root.after(0, lambda sid=session_id: self.show_hud("busy", f"\u0110ang nh\u1eadn di\u1ec7n #{sid}", None))
            audio = sr.AudioData(b"".join(audio_frames), sample_rate, sample_width)
            log(
                f"transcribe start | id={session_id} | reason={stop_reason} | "
                f"frames={len(audio_frames)} | voiced={self.session_voiced_seconds:.2f}s | "
                f"capture_wait={(capture_finished_at - last_activity_at):.2f}s"
            )
            save_last_audio(
                audio,
                {
                    "session_id": session_id,
                    "hwnd": target_hwnd,
                    "reason": stop_reason,
                    "frames": len(audio_frames),
                },
            )
            speech_seconds = max(0.1, capture_finished_at - (speech_started_at or listen_started))
            english_future = None
            if (
                session_mode == "dictation"
                and speech_seconds <= SHORT_COMMAND_MAX_SECONDS
                and bool(self.settings_value("enable_voice_commands", True))
            ):
                # Cau ngan co the la lenh "voice": nghe them mot lan bang tieng Anh, chay song song
                english_future = self.command_pool.submit(google_transcripts, audio, "en-US")
            try:
                final_text = self._transcribe_audio(audio).strip()
            except sr.UnknownValueError:
                final_text = ""
            api_ms = int((time.monotonic() - t_api) * 1000)

            command = self.voice_command(final_text) if session_mode == "dictation" and final_text else None
            if command is None and english_future is not None:
                try:
                    english_candidates = english_future.result(timeout=8)
                except Exception:
                    english_candidates = []
                # cac cach nghe du phong cua Google tieng Viet, roi den luot nghe tieng Anh
                for candidate in [*self.last_google_alternatives[1:], *english_candidates]:
                    command = self.voice_command(candidate)
                    if command:
                        log(f"voice command from alternate hearing | id={session_id} | heard={candidate} | vi={final_text}")
                        final_text = candidate
                        break
            if not final_text:
                raise sr.UnknownValueError()

            if command is None and self.last_transcript_whisper_only:
                # Google khong nghe ra, Whisper chi doan duoc vai chu cho ca doan dai: thuong la tieng on
                guessed_words = count_transcript_words(final_text)
                guessed_wpm = guessed_words / (speech_seconds / 60)
                if guessed_words <= 5 and guessed_wpm < 45:
                    log(
                        f"whisper guess rejected | id={session_id} | text={final_text} | "
                        f"words={guessed_words} | wpm={guessed_wpm:.0f}"
                    )
                    raise sr.UnknownValueError()

            if session_mode == "conversation":
                log(f"voice chat heard | id={session_id} | text={final_text}")
                self.root.after(0, self.hide_particle_effect)
                particle_result_scheduled = True
                if self.conversation is not None and self.conversation.active:
                    self.conversation.handle_user_text(final_text)
                return

            if command == "voice":
                log(f"voice command: start conversation | id={session_id} | text={final_text}")
                self.root.after(0, self.hide_particle_effect)
                particle_result_scheduled = True
                self.root.after(0, lambda h=target_hwnd, p=target_point: self.start_voice_conversation(h, p))
                return
            if command == "keep":
                log(f"voice command: keep dictation | id={session_id} | text={final_text}")
                self.root.after(0, self.hide_particle_effect)
                particle_result_scheduled = True
                self.root.after(0, lambda: self.show_hud("listen", "Anh nói đi, em gõ chữ", None))
                self.start_listening_when_free(True, target_hwnd, target_point, "dictation")
                return

            beep_async("done")
            communication_seconds = max(0.1, capture_finished_at - (speech_started_at or listen_started))
            wpm, word_count, char_count, measured_seconds = format_speech_stats(final_text, communication_seconds)
            avg_confidence = (
                sum(self.google_confidence_scores) / len(self.google_confidence_scores)
                if self.google_confidence_scores
                else None
            )
            confidence_text = format_confidence_percent(avg_confidence)
            stats_text = f"{char_count} ký tự · {word_count} từ · {wpm} từ/phút · tin cậy {confidence_text}"
            log(
                f"session transcript | id={session_id} | text={final_text} | api={api_ms}ms | "
                f"frames={len(audio_frames)} | wpm={wpm} | words={word_count} | chars={char_count} | "
                f"duration={measured_seconds:.1f}s | confidence_avg={format_confidence_percent(avg_confidence)}"
            )
            save_last_transcript(
                final_text,
                {
                    "session_id": session_id,
                    "hwnd": target_hwnd,
                    "point": target_point,
                    "reason": stop_reason,
                    "confidence": confidence_text,
                    "duration_seconds": round(measured_seconds, 2),
                    "chars": char_count,
                },
            )
            keep_transcript_on_clipboard(final_text, "recognized")
            # Clipboard/focus work does not require Tk. Run it immediately in
            # the worker so an animation-heavy Tk queue cannot delay delivery.
            self.paste_chunk(final_text, target_hwnd, target_point, click_to_focus=True)
            # hoc tu vung sau khi da dan (truoc day chay truoc, lam chu dan tre ~3 giay)
            threading.Thread(target=self.learn_after_paste, args=(final_text,), daemon=True).start()
            self.remember_voice_target(target_hwnd, target_point)
            particle_result_scheduled = True
            self.root.after(0, lambda t=final_text, s=stats_text, pt=target_point: self.show_particle_result(t, s, pt, RESULT_SHOW_MS))
            self.root.after(RESULT_SHOW_MS, lambda: self.draw("idle"))
            self.root.after(RESULT_SHOW_MS, self.hide_hud)
            self.root.after(RESULT_SHOW_MS, self.root.withdraw)
            log(
                f"session done | id={session_id} | frames={len(audio_frames)} | hwnd={target_hwnd} | "
                f"reason={stop_reason} | stats={stats_text}"
            )
        except Exception as exc:
            log(f"session error | id={session_id} | {type(exc).__name__}: {exc}")
            conversation = self.conversation
            if session_mode == "conversation" and conversation is not None and conversation.active:
                # tro chuyen: nghe khong ro thi tro ly hoi lai, khong bao loi
                conversation.handle_unclear()
                return
            beep_async("error")
            self.root.after(0, lambda: self.draw("error"))
            self.root.after(0, lambda: self.show_hud("error", "Th\u1eed l\u1ea1i g\u1ea7n micro h\u01a1n", 1200))
            self.root.after(700, lambda: self.draw("idle"))
            self.root.after(1300, self.hide_hud)
            self.root.after(1300, self.root.withdraw)
        finally:
            if not particle_result_scheduled:
                self.root.after(0, self.hide_particle_effect)
            self.capture_clicks = False
            self.stop_requested = False
            self.listening = False
            self.processing = False
            self.active_target_hwnd = 0
            self.active_target_point = None

    def learn_after_paste(self, text: str) -> None:
        try:
            with self.learn_lock:
                learn_context_terms(text)
        except Exception as exc:
            log(f"context learn error: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ che do tro chuyen (lenh "voice")
    def voice_command(self, text: str) -> str | None:
        if not bool(self.settings_value("enable_voice_commands", True)):
            return None
        try:
            from reader.assistant import detect_command
        except Exception as exc:
            log(f"voice command unavailable: {type(exc).__name__}: {exc}")
            return None
        return detect_command(text)

    def start_listening_when_free(
        self, auto_stop: bool, target_hwnd: int, target_point: tuple[int, int] | None, mode: str, tries: int = 0
    ) -> None:
        """Phien nghe cu co the chua don xong; doi mot chut roi moi mo phien moi."""
        def attempt() -> None:
            if self.listening or self.processing:
                if tries < 60:
                    self.start_listening_when_free(auto_stop, target_hwnd, target_point, mode, tries + 1)
                return
            if mode == "conversation" and (self.conversation is None or not self.conversation.active):
                return
            self.start_listening(auto_stop_after_phrase=auto_stop, target_hwnd=target_hwnd,
                                 target_point=target_point, mode=mode)
        self.root.after(0 if tries == 0 else 100, attempt)

    def start_voice_conversation(self, target_hwnd: int, target_point: tuple[int, int] | None) -> None:
        if self.conversation is not None:
            return
        try:
            from reader.assistant import Conversation
        except Exception as exc:
            log(f"voice chat import error: {type(exc).__name__}: {exc}")
            self.show_hud("error", "Chưa bật được voice", 1800)
            return

        def on_state(state: str, message: str) -> None:
            self.root.after(0, lambda: (self.draw("busy"), self.show_hud(state, message, None)))

        def listen_again() -> None:
            self.start_listening_when_free(True, target_hwnd, target_point, "conversation")

        def on_end() -> None:
            self.root.after(0, self.end_voice_conversation_ui)

        self.conversation = Conversation(self.settings, on_state, listen_again, on_end, log)
        log(f"voice chat start | hwnd={target_hwnd} | point={target_point}")
        self.conversation.start()

    # ------------------------------------------------------------ vong tron chon che do
    def handle_alt_press(self, point: tuple[int, int]) -> None:
        """Alt + click: dang doc/noi thi dieu khien phien do, con lai hien vong tron chon che do."""
        if self.listening:
            self.request_stop("alt-click")
            log(f"alt-click stops listening | session={self.active_session_id} | point={point}")
            return
        if self.processing:
            log(f"alt-click ignored: session processing | point={point}")
            return
        conversation = self.conversation
        if conversation is not None and conversation.active:
            if conversation.paused:
                log("voice chat resumed by alt-click")
                conversation.resume()
            elif conversation.speaking:
                conversation.interrupt()
                log("voice chat interrupted by alt-click")
            return
        if self.reading is not None:
            self.reading.toggle_pause()
            log("read aloud toggled by alt-click")
            return
        hwnd = foreground_window()
        if not hwnd or hwnd in {self.app_hwnd, self.hud_hwnd, self.particle_hwnd, self.radial_hwnd}:
            return
        if not bool(self.settings_value("enable_radial_menu", True)):
            self.try_alt_click_listen_from_click(point)
            return
        self.radial_target_hwnd = hwnd
        self.radial_dragging = True  # neu anh giu chuot keo toi o roi tha thi chon luon
        self.open_radial_menu(point)

    def point_in_radial(self, point: tuple[int, int]) -> bool:
        return math.hypot(point[0] - self.radial_center[0], point[1] - self.radial_center[1]) <= RADIAL_OUTER + 4

    def open_radial_menu(self, point: tuple[int, int]) -> None:
        self.radial_open = True
        self.radial_closing = False
        self.radial_choice = None
        self.radial_anchor = point
        self.radial_opened_at = time.monotonic()
        self.radial_press_inside = False
        self.radial_hover = {key: 0.0 for key, *_rest in RADIAL_OPTIONS}
        screen_left, screen_top, screen_right, screen_bottom = virtual_screen_rect()
        half = RADIAL_SIZE // 2
        x = max(screen_left, min(point[0] - half, screen_right - RADIAL_SIZE))
        y = max(screen_top, min(point[1] - half, screen_bottom - RADIAL_SIZE))
        self.radial_center = (x + half, y + half)
        self.radial.geometry(f"{RADIAL_SIZE}x{RADIAL_SIZE}+{x}+{y}")
        try:
            self.radial.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.draw_radial_menu()
        self.radial.deiconify()
        self.radial.lift()
        AUDIO_DEVICES.prewarm()  # lam moi danh sach mic trong luc anh dang chon o
        self.prefetch_voice_brain()  # co san trong cache thi khong ton gi
        beep_async("chunk")
        log(f"radial menu open | point={point}")
        if not getattr(self, "radial_animating", False):
            self.radial_animating = True
            self.root.after(RADIAL_FRAME_MS, self.animate_radial_menu)

    def animate_radial_menu(self) -> None:
        """Vong lap ve hieu ung khi vong tron dang mo hoac dang dong."""
        if not self.radial_open and not self.radial_closing:
            self.radial_animating = False
            return
        now = time.monotonic()
        if self.radial_closing:
            progress = (now - self.radial_closed_at) / RADIAL_CLOSE_SECONDS
            if progress >= 1:
                self.radial_closing = False
                self.radial_animating = False
                self.radial.withdraw()
                return
        for key in self.radial_hover:
            target = 1.0 if key == self.radial_choice else 0.0
            self.radial_hover[key] += (target - self.radial_hover[key]) * 0.32
        try:
            self.radial.attributes("-alpha", 0.97 * self.radial_visibility())
        except tk.TclError:
            pass
        self.draw_radial_menu()
        self.root.after(RADIAL_FRAME_MS, self.animate_radial_menu)

    def radial_visibility(self) -> float:
        """0..1: muc hien cua vong tron (luc hien len va luc dong lai)."""
        now = time.monotonic()
        if getattr(self, "radial_closing", False):
            t = min(1.0, (now - self.radial_closed_at) / RADIAL_CLOSE_SECONDS)
            return 1 - t * t
        t = min(1.0, (now - getattr(self, "radial_opened_at", now)) / RADIAL_OPEN_SECONDS)
        return 1 - (1 - t) ** 3

    def point_in_radial(self, point: tuple[int, int]) -> bool:
        return math.hypot(point[0] - self.radial_center[0], point[1] - self.radial_center[1]) <= RADIAL_OUTER + 4

    def update_radial_menu(self, point: tuple[int, int]) -> None:
        dx = point[0] - self.radial_center[0]
        dy = self.radial_center[1] - point[1]
        distance = math.hypot(dx, dy)
        choice: str | None = None
        if RADIAL_INNER - 4 < distance <= RADIAL_OUTER + 60:
            angle = math.degrees(math.atan2(dy, dx)) % 360
            for key, _label, _sub, start in RADIAL_OPTIONS:
                if (angle - start) % 360 < 90:
                    choice = key
                    break
        if choice != self.radial_choice:
            if choice is not None:
                beep_async("tick")
            self.radial_choice = choice  # vong lap hieu ung se ve lai

    def close_radial_menu(self, reason: str = "") -> None:
        was_open = self.radial_open
        self.radial_open = False
        self.radial_press_inside = False
        self.radial_dragging = False
        if was_open and reason.startswith("choice"):
            # chon xong: thu nho + mo di trong tich tac, lua chon van chay ngay
            self.radial_closing = True
            self.radial_closed_at = time.monotonic()
            if not getattr(self, "radial_animating", False):
                self.radial_animating = True
                self.root.after(RADIAL_FRAME_MS, self.animate_radial_menu)
        else:
            self.radial_closing = False
            self.radial.withdraw()
            self.radial.update_idletasks()
        if reason and not reason.startswith("choice"):
            log(f"radial menu closed | reason={reason}")

    def draw_radial_menu(self) -> None:
        canvas = self.radial_canvas
        canvas.delete("all")
        visibility = MicIconApp.radial_visibility(self) if hasattr(self, "radial_opened_at") else 1.0
        hover = getattr(self, "radial_hover", None) or {
            key: (1.0 if key == self.radial_choice else 0.0) for key, *_rest in RADIAL_OPTIONS
        }
        closing = getattr(self, "radial_closing", False)
        scale = (0.72 + 0.28 * visibility) if not closing else (0.86 + 0.14 * visibility)
        c = RADIAL_SIZE / 2
        r_out, r_in = RADIAL_OUTER * scale, RADIAL_INNER * scale
        tick = time.monotonic()

        # nen vong tron
        canvas.create_oval(c - r_out - 2, c - r_out - 2, c + r_out + 2, c + r_out + 2, fill="#0b1220", outline="#334155", width=1)

        # cac o: o dang tro phong ra, chuyen mau cam muot, co vien sang
        for key, label, sub, start in RADIAL_OPTIONS:
            h = hover.get(key, 0.0)
            radius = r_out + h * 6
            fill = mix_color(RADIAL_IDLE, RADIAL_ACTIVE, h)
            canvas.create_arc(c - radius, c - radius, c + radius, c + radius, start=start + 2, extent=86,
                              style="pieslice", fill=fill, outline="")
            if h > 0.05:
                glow = radius + 3
                canvas.create_arc(c - glow, c - glow, c + glow, c + glow, start=start + 4, extent=82,
                                  style="arc", outline=mix_color("#0b1220", RADIAL_GLOW, h), width=2)
            angle = math.radians(start + 45)
            text_radius = (r_out + r_in) / 2 + 3 + h * 3
            tx, ty = c + text_radius * math.cos(angle), c - text_radius * math.sin(angle)
            canvas.create_text(tx, ty - (6 if sub else 0), text=label, fill=mix_color("#d5dde8", "#ffffff", h),
                               font=("Segoe UI", 9 if h < 0.5 else 10, "bold"))
            if sub:
                canvas.create_text(tx, ty + 8, text=sub, fill=mix_color("#7f8ca1", "#ffedd5", h), font=("Segoe UI", 7))

        # cham sang chay quanh vanh (kem vet mo dan)
        orbit = r_out + 2
        base = (tick * 2.2) % math.tau
        for step in range(5):
            a = base - step * 0.09
            dot = 2.6 - step * 0.45
            px, py = c + orbit * math.cos(a), c - orbit * math.sin(a)
            canvas.create_oval(px - dot, py - dot, px + dot, py + dot,
                               fill=mix_color(RADIAL_GLOW, "#0b1220", step / 5), outline="")

        # tam: vien nhip tho, sang cam khi dang chon
        any_hover = max(hover.values()) if hover else 0.0
        breath = (math.sin(tick * 4.2) + 1) / 2
        ring = mix_color("#475569", RADIAL_GLOW, max(any_hover, breath * 0.35))
        canvas.create_oval(c - r_in, c - r_in, c + r_in, c + r_in, fill="#0b1220", outline=ring, width=2 if any_hover > 0.5 else 1)
        center_label = {"dictation": "Gõ chữ", "reader": "Đọc", "chat": "Nói", "cancel": "Huỷ"}.get(self.radial_choice, "Chọn")
        canvas.create_text(c, c - 4, text=center_label, fill="#f8fafc", font=("Segoe UI", 8, "bold"))
        canvas.create_text(c, c + 8, text="thả để chọn" if self.radial_choice else "Esc huỷ", fill="#7f8ca1",
                           font=("Segoe UI", 6))

    def run_radial_choice(self, choice: str | None, point: tuple[int, int]) -> None:
        log(f"radial menu choice | choice={choice} | point={point}")
        if choice in (None, "dictation"):
            # giu nguyen: noi thanh chu vao khung chat
            self.start_dictation_from_radial(point)
        elif choice == "chat":
            self.start_voice_conversation(self.radial_target_hwnd or foreground_window(), point)
        elif choice == "reader":
            target = self.radial_target_hwnd
            threading.Thread(target=self.read_selection_worker, args=(target,), daemon=True).start()
        else:
            self.show_hud("done", "Đã huỷ", 700)

    # ------------------------------------------------------------ "Doc": doc to doan anh boi den / vua copy
    def grab_text_for_reading(self, target_hwnd: int) -> bool:
        """Lay doan anh boi den (gui Ctrl+C) hoac doan anh vua copy. Tra ve True neu clipboard co noi dung cua anh."""
        before = clipboard_sequence()
        if target_hwnd and window_exists(target_hwnd) and foreground_window() == target_hwnd:
            keybd(VK_CONTROL)
            keybd(VK_C)
            keybd(VK_C, KEYEVENTF_KEYUP)
            keybd(VK_CONTROL, KEYEVENTF_KEYUP)
            for _ in range(8):
                time.sleep(0.05)
                if clipboard_sequence() != before:
                    break
        now = clipboard_sequence()
        if now != before:
            log("read aloud source: selection")
            return bool(get_clipboard_text().strip())
        if now != LAST_OWN_CLIPBOARD_SEQ[0] and get_clipboard_text().strip():
            log("read aloud source: clipboard")
            return True
        return False

    def read_selection_worker(self, target_hwnd: int) -> None:
        def hud(state: str, message: str, ms: int | None = None) -> None:
            self.root.after(0, lambda: self.show_hud(state, message, ms))

        try:
            if not self.grab_text_for_reading(target_hwnd):
                hud("error", "Bôi đen hoặc copy đoạn cần nghe trước", 2600)
                log("read aloud: nothing selected or copied; opening doc reader")
                self.root.after(2700, self.open_doc_reader)  # mo Tro ly doc de anh dan hoac keo file vao
                return
            hud("busy", "Đang chuẩn bị đọc...", None)
            doc = reader_import_clipboard()
        except Exception as exc:
            log(f"read aloud prepare error: {type(exc).__name__}: {exc}")
            reason = str(exc) if isinstance(exc, RuntimeError) and str(exc) else "thử lại"
            hud("error", f"Chưa đọc được: {reason}", 3500)
            return
        blocks = doc.get("blocks", [])
        sentences = [s["t"] for s in doc.get("sentences", []) if blocks[s["b"]]["type"] != "code"]
        log(f"read aloud start | doc={doc.get('id')} | title={str(doc.get('title'))[:60]} | sentences={len(sentences)}")
        hud("speak", f"Đọc: {doc.get('title', '')}", None)
        self.root.after(0, lambda: self.start_read_aloud(sentences))

    def start_read_aloud(self, sentences: list[str]) -> None:
        if self.reading is not None:
            self.reading.stop()
        from reader.assistant import ReadAloud

        def on_state(state: str, message: str) -> None:
            self.root.after(0, lambda: (self.draw("busy"), self.show_hud(state, message, None)))

        def on_end() -> None:
            def done() -> None:
                if self.reading is reader:
                    self.reading = None
                self.draw("idle")
                self.show_hud("done", "Đã đọc xong", 900)
                self.root.after(900, self.hide_hud)
            self.root.after(0, done)

        reader = ReadAloud(sentences, self.settings, on_state, on_end, log)
        self.reading = reader
        reader.start()

    def open_doc_reader(self) -> None:
        """Chuyen sang Tro ly doc: dua cua so dang mo len truoc, chua mo thi khoi dong."""
        window = find_window_by_title("Trợ lý đọc")
        if window:
            user32.ShowWindow(window, 9)  # SW_RESTORE
            user32.SetForegroundWindow(window)
            self.show_hud("done", "Mở Trợ lý đọc", 900)
            log(f"doc reader focused | hwnd={window}")
            return
        if not getattr(sys, "frozen", False) and not (APP_DIR / "doc_reader.py").exists():
            self.show_hud("error", "Không thấy Trợ lý đọc", 1500)
            log("doc reader missing: doc_reader.py")
            return
        subprocess.Popen(
            doc_reader_command(), cwd=str(APP_DIR),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.show_hud("done", "Đang mở Trợ lý đọc...", 1500)
        log("doc reader launched")

    def toggle_voice_conversation_hotkey(self) -> None:
        if self.reading is not None:
            self.reading.toggle_pause()
            return
        conversation = self.conversation
        if conversation is not None:
            # dang tro chuyen: phim tat de tam dung / noi tiep (tat han bang Esc hoac noi "thoi")
            if conversation.paused:
                log("voice chat hotkey: resume")
                conversation.resume()
            else:
                log("voice chat hotkey: pause")
                if self.listening:
                    self.discard_session_id = self.active_session_id
                    self.request_stop("voice-chat-pause")
                conversation.pause()
            return
        if self.listening:
            # dang doc chu thi bo phien do, chuyen sang tro chuyen
            self.discard_session_id = self.active_session_id
            self.request_stop("voice-chat-hotkey")
        hwnd = foreground_window()
        point = cursor_position()
        log(f"voice chat hotkey: start | hwnd={hwnd} | point={point}")
        self.start_voice_conversation(hwnd, point)

    def end_voice_conversation_ui(self) -> None:
        self.conversation = None
        log("voice chat end")
        if self.listening:
            self.request_stop("voice-chat-end")
        self.draw("idle")
        self.show_hud("done", "Đã tắt voice", 900)
        self.root.after(900, self.hide_hud)
        self.root.after(900, self.root.withdraw)

    def paste_result(self, text: str, target_hwnd: int, target_point: tuple[int, int] | None) -> None:
        try:
            paste_to_focused_field(text, self.root, target_hwnd, target_point, restore_root=False)
        except Exception as exc:
            log(f"paste error: {type(exc).__name__}: {exc}")
            self.draw("error")
            self.root.after(900, lambda: self.draw("idle"))

    def paste_chunk(self, text: str, target_hwnd: int, target_point: tuple[int, int] | None, click_to_focus: bool = True) -> None:
        """Paste má»™t chunk ngay láº­p tá»©c, giá»¯ icon hiá»ƒn thá»‹ Ä‘á»ƒ tiáº¿p tá»¥c nghe."""
        try:
            if target_hwnd and not window_exists(target_hwnd):
                keep_transcript_on_clipboard(text, "target-closed")
                log(f"chunk paste skipped: target window closed | hwnd={target_hwnd} | text={text[:120]}")
                return
            if not set_clipboard_text_retry(text):
                log(f"chunk paste skipped: clipboard busy; text={text[:120]}")
                return
            time.sleep(0.02)
            current_hwnd = foreground_window()
            needs_refocus = click_to_focus or (target_hwnd and current_hwnd != target_hwnd)
            if needs_refocus:
                focused_hwnd = focus_locked_target(target_hwnd, target_point, click_to_focus=True)
            else:
                focused_hwnd = focus_locked_target(target_hwnd, None, click_to_focus=False)
            log(
                f"paste focus | target={target_hwnd} | before={current_hwnd} | "
                f"focused={focused_hwnd} | refocus={needs_refocus} | point={target_point}"
            )
            send_ctrl_v()
            time.sleep(0.02)
            keep_transcript_on_clipboard(text, "after-paste")
            log(f"chunk pasted; transcript kept on clipboard: {text[:60]}")
        except Exception as exc:
            keep_transcript_on_clipboard(text, "paste-error")
            log(f"chunk paste error: {type(exc).__name__}: {exc}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if "--doc-reader" in sys.argv:
        # VoiNoi.exe --doc-reader: chay Tro ly doc (ban .exe khong co python rieng de chay doc_reader.py)
        sys.argv.remove("--doc-reader")
        import doc_reader

        return doc_reader.main()
    if not acquire_single_instance_lock():
        return 0
    MicIconApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
