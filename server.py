"""zero-dependency HTTP 服务：静态界面 + JSON API。

启动：
    python server.py [--port 8777] [--host 127.0.0.1] [--no-scan]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from kbcore import config
from kbcore import params as params_mod
from kbcore.graph import build_graph
from kbcore.index import Index
from kbcore.library import Library, safe_category, safe_filename

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("application/javascript", ".js")

INDEX = Index(config.DB_PATH)
LIB = Library(INDEX, config.KB_DIR)
SCAN_LOCK = threading.Lock()


# --------------------------------------------------------------------- 工具


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


MULTIPART_RE = re.compile(r'boundary=(?:"([^"]+)"|([^;\s]+))', re.I)


def parse_multipart(body: bytes, content_type: str) -> list[dict]:
    """最小可用的 multipart/form-data 解析器（文件 + 文本字段）。"""
    match = MULTIPART_RE.search(content_type or "")
    if not match:
        raise ValueError("缺少 multipart boundary")
    boundary = (match.group(1) or match.group(2)).encode("latin-1")
    delimiter = b"--" + boundary
    parts: list[dict] = []
    for raw in body.split(delimiter):
        if not raw or raw.startswith(b"--"):
            continue
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        if b"\r\n\r\n" not in raw:
            continue
        head, data = raw.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers: dict[str, str] = {}
        for line in head.decode("utf-8", "replace").split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        name_m = re.search(r'name="([^"]*)"', disposition)
        file_m = re.search(r'filename="([^"]*)"', disposition)
        parts.append(
            {
                "name": name_m.group(1) if name_m else "",
                "filename": file_m.group(1) if file_m else None,
                "data": data,
            }
        )
    return parts


class Handler(BaseHTTPRequestHandler):
    server_version = "LittleKb/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- 基础响应

    def log_message(self, fmt: str, *args) -> None:  # 静音默认日志
        if getattr(self.server, "verbose", False):
            sys.stderr.write("[%s] %s\n" % (self.address_string(), fmt % args))

    def send_body(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, payload: object, status: int = 200) -> None:
        self.send_body(status, json_bytes(payload), "application/json; charset=utf-8")

    def fail(self, status: int, message: str) -> None:
        self.send_json({"error": message, "status": status}, status)

    # ------------------------------------------------------------- 分发

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_HEAD(self) -> None:
        self._dispatch("GET")

    def _dispatch(self, method: str) -> None:
        try:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            if path.startswith("/api/"):
                self._api(method, path[len("/api/"):].rstrip("/"), query)
            elif method in {"GET", "HEAD"}:
                self._static(path)
            else:
                self.fail(405, "方法不被支持")
        except BrokenPipeError:
            pass
        except Exception as exc:  # 兜底，避免线程崩溃无响应
            traceback.print_exc()
            try:
                self.fail(500, f"服务端错误：{exc}")
            except Exception:
                pass

    # ------------------------------------------------------------- API

    def _api(self, method: str, route: str, query: dict) -> None:
        doc_match = re.fullmatch(r"doc/(\d+)", route)
        raw_match = re.fullmatch(r"doc/(\d+)/raw", route)

        if method == "GET" and route == "health":
            return self.send_json({"ok": True, "service": "little-kb", "version": "1.0.0"})

        if method == "GET" and route == "config":
            return self.send_json(
                {
                    "kb_dir": str(config.KB_DIR),
                    "db_path": str(config.DB_PATH),
                    "chunk_size": config.CHUNK_SIZE,
                    "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
                }
            )

        if method == "GET" and route == "stats":
            stats = INDEX.stats()
            stats["kb_dir"] = str(config.KB_DIR)
            return self.send_json(stats)

        if method == "GET" and route == "tree":
            return self.send_json({"groups": LIB.tree()})

        if method == "GET" and route == "param":
            name = (query.get("name") or [""])[0].strip()
            keyword = (query.get("q") or [""])[0].strip()
            with INDEX.connection() as conn:
                if name:
                    return self.send_json({"name": name, "records": params_mod.lookup(conn, name)})
                return self.send_json({"q": keyword, "records": params_mod.search(conn, keyword, limit=50)})

        if method == "GET" and route == "graph":
            max_docs = max(1, min(int((query.get("docs") or ["250"])[0] or 250), 1000))
            terms = max(1, min(int((query.get("terms") or ["6"])[0] or 6), 12))
            return self.send_json(build_graph(INDEX, max_docs=max_docs, terms_per_doc=terms))

        if method == "GET" and route == "search":
            q = (query.get("q") or [""])[0]
            limit = max(1, min(int((query.get("limit") or ["20"])[0] or 20), 60))
            category = (query.get("category") or [None])[0]
            if category == "all":
                category = None
            if not q.strip():
                return self.send_json(
                    {"query": "", "terms": [], "mode": "empty", "took_ms": 0, "total": 0, "hits": []}
                )
            return self.send_json(INDEX.search(q, limit=limit, category=category))

        if method == "GET" and doc_match:
            detail = LIB.detail(int(doc_match.group(1)))
            if not detail:
                return self.fail(404, "文档不存在")
            return self.send_json(detail)

        if method == "GET" and raw_match:
            payload = LIB.raw_bytes(int(raw_match.group(1)))
            if not payload:
                return self.fail(404, "文件不存在")
            data, name = payload
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            disposition = f"inline; filename*=UTF-8''{quote(name, safe='')}"
            return self.send_body(200, data, ctype, {"Content-Disposition": disposition})

        if method == "PATCH" and doc_match:
            body = self._read_json()
            ok = INDEX.update_meta(
                int(doc_match.group(1)),
                title=body.get("title"),
                tags=body.get("tags"),
            )
            if not ok:
                return self.fail(404, "文档不存在")
            return self.send_json({"ok": True, "doc": LIB.detail(int(doc_match.group(1)))})

        if method == "DELETE" and doc_match:
            ok = LIB.delete_document(int(doc_match.group(1)))
            return self.send_json({"ok": ok}) if ok else self.fail(404, "文档不存在")

        if method == "POST" and route == "upload":
            return self._upload()

        if method == "POST" and route == "note":
            return self._note()

        if method == "POST" and route == "reindex":
            return self._reindex()

        return self.fail(404, f"未知接口 /api/{route}")

    def _upload(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self.fail(400, "请求体为空")
        if length > config.MAX_UPLOAD_BYTES + 1024 * 1024:
            return self.fail(413, "上传体积超过上限")
        body = self.rfile.read(length)
        try:
            parts = parse_multipart(body, self.headers.get("Content-Type", ""))
        except ValueError as exc:
            return self.fail(400, str(exc))

        category = ""
        tags = ""
        files: list[dict] = []
        for part in parts:
            if part["filename"] is not None and part["filename"] != "":
                files.append(part)
            elif part["name"] == "category":
                category = part["data"].decode("utf-8", "replace")
            elif part["name"] == "tags":
                tags = part["data"].decode("utf-8", "replace")

        if not files:
            return self.fail(400, "没有收到文件")

        added, errors = [], []
        for part in files:
            filename = part["filename"].replace("\\", "/").split("/")[-1]
            try:
                added.append(LIB.add_file(filename, part["data"], category=category, tags=tags))
            except Exception as exc:
                errors.append({"file": filename, "error": str(exc)})
        return self.send_json({"ok": not errors, "added": added, "errors": errors,
                              "stats": INDEX.stats()})

    def _note(self) -> None:
        """给 Agent 用的记忆写入接口：一句话/一段笔记直接沉淀为 Markdown。"""
        body = self._read_json()
        title = (body.get("title") or "").strip()
        content = (body.get("content") or "").strip()
        if not content and not title:
            return self.fail(400, "title 与 content 至少提供一个")
        category = safe_category(body.get("category") or "记忆")
        tags = (body.get("tags") or "").strip()
        if not title:
            title = content.splitlines()[0][:40]
        text = content if content.startswith("#") else f"# {title}\n\n{content}\n"
        if not text.endswith("\n"):
            text += "\n"
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text += f"\n---\n\n写入时间：{stamp}\n"
        filename = safe_filename(title.replace("/", "-").replace("\\", "-")[:80] + ".md")
        try:
            added = LIB.add_file(filename, text.encode("utf-8"), category=category, tags=tags)
        except Exception as exc:
            return self.fail(500, f"写入失败：{exc}")
        return self.send_json({"ok": True, "doc": added, "stats": INDEX.stats()})

    def _reindex(self) -> None:
        if not SCAN_LOCK.acquire(timeout=30):
            return self.fail(429, "重建索引正在进行中")
        try:
            result = LIB.scan(force=True)
        finally:
            SCAN_LOCK.release()
        return self.send_json({"ok": True, "result": result, "stats": INDEX.stats()})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ------------------------------------------------------------- 静态文件

    def _static(self, path: str) -> None:
        if path in {"", "/"}:
            target = config.WEB_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            if rel.startswith("assets/"):
                rel = rel[len("assets/"):]
            target = (config.WEB_DIR / rel).resolve()
            web_root = config.WEB_DIR.resolve()
            if web_root != target and web_root not in target.parents:
                return self.fail(403, "禁止访问")
        if not target.exists() or not target.is_file():
            return self.send_body(404, b"Not Found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in {"application/javascript", "application/json"}:
            ctype += "; charset=utf-8"
        self.send_body(200, target.read_bytes(), ctype)


# --------------------------------------------------------------------- 启动


def pick_port(host: str, wanted: int, attempts: int) -> int:
    """探测可用端口。

    注意：Windows 上 SO_REUSEADDR 允许重复绑定同一端口，所以这里不设置它，
    否则会误判端口空闲。真正的绑定在 main() 里带重试完成。
    """
    for port in range(wanted, wanted + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"端口 {wanted}~{wanted + attempts - 1} 全部被占用")


def serve(host: str, wanted: int) -> ThreadingHTTPServer:
    """在 wanted 起始的端口段内找到一个能真正绑定的端口。"""
    start = pick_port(host, wanted, config.PORT_SCAN)
    last_error: Exception | None = None
    for port in range(start, wanted + config.PORT_SCAN):
        try:
            return ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:  # 竞态：探测时可用，绑定时被抢占
            last_error = exc
            continue
    raise SystemExit(f"端口绑定失败：{last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Little KB — 本地文件夹知识库")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    parser.add_argument("--no-scan", action="store_true", help="启动时不扫描知识库目录")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.no_scan:
        with SCAN_LOCK:
            result = LIB.scan()
        print(
            f"索引完成：新增 {result['created']} / 更新 {result['updated']} / "
            f"跳过 {result['skipped']} / 移除 {result['removed']}，用时 {result['took_ms']} ms",
            flush=True,
        )

    server = serve(args.host, args.port)
    port = server.server_address[1]
    server.daemon_threads = True
    server.verbose = args.verbose

    try:
        (config.DATA_DIR / "kb.port").write_text(str(port), encoding="utf-8")
    except OSError:
        pass

    url = f"http://{args.host}:{port}"
    print(f"知识库已启动：{url}", flush=True)
    print(f"知识库目录：{config.KB_DIR}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
