"""文件库层：知识库文件夹是唯一事实来源，索引只是它的投影。"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from . import config, extract, textutil
from .index import Index

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CATEGORY_MAX = 48


def safe_category(name: str) -> str:
    name = (name or "").strip().replace("\\", "/")
    name = "/".join(part for part in name.split("/") if part not in {"", ".", ".."})
    name = ILLEGAL.sub("_", name).strip(" .")
    return name[:CATEGORY_MAX]


def safe_filename(name: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = ILLEGAL.sub("_", name).strip(" .")
    if not name:
        name = "untitled-" + time.strftime("%Y%m%d-%H%M%S")
    stem, dot, suffix = name.rpartition(".")
    if dot and len(stem) > 80:
        name = stem[:80] + "." + suffix
    elif len(name) > 100:
        name = name[:100]
    return name


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"


class Library:
    def __init__(self, index: Index, root: Path | None = None) -> None:
        self.index = index
        self.root = Path(root or config.KB_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 路径工具

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def abs_path(self, rel_path: str) -> Path:
        rel_path = (rel_path or "").replace("\\", "/").lstrip("/")
        target = (self.root / rel_path).resolve()
        root = self.root.resolve()
        if root != target and root not in target.parents:
            raise ValueError("路径越界")
        return target

    def unique_path(self, category: str, filename: str) -> Path:
        folder = self.root / category if category else self.root
        folder.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(filename)
        candidate = folder / filename
        if not candidate.exists() and self.index.find_by_path(self.rel(candidate)) is None:
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for i in range(2, 1000):
            alt = folder / f"{stem}-{i}{suffix}"
            if not alt.exists() and self.index.find_by_path(self.rel(alt)) is None:
                return alt
        return folder / f"{stem}-{int(time.time())}{suffix}"

    # ------------------------------------------------------------ 单文件索引

    def index_file(self, path: Path, *, force: bool = False, tags: str = "") -> dict | None:
        """提取、切片并写入索引；内容未变化时跳过。"""
        try:
            stat = path.stat()
            data = path.read_bytes()
        except OSError as exc:
            return {"path": self.rel(path), "status": "error", "error": str(exc)}

        digest = hashlib.sha256(data).hexdigest()
        rel_path = self.rel(path)
        existing = self.index.find_by_path(rel_path)
        if (
            not force
            and existing
            and existing["sha256"] == digest
            and abs(existing["mtime"] - stat.st_mtime) < 0.001
        ):
            return {"path": rel_path, "action": "skipped", "id": existing["id"]}

        text, status = extract.extract_text(path, data)
        text = text.replace("\x00", " ") if text else ""
        title = self._guess_title(path, text)
        chunks = extract.split_chunks(text)
        if not chunks:
            # 纯二进制或空文件：用文件名/路径作一条可检索记录
            chunks = [{"heading": "", "content": f"{path.stem}\n{rel_path}"}]

        category = rel_path.split("/")[0] if "/" in rel_path else ""
        result = self.index.upsert_document(
            path=rel_path,
            category=category,
            title=title,
            ext=path.suffix.lower(),
            size=len(data),
            mtime=stat.st_mtime,
            sha256=digest,
            tags=tags,
            status=status,
            text=text,
            chunks=chunks,
        )
        result["path"] = rel_path
        result["title"] = title
        return result

    def _guess_title(self, path: Path, text: str) -> str:
        # 表格的「## sheet」是结构标记，不是标题，直接用文件名
        if path.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}:
            return path.stem.replace("_", " ").strip()[:120] or path.name
        if path.suffix.lower() in {".md", ".markdown", ".mdx", ".docx", ".html", ".htm"}:
            for line in (text or "").splitlines()[:40]:
                m = textutil.HEADING_RE.match(line)
                if m:
                    return m.group(1).strip()[:120]
        name = path.stem if path.suffix else path.name
        return name.replace("_", " ").replace("-", " ").strip()[:120] or path.name

    # ------------------------------------------------------------ 上传 / 删除

    def add_file(self, filename: str, data: bytes, category: str = "", tags: str = "") -> dict:
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ValueError(f"文件超过上限 {human_size(config.MAX_UPLOAD_BYTES)}")
        category = safe_category(category)
        target = self.unique_path(category, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        result = self.index_file(target, force=True, tags=tags) or {}
        doc = self.index.find_by_path(self.rel(target))
        return {
            "path": self.rel(target),
            "id": doc["id"] if doc else None,
            "title": doc["title"] if doc else target.name,
            "status": doc["status"] if doc else "unknown",
            "action": result.get("action", "created"),
        }

    def delete_document(self, doc_id: int) -> bool:
        doc = self.index.get_document(doc_id)
        if not doc:
            return False
        try:
            path = self.abs_path(doc["path"])
            if path.exists() and path.is_file():
                path.unlink()
        except (OSError, ValueError):
            pass
        self.index.delete_document(doc_id)
        return True

    # ------------------------------------------------------------ 目录扫描

    def scan(self, force: bool = False) -> dict:
        live_keys: set[str] = set()
        created = updated = skipped = failed = 0
        started = time.perf_counter()
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            parts = path.relative_to(self.root).parts
            if any(p in config.IGNORED_DIRS for p in parts[:-1]):
                continue
            if path.name in config.IGNORED_FILES or path.name.startswith("~$"):
                continue
            rel_key = self.rel(path).lower()
            live_keys.add(rel_key)
            try:
                result = self.index_file(path, force=force)
            except Exception as exc:  # 单文件失败不应中断整库扫描
                failed += 1
                continue
            action = (result or {}).get("action", "created")
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        removed = self.index.prune_missing(live_keys)
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "removed": len(removed),
            "removed_paths": removed,
            "scanned": len(live_keys),
            "took_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    # ------------------------------------------------------------ 展示用数据

    def tree(self) -> list[dict]:
        docs = self.index.all_documents()
        buckets: dict[str, list[dict]] = {}
        for doc in docs:
            buckets.setdefault(doc["category"] or "", []).append(
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "path": doc["path"],
                    "ext": doc["ext"],
                    "size": doc["size"],
                    "size_h": human_size(doc["size"]),
                    "tags": [t for t in (doc["tags"] or "").split(",") if t],
                    "updated_at": doc["updated_at"],
                    "status": doc["status"],
                }
            )
        groups = []
        for name, items in buckets.items():
            items.sort(key=lambda d: d["title"].lower())
            groups.append(
                {
                    "name": name or "未分类",
                    "key": name,
                    "count": len(items),
                    "docs": items,
                }
            )
        groups.sort(key=lambda g: (g["key"] != "", g["key"].lower()))
        return groups

    def detail(self, doc_id: int) -> dict | None:
        doc = self.index.get_document(doc_id)
        if not doc:
            return None
        chunks = self.index.get_chunks(doc_id)
        text = "\n\n".join(c["content"] for c in chunks)
        truncated = len(text) > config.DOC_PREVIEW_LIMIT
        doc.update(
            {
                "size_h": human_size(doc["size"]),
                "tags": [t for t in (doc["tags"] or "").split(",") if t],
                "content": text[: config.DOC_PREVIEW_LIMIT],
                "truncated": truncated,
                "chunks": [{"heading": c["heading"], "chars": len(c["content"])} for c in chunks],
            }
        )
        return doc

    def raw_bytes(self, doc_id: int) -> tuple[bytes, str] | None:
        doc = self.index.get_document(doc_id)
        if not doc:
            return None
        try:
            path = self.abs_path(doc["path"])
            return path.read_bytes(), path.name
        except (OSError, ValueError):
            return None
