"""知识图谱：把 分类 / 文档 / 标签 / 关键词 组织成一张可交互的网络。

节点
  category  分类目录（层级来源）
  doc       文档（大小按字数）
  tag       文档标签
  term      文档主题词（字级 n-gram 抽取）
边
  category-doc   归属
  doc-tag        打标签
  doc-term       主题词出现
"""

from __future__ import annotations

import time

from .keywords import extract_terms

_CACHE: dict[str, object] = {"key": None, "at": 0.0, "payload": None}
TTL = 20.0


def build_graph(
    index,
    max_docs: int = 250,
    terms_per_doc: int = 6,
    max_terms: int = 220,
) -> dict:
    docs_all = index.all_documents()
    key = (
        len(docs_all),
        max((d["updated_at"] or "" for d in docs_all), default=""),
        max_docs,
        terms_per_doc,
        max_terms,
    )
    now = time.time()
    if _CACHE["key"] == key and _CACHE["payload"] and now - float(_CACHE["at"] or 0) < TTL:
        return _CACHE["payload"]  # type: ignore[return-value]

    docs = sorted(docs_all, key=lambda d: d["updated_at"] or "", reverse=True)[:max_docs]
    nodes: list[dict] = []
    edges: list[dict] = []
    if not docs:
        payload = {"nodes": [], "edges": [], "stats": {"docs": 0, "terms": 0, "tags": 0,
                                                       "categories": 0, "edges": 0}}
        _CACHE.update(key=key, at=now, payload=payload)
        return payload

    doc_ids = [d["id"] for d in docs]
    texts: dict[int, list[str]] = {}
    with index.connection() as conn:
        placeholders = ",".join("?" for _ in doc_ids)
        for row in conn.execute(
            f"SELECT document_id, content FROM chunks WHERE document_id IN ({placeholders})",
            doc_ids,
        ):
            texts.setdefault(row["document_id"], []).append(row["content"])

    per_doc_terms: dict[int, list[tuple[str, int]]] = {}
    term_df: dict[str, int] = {}
    for doc in docs:
        text = "\n".join(texts.get(doc["id"], []))
        terms = extract_terms(text, limit=terms_per_doc, exclude={doc["title"] or ""})
        per_doc_terms[doc["id"]] = terms
        for term, _freq in terms:
            term_df[term] = term_df.get(term, 0) + 1

    kept_terms = {
        term
        for term, _df in sorted(term_df.items(), key=lambda kv: (-kv[1], kv[0]))[:max_terms]
    }

    categories = {doc["category"] or "" for doc in docs}
    for cat in categories:
        label = cat or "未分类"
        nodes.append({"id": "cat:" + cat, "type": "category", "label": label,
                      "weight": sum(1 for d in docs if (d["category"] or "") == cat)})

    for doc in docs:
        nodes.append(
            {
                "id": f"doc:{doc['id']}",
                "type": "doc",
                "label": doc["title"] or doc["path"],
                "doc_id": doc["id"],
                "category": doc["category"] or "",
                "weight": max(int(doc["chars"] or 0), 40),
                "path": doc["path"],
            }
        )
        edges.append({
            "source": "cat:" + (doc["category"] or ""),
            "target": f"doc:{doc['id']}",
            "type": "category",
            "weight": 1,
        })

    tags: set[str] = set()
    for doc in docs:
        for tag in (doc["tags"] or "").split(","):
            tag = tag.strip()
            if not tag:
                continue
            tags.add(tag)
            nodes.append({"id": "tag:" + tag, "type": "tag", "label": "#" + tag, "weight": 1})
            edges.append({"source": f"doc:{doc['id']}", "target": "tag:" + tag,
                          "type": "tag", "weight": 1})

    for term in sorted(kept_terms):
        nodes.append({"id": "term:" + term, "type": "term", "label": term,
                      "weight": term_df.get(term, 1)})

    for doc_id, terms in per_doc_terms.items():
        for term, freq in terms:
            if term in kept_terms:
                edges.append({
                    "source": f"doc:{doc_id}",
                    "target": "term:" + term,
                    "type": "term",
                    "weight": freq,
                })

    payload = {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "docs": len(docs),
            "categories": len(categories),
            "tags": len(tags),
            "terms": len(kept_terms),
            "edges": len(edges),
        },
    }
    _CACHE.update(key=key, at=now, payload=payload)
    return payload
