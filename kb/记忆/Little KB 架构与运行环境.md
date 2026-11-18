# Little KB 架构与运行环境

> 标签：架构,决策,环境

## 核心决策

- **文件夹是唯一事实来源**：所有文件以原始格式存放在 kb/，子目录即分类；data/kb.sqlite3 只是投影，删掉可重建，原件永不改动。
- **检索不依赖词嵌入**：用 SQLite FTS5 倒排索引 + BM25。中文在建索引前把每个汉字用空格隔开，查询时转成单字短语，无结果再降级为按字 AND。
- **切片**：按 Markdown 标题分节，再按段落装箱（目标 1100 字符，硬上限 1800），chunk id 直接作为 FTS5 的 rowid。
- **知识图谱**：四类节点（分类/文档/标签/关键词），关键词用字级 n-gram + 左右熵筛选，跨词边界碎片（如件夹）因为一侧邻字固定、熵接近 0 被淘汰。
- **零第三方依赖**：后端标准库（http.server + sqlite3），前端原生 JS + canvas 力导向，无构建步骤。

## 运行环境

| 组件 | 位置 | 用途 |
| --- | --- | --- |
| Python 3.12（DSH 自带） | C:\Users\84216\.dsh\dsh-runtimes\...\python\python.exe | 服务端、索引脚本 |
| Node.js LTS | %LOCALAPPDATA%\Programs\node | 前端工具链、npm/pnpm |
| MinGit | %LOCALAPPDATA%\Programs\git | 版本管理 |
| SQLite FTS5 | Python 内置 sqlite3 3.53 | 全文检索 |

## 常用命令

```
run.cmd                                  启动界面（默认 8777，占用则顺延）
python scripts\kb.py note 标题 内容    写入记忆
python scripts\kb.py search 关键词       检索
python scripts\smoke_test.py              端到端自测
```

## 下一步

- 词嵌入：新增 chunks_vec 表，检索时 BM25 + 向量 RRF 融合，接口结构不变。
- 文件夹监听：watchdog 替代手动重建索引。

---

写入时间：2026-10-29 20:00
