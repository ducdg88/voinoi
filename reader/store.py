"""Luu thu vien tai lieu, vi tri dang doc va ghi chu (JSON + ban Markdown de doc lai hoac dua cho AI)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
import unicodedata
import uuid
from pathlib import Path

from .extract import Block, split_sentences

# ban .exe: du lieu nam canh VoiNoi.exe (khong phai trong thu muc _internal)
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "reader-data"
DOCS_DIR = DATA_DIR / "docs"
SETTINGS_FILE = DATA_DIR / "settings.json"
LIBRARY_FILE = DATA_DIR / "library.json"

DEFAULT_SETTINGS = {
    "port": 8767,
    "notes_dir": "",  # de trong = reader-data/notes
    "open_mode": "app",  # "app" = cua so rieng (Chrome/Edge), "tab" = tab trinh duyet
}

_lock = threading.RLock()


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        settings.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return settings


def notes_dir() -> Path:
    configured = str(load_settings().get("notes_dir") or "").strip()
    path = Path(configured).expanduser() if configured else DATA_DIR / "notes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dirs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    notes_dir()
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def slugify(text: str, limit: int = 60) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (text[:limit].rstrip("-") or "tai-lieu")


# ---------------------------------------------------------------- documents

def build_content(blocks: list[Block]) -> tuple[list[dict], list[dict]]:
    """Tra ve (blocks, sentences). Moi sentence: {"t": text, "b": block_index}."""
    out_blocks: list[dict] = []
    sentences: list[dict] = []
    for block in blocks:
        kind = block["type"]
        pieces = [block["text"]] if kind == "code" or kind.startswith("h") else split_sentences(block["text"])
        if not pieces:
            continue
        index = len(out_blocks)
        out_blocks.append({"type": kind, "start": len(sentences), "end": len(sentences) + len(pieces)})
        sentences.extend({"t": piece, "b": index} for piece in pieces)
    return out_blocks, sentences


def doc_path(doc_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{6,40}", doc_id):
        raise KeyError(doc_id)
    return DOCS_DIR / f"{doc_id}.json"


def load_doc(doc_id: str) -> dict:
    data = _read_json(doc_path(doc_id), None)
    if not isinstance(data, dict):
        raise KeyError(doc_id)
    return data


def save_doc(doc: dict) -> None:
    with _lock:
        doc["updated"] = now_text()
        _write_json(doc_path(doc["id"]), doc)
        library = _read_json(LIBRARY_FILE, {})
        if not isinstance(library, dict):
            library = {}
        library[doc["id"]] = summary(doc)
        _write_json(LIBRARY_FILE, library)
        export_notes_markdown(doc)
        export_index(library)


def summary(doc: dict) -> dict:
    notes = doc.get("notes", [])
    return {
        "id": doc["id"],
        "title": doc["title"],
        "source": doc.get("source", ""),
        "source_type": doc.get("source_type", "text"),
        "total": len(doc.get("sentences", [])),
        "chars": sum(len(s["t"]) for s in doc.get("sentences", [])),
        "position": doc.get("position", 0),
        "notes": len(notes),
        "open_questions": sum(1 for n in notes if n.get("kind") == "question" and not n.get("done")),
        "created": doc.get("created", ""),
        "updated": doc.get("updated", ""),
        "opened": doc.get("opened", doc.get("created", "")),
        "notes_file": str(notes_file(doc)),
    }


def list_library() -> list[dict]:
    library = _read_json(LIBRARY_FILE, {})
    items = list(library.values()) if isinstance(library, dict) else []
    items.sort(key=lambda item: item.get("opened", ""), reverse=True)
    return items


def _reanchor_notes(notes: list[dict], old_sentences: list[dict], new_sentences: list[dict]) -> list[dict]:
    texts = [s["t"] for s in new_sentences]
    for note in notes:
        quote = note.get("quote") or ""
        old_index = note.get("i", 0)
        if 0 <= old_index < len(texts) and texts[old_index] == quote:
            continue
        candidates = [i for i, text in enumerate(texts) if quote and text == quote]
        if candidates:
            note["i"] = min(candidates, key=lambda i: abs(i - old_index))
        else:
            note["i"] = max(0, min(old_index, len(texts) - 1))
    return notes


def import_document(title: str, blocks: list[Block], source: str, source_type: str) -> dict:
    out_blocks, sentences = build_content(blocks)
    if not sentences:
        raise ValueError("Không tìm thấy chữ nào để đọc trong nội dung này.")
    content_hash = hashlib.sha1("\n".join(s["t"] for s in sentences).encode("utf-8")).hexdigest()
    identity = source if source_type in ("file", "url") else content_hash
    doc_id = hashlib.sha1(f"{source_type}|{identity}".encode("utf-8")).hexdigest()[:12]
    with _lock:
        try:
            existing = load_doc(doc_id)
        except KeyError:
            existing = None
        if existing and existing.get("content_hash") == content_hash:
            existing["opened"] = now_text()
            save_doc(existing)
            return existing
        doc = {
            "id": doc_id,
            "title": (title or "Tài liệu").strip()[:200],
            "source": source,
            "source_type": source_type,
            "content_hash": content_hash,
            "created": existing.get("created", now_text()) if existing else now_text(),
            "opened": now_text(),
            "blocks": out_blocks,
            "sentences": sentences,
            "position": 0,
            "notes": [],
        }
        if existing:
            doc["notes"] = _reanchor_notes(existing.get("notes", []), existing.get("sentences", []), sentences)
            old_position = existing.get("position", 0)
            doc["position"] = max(0, min(old_position, len(sentences) - 1))
            doc["reloaded"] = now_text()
        save_doc(doc)
        return doc


def delete_document(doc_id: str) -> None:
    with _lock:
        path = doc_path(doc_id)
        path.unlink(missing_ok=True)
        library = _read_json(LIBRARY_FILE, {})
        if isinstance(library, dict):
            library.pop(doc_id, None)
            _write_json(LIBRARY_FILE, library)
            export_index(library)
        # file ghi chu .md duoc giu lai de khong mat ghi chu


def set_position(doc_id: str, index: int) -> dict:
    with _lock:
        doc = load_doc(doc_id)
        doc["position"] = max(0, min(int(index), len(doc["sentences"]) - 1))
        doc["opened"] = now_text()
        save_doc(doc)
        return summary(doc)


# ---------------------------------------------------------------- notes

def _clean_note(payload: dict, doc: dict) -> dict:
    index = max(0, min(int(payload.get("i", doc.get("position", 0))), len(doc["sentences"]) - 1))
    kind = payload.get("kind") if payload.get("kind") in ("note", "question") else "note"
    quote = str(payload.get("quote") or "").strip() or doc["sentences"][index]["t"]
    return {"i": index, "kind": kind, "text": str(payload.get("text") or "").strip()[:20000], "quote": quote[:2000]}


def add_note(doc_id: str, payload: dict) -> dict:
    with _lock:
        doc = load_doc(doc_id)
        note = _clean_note(payload, doc)
        note.update({"id": uuid.uuid4().hex[:10], "created": now_text(), "updated": now_text(), "done": False})
        doc.setdefault("notes", []).append(note)
        save_doc(doc)
        return note


def update_note(doc_id: str, note_id: str, payload: dict) -> dict:
    with _lock:
        doc = load_doc(doc_id)
        for note in doc.get("notes", []):
            if note["id"] == note_id:
                if "text" in payload:
                    note["text"] = str(payload["text"]).strip()[:20000]
                if payload.get("kind") in ("note", "question"):
                    note["kind"] = payload["kind"]
                if "done" in payload:
                    note["done"] = bool(payload["done"])
                if "answer" in payload:
                    note["answer"] = str(payload["answer"]).strip()[:20000]
                note["updated"] = now_text()
                save_doc(doc)
                return note
        raise KeyError(note_id)


def delete_note(doc_id: str, note_id: str) -> None:
    with _lock:
        doc = load_doc(doc_id)
        before = len(doc.get("notes", []))
        doc["notes"] = [n for n in doc.get("notes", []) if n["id"] != note_id]
        if len(doc["notes"]) == before:
            raise KeyError(note_id)
        save_doc(doc)


# ---------------------------------------------------------------- markdown export

def notes_file(doc: dict) -> Path:
    return notes_dir() / f"{slugify(doc['title'])}-{doc['id'][:6]}.md"


def _context(doc: dict, index: int) -> str:
    sentences = doc["sentences"]
    block = doc["blocks"][sentences[index]["b"]]
    return " ".join(s["t"] for s in sentences[block["start"]:block["end"]])


def export_notes_markdown(doc: dict) -> None:
    notes = sorted(doc.get("notes", []), key=lambda n: (n["i"], n.get("created", "")))
    path = notes_file(doc)
    if not notes and not path.exists():
        return
    total = max(1, len(doc["sentences"]))
    questions = [n for n in notes if n["kind"] == "question" and not n.get("done")]
    lines = [
        f"# Ghi chú: {doc['title']}",
        "",
        f"- Nguồn: {doc.get('source') or '(văn bản dán vào)'}",
        f"- Mã tài liệu: {doc['id']}",
        f"- Đang nghe tới: câu {doc.get('position', 0) + 1}/{total}",
        f"- Cập nhật: {now_text()}",
        f"- Số ghi chú: {len(notes)}, câu hỏi chưa rõ: {len(questions)}",
        "",
        "_File này do Trợ lý đọc tự tạo lại mỗi khi ghi chú thay đổi. Muốn sửa ghi chú, sửa trong Trợ lý đọc._",
        "",
    ]
    if questions:
        lines += ["## Câu hỏi chưa rõ", ""]
        for note in questions:
            lines.append(f"- [ ] (câu {note['i'] + 1}) {note['text'] or '(chưa ghi nội dung)'}")
            lines.append(f"  > {note['quote']}")
        lines.append("")
    lines += ["## Tất cả ghi chú theo thứ tự tài liệu", ""]
    for note in notes:
        label = "Câu hỏi" if note["kind"] == "question" else "Ghi chú"
        status = " (đã rõ)" if note["kind"] == "question" and note.get("done") else ""
        lines.append(f"### {label}{status} ở câu {note['i'] + 1} · {note.get('created', '')}")
        lines.append("")
        lines.append(f"> {note['quote']}")
        lines.append("")
        if note.get("text"):
            lines.append(note["text"])
            lines.append("")
        if note.get("answer"):
            lines.append(f"**Trả lời:** {note['answer']}")
            lines.append("")
        context = _context(doc, note["i"]) if note["i"] < len(doc["sentences"]) else ""
        if context and context != note["quote"]:
            lines.append(f"<details><summary>Ngữ cảnh đoạn văn</summary>\n\n{context}\n\n</details>")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_index(library: dict) -> None:
    items = sorted(library.values(), key=lambda item: item.get("opened", ""), reverse=True)
    lines = [
        "# Trợ lý đọc: danh sách tài liệu và ghi chú",
        "",
        f"Cập nhật: {now_text()}. Mỗi tài liệu có một file ghi chú riêng trong thư mục này.",
        "",
        "| Tài liệu | Tiến độ | Ghi chú | Câu hỏi chưa rõ | File ghi chú |",
        "|---|---|---|---|---|",
    ]
    for item in items:
        progress = f"{min(item['position'] + 1, item['total'])}/{item['total']}"
        name = Path(item.get("notes_file", "")).name if item.get("notes") else ""
        title = item["title"].replace("|", "/")
        lines.append(f"| {title} | {progress} | {item['notes']} | {item['open_questions']} | {name} |")
    (notes_dir() / "_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
