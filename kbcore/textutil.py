"""文本工具：中文友好的 FTS5 预处理、查询解析、片段生成与高亮。

为什么需要预处理：
SQLite 的 unicode61 分词器把连续汉字当作一个 token，"知识库"就是一个词元，
所以搜"知识"永远命中不了。这里在**建索引时**把每个汉字用空格隔开，
搜索时把中文词转成由单字 token 组成的 phrase（"知 识 库"），
即可获得接近短语检索的效果，不需要任何分词词典或词嵌入。
"""

from __future__ import annotations

import html
import re

# 汉字 + 日文假名 + 韩文音节
CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af"
CJK_RE = re.compile(f"[{CJK}]")
TOKEN_RE = re.compile(f"[{CJK}]+|[A-Za-z0-9_][A-Za-z0-9_.'+\\-]*")

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def prep(text: str) -> str:
    """把每个 CJK 字符拆成独立 token，供 FTS5 索引。"""
    if not text:
        return ""
    return CJK_RE.sub(lambda m: f" {m.group(0)} ", text)


def is_cjk(token: str) -> bool:
    return bool(token) and CJK_RE.match(token[0]) is not None


def query_terms(q: str) -> list[str]:
    """把用户输入切成检索词：中文串整体保留，拉丁词按单词切分。"""
    terms: list[str] = []
    seen: set[str] = set()
    for m in TOKEN_RE.finditer(q or ""):
        tok = m.group(0).strip(".'+-")
        if not tok:
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(tok)
    return terms


def build_fts_query(terms: list[str], mode: str = "strict") -> str:
    """构造 FTS5 查询表达式。

    strict: 中文按字组成 phrase（要求连续出现），英文做前缀匹配。
    loose : 中文拆成单字 AND（允许中间插入其他字），用于 strict 无结果时兜底。
    broad : 中文拆成 2 字组合 OR，用于自然语言长句（「如何设计六轴」）。
    """
    parts: list[str] = []
    if mode == "broad":
        keys: list[str] = []
        for term in terms:
            if is_cjk(term):
                if len(term) <= 2:
                    keys.append('"' + " ".join(term) + '"')
                else:
                    keys.extend('"' + " ".join(term[i:i + 2]) + '"' for i in range(len(term) - 1))
            else:
                keys.append(f'"{term.replace(chr(34), chr(34) * 2)}"*')
        return " OR ".join(dict.fromkeys(keys))

    for term in terms:
        if is_cjk(term):
            if mode == "loose":
                parts.append(" AND ".join(f'"{ch}"' for ch in term))
            else:
                parts.append('"' + " ".join(term) + '"')
        else:
            escaped = term.replace('"', '""')
            parts.append(f'"{escaped}"*')
    return " AND ".join(p for p in parts if p)


def _hit_spans(text: str, terms: list[str]) -> list[tuple[int, int]]:
    """在原文中定位所有命中区间（不区分大小写），并合并重叠区间。"""
    if not terms:
        return []
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    for term in terms:
        needle = term.lower()
        if not needle:
            continue
        start = 0
        while True:
            idx = lowered.find(needle, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(needle)))
            start = idx + max(1, len(needle))
            if len(spans) > 400:
                break
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for a, b in spans[1:]:
        la, lb = merged[-1]
        if a <= lb:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def highlight(text: str, terms: list[str]) -> str:
    """把纯文本转成已转义的 HTML，命中处包 <mark>。"""
    spans = _hit_spans(text, terms)
    if not spans:
        return html.escape(text)
    out: list[str] = []
    cursor = 0
    for a, b in spans:
        out.append(html.escape(text[cursor:a]))
        out.append("<mark>" + html.escape(text[a:b]) + "</mark>")
        cursor = b
    out.append(html.escape(text[cursor:]))
    return "".join(out)


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMPATHY = (
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"\1"),
    (re.compile(r"__(.+?)__", re.S), r"\1"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S), r"\1"),
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", re.S), r"\1"),
)


def strip_markdown(text: str) -> str:
    """把 Markdown 记号去掉，用于生成干净的检索片段。"""
    text = _MD_LINK.sub(r"\1", text or "")
    for pattern, repl in _EMPATHY:
        text = pattern.sub(repl, text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}\d+[.)]\s+", "", text, flags=re.M)
    text = text.replace("`", "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    return text


def make_snippet(text: str, terms: list[str], width: int = 210) -> str:
    """围绕首个命中位置截取片段，返回带 <mark> 的 HTML。"""
    text = strip_markdown(text)
    text = re.sub(r"[ \t]+", " ", text)
    if not text.strip():
        return ""
    spans = _hit_spans(text, terms)
    if spans:
        pos = spans[0][0]
        start = max(0, pos - width // 3)
    else:
        start = 0
    end = min(len(text), start + width)
    fragment = text[start:end]
    if start > 0:
        fragment = "…" + fragment
    if end < len(text):
        fragment = fragment + "…"
    body = highlight(fragment, terms)
    return re.sub(r"\s*\n\s*", " ", body).strip()
