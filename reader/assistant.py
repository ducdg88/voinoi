"""Tro ly noi chuyen bang giong noi: nghe anh noi (Voice Mic), hoi AI, tra loi bang giong nam.

Bo nao (AI) tu chon theo thu tu: Claude API (neu co ANTHROPIC_API_KEY) -> Claude Code CLI
(neu da dang nhap) -> Ollama chay tren may. Co the ep bang setting "voice_chat_backend".
"""
from __future__ import annotations

import concurrent.futures
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Callable, Iterator

from . import tts
from .store import DATA_DIR, now_text

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_RATE = "+8%"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_PREFERRED = ["qwen2.5:7b", "qwen2.5:14b", "qwen3:8b", "llama3.1:8b", "gemma2:9b", "qwen2.5:3b"]
CLAUDE_MODEL = "claude-opus-5"
MAX_HISTORY_TURNS = 12
GROUP_CHARS = 150  # gop cau cho toi khoang nay ky tu roi moi tao giong
CONVERSATIONS_DIR = DATA_DIR / "conversations"

SYSTEM_PROMPT = """Bạn là trợ lý giọng nói tiếng Việt của anh ấy, giọng nam, xưng "em" và gọi người dùng là "anh".
Mọi câu bạn viết sẽ được đọc to bằng giọng nói, nên hãy nói như đang trò chuyện trực tiếp:
- Trả lời ngắn gọn, thường 2 đến 4 câu. Chỉ nói dài khi anh yêu cầu giải thích kỹ.
- Chỉ dùng câu văn nói bình thường: không markdown, không gạch đầu dòng, không bảng, không emoji, không đọc đường link.
- Không dùng dấu gạch ngang dài. Muốn liệt kê thì nói "thứ nhất, thứ hai".
- Lời anh nói được chuyển từ giọng nói sang chữ nên có thể sai vài từ. Hãy đoán ý hợp lý nhất. Nếu thật sự không hiểu thì hỏi lại một câu ngắn.
- Thân thiện, lễ phép, tự nhiên như một trợ lý người Việt, có thể mở đầu bằng "Dạ" khi phù hợp.
- Nếu không chắc chắn về một thông tin, hãy nói rõ là em không chắc."""

GREETING = "Dạ, em chào anh. Em nghe đây, anh cứ nói nhé."
GOODBYE = "Dạ vâng, em chào anh. Khi nào cần anh cứ gọi em nhé."
ACK = "Dạ."
UNCLEAR = "Em chưa nghe rõ, anh nói lại giúp em nhé."
PAUSED = "Dạ, em chờ anh. Khi nào nói tiếp, anh bấm Alt và click, hoặc Control Alt V nhé."
PAUSED_HUD = "Tạm dừng · Alt+click để nói tiếp"
RESUMED = "Dạ, em nghe đây."
SILENCE_BYE = "Em không nghe thấy anh nói gì nữa, em tạm nghỉ nhé. Cần gì anh cứ gọi em."
NO_BRAIN = ("Em chưa kết nối được với bộ não AI. Anh mở Ollama, hoặc đăng nhập Claude Code trong cửa sổ dòng lệnh, "
            "rồi gọi lại em nhé.")

# ------------------------------------------------------------------ lenh bang giong noi

FILLER_WORDS = {"chuyển", "qua", "sang", "bật", "chế", "độ", "mode", "em", "ơi", "cho", "anh", "đi", "nhé", "nha",
                "vào", "mở", "dùng", "ạ", "à", "với", "tôi", "mình", "luôn", "ok", "okay", "rồi"}
