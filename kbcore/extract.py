"""文本提取与切片：把各种文件变成可检索的纯文本。"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from . import config
from .textutil import HEADING_RE

TEXT_EXTS = {
    ".md", ".markdown", ".mdx", ".txt", ".text", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".sql", ".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".css",
    ".scss", ".less", ".html", ".htm", ".xml", ".svg", ".sh", ".ps1", ".bat",
    ".cmd", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cc", ".rb",
    ".php", ".lua", ".tex", ".r", ".kt", ".swift", ".gitignore", ".dockerfile",
}

OPAQUE_EXTS = {
    ".pdf", ".doc", ".ppt", ".xls", ".pptx", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".bmp", ".ico", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp3", ".mp4", ".wav", ".mov", ".avi", ".exe", ".dll", ".bin", ".psd",
}

DECODE_ORDER = ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1")


def decode_bytes(data: bytes) -> str:
    for enc in DECODE_ORDER:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n\s*", "\n\n", raw)
        return raw.strip()


def html_to_text(markup: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(markup)
        return parser.text()
    except Exception:  # 畸形 HTML 不阻断索引
        return re.sub(r"<[^>]+>", " ", markup)


def docx_to_text(data: bytes) -> str:
    try:
        import io

        from docx import Document

        doc = Document(io.BytesIO(data))
    except Exception:
        return ""
    parts: list[str] = []
    for para in doc.paragraphs:
        style = (para.style.name or "") if para.style is not None else ""
        text = para.text.strip()
        if not text:
            continue
        lowered = style.lower()
        if lowered.startswith("heading") or style.startswith("标题"):
            digits = "".join(ch for ch in style if ch.isdigit())
            level = min(int(digits), 6) if digits else 2
            parts.append("#" * level + " " + text)
        else:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def xlsx_to_text(data: bytes, max_rows: int = 6000, max_chars: int = 800_000) -> str:
    """把工作簿按 sheet 展开成「单元格 | 单元格」的文本行，便于全文检索。"""
    try:
        import io

        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception:
        return ""
    parts: list[str] = []
    total = 0
    for sheet in book.worksheets:
        parts.append(f"## {sheet.title}")
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= max_rows:
                parts.append(f"（本表仅索引前 {max_rows} 行）")
                break
            cells = ["" if value is None else str(value).strip() for value in row]
            while cells and not cells[-1]:
                cells.pop()
            if not cells:
                continue
            line = " | ".join(cells)
            parts.append(line)
            total += len(line)
            if total > max_chars:
                parts.append("（内容超长，已截断）")
                return "\n".join(parts)
    try:
        book.close()
    except Exception:
        pass
    return "\n".join(parts)


def extract_text(path: Path, data: bytes) -> tuple[str, str]:
    """返回 (文本, 状态说明)。

    状态：'text' 已提取正文 / 'name-only' 只能按文件名检索 / 'binary' 未知二进制。
    """
    ext = path.suffix.lower()
    name_lower = path.name.lower()

    if ext == ".docx":
        text = docx_to_text(data)
        return (text, "text") if text.strip() else ("", "name-only")

    if ext in {".xlsx", ".xlsm"}:
        text = xlsx_to_text(data)
        return (text, "text") if text.strip() else ("", "name-only")

    if ext in {".html", ".htm"}:
        text = html_to_text(decode_bytes(data))
        return (text, "text") if text.strip() else ("", "name-only")

    if ext in {".md", ".markdown", ".mdx"}:
        return decode_bytes(data), "text"

    if ext in TEXT_EXTS or name_lower in {"dockerfile", "makefile", ".gitignore", ".env"}:
        return decode_bytes(data), "text"

    if ext in OPAQUE_EXTS:
        # 二进制无法直接抽文本时，尝试一次宽松解码，挑出可读片段
        guess = _printable_only(data)
        return (guess, "text") if len(guess) > 80 else ("", "name-only")

    guess = _printable_only(data)
    if len(guess) > 80:
        return guess, "text"
    return "", "binary"


def _printable_only(data: bytes) -> str:
    try:
        decoded = decode_bytes(data)
    except Exception:
        return ""
    cleaned = "".join(ch if (ch.isprintable() or ch in "\n\t") else " " for ch in decoded)
    return re.sub(r"[ ]{3,}", " ", cleaned).strip()


def split_chunks(text: str, size: int | None = None) -> list[dict]:
    """按 Markdown 标题分节，再按段落装箱，返回 [{heading, content}]。"""
    size = size or config.CHUNK_SIZE
    hard = config.CHUNK_HARD_LIMIT
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    sections: list[tuple[str, list[str]]] = []
    heading = ""
    buf: list[str] = []
    for line in text.split("\n"):
        m = textutil_heading(line)
        if m:
            if buf:
                sections.append((heading, buf))
            heading = m
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append((heading, buf))

    chunks: list[dict] = []
    for sec_heading, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        for piece in _pack(body, size, hard):
            chunks.append({"heading": sec_heading, "content": piece})
    return chunks


def textutil_heading(line: str) -> str:
    """若该行是 Markdown 标题，返回标题文本，否则返回空串。"""
    m = HEADING_RE.match(line)
    return m.group(1).strip() if m else ""


def _pack(body: str, size: int, hard: int) -> list[str]:
    """段落装箱：尽量凑满 size，单片不超过 hard。"""
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    out: list[str] = []
    cur = ""
    for para in paragraphs:
        if len(para) > hard:
            if cur.strip():
                out.append(cur.strip())
                cur = ""
            for i in range(0, len(para), size):
                out.append(para[i : i + size].strip())
            continue
        if len(cur) + len(para) + 2 <= size:
            cur = (cur + "\n\n" + para) if cur else para
        else:
            if cur.strip():
                out.append(cur.strip())
            cur = para
    if cur.strip():
        out.append(cur.strip())
    return [c for c in out if c]
