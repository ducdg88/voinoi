"""May chu local (127.0.0.1) cho Tro ly doc: giao dien web + API thu vien, ghi chu, giong doc."""
from __future__ import annotations

import ctypes
import json
import mimetypes
import os
import re
import subprocess
import threading
import traceback
import urllib.parse
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import extract, store, tts

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 80_000_000
PREFETCH_AHEAD = 4
SEGMENT_MAX_CHARS = 420  # doc lien toi da chung nay ky tu mot lan (ca doan ngan, hoac nua doan dai)


def build_segments(doc: dict, voice: str, auto_english: bool) -> list[list[int]]:
    """Chia tai lieu thanh cac doan doc lien: cung mot khoi van, cung ngon ngu, khong qua dai.

    Moi phan tu la [cau bat dau, cau ket thuc (khong tinh), giong dung de doc].
    """
    segments: list[list] = []
    current: list | None = None
    for index, sentence in enumerate(doc["sentences"]):
        block = doc["blocks"][sentence["b"]]
        if block["type"] == "code":
            current = None
            continue
        text = sentence["t"]
        spoken_voice = tts.choose_voice(tts.speech_text(text), voice, auto_english)
        heading = block["type"].startswith("h")
        if (
            current is None
            or heading
            or current[3] != sentence["b"]
            or current[2] != spoken_voice
            or current[4] + len(text) > SEGMENT_MAX_CHARS
        ):
            current = [index, index + 1, spoken_voice, sentence["b"], len(text)]
            segments.append(current)
        else:
            current[1] = index + 1
            current[4] += len(text)
    return [[a, b, v] for a, b, v, _block, _chars in segments]


def log(message: str) -> None:
    try:
        with (store.DATA_DIR / "reader.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{store.now_text()} {message}\n")
    except OSError:
        pass