VOICE_WORDS = {
    # tieng Anh (luot nghe bang tieng Anh bat duoc chu nay chuan nhat)
    "voice", "voices", "voice mode", "voice chat", "chat voice", "voice assistant", "talk", "talk mode",
    # cach Google tieng Viet hay nghe nham chu "voice"
    "voi", "vòi", "vôi", "vơi", "vói", "vỏi", "vois", "voiz", "boi", "bồi", "void", "voi xơ", "voi sơ", "vòi xơ",
    "voz", "vos", "voiss",
    # cum tieng Viet, nhan dien chac hon
    "nói chuyện", "trò chuyện", "hội thoại", "giọng nói", "trợ lý", "trợ lý ơi", "gọi trợ lý", "em ơi",
    "nói chuyện với em", "trò chuyện với em", "nói chuyện nào", "trò chuyện nào",
}
KEEP_PHRASES = {"để nguyên", "giữ nguyên", "nhập chữ", "gõ chữ", "đánh chữ", "voice to text", "viết chữ",
                "để nguyên nhé", "bình thường", "gõ", "chép"}
END_PHRASES = {"thôi", "dừng", "dừng lại", "kết thúc", "tạm biệt", "thoát", "tắt", "cảm ơn em", "thôi em",
               "thôi nhé", "stop", "tắt voice", "thoát voice", "hết rồi", "xong rồi", "nghỉ", "nghỉ đi",
               "cám ơn em", "cảm ơn", "cám ơn", "ok thôi", "dừng voice", "bye", "bai bai"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_command(text: str) -> str | None:
    """'voice' = chuyen sang tro chuyen, 'keep' = nghe lai de go chu. None = van ban binh thuong."""
    normalized = _normalize(text)
    words = normalized.split()
    if not words or len(words) > 6:
        return None
    if normalized in KEEP_PHRASES or " ".join(w for w in words if w not in {"em", "anh", "nhé", "nha", "đi"}) in KEEP_PHRASES:
        return "keep"
    core = " ".join(w for w in words if w not in FILLER_WORDS)
    if core in VOICE_WORDS or normalized in VOICE_WORDS:
        return "voice"
    return None


PAUSE_PHRASES = {"tạm dừng", "tạm ngừng", "tạm nghỉ", "dừng chút", "dừng tí", "ngừng chút", "chờ chút", "chờ tí",
                 "chờ đã", "đợi chút", "đợi tí", "đợi đã", "khoan đã", "khoan", "pause", "tạm dừng lại",
                 "chờ anh chút", "đợi anh chút", "chờ anh", "đợi anh", "để anh nghĩ", "để anh xem"}


def is_pause_request(text: str) -> bool:
    normalized = _normalize(text)
    words = normalized.split()
    if not words or len(words) > 6:
        return False
    trimmed = " ".join(w for w in words if w not in {"em", "nhé", "nha", "ạ", "à", "ok", "đi", "một", "cái"})
    return normalized in PAUSE_PHRASES or trimmed in PAUSE_PHRASES


def is_end_request(text: str) -> bool:
    normalized = _normalize(text)
    words = normalized.split()
    if not words or len(words) > 6:
        return False
    if normalized in END_PHRASES:
        return True
    trimmed = " ".join(w for w in words if w not in {"em", "anh", "nhé", "nha", "ạ", "à", "ok", "rồi", "đi"})
    return trimmed in END_PHRASES or trimmed in {"thôi", "dừng", "tắt", "thoát", "nghỉ"}


# ------------------------------------------------------------------ bo nao AI

class BrainUnavailable(Exception):
    pass


class Brain:
    name = "brain"

    def available(self) -> bool:
        return True

    def warm_up(self) -> None:
        return

    def stream_reply(self, history: list[dict]) -> Iterator[str]:
        raise NotImplementedError


class ClaudeApiBrain(Brain):
    name = "Claude API"

    def __init__(self, model: str = CLAUDE_MODEL) -> None:
        self.model = model

    def available(self) -> bool:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def stream_reply(self, history: list[dict]) -> Iterator[str]:
        import anthropic

        client = anthropic.Anthropic()
        try:
            with client.beta.messages.stream(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=history,
                output_config={"effort": "low"},  # tra loi noi chuyen, uu tien nhanh
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
            ) as stream:
                yield from stream.text_stream
        except anthropic.AuthenticationError as exc:
            raise BrainUnavailable("API key Claude không hợp lệ.") from exc
        except anthropic.APIConnectionError as exc:
            raise BrainUnavailable("Không kết nối được Claude API.") from exc


class ClaudeCliBrain(Brain):
    name = "Claude Code"

    def __init__(self) -> None:
        self.exe = self._find_exe()
        self.logged_out = False

    @staticmethod
    def _find_exe() -> str:
        found = shutil.which("claude.exe") or shutil.which("claude") or shutil.which("claude.cmd") or ""
        if found.lower().endswith((".cmd", ".ps1")) or (found and not found.lower().endswith(".exe")):
            # ban cai qua npm: goi thang file exe de tranh loi dau ngoac cua cmd.exe
            exe = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
            if exe.exists():
                return str(exe)
        return found

    def available(self) -> bool:
        if not self.exe or self.logged_out:
            return False
        try:
            result = subprocess.run(
                [self.exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.logged_out = not json.loads(result.stdout or "{}").get("loggedIn", False)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.logged_out = True
        return not self.logged_out

    def stream_reply(self, history: list[dict]) -> Iterator[str]:
        transcript = []
        for message in history[:-1]:
            who = "Anh" if message["role"] == "user" else "Em"
            transcript.append(f"{who}: {message['content']}")
        prompt = (
            ("Đoạn hội thoại trước:\n" + "\n".join(transcript) + "\n\n" if transcript else "")
            + f"Anh vừa nói: {history[-1]['content']}\n\nHãy trả lời anh (chỉ phần em nói)."
        )
        workdir = CONVERSATIONS_DIR
        workdir.mkdir(parents=True, exist_ok=True)
        prompt_file = workdir / "_system-prompt.txt"
        prompt_file.write_text(SYSTEM_PROMPT, encoding="utf-8")
        command = [
            self.exe, "-p", "--output-format", "text", "--tools", "", "--strict-mcp-config",
            "--no-session-persistence", "--effort", "low", "--system-prompt-file", str(prompt_file),
        ]
        try:
            result = subprocess.run(
                command, input=prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=120, cwd=str(workdir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrainUnavailable(f"Claude Code không chạy được: {exc}") from exc
        output = (result.stdout or "").strip()
        if "not logged in" in output.lower() or "/login" in output or (result.returncode and not output):
            self.logged_out = True
            raise BrainUnavailable("Claude Code chưa đăng nhập.")
        yield output


class OllamaBrain(Brain):
    name = "Ollama"

    def __init__(self, model: str = "") -> None:
        self.model = model
        self._checked = False

    def _pick_model(self) -> str:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as response:
            models = [m["name"] for m in json.load(response).get("models", [])]
        chat_models = [m for m in models if not re.search(r"embed|bge|nomic|minilm", m, re.IGNORECASE)]
        if self.model and self.model in models:
            return self.model
        for preferred in OLLAMA_PREFERRED:
            if preferred in chat_models:
                return preferred
        if chat_models:
            return chat_models[0]
        raise BrainUnavailable("Ollama chưa có model trò chuyện nào.")

    def available(self) -> bool:
        try:
            self.model = self._pick_model()
            self.name = f"Ollama {self.model}"
            return True
        except Exception:
            return False

    def warm_up(self) -> None:
        # nap model vao card do hoa truoc, lan hoi dau khong phai cho
        body = json.dumps({"model": self.model, "messages": [], "keep_alive": "20m"}).encode()
        request = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=180).read()
        except Exception:
            pass

    def stream_reply(self, history: list[dict]) -> Iterator[str]:
        body = json.dumps({
            "model": self.model,
            "stream": True,
            "keep_alive": "20m",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history],
            "options": {"temperature": 0.6},
        }).encode()
        request = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                for line in response:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except OSError as exc:
            raise BrainUnavailable(f"Không gọi được Ollama: {exc}") from exc


def pick_brain(preference: str = "auto", ollama_model: str = "") -> Brain | None:
    candidates: list[Brain] = []
    if preference in ("auto", "claude-api"):
        candidates.append(ClaudeApiBrain())
    if preference in ("auto", "claude-cli"):
        candidates.append(ClaudeCliBrain())
    if preference in ("auto", "ollama"):
        candidates.append(OllamaBrain(ollama_model))
    for brain in candidates:
        if brain.available():
            return brain
    return None


# ------------------------------------------------------------------ phat am thanh (Windows MCI)

_winmm = ctypes.WinDLL("winmm")
_winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
_alias_counter = 0
_alias_lock = threading.Lock()


def _mci(command: str) -> str:
    buffer = ctypes.create_unicode_buffer(128)
    _winmm.mciSendStringW(command, buffer, 127, None)
    return buffer.value


def play_mp3(path: Path, stop_event: threading.Event) -> None:
    global _alias_counter
    with _alias_lock:
        _alias_counter += 1
        alias = f"vmchat{_alias_counter}"
    _mci(f'open "{path}" type mpegvideo alias {alias}')
    try:
        _mci(f"play {alias}")
        started = time.monotonic()
        seen_playing = False
        while not stop_event.is_set():
            mode = _mci(f"status {alias} mode")
            if mode == "playing":
                seen_playing = True
            elif seen_playing or time.monotonic() - started > 2.0:
                break
            time.sleep(0.04)
    finally:
        _mci(f"close {alias}")


# ------------------------------------------------------------------ tach cau khi AI dang tra loi

SENTENCE_BREAK = re.compile(r"(.+?[.!?…]+[\"”')\]]*)(\s+|$)", re.DOTALL)


ACK_PREFIX = re.compile(r"^\s*(dạ\s*vâng|dạ|vâng)\s*[,.!]?\s*", re.IGNORECASE)


def sentences_from_stream(chunks: Iterator[str], strip_ack: bool = False) -> Iterator[str]:
    buffer = ""
    first = True
    for chunk in chunks:
        buffer += chunk
        if strip_ack and len(buffer) > 6:
            # da noi "Da" truoc roi, bo "Da," o dau cau tra loi cho khoi lap
            stripped = ACK_PREFIX.sub("", buffer, count=1)
            buffer = stripped[:1].upper() + stripped[1:] if stripped != buffer else buffer
            strip_ack = False
        while True:
            if first:
                # cau dau: cat som o dau phay de co tieng nhanh hon
                cut = buffer.find(", ", 28)
                end = SENTENCE_BREAK.match(buffer)
                if cut > 0 and (not end or end.end(1) > cut):
                    yield buffer[: cut + 1].strip()
                    buffer = buffer[cut + 2:]
                    first = False
                    continue
            match = SENTENCE_BREAK.match(buffer)
            if match and len(match.group(1).strip()) >= 12 and match.group(2):
                yield match.group(1).strip()
                buffer = buffer[match.end():]
                first = False
                continue
            if "\n" in buffer.strip():
                line, _, rest = buffer.strip().partition("\n")
                if line.strip():
                    yield line.strip()
                buffer = rest
                continue
            if len(buffer) > 220:
                cut = buffer.rfind(",", 60, 200)
                if cut > 0:
                    yield buffer[: cut + 1].strip()
                    buffer = buffer[cut + 1:]
                    continue
            break
    if buffer.strip():
        yield buffer.strip()


def clean_spoken(text: str) -> str:
    text = re.sub(r"[*_#`>|]+", " ", text)
    text = re.sub(r"^\s*([-•]|\d+[.)])\s+", "", text)
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------------ cuoc tro chuyen

class Conversation:
    """Dieu phoi mot phien noi chuyen. Voice Mic lo phan nghe, lop nay lo phan nghi va noi."""

    def __init__(
        self,
        settings: dict,
        on_state: Callable[[str, str], None],
        listen_again: Callable[[], None],
        on_end: Callable[[], None],
        log: Callable[[str], None] = lambda _m: None,
    ) -> None:
        self.voice = str(settings.get("voice_chat_voice") or DEFAULT_VOICE)
        self.rate = str(settings.get("voice_chat_rate") or DEFAULT_RATE)
        self.preference = str(settings.get("voice_chat_backend") or "auto")
        self.ollama_model = str(settings.get("voice_chat_ollama_model") or "")
        self.on_state = on_state
        self.listen_again = listen_again
        self.on_end = on_end
        self.log = log
        self.history: list[dict] = []
        self.brain: Brain | None = None
        self.active = True
        self.speaking = False
        self.thinking = False
        self.unclear_count = 0
        self.paused = False
        self.stop_event = threading.Event()
        self._synth_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="chat-tts")
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.transcript_file = CONVERSATIONS_DIR / f"{time.strftime('%Y-%m-%d_%H%M%S')}.md"
        self._write(f"# Trò chuyện bằng giọng nói, {now_text()}\n")

    # -------------------------------------------------------------- tien ich
    def _write(self, line: str) -> None:
        try:
            with self.transcript_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def _run(self, target: Callable[[], None]) -> None:
        threading.Thread(target=target, daemon=True, name="voice-chat").start()

    def speak(self, sentences: Iterator[str] | list[str]) -> str:
        """Doc lan luot tung cau; cau sau duoc tao giong truoc trong luc cau truoc dang phat."""
        self.stop_event.clear()
        pending: "queue.Queue[concurrent.futures.Future | None]" = queue.Queue()
        spoken: list[str] = []

        def submit(text: str) -> None:
            spoken.append(text)
            pending.put(self._synth_pool.submit(tts.synthesize_to_file, text, self.voice, True, self.rate))

        def producer() -> None:
            # cau dau doc ngay cho nhanh; cac cau sau gop 2, 3 cau mot luot de giong len xuong tu nhien
            group: list[str] = []
            first = True
            try:
                for sentence in sentences:
                    if self.stop_event.is_set():
                        break
                    sentence = clean_spoken(sentence)
                    if not re.search(r"\w", sentence):
                        continue
                    if first:
                        submit(sentence)
                        first = False
                        continue
                    group.append(sentence)
                    if sum(len(item) for item in group) >= GROUP_CHARS:
                        submit(" ".join(group))
                        group = []
                if group and not self.stop_event.is_set():
                    submit(" ".join(group))
            except BrainUnavailable as exc:
                pending.put(exc)  # type: ignore[arg-type]
            except Exception as exc:  # loi mang giua chung
                self.log(f"voice chat stream error: {type(exc).__name__}: {exc}")
                pending.put(exc)  # type: ignore[arg-type]
            finally:
                pending.put(None)

        threading.Thread(target=producer, daemon=True).start()
        self.speaking = True
        first = True
        error: Exception | None = None
        try:
            while True:
                item = pending.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    error = item
                    continue
                try:
                    path = item.result(timeout=60)
                except Exception as exc:
                    self.log(f"voice chat tts error: {type(exc).__name__}: {exc}")
                    continue
                if self.stop_event.is_set():
                    continue
                if first:
                    self.on_state("speak", "Em đang trả lời...")
                    first = False
                play_mp3(path, self.stop_event)
        finally:
            self.speaking = False
        if error and not spoken:
            raise error
        return " ".join(spoken)

    # -------------------------------------------------------------- vong doi
    def start(self) -> None:
        def worker() -> None:
            self.on_state("speak", "Chế độ trò chuyện")
            self.brain = pick_brain(self.preference, self.ollama_model)
            if self.brain:
                self.log(f"voice chat brain: {self.brain.name}")
                threading.Thread(target=self.brain.warm_up, daemon=True).start()
            self._write(f"_Bộ não: {self.brain.name if self.brain else 'chưa có'}_\n")
            self._synth_pool.submit(self._ack_path)  # lam san tieng "Da" de phat ngay khi anh noi xong
            self.speak([GREETING if self.brain else NO_BRAIN])
            if not self.brain:
                self.finish()
                return
            self._continue()
        self._run(worker)

    def _ack_path(self) -> Path | None:
        try:
            return tts.synthesize_to_file(ACK, self.voice, False, self.rate)
        except Exception:
            return None

    def _continue(self) -> None:
        if self.active and not self.paused:
            self.listen_again()

    def pause(self, announce: bool = True) -> None:
        """Tam dung: thoi nghe, ngat loi dang noi, nhung van giu cuoc tro chuyen de noi tiep."""
        if not self.active or self.paused:
            return
        self.paused = True
        self.stop_event.set()
        self._write("_Tạm dừng_\n")
        self.on_state("speak", PAUSED_HUD)

        def worker() -> None:
            deadline = time.monotonic() + 3
            while self.speaking and time.monotonic() < deadline:  # doi loi dang noi dung han roi moi bao
                time.sleep(0.05)
            if announce and self.paused:
                self.speak([PAUSED])
            if self.paused and self.active:
                self.on_state("speak", PAUSED_HUD)
        self._run(worker)

    def resume(self) -> None:
        if not self.active or not self.paused:
            return
        self.paused = False
        self._write("_Nói tiếp_\n")

        def worker() -> None:
            self.speak([RESUMED])
            self._continue()
        self._run(worker)

    def finish(self, farewell: str = "") -> None:
        if farewell:
            self.speak([farewell])
        self.active = False
        self.stop_event.set()
        self._synth_pool.shutdown(wait=False, cancel_futures=True)
        self.on_end()

    def stop(self) -> None:
        """Dung ngay (phim Esc)."""
        if not self.active:
            return
        self.active = False
        self.stop_event.set()
        self.on_end()

    def interrupt(self) -> None:
        """Ngat loi dang noi de anh noi tiep."""
        self.stop_event.set()

    # -------------------------------------------------------------- su kien tu Voice Mic
    def handle_user_text(self, text: str) -> None:
        def worker() -> None:
            self.unclear_count = 0
            self._write(f"**Anh:** {text}\n")
            if is_pause_request(text):
                self.paused = False  # pause() tu dat lai
                self.pause()
                return
            if is_end_request(text):
                self._write(f"**Em:** {GOODBYE}\n")
                self.finish(GOODBYE)
                return
            ack = self._ack_path()
            if ack:
                play_mp3(ack, threading.Event())
            self.history.append({"role": "user", "content": text})
            self.history = self.history[-MAX_HISTORY_TURNS * 2:]
            if self.history[0]["role"] != "user":
                self.history = self.history[1:]
            self.thinking = True
            self.on_state("busy", "Em đang nghĩ...")
            reply = ""
            try:
                reply = self._reply_with_fallback()
            except BrainUnavailable as exc:
                self.log(f"voice chat brain failed: {exc}")
                reply = "Xin lỗi anh, em đang bị mất kết nối với bộ não AI. Anh thử lại sau giúp em nhé."
                self.speak([reply])
            finally:
                self.thinking = False
            if reply:
                self.history.append({"role": "assistant", "content": reply})
                self._write(f"**Em:** {reply}\n")
            self._continue()
        self._run(worker)

    def _reply_with_fallback(self) -> str:
        tried: set[str] = set()
        while self.brain:
            try:
                return self.speak(sentences_from_stream(self.brain.stream_reply(self.history), strip_ack=True))
            except BrainUnavailable as exc:
                tried.add(type(self.brain).__name__)
                self.log(f"voice chat brain {self.brain.name} unavailable: {exc}")
                nxt = pick_brain(self.preference, self.ollama_model)
                if not nxt or type(nxt).__name__ in tried:
                    raise
                self.brain = nxt
                threading.Thread(target=nxt.warm_up, daemon=True).start()
        raise BrainUnavailable("Không có bộ não AI.")

    def handle_unclear(self) -> None:
        def worker() -> None:
            self.unclear_count += 1
            if self.unclear_count > 2:
                self.finish(SILENCE_BYE)
                return
            self.speak([UNCLEAR])
            self._continue()
        self._run(worker)

    def handle_silence(self) -> None:
        self._run(lambda: self.finish(SILENCE_BYE))


# ------------------------------------------------------------------ doc to mot doan (lua chon "Doc" trong vong tron)

READ_GROUP_CHARS = 260  # doc lien toi khoang nay ky tu mot luot, giong tu nhien nhu doc ca doan


class ReadAloud:
    """Doc to danh sach cau bang giong nam, tam dung / doc tiep dung cho, cau sau tao truoc."""

    def __init__(
        self,
        sentences: list[str],
        settings: dict,
        on_state: Callable[[str, str], None],
        on_end: Callable[[], None],
        log: Callable[[str], None] = lambda _m: None,
    ) -> None:
        self.voice = str(settings.get("voice_read_voice") or settings.get("voice_chat_voice") or DEFAULT_VOICE)
        self.rate = str(settings.get("voice_read_rate") or "+0%")
        self.sentences = [s for s in (clean_spoken(x) for x in sentences) if re.search(r"\w", s)]
        self.groups = self._group(self.sentences)
        self.index = 0
        self.active = True
        self.paused = False
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()
        self.on_state = on_state
        self.on_end = on_end
        self.log = log
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="read-tts")
        self._futures: dict[int, concurrent.futures.Future] = {}

    @staticmethod
    def _group(sentences: list[str]) -> list[str]:
        groups: list[str] = []
        current: list[str] = []
        for sentence in sentences:
            # doan dau ngan de co tieng nhanh, cac doan sau gop lien
            limit = 120 if not groups else READ_GROUP_CHARS
            if current and sum(len(s) for s in current) + len(sentence) > limit:
                groups.append(" ".join(current))
                current = []
            current.append(sentence)
        if current:
            groups.append(" ".join(current))
        return groups

    def _future(self, index: int) -> concurrent.futures.Future:
        if index not in self._futures:
            self._futures[index] = self._pool.submit(tts.synthesize_to_file, self.groups[index], self.voice, True, self.rate)
        return self._futures[index]

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="read-aloud").start()

    def _status(self) -> str:
        percent = int(self.index * 100 / max(1, len(self.groups)))
        return f"Đang đọc {percent}% · Esc dừng"

    def _run(self) -> None:
        try:
            while self.active and self.index < len(self.groups):
                if self.paused:
                    self.resume_event.wait(0.3)
                    continue
                self.on_state("speak", self._status())
                current = self._future(self.index)
                for ahead in range(self.index + 1, min(len(self.groups), self.index + 3)):
                    self._future(ahead)
                try:
                    path = current.result(timeout=90)
                except Exception as exc:
                    self.log(f"read aloud tts error: {type(exc).__name__}: {exc}")
                    self.index += 1
                    continue
                if not self.active or self.paused:
                    continue
                self.stop_event.clear()
                play_mp3(path, self.stop_event)
                if self.active and not self.paused:
                    self.index += 1  # tam dung giua chung thi doc lai doan nay tu dau
        finally:
            finished = self.active
            self.active = False
            self._pool.shutdown(wait=False, cancel_futures=True)
            if finished:
                self.log("read aloud finished")
            self.on_end()

    def pause(self) -> None:
        if self.active and not self.paused:
            self.paused = True
            self.resume_event.clear()
            self.stop_event.set()
            self.on_state("speak", "Tạm dừng đọc · Ctrl+Alt+V đọc tiếp")

    def resume(self) -> None:
        if self.active and self.paused:
            self.paused = False
            self.resume_event.set()

    def toggle_pause(self) -> None:
        if self.paused:
            self.resume()
        else:
            self.pause()

    def stop(self) -> None:
        self.active = False
        self.paused = False
        self.stop_event.set()
        self.resume_event.set()
