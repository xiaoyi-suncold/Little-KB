"""Little KB 的命令行入口：让 Agent 直接读写这个知识库（不依赖 Web 服务）。

用法：
  python scripts/kb.py note "标题" "正文" --category 记忆 --tags 学习,结论
  python scripts/kb.py search "检索 原理" --limit 5
  python scripts/kb.py digest 12            # 文档大纲，快速消化一篇长文
  python scripts/kb.py show 12 --chars 4000 # 看正文
  python scripts/kb.py log "主题" "一句话结论" --source "文件/URL"
  python scripts/kb.py stats

不传正文时会从标准输入读取，例如：
  Get-Content draft.md | python scripts/kb.py note "读书笔记"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore import config  # noqa: E402
from kbcore import paramdict as paramdict_mod  # noqa: E402
from kbcore import params as params_mod  # noqa: E402
from kbcore.extract import decode_bytes  # noqa: E402
from kbcore.index import Index  # noqa: E402
from kbcore.keywords import extract_terms  # noqa: E402
from kbcore.library import Library, human_size, safe_category, safe_filename  # noqa: E402

CODE_FENCE = re.compile(r"^\s*```([A-Za-z0-9_+#-]*)", re.M)


def open_library() -> Library:
    return Library(Index(config.DB_PATH), config.KB_DIR)


def resolve_doc(index: Index, ref: str) -> dict | None:
    """ref 可以是文档 id，也可以是 kb 内的相对路径。"""
    if ref.isdigit():
        return index.get_document(int(ref))
    key = ref.replace("\\", "/").lstrip("/")
    if (config.KB_DIR / key).exists():
        return index.find_by_path(key)
    matches = [d for d in index.all_documents() if d["path"].endswith(key)]
    return matches[0] if matches else None


def cmd_note(args: argparse.Namespace) -> int:
    body = args.content
    if not body and not sys.stdin.isatty():
        body = sys.stdin.read()
    body = (body or "").strip()
    title = (args.title or "").strip() or (body.splitlines()[0][:40] if body else "")
    if not title:
        print("缺少标题或正文", file=sys.stderr)
        return 2

    category = safe_category(args.category or "记忆")
    lib = open_library()
    folder = lib.root / category
    folder.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(title.replace("/", "-").replace("\\", "-")[:80] + ".md")
    path = folder / filename

    stamp = time.strftime("%Y-%m-%d %H:%M")
    if path.exists():
        # 同一主题追加一个小节，避免重复文件
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n\n## 补充 {stamp}\n\n{body}\n")
        action = "append"
    else:
        text = f"# {title}\n\n{body}\n\n---\n\n写入时间：{stamp}\n"
        if args.tags:
            text = f"# {title}\n\n> 标签：{args.tags}\n\n{body}\n\n---\n\n写入时间：{stamp}\n"
        path.write_text(text, encoding="utf-8")
        action = "create"

    result = lib.index_file(path, force=True, tags=args.tags or "") or {}
    doc = lib.index.find_by_path(lib.rel(path)) or {}
    print(
        json.dumps(
            {
                "ok": True,
                "action": action,
                "path": lib.rel(path),
                "id": doc.get("id"),
                "title": doc.get("title"),
                "category": category,
                "chars": doc.get("chars"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    index = Index(config.DB_PATH)
    result = index.search(args.query, limit=args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"查询：{result['query']}  模式：{result['mode']}  命中 {result['total']} 篇  "
          f"{result['took_ms']} ms")
    for hit in result["hits"]:
        print(f"\n[{hit['id']}] {hit['title']}  ({hit['path']})  分数 {hit['score']}")
        snippet = hit.get("snippet", "")
        print("    " + snippet.replace("<mark>", "**").replace("</mark>", "**")[:300])
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    index = Index(config.DB_PATH)
    doc = resolve_doc(index, args.ref)
    if not doc:
        print(f"找不到文档：{args.ref}", file=sys.stderr)
        return 2
    chunks = index.get_chunks(doc["id"])
    text = "\n\n".join(c["content"] for c in chunks)
    terms = extract_terms(text, limit=10, exclude={doc["title"] or ""})
    langs: dict[str, int] = {}
    for lang in CODE_FENCE.findall(text):
        key = lang or "text"
        langs[key] = langs.get(key, 0) + 1

    lines = [
        f"# 文档消化：{doc['title']}",
        "",
        f"- 路径：`{doc['path']}`",
        f"- 分类：{doc['category'] or '未分类'}　状态：{doc['status']}　字数：{doc['chars']}　"
        f"切片：{len(chunks)}　占用：{human_size(doc['size'])}",
        f"- 标签：{doc['tags'] or '（无）'}",
    ]
    if terms:
        lines.append("- 关键词：" + "、".join(f"{t}({n})" for t, n in terms))
    if langs:
        lines.append("- 代码块：" + "、".join(f"{k}×{v}" for k, v in sorted(langs.items(), key=lambda kv: -kv[1])))
    lines += ["", "## 结构", ""]
    for i, chunk in enumerate(chunks):
        heading = chunk["heading"] or "（无标题段）"
        body = re.sub(r"\s+", " ", chunk["content"]).strip()
        if body.startswith("#"):
            body = re.sub(r"^#+\s*", "", body)
        lines.append(f"### [{i}] {heading} · {len(chunk['content'])} 字")
        lines.append("")
        lines.append("> " + body[: args.preview].strip() + ("…" if len(body) > args.preview else ""))
        lines.append("")

    lines += [
        "## 建议的阅读顺序",
        "",
        "1. 先看上面每个切片的首段，判断哪几节与当前问题相关；",
        f"2. 用 `python scripts/kb.py show {doc['id']} --chars 4000` 读正文；",
        f"3. 消化后写笔记：`python scripts/kb.py note \"{doc['title']} 要点\" \"…\" --category 笔记 --tags 学习`；",
        "4. 在笔记里回链原文路径，并在学习日志追加一行。",
        "",
    ]
    output = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"已写出 {args.out}（{len(output)} 字符）")
    else:
        print(output)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    index = Index(config.DB_PATH)
    doc = resolve_doc(index, args.ref)
    if not doc:
        print(f"找不到文档：{args.ref}", file=sys.stderr)
        return 2
    chunks = index.get_chunks(doc["id"])
    text = "\n\n".join(c["content"] for c in chunks)
    print(f"# {doc['title']}\n\n{text[: args.chars]}")
    if len(text) > args.chars:
        print(f"\n…（已截断，全文 {len(text)} 字符）")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """追加一行学习日志，并保持索引最新。"""
    lib = open_library()
    folder = lib.root / "记忆"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "学习日志.md"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if not path.exists():
        path.write_text("# 学习日志\n\n按时间倒序不重要，按时间正序追加即可。\n\n", encoding="utf-8")
    source = f"　来源：{args.source}" if args.source else ""
    entry = f"- **{stamp}** · {args.topic}{source}\n  - 结论：{args.summary}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    lib.index_file(path, force=True)
    doc = lib.index.find_by_path(lib.rel(path)) or {}
    print(json.dumps({"ok": True, "path": lib.rel(path), "id": doc.get("id")}, ensure_ascii=False))
    return 0


def cmd_param_import(args: argparse.Namespace) -> int:
    """把参数表（xlsx）拆成一行一个参数写进 params 表。"""
    index = Index(config.DB_PATH)
    paths = [Path(p) for p in args.paths] if args.paths else sorted(config.KB_DIR.rglob("*.xlsx"))
    if not paths:
        print("没有找到 xlsx", file=sys.stderr)
        return 2
    results = []
    with index.transaction() as conn:
        for path in paths:
            if not path.exists():
                print(f"跳过（不存在）：{path}", file=sys.stderr)
                continue
            doc = index.find_by_path(path.relative_to(config.KB_DIR).as_posix()) if path.is_relative_to(config.KB_DIR) else None
            info = params_mod.import_workbook(conn, path, doc_id=doc["id"] if doc else None)
            results.append(info)
    print(json.dumps({"ok": True, "imported": results}, ensure_ascii=False, indent=1))
    return 0


def cmd_param(args: argparse.Namespace) -> int:
    index = Index(config.DB_PATH)
    with index.connection() as conn:
        if args.keyword:
            rows = paramdict_mod.search(conn, args.keyword, limit=args.limit)
            if not rows:
                print("没有命中", file=sys.stderr)
                return 1
            for row in rows:
                print(f"[{row['vehicle']}] {row['name']} = {row['value']}  ({row['category']}) {row['desc'][:70]}")
            return 0
        rows = paramdict_mod.lookup(conn, args.name)
    if not rows:
        print(f"参数表里没有 {args.name}", file=sys.stderr)
        return 1
    for row in rows:
        print(f"\n[{row['vehicle']}] {row['name']} = {row['value']}"
              f"    默认 {row['default_value'] or '—'}    {row['category']}")
        print(f"  作用：{row['desc']}")
        print(f"  提示：{row['hint']}")
    return 0


def cmd_param_diff(args: argparse.Namespace) -> int:
    index = Index(config.DB_PATH)
    with index.connection() as conn:
        result = params_mod.diff(conn, args.a, args.b)
    print(f"{result['a']} ↔ {result['b']}")
    print(f"  仅 {result['a']}：{len(result['only_a'])} 条")
    print(f"  仅 {result['b']}：{len(result['only_b'])} 条")
    print(f"  值不同：{len(result['changed'])} 条")
    if args.show:
        for name in result["changed"][: args.show]:
            print("   ", name)
    return 0


def cmd_paramdoc(args: argparse.Namespace) -> int:
    """参数语义查询：参数的类别、作用、调参提示、改名关系。"""
    index = Index(config.DB_PATH)
    with index.connection() as conn:
        if args.category:
            rows = paramdict_mod.by_category(conn, args.category)
            if not rows:
                print("没有这个类别", file=sys.stderr)
                return 1
            for row in rows:
                print(f"{row['name']:<24} {row['meaning'][:70]}")
            return 0
        if args.keyword:
            rows = paramdict_mod.search(conn, args.keyword, limit=args.limit)
            for row in rows:
                flag = "" if row["note"] == "" else f"  [{row['note']}]"
                print(f"{row['name']:<24} ({row['category']}) {row['meaning'][:60]}{flag}")
            return 0
        record = paramdict_mod.lookup(conn, args.name)
    if not record:
        print(f"语义库里没有 {args.name}", file=sys.stderr)
        return 1
    print(f"{record['name']}  [{record['category']}]  标准参数: {'是' if record['standard'] else '否'}")
    print(f"  作用：{record['meaning']}")
    print(f"  提示：{record['hint'] or '—'}")
    if record["note"]:
        print(f"  备注：{record['note']}")
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    stats = Index(config.DB_PATH).stats()
    print(f"文档 {stats['documents']} 篇 · 切片 {stats['chunks']} 个 · 占用 {human_size(stats['bytes'])}")
    for group in stats["categories"]:
        print(f"  {group['category'] or '未分类'}: {group['c']} 篇")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Little KB 命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    note = sub.add_parser("note", help="写入一条笔记/记忆并建立索引")
    note.add_argument("title", nargs="?", default="")
    note.add_argument("content", nargs="?", default="")
    note.add_argument("--category", default="记忆")
    note.add_argument("--tags", default="")
    note.set_defaults(func=cmd_note)

    search = sub.add_parser("search", help="全文检索")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_search)

    digest = sub.add_parser("digest", help="输出文档大纲，用于快速消化长文")
    digest.add_argument("ref", help="文档 id 或 kb 内路径")
    digest.add_argument("--preview", type=int, default=180, help="每节预览字符数")
    digest.add_argument("--out", default="", help="写入文件而不是打印")
    digest.set_defaults(func=cmd_digest)

    show = sub.add_parser("show", help="打印文档正文")
    show.add_argument("ref")
    show.add_argument("--chars", type=int, default=6000)
    show.set_defaults(func=cmd_show)

    log = sub.add_parser("log", help="追加一条学习日志")
    log.add_argument("topic")
    log.add_argument("summary")
    log.add_argument("--source", default="")
    log.set_defaults(func=cmd_log)

    pimport = sub.add_parser("param-import", help="把 xlsx 参数表导入 params 表")
    pimport.add_argument("paths", nargs="*")
    pimport.set_defaults(func=cmd_param_import)

    param = sub.add_parser("param", help="按参数名精确查询（不带名字则按关键词搜索）")
    param.add_argument("name", nargs="?", default="")
    param.add_argument("--keyword", "-k", default="")
    param.add_argument("--limit", type=int, default=20)
    param.set_defaults(func=cmd_param)

    pdiff = sub.add_parser("param-diff", help="比较两个机型的参数")
    pdiff.add_argument("a")
    pdiff.add_argument("b")
    pdiff.add_argument("--show", type=int, default=0)
    pdiff.set_defaults(func=cmd_param_diff)

    pdoc = sub.add_parser("paramdoc", help="查参数语义（名字 / 类别 / 关键词）")
    pdoc.add_argument("name", nargs="?", default="")
    pdoc.add_argument("--category", default="")
    pdoc.add_argument("--keyword", "-k", default="")
    pdoc.add_argument("--limit", type=int, default=30)
    pdoc.set_defaults(func=cmd_paramdoc)

    stats = sub.add_parser("stats", help="知识库概况")
    stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
