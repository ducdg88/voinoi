"""Giong doc tieng Viet tu nhien (Microsoft Edge neural voices qua edge-tts), co cache mp3 tren dia."""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import re
import threading
import time
from pathlib import Path

from .store import DATA_DIR

CACHE_DIR = DATA_DIR / "tts-cache"
CACHE_MAX_AGE_DAYS = 30
VOICES = {
    # giong tieng Viet goc: doc tieng Viet chuan nhat, cau tieng Anh thi doi sang giong Anh cung gioi
    "vi-VN-NamMinhNeural": {"label": "Nam Minh (nam)", "english": "en-US-AndrewNeural", "lexicon": True},
    "vi-VN-HoaiMyNeural": {"label": "Hoài My (nữ)", "english": "en-US-AvaNeural", "lexicon": True},
    # giong da ngu doi moi: ngu dieu tu nhien hon, doc duoc ca tu tieng Anh xen trong cau tieng Viet
    "en-US-AndrewMultilingualNeural": {"label": "Andrew đa ngữ (nam)", "english": None, "lexicon": False},
    "en-US-BrianMultilingualNeural": {"label": "Brian đa ngữ (nam)", "english": None, "lexicon": False},
    "en-US-AvaMultilingualNeural": {"label": "Ava đa ngữ (nữ)", "english": None, "lexicon": False},
    "en-US-EmmaMultilingualNeural": {"label": "Emma đa ngữ (nữ)", "english": None, "lexicon": False},
}
PRONUNCIATION_FILE = DATA_DIR / "pronunciations.json"
DEFAULT_PRONUNCIATIONS = {
    # chu viet tat hay gap; giong Viet doc sai (vi du "AI" thanh "ai" nghia la ai do)
    "AI": "ây ai",
    "KPI": "cây pi ai",
    "OK": "ô kê",
    "Ok": "ô kê",
}
# Viet tat tieng Viet: doc thanh chu day du cho giong tu nhien
ABBREVIATION_RULES = [
    (r"\bTP\.?\s?HCM\b", "Thành phố Hồ Chí Minh"),
    (r"\bTP\.?\s?Hồ Chí Minh\b", "Thành phố Hồ Chí Minh"),
    (r"\bTP\.\s", "thành phố "),
    (r"\bQ\.(\s?\d)", r"quận\1"),
    (r"\bP\.(\s?\d)", r"phường\1"),
    (r"\bv\.v\.?", "vân vân"),
    (r"\be\.g\.", "ví dụ"),
    (r"(\d)\s?k\b", r"\1 nghìn"),
    (r"(\d)\s?tr\b", r"\1 triệu"),
    (r"(\d)\s?(?:đ|VNĐ|VND|vnđ)\b", r"\1 đồng"),
    (r"(\d)\s?h(\d{2})\b", r"\1 giờ \2"),
    (r"(\d)\s?h\b", r"\1 giờ"),
    (r"\s&\s", " và "),
    (r"\bSĐT\b", "số điện thoại"),
]
_pronunciations_cache: tuple[float, dict[str, str]] = (0.0, {})
VIETNAMESE_CHARS = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE
)
ENGLISH_WORDS = set(
    "the and of to is in that for with on are this it be as by you we can from or an will not have "
    "has was were which what when how why they their there these those our your its into than then "
    "about more most also but if would should could been being do does using use used".split()
)

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()
_inflight: dict[str, concurrent.futures.Future] = {}
_inflight_lock = threading.Lock()
_prefetch_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts-prefetch")


class TTSError(Exception):
    pass


def _event_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="tts-loop", daemon=True).start()
        return _loop


