"""Doc noi dung tu file/link/van ban va chuyen thanh cac khoi (tieu de, doan, gach dau dong)."""
from __future__ import annotations

import io
import posixpath
import re
import urllib.parse
import urllib.request
import zipfile
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

Block = dict  # {"type": "h1|h2|h3|p|li|quote|code", "text": str}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
TEXT_EXTENSIONS = {".txt", ".text", ".log", ".csv", ".json", ".srt", ".vtt"}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | HTML_EXTENSIONS | {".pdf", ".docx", ".epub"}

SENTENCE_END = ".!?…:;"
# " - Ten trang" / " | Ten trang" o cuoi tieu de (gom ca gach ngang dai)
DASHES = "-" + chr(0x2013) + chr(0x2014)
TITLE_SITE_SUFFIX = r"\s+[|" + DASHES + r"]\s+[^|" + DASHES + r"]{2,40}$"


class ExtractError(Exception):
    pass


# ---------------------------------------------------------------- text helpers

def decode_bytes(data: bytes, hint: str | None = None) -> str:
    for encoding in [hint, "utf-8-sig", "utf-16"] if data[:2] in (b"\xff\xfe", b"\xfe\xff") else [hint, "utf-8-sig"]:
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("cp1258", errors="replace")


def clean_inline(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def join_wrapped_lines(lines: list[str]) -> list[str]:
    """Noi cac dong bi ngat giua cau (van ban copy tu PDF, email...) thanh doan."""
    paragraphs: list[str] = []
    current = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if re.fullmatch(r"(trang|page)?\s*\d{1,4}(\s*/\s*\d{1,4})?", line, flags=re.IGNORECASE):
            continue
        if not current:
            current = line
            continue
        if current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        elif current[-1] not in SENTENCE_END and (line[:1].islower() or line[:1] in ",)"):
            current = current + " " + line
        else:
            paragraphs.append(current)
            current = line
    if current:
        paragraphs.append(current)
    return paragraphs


def blocks_from_plain_text(text: str) -> list[Block]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[Block] = []
    for paragraph in join_wrapped_lines(lines):
        paragraph = clean_inline(paragraph)
        if not paragraph:
            continue
        if re.match(r"^([-*•●▪]|\d{1,3}[.)])\s+", paragraph):
            blocks.append({"type": "li", "text": re.sub(r"^([-*•●▪]|\d{1,3}[.)])\s+", "", paragraph)})
        else:
            blocks.append({"type": "p", "text": paragraph})
    return blocks


# ---------------------------------------------------------------- markdown

def strip_markdown_inline(text: str) -> str:
    text = re.sub(r"!\[\[[^\]]*\]\]", "", text)                      # ![[anh.png]]
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                  # ![alt](url)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)         # [[note|alias]]
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)                    # [[note]]
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)               # [text](url)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__|~~|==)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])[*_](?!\s)(.+?)(?<!\s)[*_](?![\w*])", r"\1", text)
    text = re.sub(r"\s#[\w/-]+", lambda m: " " + m.group(0)[2:], text)  # #tag -> tag
    return clean_inline(unescape(text))


def blocks_from_markdown(text: str) -> list[Block]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)  # frontmatter
    blocks: list[Block] = []
    paragraph: list[str] = []
    code: list[str] | None = None

    def flush() -> None:
        if paragraph:
            joined = strip_markdown_inline(" ".join(paragraph))
            if joined:
                blocks.append({"type": "p", "text": joined})
            paragraph.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if code is not None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                if code:
                    blocks.append({"type": "code", "text": "\n".join(code)})
                code = None
            else:
                code.append(line)
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            code = []
            continue
        if not stripped or re.fullmatch(r"[-*_]{3,}", stripped):
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush()
            level = min(len(heading.group(1)), 3)
            value = strip_markdown_inline(heading.group(2).rstrip("#"))
            if value:
                blocks.append({"type": f"h{level}", "text": value})
            continue
        item = re.match(r"^([-*+]|\d{1,3}[.)])\s+(\[[ xX]\]\s+)?(.*)$", stripped)
        if item:
            flush()
            value = strip_markdown_inline(item.group(3))
            if value:
                blocks.append({"type": "li", "text": value})
            continue
        if stripped.startswith(">"):
            flush()
            value = strip_markdown_inline(re.sub(r"^>+\s?(\[![\w-]+\]\s*)?", "", stripped))
            if value:
                blocks.append({"type": "quote", "text": value})
            continue
        if stripped.startswith("|"):
            flush()
            if re.fullmatch(r"\|?[\s:|-]+\|?", stripped):
                continue
            cells = [strip_markdown_inline(c) for c in stripped.strip("|").split("|")]
            value = ", ".join(c for c in cells if c)
            if value:
                blocks.append({"type": "li", "text": value})
            continue
        paragraph.append(stripped)
    flush()
    if code:
        blocks.append({"type": "code", "text": "\n".join(code)})
    return blocks