def read_clipboard_text() -> str:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        threading.Event().wait(0.05)
    else:
        raise ApiError(409, "Clipboard đang bị ứng dụng khác giữ, thử lại sau.")
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer) if pointer else ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def client_doc(doc: dict) -> dict:
    data = dict(doc)
    data["notes_file"] = str(store.notes_file(doc))
    return data


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "DocReader/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    # ------------------------------------------------------------ helpers
    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data: bytes, content_type: str, cache: str = "no-cache") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD_BYTES:
            raise ApiError(413, "File quá lớn (tối đa 80 MB).")
        return self.rfile.read(length) if length else b""

    def read_json(self) -> dict:
        raw = self.read_body()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as exc:
            raise ApiError(400, "Dữ liệu gửi lên không hợp lệ.") from exc
        return data if isinstance(data, dict) else {}

    def check_origin(self) -> None:
        # Chan trang web la goi API local (chi cho phep chinh giao dien cua tro ly).
        origin = self.headers.get("Origin")
        if origin and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", origin):
            raise ApiError(403, "Nguồn gọi không được phép.")

    def dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                raise ApiError(403, "Chỉ truy cập từ máy này.")
            if method != "GET":
                self.check_origin()
            if path.startswith("/api/"):
                self.route_api(method, path[5:].strip("/").split("/"), query)
            elif method == "GET":
                self.serve_static(path)
            else:
                raise ApiError(404, "Không tìm thấy.")
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except extract.ExtractError as exc:
            self.send_json({"error": str(exc)}, 422)
        except tts.TTSError as exc:
            log(f"tts error: {exc}")
            self.send_json({"error": str(exc)}, 503)
        except KeyError:
            self.send_json({"error": "Không tìm thấy tài liệu hoặc ghi chú."}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:
            log(f"server error {method} {path}: {traceback.format_exc()}")
            try:
                self.send_json({"error": f"Lỗi máy chủ: {type(exc).__name__}: {exc}"}, 500)
            except OSError:
                pass

    def do_GET(self) -> None:  # noqa: N802
        self.dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self.dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self.dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self.dispatch("DELETE")

    # ------------------------------------------------------------ static
    def serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            raise ApiError(404, "Không tìm thấy.")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self.send_bytes(target.read_bytes(), content_type)

    # ------------------------------------------------------------ api
    def route_api(self, method: str, parts: list[str], query: dict[str, list[str]]) -> None:
        head = parts[0] if parts else ""
        if head == "ping":
            return self.send_json({"app": "doc-reader", "ok": True})
        if head == "library" and method == "GET":
            return self.send_json({"items": store.list_library(), "notes_dir": str(store.notes_dir())})
        if head == "import" and method == "POST":
            return self.api_import(self.read_json())
        if head == "upload" and method == "POST":
            name = urllib.parse.unquote(query.get("name", ["tai-lieu.txt"])[0])
            title, blocks = extract.extract_bytes(self.read_body(), name)
            doc = store.import_document(title, blocks, name, "upload")
            self.prefetch_opening(doc, query)
            return self.send_json(client_doc(doc))
        if head == "segments" and method == "GET" and len(parts) == 2:
            doc = store.load_doc(parts[1])
            voice, auto_english = self.voice_options(query)
            return self.send_json({"segments": build_segments(doc, voice, auto_english)})
        if head == "seg" and method == "GET" and len(parts) in (3, 4):
            return self.api_segment(parts[1], int(parts[2]), query, starts_only=len(parts) == 4)
        if head == "tts" and method == "GET" and len(parts) == 3:
            return self.api_tts(parts[1], int(parts[2]), query)
        if head == "tts-text" and method == "POST":
            payload = self.read_json()
            audio = tts.synthesize(str(payload.get("text", "")), str(payload.get("voice", "")),
                                   bool(payload.get("en", True)))
            return self.send_bytes(audio, "audio/mpeg")
        if head == "open" and method == "POST":
            return self.api_open(self.read_json())
        if head == "doc" and len(parts) >= 2:
            return self.route_doc(method, parts[1], parts[2:], query)
        raise ApiError(404, "API không tồn tại.")

    def api_import(self, payload: dict) -> None:
        kind = payload.get("kind")
        value = str(payload.get("value") or "")
        title_override = str(payload.get("title") or "").strip()
        if kind == "clipboard":
            value = read_clipboard_text()
            if not value.strip():
                raise ApiError(400, "Clipboard đang trống. Hãy bôi đen và Ctrl+C nội dung cần nghe trước.")
            stripped = value.strip().strip('"')
            if re.match(r"^https?://\S+$", stripped):
                kind, value = "url", stripped
            elif re.match(r"^[A-Za-z]:\\[^\n]+\.\w{2,5}$", stripped) and Path(stripped).is_file():
                kind, value = "path", stripped
            else:
                kind = "text"
        if kind == "text":
            if not value.strip():
                raise ApiError(400, "Chưa có nội dung.")
            title, blocks = extract.extract_text(value)
            doc = store.import_document(title_override or title, blocks, "", "text")
        elif kind == "path":
            title, blocks, source = extract.extract_path(value)
            doc = store.import_document(title_override or title, blocks, source, "file")
        elif kind == "url":
            title, blocks, source = extract.extract_url(value)
            doc = store.import_document(title_override or title, blocks, source, "url")
        else:
            raise ApiError(400, "Kiểu nhập không hợp lệ.")
        self.prefetch_opening(doc, {})
        self.send_json(client_doc(doc))

    def api_tts(self, doc_id: str, index: int, query: dict[str, list[str]]) -> None:
        doc = store.load_doc(doc_id)
        sentences = doc["sentences"]
        if not 0 <= index < len(sentences):
            raise ApiError(404, "Hết tài liệu.")
        voice, auto_english = self.voice_options(query)
        if query.get("ahead", ["1"])[0] != "0":
            self.prefetch_from(doc, index, query)
        audio = tts.synthesize(sentences[index]["t"], voice, auto_english)
        self.send_bytes(audio, "audio/mpeg", cache="private, max-age=86400")

    @staticmethod
    def voice_options(query: dict[str, list[str]]) -> tuple[str, bool]:
        return query.get("voice", ["vi-VN-NamMinhNeural"])[0], query.get("en", ["1"])[0] != "0"

    @staticmethod
    def rate_option(query: dict[str, list[str]]) -> str:
        return query.get("rate", ["+0%"])[0].replace(" ", "+")

    def prefetch_opening(self, doc: dict, query: dict[str, list[str]]) -> None:
        """Mo tai lieu la tao san giong cho cho dang nghe, bam Doc la co tieng ngay."""
        if query.get("natural", ["1"])[0] == "0":
            self.prefetch_from(doc, doc.get("position", 0), query, include_current=True)
            return
        voice, auto_english = self.voice_options(query)
        segments = build_segments(doc, voice, auto_english)
        position = doc.get("position", 0)
        for a, b, seg_voice in segments:
            if b > position:
                tts.prefetch_segment([s["t"] for s in doc["sentences"][a:b]], seg_voice, self.rate_option(query))
                break

    def api_segment(self, doc_id: str, index: int, query: dict[str, list[str]], starts_only: bool) -> None:
        doc = store.load_doc(doc_id)
        voice, auto_english = self.voice_options(query)
        segments = build_segments(doc, voice, auto_english)
        if not 0 <= index < len(segments):
            raise ApiError(404, "Hết tài liệu.")
        rate = self.rate_option(query)
        a, b, seg_voice = segments[index]
        path, starts = tts.synthesize_segment([s["t"] for s in doc["sentences"][a:b]], seg_voice, rate)
        # doan ke tiep tao san trong luc doan nay dang doc
        for na, nb, nvoice in segments[index + 1:index + 3]:
            tts.prefetch_segment([s["t"] for s in doc["sentences"][na:nb]], nvoice, rate)
        if starts_only:
            return self.send_json({"start": a, "end": b, "starts": starts})
        self.send_bytes(path.read_bytes(), "audio/mpeg", cache="private, max-age=86400")

    def prefetch_from(self, doc: dict, index: int, query: dict[str, list[str]], include_current: bool = False) -> None:
        sentences = doc["sentences"]
        start = index if include_current else index + 1
        speakable = [i for i in range(start, min(len(sentences), start + PREFETCH_AHEAD * 2))
                     if doc["blocks"][sentences[i]["b"]]["type"] != "code"][:PREFETCH_AHEAD]
        voice, auto_english = self.voice_options(query)
        tts.prefetch([sentences[i]["t"] for i in speakable], voice, auto_english)

    def api_open(self, payload: dict) -> None:
        target = payload.get("target")
        if target == "notes_dir":
            os.startfile(str(store.notes_dir()))  # noqa: S606
        elif target == "notes_file":
            doc = store.load_doc(str(payload.get("id", "")))
            path = store.notes_file(doc)
            if not path.exists():
                store.export_notes_markdown(doc)
            if path.exists():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                raise ApiError(404, "Tài liệu này chưa có ghi chú nào.")
        elif target == "source":
            doc = store.load_doc(str(payload.get("id", "")))
            source = doc.get("source", "")
            if doc.get("source_type") == "file" and Path(source).exists():
                os.startfile(source)  # noqa: S606
            elif doc.get("source_type") == "url":
                os.startfile(source if source.startswith("http") else "https://" + source)  # noqa: S606
            else:
                raise ApiError(400, "Tài liệu này không có file hoặc link gốc.")
        else:
            raise ApiError(400, "Không rõ cần mở gì.")
        self.send_json({"ok": True})

    def route_doc(self, method: str, doc_id: str, rest: list[str], query: dict[str, list[str]]) -> None:
        if not rest:
            if method == "GET":
                doc = store.load_doc(doc_id)
                # tao san giong doc cho vai cau tu vi tri dang nghe, bam Doc la co tieng ngay
                self.prefetch_opening(doc, query)
                return self.send_json(client_doc(doc))
            if method == "DELETE":
                store.delete_document(doc_id)
                return self.send_json({"ok": True})
        action = rest[0]
        if action == "position" and method == "POST":
            return self.send_json(store.set_position(doc_id, int(self.read_json().get("i", 0))))
        if action == "reload" and method == "POST":
            doc = store.load_doc(doc_id)
            if doc.get("source_type") == "file":
                title, blocks, source = extract.extract_path(doc["source"])
            elif doc.get("source_type") == "url":
                title, blocks, source = extract.extract_url(doc["source"])
            else:
                raise ApiError(400, "Chỉ tải lại được tài liệu mở từ file hoặc link.")
            return self.send_json(client_doc(store.import_document(doc["title"], blocks, source, doc["source_type"])))
        if action == "notes":
            if method == "POST" and len(rest) == 1:
                return self.send_json(store.add_note(doc_id, self.read_json()))
            if method == "PATCH" and len(rest) == 2:
                return self.send_json(store.update_note(doc_id, rest[1], self.read_json()))
            if method == "DELETE" and len(rest) == 2:
                store.delete_note(doc_id, rest[1])
                return self.send_json({"ok": True})
        raise ApiError(404, "API không tồn tại.")


def seed_guide() -> None:
    """Lan dau chay: dua tai lieu huong dan vao thu vien de nghe thu."""
    marker = store.DATA_DIR / ".guide-added"
    if marker.exists() or store.list_library():
        return
    try:
        title, blocks, source = extract.extract_path(str(Path(__file__).resolve().parent / "huong-dan.md"))
        store.import_document(title, blocks, source, "file")
        marker.write_text(store.now_text(), encoding="utf-8")
    except Exception as exc:
        log(f"seed guide failed: {exc}")


def make_server(port: int) -> ThreadingHTTPServer:
    store.ensure_dirs()
    seed_guide()
    threading.Thread(target=tts.warm_up, name="tts-warmup", daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=tts.cleanup_cache, name="tts-cleanup", daemon=True).start()
    return server
