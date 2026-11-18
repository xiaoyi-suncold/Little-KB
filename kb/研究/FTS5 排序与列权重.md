# FTS5 排序与列权重（BM25 调优）

## 结论

1. `bm25()` 的值越负越相关，FTS5 内部已乘 -1，`ORDER BY bm25(t)` 升序即最佳优先。
2. **标题命中会被长正文稀释**：本地实测中，正文长 8 倍的文档即使标题精确命中，默认 BM25 仍排在短文档之后。
3. 解法是列权重：`bm25(t, 10.0, 1.0, 1.0)`，权重按**声明列的顺序**依次对应，给少了默认 1.0，给多了忽略。
4. `rank MATCH 'bm25(10.0,1.0,1.0)' ORDER BY rank` 与直接 `ORDER BY bm25(…)` 结果一致，但前者更快（官方文档明确 `rank` 优于函数调用，配合 LIMIT 差距更明显）。

## 机制

FTS5 的 BM25 公式（官方文档 §5.1.1）：

```
score = -Σ_i IDF(qi) · (f(qi,D)·(k1+1)) / (f(qi,D) + k1·(1-b+b·|D|/avgdl))
IDF(qi) = ln((N - n(qi) + 0.5) / (n(qi) + 0.5))
```

- `k1=1.2`、`b=0.75` 硬编码，不可调；
- `|D|/avgdl` 是长度归一化项——**文档越长，单次命中的贡献被压得越小**，这就是「标题命中被稀释」的数学来源；
- IDF 为负时（词出现在超过一半文档里）FTS5 会截断到接近 0，实测小语料里分数会出现 `-0.000001` 这种量级，属于正常现象，不是 bug。

## 实现

```sql
-- 建表：title 作为第 0 列，body 第 1 列
CREATE VIRTUAL TABLE docs USING fts5(title, body, tokenize='unicode61');

-- 查询：标题命中算 10 次正文命中，用 rank 拿到排序加速
SELECT rowid, rank
  FROM docs
 WHERE docs MATCH ? AND rank MATCH 'bm25(10.0, 1.0)'
 ORDER BY rank
 LIMIT 20;
```

Python 侧等价写法：

```python
conn.execute(
    "SELECT rowid, bm25(t, 10.0, 1.0) AS s FROM t "
    "WHERE t MATCH ? ORDER BY s LIMIT ?", (expr, 20)
)
```

## 边界与失败模式

- **位置权重包含 UNINDEXED 列**：`UNINDEXED` 列不参与匹配，但**占一个权重位置**。三列声明只给两个权重时，第三个自动 1.0——顺序错了会静默错位，不报错。
- **`snippet()` 最多 64 个 token**，长片段要自己做截取（本项目就是自己实现的 `make_snippet`）。
- **IDF 在小语料下退化**：文档数少、词又常见时分数趋近 0，排序失去区分度。此时元数据加权（标题/路径/标签）比调 BM25 参数有效。
- **`rank` 是隐藏列**，只能用于 MATCH 查询的排序，不能当普通列 SELECT 出来做二次计算。

## 在本项目里的落点

当前实现是「单列 FTS（body）+ Python 侧给标题/路径/标签加分」，没有使用列权重。**决定暂不改**：

- 收益：标题权重交给 FTS 可以少一次 Python 重排，性能提升在毫秒级；
- 成本：`chunks_fts` 需要加 title 列并全量重建索引，schema 迁移 + 兼容旧库；
- 风险：中文按字切分后标题也会被切成单字 token，列权重会让「标题里出现某个单字」被过度放大，反而引入噪声。

结论：保持现状，把这条记下来；如果将来文档量到万级、重排成为瓶颈，再按上面的 SQL 迁移，并用 A/B 对比命中率。

## 验证记录

本地 SQLite 3.53.1，5 篇语料，查询 `sqlite`：

| 排序方式 | 第 1 名 | 分数 |
| --- | --- | --- |
| 默认 `bm25(t)` | 随手笔记（短正文） | -0.494927 |
| `bm25(t,10.0,1.0,1.0)` | SQLite 全文检索实战（标题命中） | -0.617089 |

同一查询用 `ORDER BY rank` + `rank MATCH 'bm25(10.0,1.0,1.0)'`，顺序与上表第二行一致。
另外验证：三列表只传两个权重时，第三个按 1.0 处理，结果与显式传 1.0 完全相同。

## 来源

- [SQLite FTS5 Extension（官方文档，§5.1.1 bm25、§4.2 Prefix Indexes）](https://www.sqlite.org/fts5.html) · SQLite 3.53.1 · 2026-10-29 访问
- 本地实验：Python 3.12 + sqlite3 3.53.1，`:memory:` 库，脚本见本次会话记录
