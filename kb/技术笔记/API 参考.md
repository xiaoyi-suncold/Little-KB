# HTTP API 参考

所有接口返回 JSON（`/api/doc/{id}/raw` 除外），编码 UTF-8。

## 读取

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 知识库路径、切片大小、上传上限 |
| GET | `/api/stats` | 文档数、切片数、占用字节、分类统计 |
| GET | `/api/tree` | 按分类分组的文档列表 |
| GET | `/api/search?q=&limit=&category=` | 全文检索，返回高亮片段 |
| GET | `/api/doc/{id}` | 文档详情：元数据 + 全文 + 切片列表 |
| GET | `/api/doc/{id}/raw` | 原始文件下载 |

## 写入

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/upload` | multipart：`files`（可多个）、`category`、`tags` |
| POST | `/api/reindex` | 重新扫描 `kb/` 并更新索引 |
| PATCH | `/api/doc/{id}` | 修改 `title` / `tags` |
| DELETE | `/api/doc/{id}` | 删除文档记录与原始文件 |

## 检索响应示例

```json
{
  "query": "知识库",
  "terms": ["知识库"],
  "mode": "strict",
  "took_ms": 1.8,
  "total": 2,
  "hits": [
    {
      "id": 1,
      "title": "快速开始",
      "path": "使用指南/快速开始.md",
      "category": "使用指南",
      "score": 4.21,
      "snippet": "这个<mark>知识库</mark>的一切都从 kb/ 文件夹开始。"
    }
  ]
}
```

`mode` 取值：`strict` 精确短语命中、`loose` 降级为按字匹配、`none` 无结果、`empty` 空查询。