# ---------------------------------------------------------------- html

class _HtmlBlocks(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "form", "svg",
            "button", "iframe", "template", "select", "figure", "menu"}
    VOID = {"img", "br", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed", "track"}
    SKIP_MARKERS = re.compile(
        r"(^|[\s_-])(nav|navbox|navbar|menu|footer|sidebar|breadcrumbs?|share|sharing|social|related|"
        r"comments?|advert|ads|cookie|popup|modal|newsletter|subscribe|toc|references?|reflist|"
        r"editsection|metadata|ambox|noprint|catlinks|printfooter|jump-link|hatnote|sitesub|"
        r"contentsub|redirectedfrom|infobox|mw-indicators|visually-hidden|sr-only)([\s_-]|$)",
        re.IGNORECASE,
    )
    BLOCK_TYPES = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3",
                   "li": "li", "blockquote": "quote", "pre": "code", "dt": "p", "dd": "p",
                   "p": "p", "td": "p", "th": "p", "caption": "p", "figcaption": "p"}
    CONTAINERS = {"div", "section", "article", "main", "ul", "ol", "table", "tr", "body", "dl"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[Block, bool]] = []
        self.buffer: list[str] = []
        self.kind = "p"
        self.skip_tag = ""
        self.skip_nest = 0
        self.main_depth = 0
        self.main_tags: list[str] = []
        self.title = ""
        self.meta_title = ""
        self._in_title = False

    def flush(self) -> None:
        raw = "".join(self.buffer)
        self.buffer = []
        text = raw.strip("\n") if self.kind == "code" else clean_inline(raw)
        if text:
            self.blocks.append(({"type": self.kind, "text": text}, self.main_depth > 0))
        self.kind = "p"

    def _should_skip(self, tag: str, attributes: dict[str, str | None]) -> bool:
        if tag in self.SKIP:
            return True
        if tag == "header" and not self.main_depth:
            return True
        if tag in self.VOID or tag in ("html", "body", "main", "article"):
            return False
        marker = f"{attributes.get('class') or ''} {attributes.get('id') or ''}"
        if attributes.get("aria-hidden") == "true" or attributes.get("hidden") is not None:
            return True
        return bool(marker.strip()) and bool(self.SKIP_MARKERS.search(marker))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("property") in ("og:title", "twitter:title"):
            self.meta_title = self.meta_title or (attributes.get("content") or "")
        if tag == "title":
            self._in_title = True
            return
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_nest += 1
            return
        if self._should_skip(tag, attributes):
            if tag not in self.VOID:
                self.skip_tag, self.skip_nest = tag, 1
            return
        if tag in ("article", "main") or attributes.get("role") == "main":
            self.main_depth += 1
            self.main_tags.append(tag)
        if tag == "br":
            self.buffer.append(chr(10) if self.kind == "code" else " ")
        elif tag in self.BLOCK_TYPES:
            self.flush()
            self.kind = self.BLOCK_TYPES[tag]
        elif tag in self.CONTAINERS:
            self.flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            return
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_nest -= 1
                if self.skip_nest <= 0:
                    self.skip_tag = ""
            return
        if tag in self.BLOCK_TYPES or tag in self.CONTAINERS:
            self.flush()
        if self.main_tags and tag == self.main_tags[-1]:
            self.main_tags.pop()
            self.main_depth = max(0, self.main_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if not self.skip_tag:
            self.buffer.append(data)


def blocks_from_html(html: str, prefer_main: bool = True) -> tuple[str, list[Block]]:
    parser = _HtmlBlocks()
    parser.feed(html)
    parser.flush()
    all_blocks = [b for b, _ in parser.blocks]
    main_blocks = [b for b, in_main in parser.blocks if in_main]
    if prefer_main and sum(len(b["text"]) for b in main_blocks) > 400:
        blocks = main_blocks
    else:
        blocks = all_blocks
    # bo cac dong menu/nut ngan lap lai
    seen: dict[str, int] = {}
    for block in blocks:
        seen[block["text"]] = seen.get(block["text"], 0) + 1
    blocks = [b for b in blocks if not (seen[b["text"]] > 1 and len(b["text"]) < 40)]
    title = clean_inline(parser.meta_title or parser.title)
    first_heading = next((b["text"] for b in blocks[:8] if b["type"] == "h1"), "")
    if first_heading and (not title or first_heading.lower() in title.lower()):
        title = first_heading
    else:
        title = re.sub(TITLE_SITE_SUFFIX, "", title)
    # bo phan duoi bai: tham khao, lien ket ngoai...
    tail_headings = {"tham khảo", "chú thích", "liên kết ngoài", "xem thêm", "đọc thêm", "nguồn", "references",
                     "external links", "see also", "notes", "further reading", "bibliography", "sources"}
    for index, block in enumerate(blocks):
        if block["type"].startswith("h") and block["text"].strip().lower() in tail_headings and index > len(blocks) * 0.5:
            blocks = blocks[:index]
            break
    for block in blocks:
        block["text"] = clean_inline(re.sub(r"\[(\d{1,3}|cần dẫn nguồn|citation needed|[a-z])\]", "", block["text"]))
    return title, [b for b in blocks if b["text"]]


# ---------------------------------------------------------------- pdf / docx / epub

def blocks_from_pdf(data: bytes) -> list[Block]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ExtractError("Thiếu thư viện pypdf. Chạy: .venv\\Scripts\\python.exe -m pip install pypdf") from exc
    reader = PdfReader(io.BytesIO(data))
    lines: list[str] = []
    for page in reader.pages:
        try:
            lines.extend((page.extract_text() or "").split("\n"))
        except Exception:
            continue
        lines.append("")
    blocks = blocks_from_plain_text("\n".join(lines))
    if not blocks:
        raise ExtractError("PDF này không có lớp chữ (có thể là ảnh scan). Cần OCR trước khi đọc.")
    return blocks


W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_paragraph(p: ElementTree.Element) -> Block | None:
    parts: list[str] = []
    for node in p.iter():
        if node.tag == W_NS + "t" and node.text:
            parts.append(node.text)
        elif node.tag in (W_NS + "tab", W_NS + "br", W_NS + "cr"):
            parts.append(" ")
    text = clean_inline("".join(parts))
    if not text:
        return None
    kind = "p"
    ppr = p.find(W_NS + "pPr")
    if ppr is not None:
        style = ppr.find(W_NS + "pStyle")
        style_name = (style.get(W_NS + "val") or "").lower() if style is not None else ""
        outline = ppr.find(W_NS + "outlineLvl")
        level_match = re.search(r"(heading|tieude|u)\s*(\d)", style_name)
        if style_name in ("title", "subtitle"):
            kind = "h1"
        elif level_match:
            kind = f"h{min(int(level_match.group(2)), 3)}"
        elif outline is not None:
            kind = f"h{min(int(outline.get(W_NS + 'val') or 0) + 1, 3)}"
        elif ppr.find(W_NS + "numPr") is not None or "list" in style_name:
            kind = "li"
        elif "quote" in style_name:
            kind = "quote"
    return {"type": kind, "text": text}


def blocks_from_docx(data: bytes) -> list[Block]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ExtractError("File .docx bị lỗi hoặc không đúng định dạng.") from exc
    body = root.find(W_NS + "body")
    blocks: list[Block] = []
    for child in list(body) if body is not None else []:
        if child.tag == W_NS + "p":
            block = _docx_paragraph(child)
            if block:
                blocks.append(block)
        elif child.tag == W_NS + "tbl":
            for row in child.iter(W_NS + "tr"):
                cells = []
                for cell in row.iter(W_NS + "tc"):
                    cell_text = " ".join(b["text"] for p in cell.iter(W_NS + "p") if (b := _docx_paragraph(p)))
                    if cell_text:
                        cells.append(cell_text)
                if cells:
                    blocks.append({"type": "li", "text": ", ".join(cells)})
    return blocks


def blocks_from_epub(data: bytes) -> tuple[str, list[Block]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(el for el in container.iter() if el.tag.endswith("rootfile")).get("full-path") or ""
        opf = ElementTree.fromstring(archive.read(rootfile))
    except Exception as exc:
        raise ExtractError("File EPUB bị lỗi hoặc không đúng định dạng.") from exc
    base = posixpath.dirname(rootfile)
    manifest = {el.get("id"): el.get("href") for el in opf.iter() if el.tag.endswith("item")}
    spine = [el.get("idref") for el in opf.iter() if el.tag.endswith("itemref")]
    title_el = next((el for el in opf.iter() if el.tag.endswith("title")), None)
    blocks: list[Block] = []
    for idref in spine:
        href = manifest.get(idref)
        if not href:
            continue
        try:
            html = decode_bytes(archive.read(posixpath.normpath(posixpath.join(base, urllib.parse.unquote(href)))))
        except KeyError:
            continue
        blocks.extend(blocks_from_html(html, prefer_main=False)[1])
    return (title_el.text or "").strip() if title_el is not None else "", blocks


# ---------------------------------------------------------------- entry points

def title_from_blocks(blocks: list[Block], fallback: str) -> str:
    for block in blocks[:5]:
        if block["type"].startswith("h") and 3 <= len(block["text"]) <= 160:
            return block["text"]
    return fallback


def extract_bytes(data: bytes, filename: str) -> tuple[str, list[Block]]:
    ext = Path(filename).suffix.lower()
    stem = Path(filename).stem or "Tài liệu"
    if ext == ".pdf":
        blocks = blocks_from_pdf(data)
    elif ext == ".docx":
        blocks = blocks_from_docx(data)
    elif ext == ".epub":
        title, blocks = blocks_from_epub(data)
        return title or stem, blocks
    elif ext in HTML_EXTENSIONS:
        title, blocks = blocks_from_html(decode_bytes(data))
        return title or stem, blocks
    elif ext in MARKDOWN_EXTENSIONS:
        blocks = blocks_from_markdown(decode_bytes(data))
    elif ext in TEXT_EXTENSIONS or not ext:
        blocks = blocks_from_plain_text(decode_bytes(data))
    else:
        raise ExtractError(f"Chưa hỗ trợ định dạng {ext}. Dùng: txt, md, pdf, docx, html, epub.")
    return title_from_blocks(blocks, stem), blocks


def extract_path(path: str) -> tuple[str, list[Block], str]:
    cleaned = path.strip().strip('"').strip("'")
    file_path = Path(cleaned).expanduser()
    if not file_path.is_file():
        raise ExtractError(f"Không tìm thấy file: {cleaned}")
    title, blocks = extract_bytes(file_path.read_bytes(), file_path.name)
    return title, blocks, str(file_path.resolve())


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    google_doc = re.match(r"https://docs\.google\.com/document/d/([\w-]+)", url)
    if google_doc:
        return f"https://docs.google.com/document/d/{google_doc.group(1)}/export?format=txt"
    return url


def extract_url(url: str) -> tuple[str, list[Block], str]:
    source = url.strip()
    fetch_url = normalize_url(source)
    request = urllib.request.Request(fetch_url, headers={"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.8"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(40_000_000)
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset()
    except Exception as exc:
        raise ExtractError(f"Không tải được link ({type(exc).__name__}: {exc}).") from exc
    path_name = Path(urllib.parse.urlparse(fetch_url).path).name or "trang-web"
    if "pdf" in content_type or path_name.lower().endswith(".pdf"):
        return title_from_blocks(blocks := blocks_from_pdf(data), path_name), blocks, source
    if "text/plain" in content_type:
        blocks = blocks_from_plain_text(decode_bytes(data, charset))
        return title_from_blocks(blocks, "Google Docs" if "docs.google.com" in fetch_url else path_name), blocks, source
    html = decode_bytes(data, charset)
    if "docs.google.com" in fetch_url and "ServiceLogin" in html:
        raise ExtractError("Google Docs này chưa chia sẻ công khai. Hãy tải về .docx hoặc copy nội dung rồi dán vào.")
    title, blocks = blocks_from_html(html)
    return title or urllib.parse.urlparse(fetch_url).netloc, blocks, source


def extract_text(text: str) -> tuple[str, list[Block]]:
    looks_markdown = bool(re.search(r"^(#{1,6}\s|[-*]\s|>\s|```)", text, flags=re.MULTILINE))
    blocks = blocks_from_markdown(text) if looks_markdown else blocks_from_plain_text(text)
    first_block = next((b["text"] for b in blocks), "Văn bản dán vào")
    first = (split_sentences(first_block) or [first_block])[0].rstrip(".!?…:; ")
    return title_from_blocks(blocks, first[:70] + ("..." if len(first) > 70 else "")), blocks


# ---------------------------------------------------------------- sentences

ABBREVIATIONS = {
    "tp", "tt", "q", "p", "ts", "ths", "pgs", "gs", "bs", "ks", "cn", "ng", "st", "mr", "mrs", "ms", "dr",
    "vs", "e.g", "i.e", "v.v", "vv", "no", "fig", "vol", "tr", "ch", "sđt", "đ/c", "inc", "ltd", "co",
}
MAX_SENTENCE_CHARS = 240


def _is_break(text: str, end: int, next_start: int) -> bool:
    if next_start >= len(text):
        return True
    nxt = text[next_start]
    if not (nxt.isupper() or nxt.isdigit() or nxt in "\"“‘'([«•" or nxt in DASHES):
        return False
    punct = text[end - 1]
    if punct == ".":
        token = re.search(r"([\w./]+)\.$", text[:end])
        word = token.group(1).lower() if token else ""
        if word in ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
            return False
        if re.fullmatch(r"\d+", word) and nxt.isdigit():
            return False
    return True


def _split_long(sentence: str) -> list[str]:
    if len(sentence) <= MAX_SENTENCE_CHARS:
        return [sentence]
    middle = len(sentence) // 2
    best = -1
    for pattern in (r"[;:]\s", r",\s", r"\s(và|nhưng|hoặc|để|vì|nên|mà|and|but|or|which)\s", r"\s"):
        positions = [m.start() + 1 for m in re.finditer(pattern, sentence)
                     if 40 <= m.start() <= len(sentence) - 40]
        if positions:
            best = min(positions, key=lambda p: abs(p - middle))
            break
    if best <= 0:
        return [sentence]
    return _split_long(sentence[:best].strip()) + _split_long(sentence[best:].strip())


def split_sentences(text: str) -> list[str]:
    text = clean_inline(text)
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for match in re.finditer(r"([.!?…]+)[\"”’')\]»]*(\s+)", text):
        if _is_break(text, match.end(1), match.end()):
            piece = text[start:match.start(2)].strip()
            if piece:
                sentences.append(piece)
            start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    merged: list[str] = []
    for piece in sentences:
        if merged and (len(piece) < 3 or not re.search(r"\w", piece)):
            merged[-1] += " " + piece
        else:
            merged.append(piece)
    result: list[str] = []
    for piece in merged:
        result.extend(_split_long(piece))
    return result