def speech_text(text: str) -> str:
    """Lam sach cau truoc khi doc: bo link, ky tu trang tri."""
    text = re.sub(r"https?://\S+|www\.\S+", " đường link ", text)
    text = re.sub(r"[\u2600-\u27bf\U0001f000-\U0001faff\ufe0f]", " ", text)
    text = re.sub(r"[*_#`~|<>\[\]{}^]+", " ", text)
    for pattern, replacement in ABBREVIATION_RULES:  # doc day du chu viet tat
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def pronunciations() -> dict[str, str]:
    """Bang doc tu (anh sua duoc trong reader-data/pronunciations.json)."""
    global _pronunciations_cache
    try:
        mtime = PRONUNCIATION_FILE.stat().st_mtime
    except OSError:
        try:
            PRONUNCIATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            PRONUNCIATION_FILE.write_text(json.dumps(DEFAULT_PRONUNCIATIONS, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return DEFAULT_PRONUNCIATIONS
    if mtime != _pronunciations_cache[0]:
        try:
            data = json.loads(PRONUNCIATION_FILE.read_text(encoding="utf-8"))
            table = {str(k): str(v) for k, v in data.items() if str(k).strip()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            table = DEFAULT_PRONUNCIATIONS
        _pronunciations_cache = (mtime, table)
    return _pronunciations_cache[1]


def apply_pronunciations(text: str, voice: str) -> str:
    """Chi ap cho giong tieng Viet goc; giong da ngu tu doc dung tu tieng Anh."""
    if not VOICES.get(voice, {}).get("lexicon"):
        return text
    for word, spoken in sorted(pronunciations().items(), key=lambda item: -len(item[0])):
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", spoken, text)
    return text


def is_english(text: str) -> bool:
    if VIETNAMESE_CHARS.search(text):
        return False
    words = re.findall(r"[A-Za-z']+", text.lower())
    if len(words) < 4:
        return False
    hits = [w for w in words if w in ENGLISH_WORDS]
    return len(set(hits)) >= 2 and len(hits) / len(words) >= 0.15


def choose_voice(text: str, voice: str, auto_english: bool) -> str:
    if voice not in VOICES:
        voice = "vi-VN-NamMinhNeural"
    english = VOICES[voice]["english"]
    if english and auto_english and is_english(text):
        return english
    return voice


def cache_path(text: str, voice: str, rate: str = "+0%") -> Path:
    key = f"{voice}|{text}" if rate == "+0%" else f"{voice}|{rate}|{text}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / digest[:2] / f"{digest}.mp3"


async def _synthesize_async(text: str, voice: str, rate: str = "+0%") -> tuple[bytes, list[list]]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    chunks: list[bytes] = []
    marks: list[list] = []  # [giay bat dau, chu] cho tung tu, dung de to sang dung cau khi doc ca doan
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            marks.append([round(chunk["offset"] / 1e7, 3), chunk["text"]])
    return b"".join(chunks), marks


def _nudged_rate(rate: str, delta: int) -> str:
    """Toc do lech 1-2%: tai khong nghe ra, nhung dich vu coi la yeu cau moi."""
    match = re.fullmatch(r"([+-]\d{1,3})%", rate or "")
    value = int(match.group(1)) if match else 0
    value += delta
    return f"{value:+d}%"


def _synthesize_uncached(text: str, voice: str, path: Path, rate: str = "+0%") -> bytes:
    # Dich vu Edge chap chon: cung mot cau luc tra tieng luc tra rong (NoAudioReceived), co cau hong
    # lien 3 lan neu gui y het. Lan thu sau doi toc do rat nhe nen thuong qua duoc (do ngay 28/09).
    attempt_rates = [rate, _nudged_rate(rate, 1), _nudged_rate(rate, -1), _nudged_rate(rate, 2), rate]
    last_error: Exception | None = None
    for attempt, attempt_rate in enumerate(attempt_rates):
        try:
            future = asyncio.run_coroutine_threadsafe(_synthesize_async(text, voice, attempt_rate), _event_loop())
            data, marks = future.result(timeout=60)
            if data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.with_suffix(".json").write_text(json.dumps(marks, ensure_ascii=False), encoding="utf-8")
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
                return data
            last_error = TTSError("dịch vụ giọng đọc trả về rỗng")
        except Exception as exc:  # mang cham, dich vu tam loi
            last_error = exc
        if attempt < len(attempt_rates) - 1:
            time.sleep(0.5 * (attempt + 1))
    raise TTSError(f"Không tạo được giọng đọc: {type(last_error).__name__}: {last_error}")


def _normalize_rate(rate: str) -> str:
    return rate if re.fullmatch(r"[+-]\d{1,3}%", rate or "") else "+0%"


def _render(spoken: str, chosen: str, rate: str) -> Path:
    """Tao file mp3 (va file moc thoi gian tung tu) cho doan chu da chuan hoa, co cache."""
    path = cache_path(spoken, chosen, rate)
    if path.exists():
        return path
    key = str(path)
    with _inflight_lock:
        future = _inflight.get(key)
        owner = future is None
        if owner:
            future = concurrent.futures.Future()
            _inflight[key] = future
    if not owner:
        future.result(timeout=120)
        return path
    try:
        data = _synthesize_uncached(spoken, chosen, path, rate)
        future.set_result(data)
        return path
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)


def prepare(text: str, voice: str, auto_english: bool = True) -> tuple[str, str]:
    """Chu se doc (da chuan hoa, da ap bang doc tu) va giong se dung."""
    spoken = speech_text(text)
    chosen = choose_voice(spoken, voice, auto_english)
    return apply_pronunciations(spoken, chosen), chosen


def synthesize(text: str, voice: str, auto_english: bool = True, rate: str = "+0%") -> bytes:
    return synthesize_to_file(text, voice, auto_english, rate).read_bytes()


def synthesize_to_file(text: str, voice: str, auto_english: bool = True, rate: str = "+0%") -> Path:
    """Tao (hoac lay tu cache) file mp3 cho cau nay, tra ve duong dan."""
    spoken, chosen = prepare(text, voice, auto_english)
    if not re.search(r"\w", spoken):
        raise TTSError("Câu này không có chữ để đọc.")
    return _render(spoken, chosen, _normalize_rate(rate))


def synthesize_segment(sentences: list[str], voice: str, rate: str = "+0%") -> tuple[Path, list[float]]:
    """Doc lien nhieu cau trong mot lan (ngu dieu tu nhien nhu nguoi doc ca doan).

    Tra ve file mp3 va giay bat dau cua tung cau trong file, de to sang dung cau dang doc.
    Cac cau phai cung mot giong (khong tron cau tieng Anh voi giong Viet).
    """
    pieces = [apply_pronunciations(speech_text(s), voice) for s in sentences]
    starts_chars: list[int] = []
    joined = ""
    for piece in pieces:
        if joined:
            joined += " "
        starts_chars.append(len(joined))
        joined += piece
    if not re.search(r"\w", joined):
        raise TTSError("Đoạn này không có chữ để đọc.")
    path = _render(joined, voice if voice in VOICES else "vi-VN-NamMinhNeural", _normalize_rate(rate))
    try:
        marks = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marks = []
    # tim vi tri tung tu trong doan chu de biet cau nao bat dau luc nao
    word_times: list[tuple[int, float]] = []
    cursor = 0
    lowered = joined.lower()
    for seconds, word in marks:
        found = lowered.find(str(word).lower(), cursor)
        if found < 0:
            continue
        word_times.append((found, float(seconds)))
        cursor = found + len(word)
    starts: list[float] = []
    for index, char_start in enumerate(starts_chars):
        time_at = next((t for pos, t in word_times if pos >= char_start), None)
        if time_at is None:
            time_at = starts[-1] if starts else 0.0
        starts.append(max(0.0, time_at - (0.05 if index else 0.0)))
    starts[0] = 0.0
    return path, starts


def prefetch(texts: list[str], voice: str, auto_english: bool = True) -> None:
    for text in texts:
        spoken, chosen = prepare(text, voice, auto_english)
        if not re.search(r"\w", spoken):
            continue
        if cache_path(spoken, chosen).exists():
            continue
        _prefetch_pool.submit(_quiet_synthesize, text, voice, auto_english)


def _quiet_synthesize(text: str, voice: str, auto_english: bool) -> None:
    try:
        synthesize(text, voice, auto_english)
    except Exception:
        pass


def cleanup_cache() -> None:
    cutoff = time.time() - CACHE_MAX_AGE_DAYS * 86400
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.rglob("*.mp3"):
        try:
            if path.stat().st_atime < cutoff and path.stat().st_mtime < cutoff:
                path.unlink()
                path.with_suffix(".json").unlink(missing_ok=True)
        except OSError:
            pass


def warm_up() -> None:
    """Nap thu vien va mo ket noi toi dich vu giong doc truoc, cau dau tien se ra tieng nhanh hon."""
    _quiet_synthesize("Xin chào.", "vi-VN-NamMinhNeural", False)


_queued_segments: set[tuple] = set()
_queued_lock = threading.Lock()


def prefetch_segment(sentences: list[str], voice: str, rate: str = "+0%") -> None:
    # moi doan duoc xin tao truoc nhieu lan (moi lan nghe xong mot doan), chi xep hang mot lan
    key = (tuple(sentences), voice, rate)
    with _queued_lock:
        if key in _queued_segments:
            return
        _queued_segments.add(key)

    def job() -> None:
        try:
            synthesize_segment(sentences, voice, rate)
        except Exception:
            pass
        finally:
            with _queued_lock:
                _queued_segments.discard(key)
    _prefetch_pool.submit(job)
