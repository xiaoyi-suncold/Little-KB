"""端到端冒烟测试：上传 → 检索 → 改标签 → 删除 → 重建索引。

用法：python scripts/smoke_test.py [http://127.0.0.1:8777]
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8777"
BOUNDARY = "----littlekb" + uuid.uuid4().hex


def post_json(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload(filename: str, content: str, category: str, tags: str = "") -> dict:
    body = bytearray()

    def field(name: str, value: str) -> None:
        body.extend(f"--{BOUNDARY}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    field("category", category)
    field("tags", tags)
    body.extend(f"--{BOUNDARY}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n".encode()
    )
    body.extend(content.encode("utf-8"))
    body.extend(b"\r\n")
    body.extend(f"--{BOUNDARY}--\r\n".encode())

    req = urllib.request.Request(
        BASE + "/api/upload", data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    marker = "量子纠缠" + uuid.uuid4().hex[:6]
    checks: list[tuple[str, bool, str]] = []

    print("1) 上传中文文件名的 Markdown")
    content = (
        f"# 冒烟测试文档\n\n这篇文档用来验证 {marker} 的检索链路，包含中文与 upload 英文词。\n\n"
        "## 小节\n\n- 列表项一\n- 列表项二\n"
    )
    result = upload("冒烟测试.md", content, "自动测试", tags="测试,冒烟")
    doc_id = result["added"][0]["id"]
    checks.append(("上传返回文档 id", bool(doc_id), f"id={doc_id}"))
    checks.append(("分类生效", result["added"][0]["path"].startswith("自动测试/"), result["added"][0]["path"]))

    print("2) 检索唯一词")
    hit = get_json("/api/search?q=" + urllib.parse.quote(marker))
    checks.append(("中文唯一词命中 1 篇", hit["total"] == 1, f"mode={hit['mode']} total={hit['total']}"))
    checks.append(("片段含高亮", "<mark>" in (hit["hits"][0]["snippet"] if hit["hits"] else ""), ""))

    print("3) 英文前缀检索")
    eng = get_json("/api/search?q=upload")
    checks.append(("英文前缀命中", eng["total"] >= 1, f"total={eng['total']}"))

    print("4) 标签检索")
    tag = get_json("/api/search?q=" + urllib.parse.quote("冒烟"))
    checks.append(("标签命中", any(h["id"] == doc_id for h in tag["hits"]), f"total={tag['total']}"))

    print("5) 修改标签")
    patch = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/api/doc/{doc_id}", method="PATCH",
                data=json.dumps({"tags": "已更新"}).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=10,
        ).read().decode("utf-8")
    )
    checks.append(("标签已更新", patch["doc"]["tags"] == ["已更新"], str(patch["doc"]["tags"])))

    print("6) 文档详情")
    detail = get_json(f"/api/doc/{doc_id}")
    checks.append(("详情含正文", marker in detail["content"], f"chars={len(detail['content'])}"))
    checks.append(("切片数 >= 2", len(detail["chunks"]) >= 2, f"chunks={len(detail['chunks'])}"))

    print("7) 重建索引")
    reindex = post_json("/api/reindex")
    checks.append(("重建索引成功", reindex.get("ok") is True, json.dumps(reindex["result"], ensure_ascii=False)[:120]))

    print("8) 删除文档")
    req = urllib.request.Request(f"{BASE}/api/doc/{doc_id}", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as resp:
        deleted = json.loads(resp.read().decode("utf-8"))
    checks.append(("删除成功", deleted.get("ok") is True, ""))
    after = get_json("/api/search?q=" + urllib.parse.quote(marker))
    checks.append(("删除后不再命中", after["total"] == 0, f"total={after['total']}"))

    print()
    failed = 0
    for name, ok, extra in checks:
        print(("  PASS  " if ok else "  FAIL  ") + name + (f"  ({extra})" if extra else ""))
        failed += 0 if ok else 1
    print()
    print("全部通过" if failed == 0 else f"{failed} 项失败")
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
