"""索引层：SQLite（元数据 + 切片）与 FTS5（全文）读写、检索、统计。"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from . import textutil

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL,
    path_key    TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    ext         TEXT NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL DEFAULT 0,
    sha256      TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'indexed',
    note        TEXT NOT NULL DEFAULT '',
    chars       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT '',
    indexed_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL DEFAULT 0,
    heading     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    body,
    tokenize = "unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS params (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle       TEXT NOT NULL,
    name          TEXT NOT NULL,
    value         TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    desc          TEXT NOT NULL DEFAULT '',
    hint          TEXT NOT NULL DEFAULT '',
    default_value TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT '',
    doc_id        INTEGER,
    UNIQUE(vehicle, name)
);

CREATE INDEX IF NOT EXISTS idx_params_name ON params(name);

CREATE TABLE IF NOT EXISTS param_dict (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL DEFAULT '',
    meaning     TEXT NOT NULL DEFAULT '',
    hint        TEXT NOT NULL DEFAULT '',
    vehicles    TEXT NOT NULL DEFAULT '',
    standard    INTEGER NOT NULL DEFAULT 0,
    renamed_to  TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT ''
);
"""


def now() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Index:
    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    # ---------------------------------------------------------------- 连接

    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def transaction(self):
        conn = self.connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------ 文档写入

    def upsert_document(
        self,
        *,
        path: str,
        category: str,
        title: str,
        ext: str,
        size: int,
        mtime: float,
        sha256: str,
        tags: str,
        status: str,
        text: str,
        chunks: list[dict],
    ) -> dict:
        """写入/更新一篇文档及其全文索引，返回 {action, id}。"""
        path_key = path.lower()
        stamp = now()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id, tags, created_at FROM documents WHERE path_key = ?", (path_key,)
            ).fetchone()
            action = "updated" if row else "created"
            if row:
                doc_id = row["id"]
                merged_tags = tags if tags else (row["tags"] or "")
                conn.execute(
                    """UPDATE documents SET path=?, category=?, title=?, ext=?, size=?, mtime=?,
                           sha256=?, tags=?, status=?, note=?, chars=?, updated_at=?, indexed_at=?
                       WHERE id=?""",
                    (
                        path, category, title, ext, size, mtime, sha256, merged_tags, status,
                        "已索引" if status == "text" else "仅按文件名检索",
                        len(text), stamp, stamp, doc_id,
                    ),
                )
                old_ids = [
                    r[0] for r in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))
                ]
                for cid in old_ids:
                    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            else:
                cur = conn.execute(
                    """INSERT INTO documents
                       (path, path_key, category, title, ext, size, mtime, sha256, tags, status,
                        note, chars, created_at, updated_at, indexed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        path, path_key, category, title, ext, size, mtime, sha256, tags, status,
                        "已索引" if status == "text" else "仅按文件名检索",
                        len(text), stamp, stamp, stamp,
                    ),
                )
                doc_id = int(cur.lastrowid)

            for i, chunk in enumerate(chunks):
                cur = conn.execute(
                    "INSERT INTO chunks (document_id, ord, heading, content) VALUES (?,?,?,?)",
                    (doc_id, i, chunk.get("heading", ""), chunk["content"]),
                )
                chunk_id = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO chunks_fts (rowid, body) VALUES (?, ?)",
                    (chunk_id, textutil.prep(chunk["content"])),
                )
        return {"action": action, "id": doc_id}

    def update_meta(self, doc_id: int, *, title: str | None = None, tags: str | None = None) -> bool:
        sets, args = [], []
        if title is not None:
            sets.append("title = ?")
            args.append(title.strip())
        if tags is not None:
            sets.append("tags = ?")
            args.append(tags.strip())
        if not sets:
            return False
        args.append(doc_id)
        with self.transaction() as conn:
            cur = conn.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = ?", args)
            return cur.rowcount > 0

    def delete_document(self, doc_id: int) -> dict | None:
        with self.transaction() as conn:
            row = conn.execute("SELECT id, path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))]
            for cid in ids:
                conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return {"id": row["id"], "path": row["path"]}

    def prune_missing(self, live_keys: set[str]) -> list[str]:
        """删除磁盘上已不存在的文档记录，返回被清掉的路径。"""
        removed: list[str] = []
        with self.transaction() as conn:
            rows = conn.execute("SELECT id, path, path_key FROM documents").fetchall()
            for row in rows:
                if row["path_key"] in live_keys:
                    continue
                ids = [r[0] for r in conn.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (row["id"],)
                )]
                for cid in ids:
                    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (row["id"],))
                conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
                removed.append(row["path"])
        return removed

    # ---------------------------------------------------------------- 读取

    def get_document(self, doc_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            doc = dict(row)
            doc["chunk_count"] = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,)
            ).fetchone()[0]
        return doc

    def get_chunks(self, doc_id: int) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT ord, heading, content FROM chunks WHERE document_id = ? ORDER BY ord",
                (doc_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_by_path(self, path: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE path_key = ?", (path.lower(),)
            ).fetchone()
        return dict(row) if row else None

    def all_documents(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, path, path_key, category, title, ext, size, mtime, sha256, tags,"
                " status, chars, updated_at FROM documents ORDER BY category, title"
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self.connection() as conn:
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            size = conn.execute("SELECT COALESCE(SUM(size),0) FROM documents").fetchone()[0]
            chars = conn.execute("SELECT COALESCE(SUM(chars),0) FROM documents").fetchone()[0]
            cats = conn.execute(
                "SELECT category, COUNT(*) c, COALESCE(SUM(size),0) s FROM documents"
                " GROUP BY category ORDER BY c DESC, category"
            ).fetchall()
            kinds = conn.execute(
                "SELECT ext, COUNT(*) c FROM documents GROUP BY ext ORDER BY c DESC LIMIT 12"
            ).fetchall()
        return {
            "documents": docs,
            "chunks": chunks,
            "bytes": size,
            "chars": chars,
            "categories": [dict(r) for r in cats],
            "extensions": [dict(r) for r in kinds],
        }

    # ---------------------------------------------------------------- 检索

    def search(self, query: str, limit: int = 20, category: str | None = None) -> dict:
        terms = textutil.query_terms(query)
        if not terms:
            return {"query": query, "terms": [], "mode": "empty", "took_ms": 0,
                    "total": 0, "hits": []}

        import time

        started = time.perf_counter()
        rows, mode = self._run_fts(textutil.build_fts_query(terms, "strict"), category, limit * 6), "strict"
        if not rows:
            loose = textutil.build_fts_query(terms, "loose")
            if loose:
                rows, mode = self._run_fts(loose, category, limit * 6), "loose"
        if not rows and any(len(t) > 2 for t in terms):
            broad = textutil.build_fts_query(terms, "broad")
            if broad:
                rows, mode = self._run_fts(broad, category, limit * 6), "broad"

        hits: dict[int, dict] = {}
        for row in rows:
            doc_id = row["document_id"]
            score = -float(row["score"])
            title_lc = (row["title"] or "").lower()
            path_lc = (row["path"] or "").lower()
            for term in terms:
                t = term.lower()
                if t in title_lc:
                    score += 2.5
                elif t in path_lc:
                    score += 1.0
            if doc_id not in hits or score > hits[doc_id]["score"]:
                hits[doc_id] = {
                    "id": doc_id,
                    "title": row["title"],
                    "path": row["path"],
                    "category": row["category"],
                    "ext": row["ext"],
                    "size": row["size"],
                    "updated_at": row["updated_at"],
                    "tags": row["tags"],
                    "score": round(score, 4),
                    "snippet": textutil.make_snippet(row["content"], terms),
                    "heading": row["heading"],
                }
            else:
                hits[doc_id]["snippet"] = hits[doc_id]["snippet"] or textutil.make_snippet(
                    row["content"], terms
                )

        # 文件名 / 标签命中，即使正文里没有这些字也要出现
        for doc in self._meta_hits(terms, category):
            if doc["id"] in hits:
                hits[doc["id"]]["score"] += 1.5
                continue
            hits[doc["id"]] = {
                "id": doc["id"],
                "title": doc["title"],
                "path": doc["path"],
                "category": doc["category"],
                "ext": doc["ext"],
                "size": doc["size"],
                "updated_at": doc["updated_at"],
                "tags": doc["tags"],
                "score": 1.0,
                "snippet": "文件名/标签命中：" + textutil.highlight(doc["path"], terms),
                "heading": "",
            }

        if mode == "broad":
            # 自然语言提问：把查询拆成 2 字组合，标题/路径命中这些组合的文档优先
            grams: list[str] = []
            for term in terms:
                if textutil.is_cjk(term) and len(term) > 2:
                    grams.extend(term[i:i + 2] for i in range(len(term) - 1))
                else:
                    grams.append(term)
            for doc in self._meta_hits(dict.fromkeys(grams), category):
                if doc["id"] in hits:
                    hits[doc["id"]]["score"] += 6.0
                else:
                    hits[doc["id"]] = {
                        "id": doc["id"],
                        "title": doc["title"],
                        "path": doc["path"],
                        "category": doc["category"],
                        "ext": doc["ext"],
                        "size": doc["size"],
                        "updated_at": doc["updated_at"],
                        "tags": doc["tags"],
                        "score": 6.0,
                        "snippet": textutil.make_snippet(doc["title"] + " " + doc["path"], grams),
                        "heading": "",
                    }

        ordered = sorted(hits.values(), key=lambda h: h["score"], reverse=True)[:limit]
        if mode == "broad":
            # 自然语言提问时优先「知识页」，原始大表往后放
            for hit in ordered:
                if "知识库" in (hit.get("path") or ""):
                    hit["score"] = round(hit["score"] + 4.0, 4)
                elif (hit.get("ext") or "") in {".xlsx", ".xls", ".csv"}:
                    hit["score"] = round(hit["score"] - 2.0, 4)
            ordered.sort(key=lambda h: h["score"], reverse=True)
        return {
            "query": query,
            "terms": terms,
            "mode": mode if ordered else "none",
            "took_ms": round((time.perf_counter() - started) * 1000, 2),
            "total": len(hits),
            "hits": ordered,
        }

    def _run_fts(self, expr: str, category: str | None, limit: int) -> list[sqlite3.Row]:
        if not expr:
            return []
        sql = (
            "SELECT c.id AS chunk_id, c.document_id, c.heading, c.content,"
            "       bm25(chunks_fts) AS score,"
            "       d.title, d.path, d.category, d.ext, d.size, d.tags, d.updated_at"
            "  FROM chunks_fts"
            "  JOIN chunks c ON c.id = chunks_fts.rowid"
            "  JOIN documents d ON d.id = c.document_id"
            " WHERE chunks_fts MATCH ?"
        )
        args: list[Any] = [expr]
        if category is not None:
            sql += " AND d.category = ?"
            args.append(category)
        sql += " ORDER BY score LIMIT ?"
        args.append(int(limit))
        try:
            with self.connection() as conn:
                return conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []

    def _meta_hits(self, terms: Iterable[str], category: str | None) -> list[dict]:
        clauses, args = [], []
        for term in terms:
            like = f"%{term.lower()}%"
            clauses.append("(lower(title) LIKE ? OR lower(path) LIKE ? OR lower(tags) LIKE ?)")
            args.extend([like, like, like])
        if not clauses:
            return []
        sql = f"SELECT * FROM documents WHERE ({' OR '.join(clauses)})"
        if category is not None:
            sql += " AND category = ?"
            args.append(category)
        sql += " LIMIT 50"
        with self.connection() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]


